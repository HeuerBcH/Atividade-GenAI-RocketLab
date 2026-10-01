"""Contratos de dados do agente: o que o LLM produz e o que a aplicação devolve."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentOutput(BaseModel):
    """Saída estruturada gerada pelo LLM.

    Contém só texto: os dados vêm direto do banco (capturados pela ferramenta), para que o
    modelo não possa alterar números ao reescrevê-los nem gastar tokens copiando tabelas.
    """

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
    """Um passo do ciclo ReAct, para transparência e depuração."""

    kind: Literal["pensamento", "acao", "observacao", "erro"]
    content: str


class Usage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class AskResponse(BaseModel):
    question: str
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
