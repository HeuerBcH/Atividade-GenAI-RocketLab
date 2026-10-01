from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from cinedata_agent.config import Settings
from cinedata_agent.quota import QuotaError, fetch_quota, list_models, next_reset

FAKE_KEY = "sk-or-v1-test"


def _settings(key: str | None = FAKE_KEY) -> Settings:
    return Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key=key)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parses_daily_free_quota() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/key")
        assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
        payload = {
            "data": {
                "is_free_tier": True,
                "free_model_daily_requests": {"used": 12, "limit": 50, "remaining": 38},
            }
        }
        return httpx.Response(200, json=payload)

    status = fetch_quota(_settings(), client=_client(handler))

    assert (status.used, status.limit, status.remaining) == (12, 50, 38)
    assert status.is_free_tier is True


def test_tolerates_missing_quota_field() -> None:
    status = fetch_quota(_settings(), client=_client(lambda _: httpx.Response(200, json={})))
    assert status.remaining is None


def test_invalid_key_raises_clear_error() -> None:
    with pytest.raises(QuotaError, match="401"):
        fetch_quota(_settings(), client=_client(lambda _: httpx.Response(401)))


def test_missing_key_fails_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("não deveria chamar a rede sem chave")

    with pytest.raises(QuotaError, match="OPENROUTER_API_KEY"):
        fetch_quota(_settings(key=None), client=_client(handler))


def test_network_failure_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with pytest.raises(QuotaError, match="rede"):
        fetch_quota(_settings(), client=_client(handler))


def test_reset_is_next_utc_midnight() -> None:
    now = datetime(2026, 10, 2, 23, 30, tzinfo=UTC)  # 20h30 em Brasília
    assert next_reset(now) == datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


def test_quota_endpoint_is_openrouter_only() -> None:
    with pytest.raises(QuotaError, match="Groq"):
        fetch_quota(Settings(_env_file=None, llm_provider="groq", groq_api_key="gsk_x"))


def test_lists_active_groq_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.groq.com"
        data = [
            {"id": "llama-3.3-70b-versatile", "context_window": 131072, "active": True},
            {"id": "old-model", "active": False},
        ]
        return httpx.Response(200, json={"data": data})

    settings = Settings(_env_file=None, llm_provider="groq", groq_api_key="gsk_x")
    models = list_models(settings, client=_client(handler))
    assert [(m.id, m.context_window) for m in models] == [("llama-3.3-70b-versatile", 131072)]


def test_lists_only_free_openrouter_models_with_tool_support() -> None:
    data = [
        {"id": "a/m:free", "context_length": 1000, "supported_parameters": ["tools"]},
        {"id": "b/paid", "supported_parameters": ["tools"]},
    ]
    models = list_models(
        _settings(), client=_client(lambda _: httpx.Response(200, json={"data": data}))
    )
    assert [(m.id, m.supports_tools) for m in models] == [("a/m:free", True)]
