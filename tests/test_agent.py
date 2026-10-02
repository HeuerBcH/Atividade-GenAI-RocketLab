"""Testes do agente com FunctionModel: o ciclo ReAct completo, sem chamar o LLM real."""

from __future__ import annotations

import asyncio
import typing
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.openrouter import OpenRouterModel

from cinedata_agent import agent as agent_module
from cinedata_agent.agent import (
    AgentDeps,
    AgentError,
    ConfigurationError,
    ask,
    build_agent,
    build_model,
)
from cinedata_agent.config import Settings
from cinedata_agent.prompt import build_instructions, prompt_version
from cinedata_agent.semantic_layer import SEARCHABLE_FIELDS

Script = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


@pytest.fixture
def deps(mini_gold_db: Path) -> AgentDeps:
    return AgentDeps(db_path=mini_gold_db, max_rows=100, timeout_seconds=5.0)


def _tool_returns(messages: list[ModelMessage]) -> int:
    return sum(
        1
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if p.part_kind in {"tool-return", "retry-prompt"}
    )


def _call(tool: str, **args: object) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args)])


def _final(info: AgentInfo, answer: str, assumptions: list[str] | None = None) -> ModelResponse:
    args = {"answer": answer, "assumptions": assumptions or []}
    return _call(info.output_tools[0].name, **args)


def _scripted(*steps: Callable[[AgentInfo], ModelResponse]) -> FunctionModel:
    """Modelo roteirizado: o passo i é executado após i retornos de ferramenta."""

    def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return steps[min(_tool_returns(messages), len(steps) - 1)](info)

    return FunctionModel(function)


def _run(model: FunctionModel, deps: AgentDeps, question: str = "pergunta", **kwargs):
    agent = build_agent(model)
    return asyncio.run(ask(agent, question, deps=deps, max_requests=5, **kwargs))


# --------------------------------------------------------------------------- ciclo ReAct
def test_full_react_cycle_returns_database_rows_not_model_text(deps: AgentDeps) -> None:
    model = _scripted(
        lambda _: _call("buscar_valores", campo="pessoa", termo="diretora"),
        lambda _: _call(
            "executar_sql",
            sql="SELECT nome_pessoa AS nome, tipo_pessoa AS papel FROM dim_people ORDER BY 1",
        ),
        lambda info: _final(
            info, "Há 2 pessoas cadastradas na base.", ["Considerei todos os papéis."]
        ),
    )
    response, history = _run(model, deps, "Quem está na base?")

    assert response.answer == "Há 2 pessoas cadastradas na base."
    assert response.assumptions == ["Considerei todos os papéis."]
    assert response.columns == ["nome", "papel"]
    assert response.rows == [["Ator Um", "Ator"], ["Diretora Dois", "Diretor"]]
    assert response.sql.startswith("SELECT nome_pessoa")
    assert [s.kind for s in response.steps] == ["acao", "observacao", "acao", "observacao"]
    assert response.usage.requests == 3
    assert len(history) > 0


def test_sql_error_is_sent_back_for_self_correction(deps: AgentDeps) -> None:
    model = _scripted(
        lambda _: _call("executar_sql", sql="SELECT coluna_inventada FROM dim_people"),
        lambda _: _call("executar_sql", sql="SELECT COUNT(*) AS total FROM dim_people"),
        lambda info: _final(info, "O total de pessoas na base é 2."),
    )
    response, _ = _run(model, deps)

    assert response.rows == [[2]]
    errors = [s for s in response.steps if s.kind == "erro"]
    assert errors and "no such column" in errors[0].content


def test_write_attempt_is_blocked_and_reported_to_the_model(deps: AgentDeps) -> None:
    model = _scripted(
        lambda _: _call("executar_sql", sql="WITH x AS (SELECT 1) DELETE FROM dim_people"),
        lambda info: _final(info, "Não posso alterar dados: acesso somente leitura."),
    )
    response, _ = _run(model, deps)

    assert response.sql is None
    assert any("não autorizada" in s.content for s in response.steps if s.kind == "erro")
    assert _run(
        _scripted(
            lambda _: _call("executar_sql", sql="SELECT COUNT(*) FROM dim_people"),
            lambda info: _final(info, "Resposta de teste suficientemente longa."),
        ),
        deps,
    )[0].rows == [[2]]


def test_empty_answer_forces_the_model_to_retry(deps: AgentDeps) -> None:
    """Regressão: um modelo real devolveu resposta vazia junto com a chamada da consulta."""
    model = _scripted(
        lambda info: _final(info, ""),
        lambda info: _final(info, "Agora sim, uma resposta completa ao usuário."),
    )
    response, _ = _run(model, deps)
    assert response.answer == "Agora sim, uma resposta completa ao usuário."
    assert response.usage.requests == 2


