from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cinedata_agent import agent as agent_module
from cinedata_agent.agent import AgentDeps, ask, build_agent
from cinedata_agent.config import get_settings
from cinedata_agent.synopsis import (
    EMPTY_SYNOPSIS,
    MODEL_NAME,
    IndexUnavailable,
    SynopsisIndex,
    build_index,
)

VOCAB = ("time", "travel", "future", "bank", "heist", "robbery", "love", "wedding")

MOVIES = [
    ("101", "Paradox", 2016, "Scientists travel through time and return from the future."),
    ("102", "The Vault", 2017, "A crew plans a bank heist and the robbery goes wrong."),
    ("103", "Ever After", 2018, "Two strangers fall in love before a wedding."),
    ("104", "Sem Sinopse", 2019, EMPTY_SYNOPSIS),
]


class FakeEmbedder:
    """Saco de palavras sobre um vocabulário fixo: determinístico e sem baixar modelo."""

    def _vector(self, text: str) -> np.ndarray:
        words = text.lower().replace(".", " ").split()
        return np.array([float(words.count(w)) for w in VOCAB])

    def embed(self, documents: Iterable[str], batch_size: int = 16) -> Iterable[np.ndarray]:
        return [self._vector(d) for d in documents]

    def query_embed(self, query: str) -> Iterable[np.ndarray]:
        return [self._vector(query)]


@pytest.fixture
def movies_db(tmp_path: Path) -> Path:
    path = tmp_path / "movies.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE dim_movies (id_filme TEXT, titulo TEXT, ano_lancamento INT, sinopse TEXT)"
    )
    conn.executemany("INSERT INTO dim_movies VALUES (?, ?, ?, ?)", MOVIES)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def index(movies_db: Path, tmp_path: Path) -> SynopsisIndex:
    index_path = tmp_path / "synopsis_index.npz"
    build_index(movies_db, index_path, FakeEmbedder())
    return SynopsisIndex.load(index_path, FakeEmbedder())


def test_index_skips_movies_without_synopsis(index: SynopsisIndex) -> None:
    assert len(index) == 3


def test_search_ranks_by_meaning_of_the_synopsis(index: SynopsisIndex) -> None:
    matches = index.search("time travel to the future", limit=3)
    assert matches[0].id_filme == "101"
    assert matches[0].similarity > matches[1].similarity
    assert index.search("bank robbery", limit=1)[0].id_filme == "102"
    assert index.search("a wedding", limit=1)[0].id_filme == "103"


def test_missing_or_stale_index_is_reported(tmp_path: Path) -> None:
    with pytest.raises(IndexUnavailable, match="build_synopsis_index"):
        SynopsisIndex.load(tmp_path / "nao_existe.npz", FakeEmbedder())

    stale = tmp_path / "antigo.npz"
    with stale.open("wb") as file:
        np.savez(file, ids=np.array(["1"]), vectors=np.ones((1, 8)), model=np.array("outro"))
    with pytest.raises(IndexUnavailable, match="outro modelo"):
        SynopsisIndex.load(stale, FakeEmbedder())


def _tool_returns(messages: list[ModelMessage]) -> int:
    return sum(
        1
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if p.part_kind == "tool-return"
    )


def test_agent_combines_synopsis_search_with_sql(
    movies_db: Path, index: SynopsisIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_module, "get_index", lambda *_: index)

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = _tool_returns(messages)
        if step == 0:
            call = ToolCallPart("buscar_por_sinopse", {"descricao": "bank heist", "quantidade": 1})
        elif step == 1:
            sql = "SELECT titulo, ano_lancamento FROM dim_movies WHERE id_filme IN ('102')"
            call = ToolCallPart("executar_sql", {"sql": sql})
        else:
            answer = "Pela sinopse, o filme de assalto a banco é The Vault, de 2017."
            call = ToolCallPart(info.output_tools[0].name, {"answer": answer, "assumptions": []})
        return ModelResponse(parts=[call])

    deps = AgentDeps(
        db_path=movies_db,
        max_rows=100,
        timeout_seconds=5.0,
        synopsis_index_path=Path("ignorado"),
        embedding_cache_dir=Path("ignorado"),
    )
    response, _ = asyncio.run(
        ask(
            build_agent(FunctionModel(model)),
            "filmes de assalto a banco",
            deps=deps,
            max_requests=5,
        )
    )

    assert "The Vault" in response.answer  # passou na verificação anti-alucinação
    assert response.rows == [["The Vault", 2017]]  # a tabela final é a da SQL
    assert deps.results[0].columns == ["titulo", "ano_lancamento", "similaridade", "sinopse"]
    assert [s.kind for s in response.steps] == ["acao", "observacao", "acao", "observacao"]
    assert "The Vault (2017" in response.steps[1].content


def test_tool_reports_missing_index_instead_of_failing(movies_db: Path, tmp_path: Path) -> None:
    deps = AgentDeps(
        db_path=movies_db,
        max_rows=100,
        timeout_seconds=5.0,
        synopsis_index_path=tmp_path / "nao_existe.npz",
        embedding_cache_dir=tmp_path,
    )
    ctx = type("Ctx", (), {"deps": deps})()
    result = agent_module.buscar_por_sinopse(ctx, "time travel")  # type: ignore[arg-type]
    assert result["filmes"] == [] and "build_synopsis_index" in str(result["aviso"])


@pytest.mark.db
def test_real_index_finds_time_travel_movies() -> None:
    settings = get_settings()
    if not settings.synopsis_index_path.is_file():
        pytest.skip("índice de sinopses não gerado")
    from cinedata_agent.synopsis import get_index

    index = get_index(settings.synopsis_index_path, settings.embedding_cache_dir)
    with np.load(settings.synopsis_index_path) as data:
        assert str(data["model"]) == MODEL_NAME
    matches = index.search("time travel", limit=10)
    with sqlite3.connect(f"file:{settings.db_path.as_posix()}?mode=ro&immutable=1", uri=True) as c:
        synopses = [
            c.execute(
                "SELECT sinopse FROM dim_movies WHERE id_filme = ?", (m.id_filme,)
            ).fetchone()[0]
            for m in matches
        ]
    assert sum("time" in s.lower() for s in synopses) >= 8
