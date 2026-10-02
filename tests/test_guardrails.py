from __future__ import annotations

import pytest

from cinedata_agent.guardrails import GuardrailError, validate_sql


def test_accepts_a_single_read_statement() -> None:
    assert validate_sql("  select titulo from dim_movies ;  ") == "select titulo from dim_movies"
    assert (
        validate_sql("WITH t AS (SELECT 1) SELECT * FROM t;")
        == "WITH t AS (SELECT 1) SELECT * FROM t"
    )
    assert validate_sql("-- comentário\n/* bloco */ SELECT 1") == "SELECT 1"


def test_does_not_reject_legitimate_queries() -> None:
    # um filtro de palavras proibidas por regex barraria todas estas
    for sql in [
        "SELECT * FROM dim_movies WHERE titulo = 'A;B'",
        "SELECT * FROM dim_movies WHERE titulo = 'It''s; fine'",
        "SELECT * FROM dim_movies WHERE titulo = 'Drop Dead Fred'",
        'SELECT "delete" FROM (SELECT 1 AS "delete")',
        "SELECT 1 -- comentário com ; e DROP TABLE",
    ]:
        validate_sql(sql)


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("   ;  -- só comentário", "vazia"),
        ("SELECT 1;\nDELETE FROM dim_movies -- ", "2 comandos"),
        ("/* disfarce */ DELETE FROM dim_movies", "'DELETE'"),
        ("UPDATE dim_movies SET titulo = 'x'", "'UPDATE'"),
        ("PRAGMA table_info(dim_movies)", "'PRAGMA'"),
        ("ATTACH DATABASE 'x.db' AS x", "'ATTACH'"),
    ],
)
def test_rejects_with_a_message_the_llm_can_act_on(sql: str, message: str) -> None:
    with pytest.raises(GuardrailError, match=message):
        validate_sql(sql)
