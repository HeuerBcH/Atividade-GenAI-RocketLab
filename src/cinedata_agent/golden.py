"""Modelo e carregamento do conjunto de avaliação (`eval/golden.yaml`).

Cada caso traz uma pergunta em linguagem natural e a SQL de referência escrita à mão. A
avaliação (Fase 6) compara o *resultado* da SQL do agente com o da referência (execution
accuracy), e não o texto da SQL: consultas diferentes podem estar igualmente corretas.

Modos de comparação (`check.mode`):
- ``ordered``: os valores de ``key`` nas ``top_n`` primeiras linhas, na mesma ordem
  (``metric`` é a coluna de ordenação, usada para detectar empates).
- ``set``: o mesmo conjunto de valores de ``key``, em qualquer ordem.
- ``values``: os ``top_n`` primeiros valores de ``metric`` (robusto a empates).
- ``mapping``: o par ``key`` -> ``metric`` de todas as linhas (ex.: gênero -> contagem).
- ``scalar``: um único valor de ``metric``.
- ``refusal``: o agente deve recusar, sem executar SQL.
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
]
Mode = Literal["ordered", "set", "values", "mapping", "scalar", "refusal"]

_NEEDS_KEY: frozenset[str] = frozenset({"ordered", "set", "mapping"})
_NEEDS_METRIC: frozenset[str] = frozenset({"ordered", "values", "mapping", "scalar"})


class Check(BaseModel):
    mode: Mode
    key: list[str] = Field(default_factory=list)
    metric: str | None = None
    top_n: int | None = Field(default=None, ge=1)
    rel_tol: float = Field(default=0.01, ge=0)

    @model_validator(mode="after")
    def _fields_match_mode(self) -> Self:
        if self.mode in _NEEDS_KEY and not self.key:
            raise ValueError(f"modo '{self.mode}' exige 'key'")
        if self.mode in _NEEDS_METRIC and not self.metric:
            raise ValueError(f"modo '{self.mode}' exige 'metric'")
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
        is_refusal = self.check.mode == "refusal"
        if is_refusal and self.sql:
            raise ValueError(f"{self.id}: casos de recusa não têm SQL de referência")
        if not is_refusal and not self.sql:
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
