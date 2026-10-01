from __future__ import annotations

import pytest

from cinedata_agent.evaluation import Table, compare
from cinedata_agent.golden import GoldenCase


def _case(mode: str, **check: object) -> GoldenCase:
    return GoldenCase.model_validate(
        {
            "id": "TST-01",
            "category": "robustez",
            "source": "extra",
            "question": "Pergunta de teste?",
            "sql": None if mode == "refusal" else "SELECT 1",
            "check": {"mode": mode, **check},
        }
    )


REF_TOP = Table(["titulo", "receita_brl"], [["Avatar", 100.0], ["Titanic", 90.0], ["Up", 80.0]])


def test_ordered_matches_by_content_regardless_of_column_names() -> None:
    case = _case("ordered", key=["titulo"], metric="receita_brl", top_n=2)
    agent = Table(["Filme", "Faturamento (R$)"], [["avatar ", 100.0], ["Titanic", 90.0]])
    assert compare(case, REF_TOP, agent).passed


def test_ordered_fails_on_wrong_order() -> None:
    case = _case("ordered", key=["titulo"], metric="receita_brl", top_n=2)
    agent = Table(["filme"], [["Titanic"], ["Avatar"]])
    assert not compare(case, REF_TOP, agent).passed


def test_set_ignores_order_but_not_membership() -> None:
    case = _case("set", key=["titulo"])
    assert compare(case, REF_TOP, Table(["t"], [["Up"], ["Avatar"], ["Titanic"]])).passed
    assert not compare(case, REF_TOP, Table(["t"], [["Up"], ["Avatar"]])).passed


def test_values_accepts_rounding_and_percent_scale() -> None:
    reference = Table(["titulo", "margem"], [["A", 0.9999], ["B", 0.5]])
    case = _case("values", metric="margem", top_n=2, rel_tol=0.01)
    assert compare(
        case, reference, Table(["filme", "margem_%"], [["X", 99.99], ["Y", 50.0]])
    ).passed
    assert not compare(case, reference, Table(["filme", "m"], [["X", 0.9], ["Y", 0.5]])).passed


def test_mapping_requires_every_key_with_its_value() -> None:
    reference = Table(["genero", "filmes"], [["Drama", 10], ["Action", 5]])
    case = _case("mapping", key=["genero"], metric="filmes", rel_tol=0)
    assert compare(case, reference, Table(["g", "n"], [["Action", 5], ["Drama", 10]])).passed
    assert not compare(case, reference, Table(["g", "n"], [["Action", 5], ["Drama", 11]])).passed
    assert not compare(case, reference, Table(["g", "n"], [["Drama", 10]])).passed


def test_scalar_finds_the_value_in_any_column() -> None:
    reference = Table(["total"], [[17286781014.89]])
    case = _case("scalar", metric="total")
    assert compare(case, reference, Table(["produtora", "receita"], [["Pixar", 1.7286e10]])).passed


@pytest.mark.parametrize(
    ("actual", "passed"),
    [(None, True), (Table(["x"], []), True), (Table(["x"], [[1]]), False)],
)
def test_refusal_passes_only_without_results(actual: Table | None, passed: bool) -> None:
    assert compare(_case("refusal"), Table([], []), actual).passed is passed


def test_missing_result_fails_with_reason() -> None:
    verdict = compare(_case("scalar", metric="total"), Table(["total"], [[1]]), None)
    assert not verdict.passed and "nenhum resultado" in verdict.detail
