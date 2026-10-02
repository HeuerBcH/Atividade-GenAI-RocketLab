"""Busca semântica nas sinopses: embeddings locais (fastembed/ONNX), sem alterar o banco.

O índice (um vetor por sinopse) é gerado uma vez por `scripts/build_synopsis_index.py` e salvo
fora do banco, em `data/`. A busca compara o vetor da descrição pedida com todos os vetores
(similaridade de cosseno) e devolve os `id_filme` mais parecidos, que o agente usa na SQL.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Protocol

import numpy as np

from .db import readonly_connection

MODEL_NAME = "BAAI/bge-small-en-v1.5"  # as sinopses estão em inglês; ~65 MB, roda na CPU
EMPTY_SYNOPSIS = "Sem descrição"  # marcador da fonte para filmes sem sinopse


class IndexUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    def embed(self, documents: Iterable[str], batch_size: int = ...) -> Iterable[np.ndarray]: ...

    def query_embed(self, query: str) -> Iterable[np.ndarray]: ...


def load_embedder(cache_dir: Path) -> Embedder:
    # no Windows sem modo desenvolvedor o cache funciona sem symlinks; o aviso só polui a saída
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    # import tardio: só quem gera ou consulta o índice paga o custo de carregar o ONNX
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_NAME, cache_dir=str(cache_dir))


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1, norms)


def read_synopses(db_path: Path) -> Iterator[tuple[str, str]]:
    with readonly_connection(db_path) as conn:
        yield from conn.execute(
            "SELECT id_filme, sinopse FROM dim_movies "
            "WHERE sinopse IS NOT NULL AND trim(sinopse) <> '' AND sinopse <> ? "
            "ORDER BY id_filme",
            (EMPTY_SYNOPSIS,),
        )


def build_index(
    db_path: Path,
    index_path: Path,
    embedder: Embedder,
    *,
    batch_size: int = 16,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    # lotes de sinopses de tamanho parecido: cada lote é completado até o texto mais longo,
    # então ordenar por tamanho evita processar padding (medido: ~3,5x mais rápido)
    rows = sorted(read_synopses(db_path), key=lambda row: len(row[1]))
    ids = [movie_id for movie_id, _ in rows]
    chunks: list[np.ndarray] = []
    for start in range(0, len(rows), batch_size):
        batch = [synopsis for _, synopsis in rows[start : start + batch_size]]
        chunks.append(np.asarray(list(embedder.embed(batch, batch_size=batch_size))))
        if on_progress:
            on_progress(min(start + batch_size, len(rows)), len(rows))
    # float16 normalizado: metade do espaço, e o produto escalar já é o cosseno
    vectors = _normalize(np.vstack(chunks)).astype(np.float16)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("wb") as file:  # com o arquivo aberto, o numpy não acrescenta .npz
        np.savez(file, ids=np.array(ids), vectors=vectors, model=np.array(MODEL_NAME))
    return len(ids)


@dataclass(frozen=True)
class Match:
    id_filme: str
    similarity: float


class SynopsisIndex:
    def __init__(self, ids: np.ndarray, vectors: np.ndarray, embedder: Embedder) -> None:
        self._ids = ids
        # float16 no disco (metade do espaço), float32 na memória: converter a cada busca
        # custava ~40 ms; assim a busca fica só no produto escalar
        self._vectors = vectors.astype(np.float32)
        self._embedder = embedder

    def __len__(self) -> int:
        return len(self._ids)

    @classmethod
    def load(cls, index_path: Path, embedder: Embedder | Callable[[], Embedder]) -> SynopsisIndex:
        """`embedder` pode vir pronto ou como fábrica: o modelo só é carregado se o índice valer."""
        if not index_path.is_file():
            raise IndexUnavailable(
                "O índice de sinopses não foi gerado. Rode: python scripts/build_synopsis_index.py"
            )
        with np.load(index_path) as data:
            if str(data["model"]) != MODEL_NAME:
                raise IndexUnavailable("Índice gerado com outro modelo: gere-o de novo.")
            ids, vectors = data["ids"], data["vectors"]
        return cls(ids, vectors, embedder() if callable(embedder) else embedder)

    def search(self, text: str, limit: int) -> list[Match]:
        query = _normalize(np.asarray(next(iter(self._embedder.query_embed(text)))))
        scores = self._vectors @ query.astype(np.float32)
        limit = min(limit, len(scores))
        top = np.argpartition(-scores, limit - 1)[:limit]
        top = top[np.argsort(-scores[top])]
        return [Match(str(self._ids[i]), round(float(scores[i]), 3)) for i in top]


_lock = Lock()


@lru_cache(maxsize=2)
def _cached(index_path: Path, cache_dir: Path) -> SynopsisIndex:
    return SynopsisIndex.load(index_path, lambda: load_embedder(cache_dir))


def get_index(index_path: Path, cache_dir: Path) -> SynopsisIndex:
    """Carrega o índice e o modelo uma única vez por processo (1 a 2 s na primeira busca)."""
    with _lock:
        return _cached(index_path, cache_dir)
