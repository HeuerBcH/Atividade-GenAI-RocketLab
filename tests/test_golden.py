from __future__ import annotations

import re
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


def test_covers_the_assignment_questions_and_robustness_cases() -> None:
    from_assignment = Counter(c.category for c in GOLDEN.cases if c.source == "enunciado")
    assert from_assignment == {
        "bilheteria_financas": 3,
        "popularidade_engajamento": 3,
        "elenco_equipe": 3,
        "generos_produtoras": 3,
        "avaliacoes_usuarios": 2,
    }
    assert sum(c.check.mode == "refusal" for c in GOLDEN.cases) >= 3
    assert any(c.history for c in GOLDEN.cases)


def test_rejects_malformed_cases() -> None:
    base = {
        "id": "TST-01",
        "category": "robustez",
        "source": "extra",
        "question": "Pergunta de teste?",
        "sql": "SELECT 1 AS x",
        "check": {"mode": "scalar", "metric": "x"},
    }
    broken = [
        {"check": {"mode": "refusal"}},  # recusa com SQL
        {"sql": None},
        {"check": {"mode": "ordered", "metric": "x"}},  # sem key
        {"check": {"mode": "values", "key": ["x"]}},  # sem metric
        {"id": "invalido"},
    ]
    for overrides in broken:
        with pytest.raises(ValidationError):
            GoldenCase.model_validate(base | overrides)
    with pytest.raises(ValidationError, match="duplicados"):
        GoldenSet.model_validate({"version": 1, "cases": [base, base]})


def test_reference_sql_uses_the_documented_thresholds() -> None:
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
def test_reference_sqls_on_the_real_database(gold_conn) -> None:
    settings = get_settings()
    for case in SQL_CASES:
        check = case.check
        # pelo mesmo caminho do agente (guardrail, authorizer, timeout)
        result = run_query(
            case.sql,
            db_path=settings.db_path,
            max_rows=settings.max_rows,
            timeout_seconds=settings.query_timeout_seconds,
        )
        columns, rows = result.columns, result.rows
        assert rows and not result.truncated, case.id
        for name in [*check.key, *filter(None, [check.metric])]:
            assert name in columns, f"{case.id}: coluna {name} ausente"
        assert not any(c.startswith("sk_") for c in columns), case.id
        assert not any(isinstance(v, str) and HASH.match(v) for r in rows for v in r), case.id
        if check.mode == "scalar":
            assert len(rows) == 1, case.id
        if check.mode in {"ordered", "values"}:
            assert len(rows) >= check.top_n, case.id

        if check.mode == "ordered":
            # empate na posição de corte deixaria a ordem "certa" arbitrária
            n = check.top_n
            extended = TRAILING_LIMIT.sub("", case.sql.strip()) + f"\nLIMIT {n + 1}"
            more = gold_conn.execute(extended).fetchall()
            metric = columns.index(check.metric)
            assert len(more) <= n or more[n - 1][metric] != more[n][metric], case.id

        reference = Table(columns, rows)
        assert compare(case, reference, reference).passed, case.id
