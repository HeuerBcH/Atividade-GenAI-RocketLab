from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from cinedata_agent import db_setup
from cinedata_agent.config import get_settings

# Esqueleto mínimo das 10 tabelas Gold (só as colunas usadas por índices/testes),
# para que os testes não dependam do arquivo real de ~580 MB.
MINI_GOLD_SCHEMA = """
CREATE TABLE dim_movies (sk_movie_id TEXT PRIMARY KEY, titulo TEXT NOT NULL);
CREATE TABLE fact_movies_performance (sk_movie_id TEXT PRIMARY KEY, receita_brl NUMERIC);
CREATE TABLE dim_genres (sk_genre_id TEXT PRIMARY KEY, nome_genero TEXT NOT NULL);
CREATE TABLE dim_people (
    sk_person_id TEXT PRIMARY KEY, nome_pessoa TEXT NOT NULL, tipo_pessoa TEXT NOT NULL
);
CREATE TABLE dim_companies (sk_company_id TEXT PRIMARY KEY, nome_produtora TEXT NOT NULL);
CREATE TABLE dim_reviews (sk_review_id TEXT PRIMARY KEY, sk_movie_id TEXT NOT NULL);
CREATE TABLE movie_reviews (id INTEGER PRIMARY KEY, sk_movie_id TEXT NOT NULL);
CREATE TABLE bridge_movie_genre (sk_movie_id TEXT, sk_genre_id TEXT,
    PRIMARY KEY (sk_movie_id, sk_genre_id));
CREATE TABLE bridge_movie_person (sk_movie_id TEXT, sk_person_id TEXT,
    PRIMARY KEY (sk_movie_id, sk_person_id));
CREATE TABLE bridge_movie_company (sk_movie_id TEXT, sk_company_id TEXT,
    PRIMARY KEY (sk_movie_id, sk_company_id));
INSERT INTO dim_people VALUES ('p1', 'Ator Um', 'Ator'), ('p2', 'Diretora Dois', 'Diretor');
"""


@pytest.fixture(scope="session")
def gold_conn() -> Iterator[sqlite3.Connection]:
    """Conexão somente leitura com o banco real; pula o teste se ele não estiver pronto."""
    db_path = get_settings().db_path
    if not db_path.is_file():
        pytest.skip(f"banco real ausente em {db_path}")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    if not db_setup.is_prepared(conn):
        conn.close()
        pytest.skip("banco real não preparado (rode scripts/prepare_db.py)")
    for pragma in db_setup.READ_PRAGMAS:
        conn.execute(pragma)
    yield conn
    conn.close()


@pytest.fixture
def mini_gold_db(tmp_path: Path) -> Path:
    path = tmp_path / "mini_gold.db"
    conn = sqlite3.connect(path)
    conn.executescript(MINI_GOLD_SCHEMA)
    conn.execute("PRAGMA journal_mode = WAL")  # igual ao arquivo distribuído
    conn.close()
    return path


@pytest.fixture
def mini_gold_conn(mini_gold_db: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(mini_gold_db)
    yield conn
    conn.close()
