"""Consulta da cota diária de modelos gratuitos do OpenRouter.

`GET /key` não é uma chamada de modelo, então pode ser usada à vontade para planejar
testes antes de gastar requisições (limite de 50/dia no plano gratuito).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from .config import Settings

TIMEOUT_SECONDS = 10.0


class QuotaError(RuntimeError):
    """Falha ao consultar a cota (chave ausente/inválida ou erro de rede)."""


class QuotaStatus(BaseModel):
    used: int | None = None
    limit: int | None = None
    remaining: int | None = None
    is_free_tier: bool | None = None
    resets_at: datetime


def next_reset(now: datetime | None = None) -> datetime:
    """O contador zera à meia-noite UTC (21h no horário de Brasília)."""
    now = now or datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def parse_key_response(payload: dict) -> QuotaStatus:
    data = payload.get("data") or {}
    daily = data.get("free_model_daily_requests") or {}
    return QuotaStatus(
        used=daily.get("used"),
        limit=daily.get("limit"),
        remaining=daily.get("remaining"),
        is_free_tier=data.get("is_free_tier"),
        resets_at=next_reset(),
    )


def fetch_quota(settings: Settings, client: httpx.Client | None = None) -> QuotaStatus:
    if settings.openrouter_api_key is None:
        raise QuotaError("OPENROUTER_API_KEY não configurada (veja .env.example).")

    headers = {"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"}
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(f"{settings.openrouter_base_url}/key", headers=headers)
    except httpx.HTTPError as exc:
        raise QuotaError(f"Falha de rede ao consultar o OpenRouter: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if response.status_code == 401:
        raise QuotaError("Chave do OpenRouter inválida ou revogada (HTTP 401).")
    if response.is_error:
        raise QuotaError(f"OpenRouter respondeu HTTP {response.status_code}.")
    return parse_key_response(response.json())
