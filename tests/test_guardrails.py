from __future__ import annotations

import pytest

from cinedata_agent.guardrails import GuardrailError, validate_sql


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1", "SELECT 1"),
        ("  select titulo from dim_movies ;  ", "select titulo from dim_movies"),
        ("WITH t AS (SELECT 1) SELECT * FROM t;", "WITH t AS (SELECT 1) SELECT * FROM t"),
        ("-- comentário inicial\nSELECT 1", "SELECT 1"),
        ("/* bloco */ SELECT 1", "SELECT 1"),
    ],
)
def test_accepts_single_read_statement(sql: str, expected: str) -> None:
    assert validate_sql(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dim_movies WHERE titulo = 'A;B'",  # ';' dentro de string
        "SELECT * FROM dim_movies WHERE titulo = 'It''s; fine'",  # aspas escapadas
        "SELECT * FROM dim_movies WHERE titulo = 'Drop Dead Fred'",  # palavra reservada em literal
        'SELECT "delete" FROM (SELECT 1 AS "delete")',  # palavra reservada como identificador
        "SELECT 1 -- comentário com ; e DROP TABLE",
        "SELECT 1 /* ; */",
    ],
)
def test_does_not_reject_legitimate_queries(sql: str) -> None:
    validate_sql(sql)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("", "vazia"),
        ("   ;  ", "vazia"),
        ("-- só comentário", "vazia"),
        ("SELECT 1; SELECT 2", "2 comandos"),
        ("SELECT 1; DROP TABLE dim_movies", "2 comandos"),
        ("DROP TABLE dim_movies", "'DROP'"),
        ("DELETE FROM dim_movies", "'DELETE'"),
        ("UPDATE dim_movies SET titulo = 'x'", "'UPDATE'"),
        ("INSERT INTO dim_genres VALUES ('x', 'y')", "'INSERT'"),
        ("PRAGMA table_info(dim_movies)", "'PRAGMA'"),
        ("ATTACH DATABASE 'x.db' AS x", "'ATTACH'"),
        ("/* disfarce */ DELETE FROM dim_movies", "'DELETE'"),
        ("SELECT 1;\nDELETE FROM dim_movies -- ", "2 comandos"),
    ],
)
def test_rejects_with_actionable_message(sql: str, message: str) -> None:
    with pytest.raises(GuardrailError, match=message):
        validate_sql(sql)
