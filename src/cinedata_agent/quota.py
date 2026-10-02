"""Consulta da cota diária de modelos gratuitos do OpenRouter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from .config import Settings

TIMEOUT_SECONDS = 10.0
GROQ_LIMITS_URL = "https://console.groq.com/settings/limits"


class QuotaError(RuntimeError):
    pass


class QuotaStatus(BaseModel):
    used: int | None = None
    limit: int | None = None
    remaining: int | None = None
    is_free_tier: bool | None = None
    resets_at: datetime


def next_reset(now: datetime | None = None) -> datetime:
    # zera à meia-noite UTC (21h em Brasília)
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
    if settings.llm_provider != "openrouter":
        raise QuotaError(f"O Groq não informa a cota por API; consulte {GROQ_LIMITS_URL}.")
    if settings.openrouter_api_key is None:
        raise QuotaError("OPENROUTER_API_KEY não configurada (veja .env.example).")

    headers = {"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"}
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(f"{settings.base_url}/key", headers=headers)
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


class ModelInfo(BaseModel):
    id: str
    context_window: int | None = None
    supports_tools: bool | None = None


def parse_models(provider: str, payload: dict) -> list[ModelInfo]:
    models = []
    for item in payload.get("data") or []:
        if provider == "groq":
            if item.get("active") is False:
                continue
            models.append(ModelInfo(id=item["id"], context_window=item.get("context_window")))
        elif item["id"].endswith(":free"):
            params = item.get("supported_parameters") or []
            models.append(
                ModelInfo(
                    id=item["id"],
                    context_window=item.get("context_length"),
                    supports_tools="tools" in params,
                )
            )
    return sorted(models, key=lambda m: m.id)


def list_models(settings: Settings, client: httpx.Client | None = None) -> list[ModelInfo]:
    if settings.api_key is None:
        variable = f"{settings.llm_provider.upper()}_API_KEY"
        raise QuotaError(f"{variable} não configurada (veja .env.example).")
    base = settings.base_url
    headers = {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}
    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(f"{base}/models", headers=headers)
    except httpx.HTTPError as exc:
        raise QuotaError(f"Falha de rede ao listar modelos: {exc}") from exc
    finally:
        if owns_client:
            client.close()
    if response.status_code == 401:
        raise QuotaError("Chave inválida ou revogada (HTTP 401).")
    if response.is_error:
        raise QuotaError(f"O provedor respondeu HTTP {response.status_code}.")
    return parse_models(settings.llm_provider, response.json())
