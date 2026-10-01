"""Preparação (idempotente) do banco Gold para servir consultas do agente.

O arquivo `cinerocket.db` é distribuído sem índices para os caminhos de join que as
perguntas de negócio usam (pessoa -> filmes, gênero -> filmes, produtora -> filmes).
Medido em 2026-10-01, a pergunta "dupla ator-diretor que mais trabalhou junta" caiu de
~60 s para ~4,5 s com os PRAGMAs de leitura + índices abaixo (ver docs/decisoes.md).

Tudo aqui é aditivo: nenhum dado ou índice existente da camada Gold é alterado.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "dim_movies",
        "fact_movies_performance",
        "dim_genres",
        "dim_people",
        "dim_companies",
        "dim_reviews",
        "movie_reviews",
        "bridge_movie_genre",
        "bridge_movie_person",
        "bridge_movie_company",
    }
)

# Índices de cobertura: as consultas resolvem joins e filtros sem tocar nas tabelas.
REQUIRED_INDEXES: dict[str, str] = {
    "ix_dim_people_tipo_sk": "dim_people(tipo_pessoa, sk_person_id, nome_pessoa)",
    "ix_dim_people_sk_tipo": "dim_people(sk_person_id, tipo_pessoa, nome_pessoa)",
    "ix_bridge_movie_person_person_movie": "bridge_movie_person(sk_person_id, sk_movie_id)",
    "ix_bridge_movie_genre_genre_movie": "bridge_movie_genre(sk_genre_id, sk_movie_id)",
    "ix_bridge_movie_company_company_movie": "bridge_movie_company(sk_company_id, sk_movie_id)",
}

# Aplicados em cada conexão de leitura; sozinhos reduzem a consulta mais pesada em ~8x.
READ_PRAGMAS: tuple[str, ...] = (
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -262144",  # 256 MiB
    "PRAGMA mmap_size = 1073741824",  # 1 GiB
)


@dataclass(frozen=True)
class SetupReport:
    created_indexes: list[str]
    analyzed: bool
    journal_mode: str


def missing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return set(EXPECTED_TABLES) - {name for (name,) in rows}


def missing_indexes(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    existing = {name for (name,) in rows}
    return [name for name in REQUIRED_INDEXES if name not in existing]


def has_statistics(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_stat1'"
    ).fetchone()
    return row is not None


def journal_mode(conn: sqlite3.Connection) -> str:
    return conn.execute("PRAGMA journal_mode").fetchone()[0].lower()


def is_prepared(conn: sqlite3.Connection) -> bool:
    return not missing_indexes(conn) and has_statistics(conn) and journal_mode(conn) != "wal"


def prepare(conn: sqlite3.Connection) -> SetupReport:
    """Cria os índices faltantes, atualiza estatísticas e sai do modo WAL.

    Sair do WAL permite abrir o arquivo com `mode=ro` sem depender dos arquivos
    auxiliares `-wal`/`-shm` nem de permissão de escrita no diretório.
    """
    to_create = missing_indexes(conn)
    for name in to_create:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {REQUIRED_INDEXES[name]}")
    conn.commit()

    analyzed = bool(to_create) or not has_statistics(conn)
    if analyzed:
        conn.execute("ANALYZE")
        conn.commit()

    mode = conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0].lower()
    return SetupReport(created_indexes=to_create, analyzed=analyzed, journal_mode=mode)
