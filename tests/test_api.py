from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel

from cinedata_agent.agent import build_agent
from cinedata_agent.api import create_app
from cinedata_agent.config import Settings
from cinedata_agent.service import CineDataService
from tests.test_service import FakeLLM


def _client(mini_gold_db: Path, llm: FakeLLM) -> TestClient:
    settings = Settings(_env_file=None, db_path=mini_gold_db)
    svc = CineDataService(settings, agent=build_agent(FunctionModel(llm)), log_path=None)
    return TestClient(create_app(svc))


def test_ask_and_sessions(mini_gold_db: Path) -> None:
    with _client(mini_gold_db, FakeLLM()) as client:
        body = client.post("/ask", json={"question": "Quantas pessoas há na base?"}).json()
        assert body["answer"] == "Há 2 pessoas cadastradas na base."
        assert body["sql"].startswith("SELECT COUNT(*)") and body["rows"] == [[2]]
        assert {s["kind"] for s in body["steps"]} >= {"acao", "observacao"}

        assert client.delete("/sessions/default").json() == {"removed": True}

        for payload in [
            {"question": ""},
            {"question": "x" * 501},
            {"question": "ok?", "session_id": "a b"},
        ]:
            assert client.post("/ask", json=payload).status_code == 422


def test_agent_failure_becomes_503(mini_gold_db: Path) -> None:
    with _client(mini_gold_db, FakeLLM(fail=True)) as client:
        response = client.post("/ask", json={"question": "Quantas pessoas há na base?"})
    assert response.status_code == 503 and "indisponíveis" in response.json()["detail"]


def test_operational_routes(mini_gold_db: Path) -> None:
    with _client(mini_gold_db, FakeLLM()) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert len(client.get("/schema").json()["tables"]) == 10
        assert client.get("/examples").json()
        assert "/ask" in client.get("/openapi.json").json()["paths"]
