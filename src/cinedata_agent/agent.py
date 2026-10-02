"""Agente Text-to-SQL (Pydantic AI) que responde perguntas sobre a camada Gold."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from groq import AsyncGroq
from openai import AsyncOpenAI
from pydantic import ValidationError
from pydantic_ai import (
    Agent,
    ModelRetry,
    RunContext,
    Tool,
    UnexpectedModelBehavior,
    capture_run_messages,
)
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.groq import GroqModel, GroqModelSettings
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.usage import UsageLimits

from .config import Settings
from .db import QueryError, QueryResult, run_query
from .grounding import Evidence, collect_values, ungrounded_names, ungrounded_numbers
from .guardrails import GuardrailError
from .models import AgentOutput, AskResponse, TraceStep, Usage
from .prompt import build_instructions
from .semantic_layer import GENRE_TRANSLATIONS, SEARCHABLE_FIELDS, render_markdown

PREVIEW_ROWS = 10
MIN_ANSWER_CHARS = 20
GROQ_MAX_RETRIES = 3
MAX_CELL_CHARS = 120
SEARCH_LIMIT = 15
MAX_TRACE_CHARS = 1500
PARSE_RETRIES = 1
_PARSE_ERRORS = ("output_parse_failed", "tool_use_failed")

SearchField = Literal["filme", "pessoa", "produtora", "genero", "status"]
TOOL_NAMES = frozenset({"executar_sql", "buscar_valores"})

_ALLOWED_TERMS = (*GENRE_TRANSLATIONS, *GENRE_TRANSLATIONS.values(), "CineData Analyst")


class AgentError(RuntimeError):
    def __init__(self, message: str, *, detail: str = "", steps: list[TraceStep] | None = None):
        super().__init__(message)
        self.detail = detail
        self.steps = steps or []


class ConfigurationError(AgentError):
    pass


@dataclass
class AgentDeps:
    db_path: Path
    max_rows: int
    timeout_seconds: float
    results: list[QueryResult] = field(default_factory=list)

    @classmethod
    def from_settings(cls, settings: Settings) -> AgentDeps:
        return cls(
            db_path=settings.db_path,
            max_rows=settings.max_rows,
            timeout_seconds=settings.query_timeout_seconds,
        )


def _clip(value: object) -> object:
    if isinstance(value, str) and len(value) > MAX_CELL_CHARS:
        return value[:MAX_CELL_CHARS] + "..."
    return value


def executar_sql(ctx: RunContext[AgentDeps], sql: str) -> dict[str, object]:
    """Executa uma consulta SELECT (SQLite) na camada Gold e devolve uma amostra do resultado.

    Args:
        sql: Um único comando SELECT (ou WITH ... SELECT) no dialeto SQLite.
    """
    deps = ctx.deps
    try:
        result = run_query(
            sql, db_path=deps.db_path, max_rows=deps.max_rows, timeout_seconds=deps.timeout_seconds
        )
    except (GuardrailError, QueryError) as exc:
        raise ModelRetry(str(exc)) from exc
    deps.results.append(result)

    warnings = []
    if not result.rows:
        warnings.append(
            "Nenhuma linha retornada. Revise filtros e valores (use buscar_valores para nomes) "
            "antes de concluir que não há dados."
        )
    if any(column.startswith("sk_") for column in result.columns):
        warnings.append("O resultado expõe colunas sk_*: remova-as e exiba nomes legíveis.")
    if result.truncated:
        warnings.append(f"Resultado truncado em {deps.max_rows} linhas: agregue ou use LIMIT.")

    return {
        "colunas": result.columns,
        "total_linhas": result.row_count,
        "amostra": [[_clip(v) for v in row] for row in result.rows[:PREVIEW_ROWS]],
        "avisos": warnings,
    }


def buscar_valores(ctx: RunContext[AgentDeps], campo: SearchField, termo: str) -> dict[str, object]:
    """Encontra o valor exato gravado no banco para um nome citado pelo usuário.

    Args:
        campo: Onde procurar: 'filme', 'pessoa', 'produtora', 'genero' (em inglês) ou 'status'.
        termo: Trecho do nome, sem aspas (ex.: 'nolan', 'pixar').
    """
    table, column, extra = SEARCHABLE_FIELDS[campo]
    selected = f"{column}, {extra}" if extra else column
    # tabela/coluna vêm da allowlist e o termo vai como parâmetro, então não há injeção
    sql = (
        f"SELECT DISTINCT {selected} FROM {table} "
        f"WHERE {column} LIKE ? ESCAPE '\\' "
        f"ORDER BY ({column} = ? COLLATE NOCASE) DESC, length({column}) LIMIT {SEARCH_LIMIT}"
    )
    escaped = termo.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    result = run_query(
        sql,
        db_path=ctx.deps.db_path,
        max_rows=SEARCH_LIMIT,
        timeout_seconds=ctx.deps.timeout_seconds,
        params=(f"%{escaped}%", termo.strip()),
    )
    if not result.rows:
        return {"valores": [], "aviso": f"Nenhum {campo} contém '{termo}'. Tente outro trecho."}
    return {"colunas": result.columns, "valores": result.rows}


def _groq_models(settings: Settings, api_key: str) -> list[Model]:
    # o gratuito limita 8 mil tokens/min; num 429 o SDK espera o tempo pedido e tenta de novo
    base = settings.base_url.removesuffix("/openai/v1")  # o SDK já acrescenta esse caminho
    client = AsyncGroq(api_key=api_key, base_url=base, max_retries=GROQ_MAX_RETRIES)
    provider = GroqProvider(groq_client=client)
    model_settings = GroqModelSettings(
        temperature=settings.temperature,
        timeout=settings.model_timeout_seconds,
        parallel_tool_calls=False,
    )
    if settings.reasoning_effort != "none":
        # modelos sem raciocínio rejeitam esse parâmetro
        model_settings["groq_reasoning_effort"] = settings.reasoning_effort
    return [GroqModel(n, provider=provider, settings=model_settings) for n in settings.model_chain]


def _openrouter_models(settings: Settings, api_key: str) -> list[Model]:
    # no OpenRouter requisição com erro conta na cota de 50/dia
    client = AsyncOpenAI(base_url=settings.base_url, api_key=api_key, max_retries=0)
    provider = OpenRouterProvider(openai_client=client)
    model_settings = OpenRouterModelSettings(
        temperature=settings.temperature,
        timeout=settings.model_timeout_seconds,
        parallel_tool_calls=False,
        openrouter_reasoning={"effort": settings.reasoning_effort},
    )
    return [
        OpenRouterModel(n, provider=provider, settings=model_settings) for n in settings.model_chain
    ]


def build_model(settings: Settings) -> Model:
    if settings.api_key is None:
        variable = f"{settings.llm_provider.upper()}_API_KEY"
        raise ConfigurationError(f"{variable} não configurada (veja .env.example).")
    key = settings.api_key.get_secret_value()
    builder = _groq_models if settings.llm_provider == "groq" else _openrouter_models
    models = builder(settings, key)
    return models[0] if len(models) == 1 else FallbackModel(*models)


def _instructions() -> str:
    # sem parâmetros: se tiver, o Pydantic AI passa o RunContext no primeiro argumento
    return build_instructions()


def _evidence(messages: list[ModelMessage]) -> Evidence:
    numbers, texts = collect_values(render_markdown())
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            is_tool_data = isinstance(part, ToolReturnPart) and part.tool_name in TOOL_NAMES
            if not (is_tool_data or isinstance(part, UserPromptPart)):
                continue
            found_numbers, found_texts = collect_values(part.content)
            if isinstance(part, UserPromptPart):
                # da pergunta só valem anos e tamanhos de lista ("em 2020", "top 10"), para o
                # modelo não confirmar um valor falso que o próprio usuário afirmou
                found_numbers = [
                    n
                    for n in found_numbers
                    if n.is_integer() and (0 < n <= 50 or 1900 <= n <= 2100)
                ]
            numbers += found_numbers
            texts += found_texts
    numbers.append(float(date.today().year))
    return Evidence(numbers=numbers, texts=texts)


def _validate_answer(ctx: RunContext[AgentDeps], output: AgentOutput | str) -> AgentOutput | str:
    messages = ctx.messages
    last = max((i for i, m in enumerate(messages) if isinstance(m, ModelResponse)), default=None)
    if last is not None:
        called_tools = any(
            isinstance(p, ToolCallPart) and p.tool_name in TOOL_NAMES for p in messages[last].parts
        )
        observed_before = any(
            isinstance(p, ToolReturnPart) and p.tool_name in TOOL_NAMES
            for m in messages[:last]
            if isinstance(m, ModelRequest)
            for p in m.parts
        )
        # alguns modelos mandam a consulta e a resposta juntas e inventam o resultado
        if called_tools and not observed_before:
            raise ModelRetry(
                "Você enviou a resposta final junto com uma chamada de ferramenta, antes de ver "
                "o resultado. Leia o resultado das ferramentas acima e só então responda, "
                "usando apenas números que aparecem nele."
            )

    if isinstance(output, str) and len(output.strip()) < MIN_ANSWER_CHARS:
        raise ModelRetry("Responda ao usuário com o resultado da consulta, em 2 a 5 frases.")
    evidence = _evidence(messages)
    text = output if isinstance(output, str) else " ".join([output.answer, *output.assumptions])
    numbers = ungrounded_numbers(text, evidence)
    names = ungrounded_names(text, evidence, allowed_terms=_ALLOWED_TERMS)
    if numbers or names:
        problems = [f"números {numbers}" if numbers else "", f"nomes {names}" if names else ""]
        raise ModelRetry(
            f"A resposta cita {' e '.join(p for p in problems if p)} que NÃO aparecem nos "
            "resultados consultados. Use apenas valores e nomes exatamente como retornados pelas "
            "ferramentas (sem traduzir títulos). Se precisar de um valor derivado (soma, "
            "diferença, percentual), calcule-o na SQL com executar_sql."
        )
    return output


def build_agent(model: Model) -> Agent[AgentDeps, AgentOutput | str]:
    agent = Agent(
        model,
        name="cinedata-analyst",
        deps_type=AgentDeps,
        # com saída só estruturada o Groq exige ferramenta em toda rodada (tool_use_failed)
        output_type=[AgentOutput, str],
        instructions=_instructions,
        tools=[Tool(buscar_valores, max_retries=2), Tool(executar_sql, max_retries=2)],
        retries=3,
    )
    agent.output_validator(_validate_answer)
    return agent


def _short(text: str) -> str:
    return text if len(text) <= MAX_TRACE_CHARS else text[:MAX_TRACE_CHARS] + "..."


def _observation(content: object) -> str:
    if isinstance(content, dict):
        if "total_linhas" in content:
            avisos = " ".join(content.get("avisos") or [])
            return _short(
                f"{content['total_linhas']} linha(s); colunas {content['colunas']}. {avisos}"
            )
        return _short(json.dumps(content, ensure_ascii=False, default=str))
    return _short(str(content))


def extract_trace(messages: list[ModelMessage]) -> list[TraceStep]:
    steps = []
    for message in messages:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ThinkingPart | TextPart) and part.content.strip():
                    steps.append(TraceStep(kind="pensamento", content=_short(part.content)))
                elif isinstance(part, ToolCallPart) and part.tool_name in TOOL_NAMES:
                    args = json.dumps(part.args_as_dict(), ensure_ascii=False)
                    steps.append(TraceStep(kind="acao", content=f"{part.tool_name}({args})"))
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name in TOOL_NAMES:
                    steps.append(TraceStep(kind="observacao", content=_observation(part.content)))
                elif isinstance(part, RetryPromptPart):
                    detail = part.content if isinstance(part.content, str) else str(part.content)
                    steps.append(TraceStep(kind="erro", content=_short(detail)))
    return steps


def _parse_text_answer(text: str) -> AgentOutput:
    # às vezes o modelo escreve o JSON do formato estruturado como texto
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if cleaned.startswith("{"):
        try:
            return AgentOutput.model_validate_json(cleaned)
        except ValidationError:
            pass
    return AgentOutput(answer=text.strip())


def _friendly(exc: Exception) -> str:
    if isinstance(exc, UsageLimitExceeded):
        return (
            "A pergunta exigiu passos demais e foi interrompida para proteger a cota. "
            "Tente reformulá-la de forma mais direta."
        )
    if isinstance(exc, FallbackExceptionGroup | ModelAPIError):
        return (
            "Os modelos de IA estão indisponíveis no momento (limite de uso ou instabilidade "
            "do provedor). Tente novamente em instantes."
        )
    return "O modelo não conseguiu concluir a consulta após algumas tentativas. Tente reformular."


def _describe(exc: BaseException) -> str:
    parts = [f"{type(exc).__name__}: {exc}"]
    parts += [f"{type(sub).__name__}: {sub}" for sub in getattr(exc, "exceptions", [])]
    return " | ".join(parts)[:2000]


async def ask(
    agent: Agent[AgentDeps, AgentOutput | str],
    question: str,
    *,
    deps: AgentDeps,
    max_requests: int,
    message_history: list[ModelMessage] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[AskResponse, list[ModelMessage]]:
    start = time.perf_counter()
    for attempt in range(PARSE_RETRIES + 1):
        try:
            return await _run_once(
                agent, question, deps, max_requests, message_history, timeout_seconds, start
            )
        except AgentError as exc:
            # o Groq às vezes não consegue interpretar a saída do gpt-oss (400 intermitente)
            if attempt == PARSE_RETRIES or not any(c in exc.detail for c in _PARSE_ERRORS):
                raise
            deps.results.clear()
    raise AssertionError("inalcançável")


async def _run_once(
    agent: Agent[AgentDeps, AgentOutput | str],
    question: str,
    deps: AgentDeps,
    max_requests: int,
    message_history: list[ModelMessage] | None,
    timeout_seconds: float | None,
    start: float,
) -> tuple[AskResponse, list[ModelMessage]]:
    with capture_run_messages() as captured:
        try:
            run = agent.run(
                question,
                deps=deps,
                message_history=message_history,
                usage_limits=UsageLimits(request_limit=max_requests),
            )
            result = await asyncio.wait_for(run, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise AgentError(
                f"A pergunta passou de {timeout_seconds:.0f} s sem resposta e foi interrompida. "
                "Tente de novo em instantes ou reformule de forma mais direta.",
                detail="TimeoutError",
                steps=extract_trace(captured[len(message_history or []) :]),
            ) from exc
        except (
            UsageLimitExceeded,
            FallbackExceptionGroup,
            ModelAPIError,
            UnexpectedModelBehavior,
        ) as exc:
            raise AgentError(
                _friendly(exc),
                detail=_describe(exc),
                steps=extract_trace(captured[len(message_history or []) :]),
            ) from exc

    # a tabela é a última consulta com linhas (uma checagem vazia depois não deve substituí-la)
    final = next((r for r in reversed(deps.results) if r.rows), None) or (
        deps.results[-1] if deps.results else None
    )
    output = result.output
    if isinstance(output, str):
        output = _parse_text_answer(output)
    usage = result.usage
    response = AskResponse(
        question=question,
        answer=output.answer,
        assumptions=output.assumptions,
        sql=final.sql if final else None,
        columns=final.columns if final else [],
        rows=final.rows if final else [],
        truncated=final.truncated if final else False,
        steps=extract_trace(result.new_messages()),
        model=result.response.model_name,
        usage=Usage(
            requests=usage.requests,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        ),
        latency_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response, result.new_messages()
