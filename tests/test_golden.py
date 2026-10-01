"""Valida o golden set: estrutura (sempre) e SQLs de referência no banco real (marcador db)."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter

import pytest
from pydantic import ValidationError

from cinedata_agent import semantic_layer
from cinedata_agent.config import get_settings
from cinedata_agent.db import run_query
from cinedata_agent.evaluation import Table, compare
from cinedata_agent.golden import GoldenCase, GoldenSet, load_golden

GOLDEN = load_golden()
SQL_CASES = [case for case in GOLDEN.cases if case.sql]
HASH = re.compile(r"^[0-9a-f]{64}$")
TRAILING_LIMIT = re.compile(r"\s+LIMIT\s+\d+\s*$", re.IGNORECASE)


# ------------------------------------------------------------------- estrutura do arquivo
def test_covers_every_example_question_of_the_assignment() -> None:
    from_assignment = Counter(c.category for c in GOLDEN.cases if c.source == "enunciado")
    assert from_assignment == {
        "bilheteria_financas": 3,
        "popularidade_engajamento": 3,
        "elenco_equipe": 3,
        "generos_produtoras": 3,
        "avaliacoes_usuarios": 2,
    }


def test_includes_robustness_cases() -> None:
    modes = Counter(c.check.mode for c in GOLDEN.cases if c.category == "robustez")
    assert modes["refusal"] >= 3
    assert any(c.history for c in GOLDEN.cases), "falta caso de follow-up (memória)"


def _case(**overrides) -> dict:
    base = {
        "id": "TST-01",
        "category": "robustez",
        "source": "extra",
        "question": "Pergunta de teste?",
        "sql": "SELECT 1 AS x",
        "check": {"mode": "scalar", "metric": "x"},
    }
    return base | overrides


@pytest.mark.parametrize(
    "overrides",
    [
        {"check": {"mode": "refusal"}},  # recusa com SQL
        {"sql": None},  # caso comum sem SQL
        {"check": {"mode": "ordered", "metric": "x"}},  # ordered sem key
        {"check": {"mode": "values", "key": ["x"]}},  # values sem metric
        {"id": "invalido"},
    ],
)
def test_rejects_malformed_cases(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(_case(**overrides))


def test_rejects_duplicated_ids() -> None:
    with pytest.raises(ValidationError, match="duplicados"):
        GoldenSet.model_validate({"version": 1, "cases": [_case(), _case()]})


# ------------------------------------------------------------ SQLs de referência (banco real)
def _run(conn: sqlite3.Connection, sql: str) -> tuple[list[str], list[tuple]]:
    cursor = conn.execute(sql)
    return [d[0] for d in cursor.description], cursor.fetchall()


@pytest.mark.db
@pytest.mark.parametrize("case", SQL_CASES, ids=lambda c: c.id)
def test_reference_sql_is_valid_and_user_friendly(
    case: GoldenCase, gold_conn: sqlite3.Connection
) -> None:
    columns, rows = _run(gold_conn, case.sql)
    check = case.check

    assert rows, "a SQL de referência não retornou linhas"
    for name in [*check.key, *filter(None, [check.metric])]:
        assert name in columns, f"coluna '{name}' ausente no resultado {columns}"
    assert not [c for c in columns if c.startswith("sk_")], "resultado expõe chaves sk_*"
    assert not [v for r in rows for v in r if isinstance(v, str) and HASH.match(v)]

    if check.mode == "scalar":
        assert len(rows) == 1 and rows[0][columns.index(check.metric)] is not None
    if check.mode in {"ordered", "values"}:
        assert len(rows) >= check.top_n


@pytest.mark.db
@pytest.mark.parametrize(
    "case", [c for c in SQL_CASES if c.check.mode == "ordered"], ids=lambda c: c.id
)
def test_ordered_cases_have_no_tie_at_the_cutoff(
    case: GoldenCase, gold_conn: sqlite3.Connection
) -> None:
    """Um empate na posição top_n tornaria a ordem "correta" arbitrária."""
    n = case.check.top_n
    extended = TRAILING_LIMIT.sub("", case.sql.strip()) + f"\nLIMIT {n + 1}"
    columns, rows = _run(gold_conn, extended)
    if len(rows) > n:
        metric = columns.index(case.check.metric)
        assert rows[n - 1][metric] != rows[n][metric], f"empate na posição {n}"


def test_reference_sql_uses_the_documented_thresholds() -> None:
    """As SQLs de referência não podem divergir das constantes da camada semântica."""
    expected = {
        "qtd_imdb": semantic_layer.MIN_RATING_VOTES,
        "qtd_tmdb": semantic_layer.MIN_RATING_VOTES,
        "qtd_avaliacoes_usuarios": semantic_layer.MIN_USER_REVIEWS,
    }
    for case in SQL_CASES:
        for column, value in re.findall(r"(\w+)\s*>=\s*(\d+)", case.sql):
            if column in expected:
                assert int(value) == expected[column], f"{case.id}: {column} >= {value}"


@pytest.mark.db
@pytest.mark.parametrize("case", SQL_CASES, ids=lambda c: c.id)
def test_reference_sql_passes_the_production_guardrails(case: GoldenCase, gold_conn) -> None:
    """O caminho do agente (guardrail + authorizer + timeout) aceita todas as SQLs corretas."""
    settings = get_settings()
    result = run_query(
        case.sql,
        db_path=settings.db_path,
        max_rows=settings.max_rows,
        timeout_seconds=settings.query_timeout_seconds,
    )
    assert result.row_count > 0 and not result.truncated


@pytest.mark.db
@pytest.mark.parametrize("case", SQL_CASES, ids=lambda c: c.id)
def test_comparator_accepts_the_reference_itself(case: GoldenCase, gold_conn) -> None:
    columns, rows = _run(gold_conn, case.sql)
    reference = Table(columns, [list(r) for r in rows])
    verdict = compare(case, reference, reference)
    assert verdict.passed, verdict.detail
