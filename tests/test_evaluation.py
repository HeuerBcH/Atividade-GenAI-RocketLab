from __future__ import annotations

from cinedata_agent.evaluation import CaseResult, Table, build_report, compare
from cinedata_agent.golden import GoldenCase, load_golden


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


def test_keys_are_found_by_content_not_by_column_name() -> None:
    reference = Table(["titulo", "receita"], [["Avatar", 100.0], ["Titanic", 90.0], ["Up", 80.0]])
    ordered = _case("ordered", key=["titulo"], metric="receita", top_n=2)
    agent = Table(["Filme", "R$"], [["avatar ", 100], ["Titanic (1997)", 90]])
    assert compare(ordered, reference, agent).passed
    assert not compare(ordered, reference, Table(["filme"], [["Titanic"], ["Avatar"]])).passed

    as_set = _case("set", key=["titulo"])
    assert compare(as_set, reference, Table(["t"], [["Up"], ["Avatar"], ["Titanic"]])).passed
    assert not compare(as_set, reference, Table(["t"], [["Up"], ["Avatar"]])).passed


def test_numbers_tolerate_rounding_percent_and_row_order() -> None:
    reference = Table(["titulo", "margem"], [["A", 0.9999], ["B", 0.5]])
    values = _case("values", metric="margem", top_n=2, rel_tol=0.01)
    assert compare(values, reference, Table(["filme", "%"], [["X", 99.99], ["Y", 50.0]])).passed
    assert not compare(values, reference, Table(["filme", "m"], [["X", 0.9], ["Y", 0.5]])).passed

    counts = Table(["genero", "filmes"], [["Drama", 10], ["Action", 5]])
    mapping = _case("mapping", key=["genero"], metric="filmes", rel_tol=0)
    assert compare(mapping, counts, Table(["g", "n"], [["Action", 5], ["Drama", 10]])).passed
    assert not compare(mapping, counts, Table(["g", "n"], [["Action", 5], ["Drama", 11]])).passed

    scalar = _case("scalar", metric="total")
    total = Table(["total"], [[17286781014.89]])
    assert compare(scalar, total, Table(["produtora", "receita"], [["Pixar", 1.7286e10]])).passed
    assert not compare(scalar, total, None).passed


def test_refusal_passes_only_without_a_query() -> None:
    refusal = _case("refusal")
    assert compare(refusal, Table([], []), None).passed
    assert not compare(refusal, Table([], []), Table(["x"], [[1]])).passed


def test_report_summarizes_accuracy_by_category() -> None:
    ok = CaseResult(
        case_id="BIL-01",
        category="bilheteria_financas",
        model="m",
        reasoning="none",
        passed=True,
        detail="ordem confere",
        answer="Avatar lidera.",
        sql="SELECT 1",
        requests=2,
        latency_ms=1500,
    )
    failed = CaseResult(
        case_id="EXT-06",
        category="robustez",
        model="m",
        reasoning="none",
        passed=False,
        detail="x",
        error="Os modelos estão indisponíveis.",
    )
    report = build_report([ok, failed], load_golden().cases, "01/10/2026 21:00")

    assert "| Acerto geral | 1/2 (50%) |" in report
    assert "| Perguntas do enunciado | 1/1 (100%) |" in report
    assert "| Bilheteria e Finanças | 1/1 (100%) |" in report
    assert "### EXT-06 — FALHA" in report