def test_answer_sent_with_a_tool_call_is_rejected(deps: AgentDeps) -> None:
    """Regressão: um modelo real respondeu na mesma rodada da consulta e inventou números."""

    def premature(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:  # consulta + resposta inventada na mesma rodada
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="executar_sql", args={"sql": "SELECT 2 AS total"}),
                    ToolCallPart(
                        tool_name=info.output_tools[0].name,
                        args={"answer": "O total inventado é 999 pessoas.", "assumptions": []},
                    ),
                ]
            )
        return _final(info, "Depois de observar, o total correto é 2.")

    response, _ = _run(FunctionModel(premature), deps)
    assert response.answer == "Depois de observar, o total correto é 2."
    assert any("antes de ver o resultado" in s.content for s in response.steps if s.kind == "erro")


def test_redundant_tool_call_after_observing_is_accepted(deps: AgentDeps) -> None:
    """Regressão: o modelo repetia a consulta junto com a resposta e o validador entrava em laço."""
    sql = "SELECT COUNT(*) AS total FROM dim_people"

    def redundant(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:
            return _call("executar_sql", sql=sql)
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name="executar_sql", args={"sql": sql}),
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={"answer": "Há 2 pessoas cadastradas na base.", "assumptions": []},
                ),
            ]
        )

    response, _ = _run(FunctionModel(redundant), deps)
    assert response.answer == "Há 2 pessoas cadastradas na base."
    assert response.rows == [[2]]


def test_refusal_without_tools_has_no_sql(deps: AgentDeps) -> None:
    response, _ = _run(
        _scripted(lambda info: _final(info, "Só respondo perguntas sobre o catálogo de filmes.")),
        deps,
    )

    assert response.sql is None and response.rows == [] and response.steps == []
    assert response.usage.requests == 1


def test_runaway_agent_is_stopped_by_request_limit(deps: AgentDeps) -> None:
    looping = _scripted(lambda _: _call("executar_sql", sql="SELECT 1 AS x"))
    with pytest.raises(AgentError, match="passos demais"):
        _run(looping, deps)


