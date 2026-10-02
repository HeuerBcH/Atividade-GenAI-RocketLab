"""Golden set (eval/golden.yaml): perguntas com SQL de referência.

Modos de comparação: ordered (chaves na mesma ordem), set (mesmo conjunto), values (top N da
métrica, tolera empates), mapping (chave -> métrica), scalar (um valor), refusal (sem SQL) e
semantic (agente híbrido: usou a busca nas sinopses e os filmes devolvidos são do tema `query`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field, model_validator

from .config import PROJECT_ROOT

GOLDEN_PATH = PROJECT_ROOT / "eval" / "golden.yaml"

Category = Literal[
    "bilheteria_financas",
    "popularidade_engajamento",
    "elenco_equipe",
    "generos_produtoras",
    "avaliacoes_usuarios",
    "robustez",
    "busca_semantica",
]
Mode = Literal["ordered", "set", "values", "mapping", "scalar", "refusal", "semantic"]

_NEEDS_KEY: frozenset[str] = frozenset({"ordered", "set", "mapping"})
_NEEDS_METRIC: frozenset[str] = frozenset({"ordered", "values", "mapping", "scalar"})
WITHOUT_SQL: frozenset[str] = frozenset({"refusal", "semantic"})


class Check(BaseModel):
    mode: Mode
    key: list[str] = Field(default_factory=list)
    metric: str | None = None
    top_n: int | None = Field(default=None, ge=1)
    rel_tol: float = Field(default=0.01, ge=0)
    query: str | None = Field(default=None, description="Tema de referência (modo semantic).")

    @model_validator(mode="after")
    def _fields_match_mode(self) -> Self:
        if self.mode in _NEEDS_KEY and not self.key:
            raise ValueError(f"modo '{self.mode}' exige 'key'")
        if self.mode in _NEEDS_METRIC and not self.metric:
            raise ValueError(f"modo '{self.mode}' exige 'metric'")
        if self.mode == "semantic" and not self.query:
            raise ValueError("modo 'semantic' exige 'query'")
        return self


class GoldenCase(BaseModel):
    id: str = Field(pattern=r"^[A-Z]{3}-\d{2}$")
    category: Category
    source: Literal["enunciado", "extra"]
    question: str = Field(min_length=5)
    history: list[str] = Field(default_factory=list)
    sql: str | None = None
    check: Check
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sql_matches_mode(self) -> Self:
        without_sql = self.check.mode in WITHOUT_SQL
        if without_sql and self.sql:
            raise ValueError(f"{self.id}: o modo '{self.check.mode}' não tem SQL de referência")
        if not without_sql and not self.sql:
            raise ValueError(f"{self.id}: SQL de referência obrigatória")
        return self


class GoldenSet(BaseModel):
    version: int
    cases: list[GoldenCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        if duplicated := {i for i in ids if ids.count(i) > 1}:
            raise ValueError(f"ids duplicados: {sorted(duplicated)}")
        return self


def load_golden(path: Path = GOLDEN_PATH) -> GoldenSet:
    with path.open(encoding="utf-8") as fh:
        return GoldenSet.model_validate(yaml.safe_load(fh))
