"""Configuração central da aplicação, lida de variáveis de ambiente e do `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

Provider = Literal["groq", "openrouter"]
ReasoningEffort = Literal["none", "low", "medium", "high"]

# fallback automático em erro/429, ver docs/decisoes.md (D4 e D9)
DEFAULT_BASE_URLS: dict[Provider, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

DEFAULT_MODELS: dict[Provider, list[str]] = {
    "groq": ["openai/gpt-oss-120b"],
    "openrouter": [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3.5-lightning:free",
        "google/gemma-4-31b-it:free",
        "qwen/qwen3.8-27b:free",
    ],
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Provider = "groq"
    groq_api_key: SecretStr | None = Field(default=None, description="Chave do Groq (gsk_...).")
    openrouter_api_key: SecretStr | None = Field(
        default=None, description="Chave da API do OpenRouter (sk-or-v1-...)."
    )

    model_name: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Modelo, ou cadeia de fallback separada por vírgulas. Vazio = padrão.",
    )
    model_base_url: str | None = Field(
        default=None, description="URL da API compatível com OpenAI. Vazio = padrão do provedor."
    )
    temperature: float = Field(
        default=0.0, ge=0, le=2, description="0 = saída determinística (adequado para SQL)."
    )
    reasoning_effort: ReasoningEffort = Field(
        default="none", description="Nível de raciocínio pedido aos modelos que o suportam."
    )
    max_requests_per_question: int = Field(
        default=10, ge=1, description="Teto de chamadas ao LLM por pergunta (protege a cota)."
    )
    model_timeout_seconds: float = Field(default=90.0, gt=0)
    question_timeout_seconds: float = Field(
        default=180.0, gt=0, description="Tempo máximo para responder uma pergunta inteira."
    )

    db_path: Path = Field(
        default=Path("data/cinerocket.db"),
        description="Banco SQLite da camada Gold; caminhos relativos partem da raiz do projeto.",
    )
    query_timeout_seconds: float = Field(
        default=30.0, gt=0, description="Tempo máximo de uma consulta antes de ser interrompida."
    )
    max_rows: int = Field(default=1000, ge=1, description="Teto de linhas devolvidas por consulta.")

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Origens liberadas para o frontend (separadas por vírgula).",
    )

    @field_validator("model_name", "cors_origins", mode="before")
    @classmethod
    def _split_models(cls, value: object) -> object:
        # no .env a lista vem separada por vírgulas
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("db_path")
    @classmethod
    def _resolve_relative_to_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @property
    def model_chain(self) -> list[str]:
        return self.model_name or DEFAULT_MODELS[self.llm_provider]

    @property
    def base_url(self) -> str:
        return (self.model_base_url or DEFAULT_BASE_URLS[self.llm_provider]).rstrip("/")

    @property
    def api_key(self) -> SecretStr | None:
        return self.groq_api_key if self.llm_provider == "groq" else self.openrouter_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
