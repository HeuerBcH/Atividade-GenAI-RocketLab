from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from cinedata_agent.config import get_settings
from cinedata_agent.db import (
    DatabaseUnavailable,
    QueryError,
    QueryTimeoutError,
    check_database,
    readonly_connection,
    run_query,
)


def _run(sql: str, db: Path, **kwargs):
    return run_query(sql, db_path=db, **({"max_rows": 100, "timeout_seconds": 5.0} | kwargs))


def test_returns_rows_and_caps_them(mini_gold_db: Path) -> None:
    result = _run("SELECT nome_pessoa, tipo_pessoa FROM dim_people ORDER BY 1", mini_gold_db)
    assert result.columns == ["nome_pessoa", "tipo_pessoa"]
    assert result.rows == [["Ator Um", "Ator"], ["Diretora Dois", "Diretor"]]

    capped = _run("SELECT * FROM dim_people", mini_gold_db, max_rows=1)
    assert capped.row_count == 1 and capped.truncated

    sql = "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<2) SELECT x FROM n"
    assert _run(sql, mini_gold_db).rows == [[1], [2]]


@pytest.mark.parametrize(
    "sql",
    [
        # começam com WITH/SELECT, passam pelo guardrail de texto e o próprio SQLite barra
        "WITH x AS (SELECT 1) DELETE FROM dim_people",
        "WITH x AS (SELECT 1) UPDATE dim_people SET nome_pessoa = 'hack'",
        "SELECT load_extension('malicioso')",
    ],
)
def test_engine_blocks_writes_that_pass_the_text_check(mini_gold_db: Path, sql: str) -> None:
    before = mini_gold_db.read_bytes()
    with pytest.raises(QueryError, match="não autorizada"):
        _run(sql, mini_gold_db)
    assert mini_gold_db.read_bytes() == before


def test_connection_is_read_only_even_without_the_authorizer(mini_gold_db: Path) -> None:
    with readonly_connection(mini_gold_db) as conn:
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            conn.execute("ATTACH DATABASE ':memory:' AS x")
        conn.set_authorizer(None)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM dim_people")


def test_timeout_and_sql_errors_go_back_to_the_llm(mini_gold_db: Path) -> None:
    infinite = (
        "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT MAX(x) FROM n"
    )
    start = time.perf_counter()
    with pytest.raises(QueryTimeoutError, match="excedeu"):
        _run(infinite, mini_gold_db, timeout_seconds=0.3)
    assert time.perf_counter() - start < 3

    with pytest.raises(QueryError, match="no such column: inventada"):
        _run("SELECT inventada FROM dim_people", mini_gold_db)


def test_database_check(mini_gold_db: Path, tmp_path: Path) -> None:
    check_database(mini_gold_db)

    with pytest.raises(DatabaseUnavailable, match="Baixe o cinerocket"):
        check_database(tmp_path / "ausente.db")

    wal = mini_gold_db.with_name(mini_gold_db.name + "-wal")
    wal.write_bytes(b"x" * 32)  # immutable=1 ignoraria essas transações
    with pytest.raises(DatabaseUnavailable, match="pendentes"):
        check_database(mini_gold_db)
    wal.unlink()

    conn = sqlite3.connect(mini_gold_db)
    conn.execute("DROP TABLE dim_reviews")
    conn.commit()
    conn.close()
    with pytest.raises(DatabaseUnavailable, match="dim_reviews"):
        check_database(mini_gold_db)


@pytest.mark.db
def test_heaviest_assignment_query_fits_the_timeout(gold_conn) -> None:
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
