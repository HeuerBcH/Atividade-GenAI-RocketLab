"""Configuração central da aplicação, lida de variáveis de ambiente e do `.env`.

Todo valor ajustável (caminhos, chaves, parâmetros do modelo) passa por aqui, para que
nenhum módulo leia `os.environ` diretamente.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: SecretStr | None = Field(
        default=None, description="Chave da API do OpenRouter (sk-or-v1-...)."
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    db_path: Path = Field(
        default=Path("data/cinerocket.db"),
        description="Banco SQLite da camada Gold; caminhos relativos partem da raiz do projeto.",
    )

    @field_validator("db_path")
    @classmethod
    def _resolve_relative_to_root(cls, value: Path) -> Path:
        # Torna o caminho independente do diretório de onde o comando foi executado.
        return value if value.is_absolute() else PROJECT_ROOT / value


@lru_cache
def get_settings() -> Settings:
    return Settings()
