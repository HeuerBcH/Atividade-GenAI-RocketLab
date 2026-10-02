"""Modelos de entrada e saída do agente."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentOutput(BaseModel):
    # só texto: as linhas vão direto do banco para o usuário, o modelo não reescreve números

    answer: str = Field(
        min_length=20,
        description="Resposta em português para um público leigo (2 a 5 frases), escrita só "
        "DEPOIS de observar o resultado da consulta.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Interpretações e filtros adotados; vazia se não houver.",
    )


class TraceStep(BaseModel):
    kind: Literal["pensamento", "acao", "observacao", "erro"]
    content: str


class Usage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class AskResponse(BaseModel):
    question: str
    session_id: str | None = None
    cached: bool = False
    answer: str
    assumptions: list[str] = Field(default_factory=list)
    sql: str | None = Field(default=None, description="Última consulta executada com sucesso.")
    columns: list[str] = Field(default_factory=list)
    rows: list[list[object]] = Field(default_factory=list)
    truncated: bool = False
    steps: list[TraceStep] = Field(default_factory=list)
    model: str | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0
