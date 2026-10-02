from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cinedata_agent import service
from cinedata_agent.agent import AgentError, build_agent
from cinedata_agent.config import Settings
from cinedata_agent.service import CineDataService, ResponseCache, normalize_question


class FakeLLM:
    """Consulta o banco uma vez por pergunta e responde; registra os prompts que recebeu."""

    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.prompts_seen: list[list[str]] = []
        self.fail = fail

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        if self.fail:
            from pydantic_ai.exceptions import ModelHTTPError

            raise ModelHTTPError(status_code=429, model_name="fake", body="rate limited")
        last = messages[-1]
        if any(p.part_kind == "user-prompt" for p in last.parts):
            self.prompts_seen.append(
                [
                    p.content
                    for m in messages
                    if isinstance(m, ModelRequest)
                    for p in m.parts
                    if p.part_kind == "user-prompt"
                ]
            )
            sql = "SELECT COUNT(*) AS total FROM dim_people"
            return ModelResponse(parts=[ToolCallPart(tool_name="executar_sql", args={"sql": sql})])
        answer = {"answer": "Há 2 pessoas cadastradas na base.", "assumptions": []}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=answer)])


@pytest.fixture
def settings(mini_gold_db: Path) -> Settings:
    return Settings(_env_file=None, db_path=mini_gold_db)


def _service(settings: Settings, llm: FakeLLM, log_path: Path | None = None) -> CineDataService:
    return CineDataService(settings, agent=build_agent(FunctionModel(llm)), log_path=log_path)


def _ask(svc: CineDataService, question: str, session: str = "s1"):
    return asyncio.run(svc.ask(question, session))


def test_follow_up_receives_the_conversation_history(settings: Settings) -> None:
    llm = FakeLLM()
    svc = _service(settings, llm)
    _ask(svc, "Quantas pessoas há na base?")
    _ask(svc, "E só diretores?")

    assert llm.prompts_seen[-1] == ["Quantas pessoas há na base?", "E só diretores?"]


def test_sessions_are_isolated(settings: Settings) -> None:
    llm = FakeLLM()
    svc = _service(settings, llm)
    _ask(svc, "Quantas pessoas há na base?", "a")
    _ask(svc, "E só diretores?", "b")

    assert llm.prompts_seen[-1] == ["E só diretores?"]


def test_history_is_trimmed_by_whole_turns(settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(service, "MAX_TURNS", 2)
    svc = _service(settings, FakeLLM())
    for i in range(4):
        _ask(svc, f"Pergunta número {i}?")

    history = svc.sessions.history("s1")
    first = history[0]
    assert isinstance(first, ModelRequest)
    assert first.parts[-1].content == "Pergunta número 2?"  # turno inteiro, sem órfãos


def test_repeated_question_is_served_from_cache(settings: Settings) -> None:
    llm = FakeLLM()
    svc = _service(settings, llm)
    first = _ask(svc, "Quantas pessoas há na base?", "a")
    calls = llm.calls
    second = _ask(svc, "  quantas PESSOAS há na base ", "b")

    assert llm.calls == calls
    assert second.cached and not first.cached
    assert second.rows == first.rows and second.session_id == "b"


def test_cache_hit_still_feeds_the_conversation_memory(settings: Settings) -> None:
    llm = FakeLLM()
    svc = _service(settings, llm)
    _ask(svc, "Quantas pessoas há na base?", "a")
    _ask(svc, "Quantas pessoas há na base?", "b")
    _ask(svc, "E só diretores?", "b")

    assert llm.prompts_seen[-1] == ["Quantas pessoas há na base?", "E só diretores?"]


def test_follow_ups_are_never_cached(settings: Settings) -> None:
    llm = FakeLLM()
    svc = _service(settings, llm)
    _ask(svc, "Quantas pessoas há na base?", "a")
    _ask(svc, "E só diretores?", "a")
    calls = llm.calls
    _ask(svc, "Primeira pergunta?", "b")
    response = _ask(svc, "E só diretores?", "b")

    assert not response.cached and llm.calls > calls + 2


def test_cache_expires() -> None:
    cache = ResponseCache(ttl_seconds=0)
    from cinedata_agent.models import AskResponse

    cache.put("pergunta", AskResponse(question="pergunta", answer="x" * 20), [])
    assert cache.get("pergunta") is None


def test_normalize_question() -> None:
    assert normalize_question("  Top 10   FILMES?? ") == "top 10 filmes"


def test_reset_clears_the_session(settings: Settings) -> None:
    svc = _service(settings, FakeLLM())
    _ask(svc, "Quantas pessoas há na base?")
    assert svc.reset("s1") and svc.sessions.history("s1") == []
    assert not svc.reset("s1")


def test_every_run_is_logged_as_jsonl(settings: Settings, tmp_path: Path) -> None:
    log = tmp_path / "agent.jsonl"
    svc = _service(settings, FakeLLM(), log_path=log)
    _ask(svc, "Quantas pessoas há na base?", "a")
    _ask(svc, "Quantas pessoas há na base?", "b")

    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["cached"] for r in records] == [False, True]
    assert records[0]["sql"].startswith("SELECT COUNT(*)")
    assert records[0]["requests"] == 2 and records[1]["requests"] == 0
    assert {"ts", "session_id", "prompt_version", "model", "latency_ms"} <= set(records[0])


def test_failures_are_logged_and_reraised(settings: Settings, tmp_path: Path) -> None:
    log = tmp_path / "agent.jsonl"
    svc = _service(settings, FakeLLM(fail=True), log_path=log)
    with pytest.raises(AgentError):
        _ask(svc, "Quantas pessoas há na base?")

    record = json.loads(log.read_text(encoding="utf-8"))
    assert record["error"] and "429" in record["detail"]
    assert svc.sessions.history("s1") == []
