from __future__ import annotations

import asyncio
import time
import typing
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.groq import GroqModel

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
from cinedata_agent.prompt import build_instructions
from cinedata_agent.semantic_layer import SEARCHABLE_FIELDS

COUNT_SQL = "SELECT COUNT(*) AS total FROM dim_people"


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
    return _call(info.output_tools[0].name, answer=answer, assumptions=assumptions or [])


def _scripted(*steps: Callable[[AgentInfo], ModelResponse]) -> FunctionModel:
    # o passo i roda depois de i retornos de ferramenta
    def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return steps[min(_tool_returns(messages), len(steps) - 1)](info)

    return FunctionModel(function)


def _after_query(answers: list[str], sql: str = COUNT_SQL) -> FunctionModel:
    attempts = iter(answers)

    def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:
            return _call("executar_sql", sql=sql)
        return _final(info, next(attempts))

    return FunctionModel(function)


def _run(model: FunctionModel, deps: AgentDeps, question: str = "pergunta", **kwargs):
    return asyncio.run(ask(build_agent(model), question, deps=deps, max_requests=5, **kwargs))


def _errors(steps) -> str:
    return " ".join(s.content for s in steps if s.kind == "erro")


def test_react_cycle_returns_rows_from_the_database(deps: AgentDeps) -> None:
    model = _scripted(
        lambda _: _call("buscar_valores", campo="pessoa", termo="diretora"),
        lambda _: _call(
            "executar_sql",
            sql="SELECT nome_pessoa AS nome, tipo_pessoa AS papel FROM dim_people ORDER BY 1",
        ),
        lambda info: _final(info, "Há 2 pessoas cadastradas na base.", ["Todos os papéis."]),
    )
    response, history = _run(model, deps, "Quem está na base?")

    assert response.answer == "Há 2 pessoas cadastradas na base."
    assert response.assumptions == ["Todos os papéis."]
    assert response.rows == [["Ator Um", "Ator"], ["Diretora Dois", "Diretor"]]
    assert [s.kind for s in response.steps] == ["acao", "observacao", "acao", "observacao"]
    assert response.usage.requests == 3 and history


def test_sql_errors_and_blocked_writes_go_back_to_the_model(deps: AgentDeps) -> None:
    model = _scripted(
        lambda _: _call("executar_sql", sql="WITH x AS (SELECT 1) DELETE FROM dim_people"),
        lambda _: _call("executar_sql", sql="SELECT inventada FROM dim_people"),
        lambda _: _call("executar_sql", sql=COUNT_SQL),
        lambda info: _final(info, "O total de pessoas na base é 2."),
    )
    response, _ = _run(model, deps)

    assert response.rows == [[2]]
    assert "não autorizada" in _errors(response.steps)
    assert "no such column" in _errors(response.steps)


def test_table_is_the_last_query_that_returned_rows(deps: AgentDeps) -> None:
    model = _scripted(
        lambda _: _call("executar_sql", sql=COUNT_SQL),
        lambda _: _call("executar_sql", sql="SELECT * FROM dim_people WHERE 1 = 0"),
        lambda info: _final(info, "O total de pessoas na base é 2."),
    )
    assert _run(model, deps)[0].rows == [[2]]


def test_answer_sent_together_with_the_query_is_rejected(deps: AgentDeps) -> None:
    # caso real: o modelo pediu a consulta e já mandou uma resposta inventada junto
    def premature(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:
            invented = {"answer": "O total inventado é 999 pessoas.", "assumptions": []}
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="executar_sql", args={"sql": COUNT_SQL}),
                    ToolCallPart(tool_name=info.output_tools[0].name, args=invented),
                ]
            )
        # repetir a consulta junto com a resposta depois de já ter visto os dados é aceito
        grounded = {"answer": "Há 2 pessoas cadastradas na base.", "assumptions": []}
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name="executar_sql", args={"sql": COUNT_SQL}),
                ToolCallPart(tool_name=info.output_tools[0].name, args=grounded),
            ]
        )

    response, _ = _run(FunctionModel(premature), deps)
    assert response.answer == "Há 2 pessoas cadastradas na base."
    assert "antes de ver o resultado" in _errors(response.steps)


def test_invented_numbers_and_names_never_reach_the_user(deps: AgentDeps) -> None:
    grounded = "Há 2 pessoas: Ator Um e Diretora Dois."
    sql = "SELECT nome_pessoa AS nome FROM dim_people"
    for invented in [
        "Há 7 pessoas cadastradas na base.",
        "As pessoas são Ator Um e Greta Gerwig.",
        "Somadas, as pessoas têm 2.500 filmes.",  # conta de cabeça
    ]:
        response, _ = _run(_after_query([invented, grounded], sql), deps)
        assert response.answer == grounded, invented
        assert "NÃO aparecem" in _errors(response.steps)

    with pytest.raises(AgentError):  # insistir no erro termina em falha, nunca em resposta
        _run(_after_query(["Há 99 pessoas cadastradas na base."] * 10), deps)


def test_model_cannot_confirm_a_value_stated_by_the_user(deps: AgentDeps) -> None:
    question = "É verdade que a base tem 350 pessoas?"
    model = _after_query(["Sim, a base tem 350 pessoas.", "Não, a base tem 2 pessoas."])
    response, _ = _run(model, deps, question)
    assert response.answer == "Não, a base tem 2 pessoas."


def test_answer_without_a_query_cannot_cite_numbers(deps: AgentDeps) -> None:
    model = _scripted(
        lambda info: _final(info, "O filme mais popular tem nota 9,4 no IMDb."),
        lambda info: _final(info, "Só respondo perguntas sobre o catálogo de filmes."),
    )
    response, _ = _run(model, deps)
    assert response.answer == "Só respondo perguntas sobre o catálogo de filmes."
    assert response.sql is None and response.rows == []