def test_provider_failure_becomes_friendly_error(deps: AgentDeps) -> None:
    def rate_limited(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(status_code=429, model_name="free-model", body="rate limited")

    with pytest.raises(AgentError, match="indisponíveis"):
        _run(FunctionModel(rate_limited), deps)


def test_conversation_history_reaches_the_model(deps: AgentDeps) -> None:
    seen_prompts: list[str] = []

    def remember(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen_prompts[:] = [
            p.content
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if p.part_kind == "user-prompt"
        ]
        return _final(info, "Resposta de teste suficientemente longa.")

    model = FunctionModel(remember)
    _, history = _run(model, deps, "Quais os 5 filmes mais populares?")
    _run(model, deps, "E só de 2020?", message_history=history)

    assert seen_prompts == ["Quais os 5 filmes mais populares?", "E só de 2020?"]


# ------------------------------------------------------------------------ buscar_valores
def _search(deps: AgentDeps, campo: str, termo: str) -> dict:
    model = _scripted(
        lambda _: _call("buscar_valores", campo=campo, termo=termo),
        lambda info: _final(info, "Resposta de teste suficientemente longa."),
    )
    agent = build_agent(model)
    captured: dict = {}

    async def run() -> None:
        result = await agent.run("x", deps=deps)
        for m in result.all_messages():
            for p in getattr(m, "parts", []):
                if p.part_kind == "tool-return" and p.tool_name == "buscar_valores":
                    captured.update(p.content)

    asyncio.run(run())
    return captured


def test_search_is_case_insensitive_and_shows_role(deps: AgentDeps) -> None:
    found = _search(deps, "pessoa", "DIRETORA")
    assert found["valores"] == [["Diretora Dois", "Diretor"]]


def test_search_treats_wildcards_literally(deps: AgentDeps) -> None:
    assert _search(deps, "pessoa", "%")["valores"] == []


def test_search_fields_match_tool_signature() -> None:
    hints = typing.get_type_hints(agent_module.buscar_valores)
    assert set(typing.get_args(hints["campo"])) == set(SEARCHABLE_FIELDS)


# ---------------------------------------------------------------------- prompt e modelo
def test_instructions_follow_class_structure_and_embed_semantic_layer() -> None:
    text = build_instructions(today=date(2026, 10, 3))
    for section in ("# Persona", "# Objetivo", "# Ferramentas", "# Como trabalhar", "# Regras"):
        assert section in text
    assert "2026-10-03" in text
    assert "fact_movies_performance" in text and "Science Fiction" in text
    assert "{" not in text.split("# Camada semântica")[0], "placeholder não substituído"


def test_prompt_version_is_stable() -> None:
    assert prompt_version() == prompt_version() and len(prompt_version()) == 12


def test_build_model_requires_api_key() -> None:
    with pytest.raises(ConfigurationError):
        build_model(Settings(_env_file=None))


def test_build_model_uses_fallback_chain_and_generation_settings() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        openrouter_api_key="sk-or-v1-x",
        model_name="a/m1:free, b/m2:free",
        temperature=0,
        reasoning_effort="low",
    )
    model = build_model(settings)

    assert isinstance(model, FallbackModel)
    assert [m.model_name for m in model.models] == ["a/m1:free", "b/m2:free"]
    first = model.models[0]
    assert first.settings["temperature"] == 0
    assert first.settings["openrouter_reasoning"] == {"effort": "low"}
    assert first.settings["parallel_tool_calls"] is False

    single = build_model(
        Settings(
            _env_file=None,
            llm_provider="openrouter",
            openrouter_api_key="k",
            model_name="a/m1:free",
        )
    )
    assert isinstance(single, OpenRouterModel)


# ------------------------------------------------------------- tolerância zero a alucinação
def _after_query(final_answers: list[str]) -> FunctionModel:
    """Consulta uma vez e depois tenta as respostas em sequência (uma por rodada)."""
    attempts = iter(final_answers)

    def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:
            return _call("executar_sql", sql="SELECT nome_pessoa AS nome FROM dim_people")
        return _final(info, next(attempts))

    return FunctionModel(function)


@pytest.mark.parametrize(
    "invented",
    [
        "Há 7 pessoas cadastradas na base.",  # número inventado
        "As pessoas são Ator Um e Greta Gerwig.",  # nome inventado
        "Somadas, as pessoas têm 2.500 filmes.",  # cálculo de cabeça
    ],
)
def test_invented_data_is_rejected_and_never_reaches_the_user(
    deps: AgentDeps, invented: str
) -> None:
    grounded = "Há 2 pessoas: Ator Um e Diretora Dois."
    response, _ = _run(_after_query([invented, grounded]), deps)

    assert response.answer == grounded
    assert any("NÃO aparecem" in s.content for s in response.steps if s.kind == "erro")


def test_persistent_hallucination_fails_safely_instead_of_answering(deps: AgentDeps) -> None:
    with pytest.raises(AgentError) as error:
        _run(_after_query(["Há 99 pessoas cadastradas na base."] * 10), deps)
    assert "NÃO aparecem" in " ".join(s.content for s in error.value.steps)


def test_answer_without_query_cannot_cite_numbers(deps: AgentDeps) -> None:
    model = _scripted(
        lambda info: _final(info, "O filme mais popular tem nota 9,4 no IMDb."),
        lambda info: _final(info, "Só respondo perguntas sobre o catálogo de filmes."),
    )
    response, _ = _run(model, deps)
    assert response.answer == "Só respondo perguntas sobre o catálogo de filmes."


def test_groq_is_the_default_provider_with_its_own_chain() -> None:
    settings = Settings(_env_file=None, groq_api_key="gsk_x")
    model = build_model(settings)

    assert settings.llm_provider == "groq"
    assert isinstance(model, FallbackModel)
    assert all(isinstance(m, GroqModel) for m in model.models)
    first = model.models[0]
    assert first.settings["temperature"] == 0
    assert first.settings["parallel_tool_calls"] is False
    assert "groq_reasoning_effort" not in first.settings  # só enviado quando pedido


def test_groq_reasoning_effort_is_forwarded_when_requested() -> None:
    settings = Settings(
        _env_file=None,
        groq_api_key="gsk_x",
        model_name="openai/gpt-oss-120b",
        reasoning_effort="low",
    )
    assert build_model(settings).settings["groq_reasoning_effort"] == "low"


def test_missing_key_names_the_right_variable() -> None:
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        build_model(Settings(_env_file=None, llm_provider="groq"))


def test_retry_policy_per_provider() -> None:
    groq = build_model(
        Settings(_env_file=None, groq_api_key="gsk_x", model_name="openai/gpt-oss-120b")
    )
    openrouter = build_model(
        Settings(
            _env_file=None, llm_provider="openrouter", openrouter_api_key="k", model_name="a/m"
        )
    )
    assert groq.client.max_retries == 3  # espera a janela de tokens/minuto do Groq
    assert openrouter.client.max_retries == 0


def test_plain_text_answer_is_accepted_and_still_verified(deps: AgentDeps) -> None:
    """Regressão: o gpt-oss responde em texto depois de consultar (o Groq dava tool_use_failed)."""
    answers = iter(["Há 9 pessoas cadastradas na base.", "Há 2 pessoas cadastradas na base."])

    def text_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:
            return _call("executar_sql", sql="SELECT COUNT(*) AS total FROM dim_people")
        return ModelResponse(parts=[TextPart(content=next(answers))])

    response, _ = _run(FunctionModel(text_model), deps)
    assert response.answer == "Há 2 pessoas cadastradas na base."
    assert response.assumptions == [] and response.rows == [[2]]
    assert any("NÃO aparecem" in s.content for s in response.steps if s.kind == "erro")


def test_groq_base_url_accepts_the_openai_compatible_form() -> None:
    settings = Settings(
        _env_file=None,
        groq_api_key="gsk_x",
        model_name="openai/gpt-oss-120b",
        model_base_url="https://api.groq.com/openai/v1/",
    )
    assert str(build_model(settings).client.base_url).rstrip("/") == "https://api.groq.com"


def test_question_timeout_interrupts_the_run(deps: AgentDeps) -> None:
    import time as _time

    def slow(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _time.sleep(1)
        return _final(info, "Resposta de teste suficientemente longa.")

    agent = build_agent(FunctionModel(slow))
    with pytest.raises(AgentError, match="passou de"):
        asyncio.run(ask(agent, "x", deps=deps, max_requests=5, timeout_seconds=0.2))
