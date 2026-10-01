"""Agente Text-to-SQL (Pydantic AI, ciclo ReAct) sobre a camada Gold.

Componentes de um agente, na terminologia vista em aula:
- **Persona e instruções:** `prompts/system_prompt.md` + camada semântica (`prompt.py`).
- **Planejamento:** ciclo ReAct conduzido pelo próprio modelo via tool calling.
- **Ferramentas:** `buscar_valores` e `executar_sql` (2 ferramentas, bem abaixo do limite
  prático de ~5 a partir do qual o desempenho do ReAct cai).
- **Memória:** `message_history` repassado entre perguntas da mesma conversa.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

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

PREVIEW_ROWS = 15  # linhas da amostra devolvida ao LLM (a tabela completa vai ao usuário)
MAX_CELL_CHARS = 120  # textos longos (sinopses) são cortados na amostra
SEARCH_LIMIT = 15
MAX_TRACE_CHARS = 1500

SearchField = Literal["filme", "pessoa", "produtora", "genero", "status"]


class AgentError(RuntimeError):
    """Falha ao responder; a mensagem é segura para exibir ao usuário.

    `detail` e `steps` guardam a causa técnica e o trace até a falha (para logs/depuração).
    """

    def __init__(self, message: str, *, detail: str = "", steps: list[TraceStep] | None = None):
        super().__init__(message)
        self.detail = detail
        self.steps = steps or []


class ConfigurationError(AgentError):
    """Configuração ausente ou inválida (ex.: chave da API)."""


@dataclass
class AgentDeps:
    """Dependências de uma execução do agente (injetadas nas ferramentas)."""

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


# ------------------------------------------------------------------------------ ferramentas
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

    warnings: list[str] = []
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
    # Identificadores vêm da allowlist; o termo vai como parâmetro (sem risco de injeção).
    sql = (
        f"SELECT DISTINCT {selected} FROM {table} "
        f"WHERE {column} LIKE ? ESCAPE '\\' "
        f"ORDER BY ({column} = ? COLLATE NOCASE) DESC, length({column}) LIMIT {SEARCH_LIMIT}"
    )
    escaped = termo.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    deps = ctx.deps
    result = run_query(
        sql,
        db_path=deps.db_path,
        max_rows=SEARCH_LIMIT,
        timeout_seconds=deps.timeout_seconds,
        params=(f"%{escaped}%", termo.strip()),
    )
    if not result.rows:
        return {"valores": [], "aviso": f"Nenhum {campo} contém '{termo}'. Tente outro trecho."}
    return {"colunas": result.columns, "valores": result.rows}


TOOL_NAMES: frozenset[str] = frozenset({"executar_sql", "buscar_valores"})

# Termos que podem aparecer na resposta sem estar nos resultados (nomes de gêneros em PT etc.).
_ALLOWED_TERMS: tuple[str, ...] = (
    *GENRE_TRANSLATIONS,
    *GENRE_TRANSLATIONS.values(),
    "CineData Analyst",
)


# ------------------------------------------------------------------------- modelo e agente
def _groq_models(settings: Settings, api_key: str) -> list[Model]:
    provider = GroqProvider(api_key=api_key)
    model_settings = GroqModelSettings(
        temperature=settings.temperature,
        timeout=settings.model_timeout_seconds,
        parallel_tool_calls=False,
    )
    if settings.reasoning_effort != "none":
        # Só para modelos com raciocínio; nos demais o parâmetro seria rejeitado pela API.
        model_settings["groq_reasoning_effort"] = settings.reasoning_effort
    return [GroqModel(n, provider=provider, settings=model_settings) for n in settings.model_chain]


def _openrouter_models(settings: Settings, api_key: str) -> list[Model]:
    provider = OpenRouterProvider(api_key=api_key)
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
    """Cadeia de modelos do provedor configurado, com fallback automático em erro (ex.: 429).

    `parallel_tool_calls=False` pede ao modelo que não responda na mesma rodada em que consulta;
    como alguns modelos ignoram o pedido, a garantia real fica no validador de respostas.
    """
    if settings.api_key is None:
        variable = f"{settings.llm_provider.upper()}_API_KEY"
        raise ConfigurationError(f"{variable} não configurada (veja .env.example).")
    key = settings.api_key.get_secret_value()
    builder = _groq_models if settings.llm_provider == "groq" else _openrouter_models
    models = builder(settings, key)
    return models[0] if len(models) == 1 else FallbackModel(*models)


def _instructions() -> str:
    # Sem parâmetros de propósito: o Pydantic AI injeta RunContext em funções que recebem argumento.
    return build_instructions()


def _evidence(messages: list[ModelMessage]) -> Evidence:
    """O que a resposta pode citar: resultados das ferramentas, perguntas e fatos documentados."""
    numbers, texts = collect_values(render_markdown())  # fatos verificados da camada semântica
    for message in messages:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            is_tool_data = isinstance(part, ToolReturnPart) and part.tool_name in TOOL_NAMES
            if is_tool_data or isinstance(part, UserPromptPart):
                found_numbers, found_texts = collect_values(part.content)
                numbers += found_numbers
                texts += found_texts
    numbers.append(float(date.today().year))  # o ano corrente consta das instruções
    return Evidence(numbers=numbers, texts=texts)


def _validate_answer(ctx: RunContext[AgentDeps], output: AgentOutput) -> AgentOutput:
    """Tolerância zero a alucinação: rejeita (ModelRetry) respostas não fundamentadas.

    1. Resposta antes de observar qualquer resultado (o modelo enviou a consulta e a resposta
       na mesma rodada e inventou os dados). Se já observou em rodada anterior, a resposta
       está fundamentada mesmo que ele repita a consulta por redundância.
    2. Número ou nome próprio que não aparece nos dados observados, na pergunta ou nos fatos
       documentados da camada semântica (ver `grounding.py`).
    """
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
        if called_tools and not observed_before:
            raise ModelRetry(
                "Você enviou a resposta final junto com uma chamada de ferramenta, antes de ver "
                "o resultado. Leia o resultado das ferramentas acima e só então responda, "
                "usando apenas números que aparecem nele."
            )

    evidence = _evidence(messages)
    text = " ".join([output.answer, *output.assumptions])
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


def build_agent(model: Model) -> Agent[AgentDeps, AgentOutput]:
    agent = Agent(
        model,
        name="cinedata-analyst",
        deps_type=AgentDeps,
        output_type=AgentOutput,
        instructions=_instructions,
        tools=[Tool(buscar_valores, max_retries=2), Tool(executar_sql, max_retries=2)],
        retries=3,
    )
    agent.output_validator(_validate_answer)
    return agent


# ------------------------------------------------------------------------------ execução
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
    """Reconstrói os passos do ciclo ReAct a partir das mensagens trocadas."""
    steps: list[TraceStep] = []
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
    agent: Agent[AgentDeps, AgentOutput],
    question: str,
    *,
    deps: AgentDeps,
    max_requests: int,
    message_history: list[ModelMessage] | None = None,
) -> tuple[AskResponse, list[ModelMessage]]:
    """Responde a uma pergunta e devolve a resposta + o histórico atualizado da conversa.

    Raises:
        AgentError: com mensagem amigável quando não for possível responder.
    """
    start = time.perf_counter()
    with capture_run_messages() as captured:
        try:
            result = await agent.run(
                question,
                deps=deps,
                message_history=message_history,
                usage_limits=UsageLimits(request_limit=max_requests),
            )
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

    final = deps.results[-1] if deps.results else None
    usage = result.usage
    new_messages = result.new_messages()
    response = AskResponse(
        question=question,
        answer=result.output.answer,
        assumptions=result.output.assumptions,
        sql=final.sql if final else None,
        columns=final.columns if final else [],
        rows=final.rows if final else [],
        truncated=final.truncated if final else False,
        steps=extract_trace(new_messages),
        model=result.response.model_name,
        usage=Usage(
            requests=usage.requests,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        ),
        latency_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response, result.all_messages()