def test_text_answers_are_accepted_verified_and_parsed(deps: AgentDeps) -> None:
    # o gpt-oss no Groq responde em texto, às vezes com o JSON estruturado dentro
    answers = iter(
        [
            "Há 9 pessoas cadastradas na base.",
            '```json\n{"answer": "Há 2 pessoas cadastradas na base.", '
            '"assumptions": ["Todos."]}\n```',
        ]
    )

    def text_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if _tool_returns(messages) == 0:
            return _call("executar_sql", sql=COUNT_SQL)
        return ModelResponse(parts=[TextPart(content=next(answers))])

    response, _ = _run(FunctionModel(text_model), deps)
    assert response.answer == "Há 2 pessoas cadastradas na base."
    assert response.assumptions == ["Todos."]
    assert "NÃO aparecem" in _errors(response.steps)


def test_failures_become_friendly_errors(deps: AgentDeps) -> None:
    with pytest.raises(AgentError, match="passos demais"):
        _run(_scripted(lambda _: _call("executar_sql", sql="SELECT 1 AS x")), deps)

    def rate_limited(messages, info):
        raise ModelHTTPError(status_code=429, model_name="m", body="rate limited")

    with pytest.raises(AgentError, match="indisponíveis"):
        _run(FunctionModel(rate_limited), deps)

    def slow(messages, info):
        time.sleep(1)
        return _final(info, "Resposta de teste suficientemente longa.")

    with pytest.raises(AgentError, match="passou de"):
        _run(FunctionModel(slow), deps, timeout_seconds=0.2)


def test_conversation_history_reaches_the_model(deps: AgentDeps) -> None:
    seen: list[str] = []

    def remember(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen[:] = [
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
    assert seen == ["Quais os 5 filmes mais populares?", "E só de 2020?"]


def test_buscar_valores(deps: AgentDeps) -> None:
    def search(termo: str) -> dict:
        model = _scripted(
            lambda _: _call("buscar_valores", campo="pessoa", termo=termo),
            lambda info: _final(info, "Resposta de teste suficientemente longa."),
        )
        result = asyncio.run(build_agent(model).run("x", deps=deps))
        return next(
            p.content
            for m in result.all_messages()
            for p in getattr(m, "parts", [])
            if p.part_kind == "tool-return" and p.tool_name == "buscar_valores"
        )

    assert search("DIRETORA")["valores"] == [["Diretora Dois", "Diretor"]]
    assert search("%")["valores"] == []  # curinga é tratado como texto

    hints = typing.get_type_hints(agent_module.buscar_valores)
    assert set(typing.get_args(hints["campo"])) == set(SEARCHABLE_FIELDS)


def test_instructions_follow_the_agent_structure() -> None:
    text = build_instructions(today=date(2026, 10, 3))
    for section in ("# Persona", "# Objetivo", "# Ferramentas", "# Como trabalhar", "# Regras"):
        assert section in text
    assert "2026-10-03" in text and "fact_movies_performance" in text
    assert "{" not in text.split("Tabelas:")[0]


def test_groq_model_settings() -> None:
    first = build_model(Settings(_env_file=None, groq_api_key="gsk_x"))
    assert isinstance(first, GroqModel) and first.model_name == "openai/gpt-oss-120b"
    assert first.settings["temperature"] == 0 and first.settings["parallel_tool_calls"] is False
    assert "groq_reasoning_effort" not in first.settings  # só vai quando pedido
    assert first.client.max_retries == 3  # espera a janela de tokens/minuto

    single = build_model(
        Settings(
            _env_file=None,
            groq_api_key="gsk_x",
            model_name="openai/gpt-oss-120b",
            model_base_url="https://api.groq.com/openai/v1/",
            reasoning_effort="low",
        )
    )
    assert single.settings["groq_reasoning_effort"] == "low"
    assert str(single.client.base_url).rstrip("/") == "https://api.groq.com"

    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        build_model(Settings(_env_file=None))


def test_openrouter_model_settings() -> None:
    model = build_model(
        Settings(
            _env_file=None,
            llm_provider="openrouter",
            openrouter_api_key="k",
            model_name="a/m1:free, b/m2:free",
        )
    )
    assert [m.model_name for m in model.models] == ["a/m1:free", "b/m2:free"]
    assert model.models[0].client.max_retries == 0  # erro conta na cota de 50/dia


def test_groq_parse_failure_is_retried_once(deps: AgentDeps) -> None:
    calls = {"n": 0}

    def flaky(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelHTTPError(
                status_code=400, model_name="m", body={"code": "output_parse_failed"}
            )
        if _tool_returns(messages) == 0:
            return _call("executar_sql", sql=COUNT_SQL)
        return _final(info, "O total de pessoas na base é 2.")

    assert _run(FunctionModel(flaky), deps)[0].rows == [[2]]

    def always_broken(messages, info):
        raise ModelHTTPError(status_code=400, model_name="m", body={"code": "output_parse_failed"})

    with pytest.raises(AgentError):
        _run(FunctionModel(always_broken), deps)


def test_leaked_reasoning_is_not_accepted_as_the_answer(deps: AgentDeps) -> None:
    # caso real: o gpt-oss devolveu o próprio raciocínio, em inglês, no lugar da resposta
    leaked = "We have the top 3 movies. Need to answer in Portuguese, include assumptions."
    model = _after_query([leaked, "O total de pessoas na base é 2."])
    response, _ = _run(model, deps)
    assert response.answer == "O total de pessoas na base é 2."
    assert "raciocínio interno" in _errors(response.steps)
