from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cinedata_agent import service
from cinedata_agent.agent import AgentError, build_agent
from cinedata_agent.config import Settings
from cinedata_agent.models import AskResponse
from cinedata_agent.service import CineDataService, ResponseCache


class FakeLLM:
    """Consulta uma vez e responde; guarda as perguntas que enxergou no histórico."""

    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.prompts_seen: list[list[str]] = []
        self.fail = fail

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        if self.fail:
            raise ModelHTTPError(status_code=429, model_name="fake", body="rate limited")
        if any(p.part_kind == "user-prompt" for p in messages[-1].parts):
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


def _service(db: Path, llm: FakeLLM, log_path: Path | None = None) -> CineDataService:
    settings = Settings(_env_file=None, db_path=db)
    return CineDataService(settings, agent=build_agent(FunctionModel(llm)), log_path=log_path)


def _ask(svc: CineDataService, question: str, session: str = "s1") -> AskResponse:
    return asyncio.run(svc.ask(question, session))


def test_memory_is_per_session_and_cleared_on_reset(mini_gold_db: Path) -> None:
    llm = FakeLLM()
    svc = _service(mini_gold_db, llm)
    _ask(svc, "Quantas pessoas há na base?", "a")
    _ask(svc, "E só diretores?", "a")
    assert llm.prompts_seen[-1] == ["Quantas pessoas há na base?", "E só diretores?"]

    _ask(svc, "E só diretores?", "b")
    assert llm.prompts_seen[-1] == ["E só diretores?"]

    assert svc.reset("a") and svc.sessions.history("a") == []


def test_history_is_trimmed_by_whole_turns(mini_gold_db: Path, monkeypatch) -> None:
    monkeypatch.setattr(service, "MAX_TURNS", 2)
    svc = _service(mini_gold_db, FakeLLM())
    for i in range(4):
        _ask(svc, f"Pergunta número {i}?")

    first = svc.sessions.history("s1")[0]
    # o corte nunca separa uma chamada de ferramenta do seu resultado
    assert isinstance(first, ModelRequest) and first.parts[-1].content == "Pergunta número 2?"


def test_cache_only_for_standalone_questions(mini_gold_db: Path) -> None:
    llm = FakeLLM()
    svc = _service(mini_gold_db, llm)
    first = _ask(svc, "Quantas pessoas há na base?", "a")
    calls = llm.calls
    second = _ask(svc, "  quantas PESSOAS há na base?? ", "b")
    assert llm.calls == calls and second.cached and not first.cached
    assert second.rows == first.rows

    # o follow-up depois de um acerto de cache ainda enxerga a conversa e não vem do cache
    follow_up = _ask(svc, "E só diretores?", "b")
    assert not follow_up.cached
    assert llm.prompts_seen[-1] == ["Quantas pessoas há na base?", "E só diretores?"]

    expired = ResponseCache(ttl_seconds=0)
    expired.put("pergunta", first, [])
    assert expired.get("pergunta") is None


def test_runs_and_failures_are_logged(mini_gold_db: Path, tmp_path: Path) -> None:
    log = tmp_path / "agent.jsonl"
    svc = _service(mini_gold_db, FakeLLM(), log_path=log)
    _ask(svc, "Quantas pessoas há na base?", "a")
    _ask(svc, "Quantas pessoas há na base?", "b")
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["cached"] for r in records] == [False, True]
    assert records[0]["sql"].startswith("SELECT COUNT(*)") and records[0]["requests"] == 2

    failing = _service(mini_gold_db, FakeLLM(fail=True), log_path=log)
    with pytest.raises(AgentError):
        _ask(failing, "Outra pergunta qualquer?")
    assert "429" in json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["detail"]
