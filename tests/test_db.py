from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from cinedata_agent import db_setup
from cinedata_agent.config import get_settings
from cinedata_agent.db import QueryError, QueryTimeoutError, readonly_connection, run_query
from cinedata_agent.guardrails import GuardrailError

INFINITE_CTE = (
    "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT MAX(x) FROM n"
)


@pytest.fixture
def prepared_db(mini_gold_db: Path) -> Path:
    conn = sqlite3.connect(mini_gold_db)
    db_setup.prepare(conn)
    conn.close()
    return mini_gold_db


def _run(sql: str, db: Path, **kwargs):
    options = {"max_rows": 100, "timeout_seconds": 5.0} | kwargs
    return run_query(sql, db_path=db, **options)


def _people(db: Path) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT * FROM dim_people ORDER BY 1").fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------------- caminho feliz
def test_returns_columns_and_rows(prepared_db: Path) -> None:
    result = _run("SELECT nome_pessoa, tipo_pessoa FROM dim_people ORDER BY 1", prepared_db)

    assert result.columns == ["nome_pessoa", "tipo_pessoa"]
    assert result.rows == [["Ator Um", "Ator"], ["Diretora Dois", "Diretor"]]
    assert not result.truncated
    assert result.elapsed_ms >= 0


def test_caps_rows_and_flags_truncation(prepared_db: Path) -> None:
    result = _run("SELECT * FROM dim_people", prepared_db, max_rows=1)
    assert result.row_count == 1 and result.truncated


def test_allows_recursive_cte_and_functions(prepared_db: Path) -> None:
    sql = "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<3) SELECT x FROM n"
    assert _run(sql, prepared_db).rows == [[1], [2], [3]]
    assert _run("SELECT upper('a'), date('now') IS NOT NULL", prepared_db).rows == [["A", 1]]


def test_serializes_blobs(prepared_db: Path) -> None:
    assert _run("SELECT x'00FF'", prepared_db).rows == [["<blob de 2 bytes>"]]


# --------------------------------------------------------------------- camadas de segurança
def test_guardrail_rejects_before_touching_the_database(tmp_path: Path) -> None:
    with pytest.raises(GuardrailError):
        _run("DROP TABLE dim_people", tmp_path / "nem_existe.db")


@pytest.mark.parametrize(
    "sql",
    [
        # Começam com WITH/SELECT, passam pelo guardrail textual e são barrados pelo motor:
        "WITH x AS (SELECT 1) DELETE FROM dim_people",
        "WITH x AS (SELECT 1) UPDATE dim_people SET nome_pessoa = 'hack'",
        "WITH x AS (SELECT 1) INSERT INTO dim_genres VALUES ('g', 'Hack')",
        "SELECT load_extension('malicioso')",
    ],
)
def test_engine_blocks_writes_that_bypass_text_checks(prepared_db: Path, sql: str) -> None:
    before = _people(prepared_db)
    with pytest.raises(QueryError, match="não autorizada"):
        _run(sql, prepared_db)
    assert _people(prepared_db) == before


def test_authorizer_blocks_pragma_and_attach_at_engine_level(prepared_db: Path) -> None:
    with readonly_connection(prepared_db) as conn:
        for sql in ("PRAGMA journal_mode = WAL", "ATTACH DATABASE ':memory:' AS x"):
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                conn.execute(sql)


def test_connection_is_read_only_even_without_authorizer(prepared_db: Path) -> None:
    with readonly_connection(prepared_db) as conn:
        conn.set_authorizer(None)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM dim_people")


# ------------------------------------------------------------------------- erros e timeout
def test_timeout_interrupts_runaway_query(prepared_db: Path) -> None:
    start = time.perf_counter()
    with pytest.raises(QueryTimeoutError, match="excedeu"):
        _run(INFINITE_CTE, prepared_db, timeout_seconds=0.3)
    assert time.perf_counter() - start < 3


def test_sqlite_errors_are_reported_for_self_correction(prepared_db: Path) -> None:
    with pytest.raises(QueryError, match="no such column: coluna_inventada"):
        _run("SELECT coluna_inventada FROM dim_people", prepared_db)


def test_missing_database_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="não encontrado"):
        _run("SELECT 1", tmp_path / "ausente.db")


# --------------------------------------------------------------------------- banco real
@pytest.mark.db
def test_heaviest_assignment_query_fits_the_timeout(gold_conn) -> None:
    """A pergunta mais cara do enunciado (dupla ator-diretor) cabe no timeout padrão."""
    settings = get_settings()
    sql = """
        SELECT a.nome_pessoa, d.nome_pessoa, COUNT(*) AS filmes
        FROM bridge_movie_person ba
        JOIN dim_people a ON a.sk_person_id = ba.sk_person_id AND a.tipo_pessoa = 'Ator'
        JOIN bridge_movie_person bd ON bd.sk_movie_id = ba.sk_movie_id
        JOIN dim_people d ON d.sk_person_id = bd.sk_person_id AND d.tipo_pessoa = 'Diretor'
        GROUP BY a.sk_person_id, d.sk_person_id ORDER BY filmes DESC LIMIT 1"""
    result = run_query(
        sql,
        db_path=settings.db_path,
        max_rows=settings.max_rows,
        timeout_seconds=settings.query_timeout_seconds,
    )
    assert result.rows[0][2] == 37
    assert result.elapsed_ms < settings.query_timeout_seconds * 1000
