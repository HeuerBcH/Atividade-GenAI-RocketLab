from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from cinedata_agent.config import Settings
from cinedata_agent.quota import QuotaError, fetch_quota, list_models, next_reset


def _openrouter(key: str | None = "sk-or-v1-test") -> Settings:
    return Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key=key)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reads_the_openrouter_daily_quota() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-or-v1-test"
        daily = {"used": 12, "limit": 50, "remaining": 38}
        return httpx.Response(200, json={"data": {"free_model_daily_requests": daily}})

    status = fetch_quota(_openrouter(), client=_client(handler))
    assert (status.used, status.limit, status.remaining) == (12, 50, 38)
    reset = next_reset(datetime(2026, 10, 2, 23, 30, tzinfo=UTC))  # 21h em Brasília
    assert reset == datetime(2026, 10, 3, tzinfo=UTC)


def test_quota_errors_are_clear() -> None:
    with pytest.raises(QuotaError, match="401"):
        fetch_quota(_openrouter(), client=_client(lambda _: httpx.Response(401)))
    with pytest.raises(QuotaError, match="OPENROUTER_API_KEY"):
        fetch_quota(_openrouter(key=None))
    with pytest.raises(QuotaError, match="Groq"):
        fetch_quota(Settings(_env_file=None, groq_api_key="gsk_x"))


def test_lists_active_groq_models() -> None:
    data = [
        {"id": "openai/gpt-oss-120b", "context_window": 131072, "active": True},
        {"id": "antigo", "active": False},
    ]
    response = httpx.Response(200, json={"data": data})
    models = list_models(
        Settings(_env_file=None, groq_api_key="gsk_x"), client=_client(lambda _: response)
    )
    assert [(m.id, m.context_window) for m in models] == [("openai/gpt-oss-120b", 131072)]
