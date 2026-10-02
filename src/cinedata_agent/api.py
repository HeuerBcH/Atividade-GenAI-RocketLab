"""API HTTP do agente. Rode com: uvicorn cinedata_agent.api:app --port 8000"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .agent import AgentError
from .config import get_settings
from .models import AskResponse
from .prompt import prompt_version
from .semantic_layer import BUSINESS_RULES, JOIN_PATHS, TABLES
from .service import CineDataService

logger = logging.getLogger(__name__)

EXAMPLES: dict[str, list[str]] = {
    "Bilheteria e Finanças": [
        "Quais são os 10 filmes com maior receita em R$?",
        "Qual o lucro médio por gênero, considerando apenas filmes com receita informada?",
        "Quais filmes têm a maior margem de lucro, entre os que possuem receita e orçamento?",
    ],
    "Popularidade e Engajamento": [
        "Quais são os 5 filmes mais populares?",
        "Quais filmes têm a maior divergência entre a nota TMDB e a nota IMDb?",
        "Qual a nota média IMDb por ano de lançamento?",
    ],
    "Elenco e Equipe": [
        "Qual ator teve mais participações em filmes lançados nos últimos 5 anos?",
        "Quais diretores têm a maior nota média, considerando um mínimo de 5 filmes?",
        "Qual dupla ator-diretor mais trabalhou junta?",
    ],
    "Gêneros e Produtoras": [
        "Qual a quantidade de filmes por gênero?",
        "Qual produtora teve o maior lucro total?",
        "Qual gênero tem a maior margem de lucro média?",
    ],
    "Avaliações dos Usuários": [
        "Quais filmes foram mais avaliados pelos usuários?",
        "Em quais filmes a nota média dos usuários mais diverge da nota IMDb?",
    ],
}


class AskRequest(BaseModel):
    question: str = Field(
        min_length=3, max_length=500, examples=[q for qs in EXAMPLES.values() for q in qs]
    )
    session_id: str = Field(
        default="default",
        min_length=1,
        max_length=64,
        pattern=r"^[\w-]+$",
        description="Identifica a conversa; perguntas com o mesmo id compartilham memória.",
    )


def create_app(service: CineDataService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # nos testes o serviço chega pronto; em produção é montado aqui (e falha cedo)
        app.state.service = service or CineDataService(get_settings())
        yield

    app = FastAPI(
        title="CineData Agent",
        description="Perguntas em português sobre o catálogo de filmes, respondidas com SQL "
        "somente leitura sobre a camada Gold.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    def _service(request: Request) -> CineDataService:
        return request.app.state.service

    @app.post("/ask", response_model=AskResponse, tags=["agente"])
    async def ask(body: AskRequest, request: Request) -> AskResponse:
        try:
            return await _service(request).ask(body.question, body.session_id)
        except AgentError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.delete("/sessions/{session_id}", tags=["agente"])
    async def reset_session(session_id: str, request: Request) -> dict[str, bool]:
        return {"removed": _service(request).reset(session_id)}

    @app.get("/health", tags=["operação"])
    async def health(request: Request) -> dict[str, object]:
        svc = _service(request)
        return {
            "status": "ok",
            "provider": svc.settings.llm_provider,
            "models": svc.settings.model_chain,
            "prompt_version": prompt_version(),
            "sessions": len(svc.sessions),
            "cached_answers": len(svc.cache),
        }

    @app.get("/schema", tags=["operação"])
    async def schema() -> dict[str, object]:
        return {
            "tables": [
                {
                    "name": t.name,
                    "description": t.description,
                    "columns": [{"name": c.name, "description": c.description} for c in t.columns],
                }
                for t in TABLES
            ],
            "joins": list(JOIN_PATHS),
            "business_rules": list(BUSINESS_RULES),
        }

    @app.get("/examples", tags=["operação"])
    async def examples() -> dict[str, list[str]]:
        return EXAMPLES

    return app


app = create_app()
