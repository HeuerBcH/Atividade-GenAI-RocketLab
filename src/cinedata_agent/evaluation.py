"""Comparação do resultado do agente com a SQL de referência (execution accuracy).

As colunas do agente são localizadas pelo CONTEÚDO, não pelo nome: o modelo pode chamar
"titulo" de "filme" ou "receita_brl" de "receita_total" sem que isso seja um erro. Números
são comparados com tolerância relativa e aceitam escala percentual (0,25 == 25%).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .agent import AgentDeps, AgentError, ask
from .config import Settings
from .db import run_query
from .golden import GoldenCase
from .models import AgentOutput

PERCENT_SCALES = (1.0, 100.0)


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[list[object]]

    def column(self, name: str) -> list[object]:
        index = self.columns.index(name)
        return [row[index] for row in self.rows]

    def column_at(self, index: int) -> list[object]:
        return [row[index] for row in self.rows]


@dataclass(frozen=True)
class Verdict:
    passed: bool
    detail: str


def _norm_text(value: object) -> str:
    return str(value).strip().casefold()


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _close(expected: object, actual: object, rel_tol: float) -> bool:
    exp, act = _as_float(expected), _as_float(actual)
    if exp is None or act is None:
        return _norm_text(expected) == _norm_text(actual)
    return any(
        math.isclose(exp * scale, act, rel_tol=rel_tol, abs_tol=1e-6) for scale in PERCENT_SCALES
    )


def _best_text_column(expected: list[object], table: Table) -> int | None:
    wanted = {_norm_text(v) for v in expected}
    scores = [
        (sum(_norm_text(v) in wanted for v in table.column_at(i)), i)
        for i in range(len(table.columns))
    ]
    best_score, best_index = max(scores, default=(0, None))
    return best_index if best_score else None


def _best_numeric_column(expected: list[object], table: Table, rel_tol: float) -> int | None:
    """Coluna com mais valores esperados, em qualquer posição (a ordem é checada depois)."""
    scores = []
    for i in range(len(table.columns)):
        actual = [a for a in table.column_at(i) if _as_float(a) is not None]
        hits = sum(any(_close(e, a, rel_tol) for a in actual) for e in expected)
        scores.append((hits, i))
    best_score, best_index = max(scores, default=(0, None))
    return best_index if best_score else None


def _keys(table: Table, indexes: list[int], limit: int | None) -> list[tuple[str, ...]]:
    rows = table.rows[:limit] if limit else table.rows
    return [tuple(_norm_text(row[i]) for i in indexes) for row in rows]


def compare(case: GoldenCase, reference: Table, actual: Table | None) -> Verdict:
    """Compara o resultado do agente (`actual`) com o da SQL de referência."""
    check = case.check
    if check.mode == "refusal":
        if actual is None or not actual.rows:
            return Verdict(True, "recusou sem executar consulta")
        return Verdict(False, "deveria recusar, mas executou uma consulta")
    if actual is None or not actual.rows:
        return Verdict(False, "nenhum resultado do agente")

    top = check.top_n
    if check.mode in {"ordered", "set", "mapping"}:
        indexes = [_best_text_column(reference.column(k), actual) for k in check.key]
        if None in indexes:
            return Verdict(False, f"coluna(s) {check.key} não encontrada(s) no resultado")
        ref_keys = _keys(reference, [reference.columns.index(k) for k in check.key], top)
        act_keys = _keys(actual, indexes, top)  # type: ignore[arg-type]

        if check.mode == "ordered":
            ok = act_keys == ref_keys
            return Verdict(ok, "ordem confere" if ok else f"esperado {ref_keys}, obtido {act_keys}")
        if check.mode == "set":
            missing, extra = set(ref_keys) - set(act_keys), set(act_keys) - set(ref_keys)
            ok = not missing and not extra
            return Verdict(ok, "conjunto confere" if ok else f"faltam {missing}; sobram {extra}")

        # mapping: chave -> métrica, para todas as linhas
        metric_idx = _best_numeric_column(reference.column(check.metric), actual, check.rel_tol)
        if metric_idx is None:
            return Verdict(False, f"métrica '{check.metric}' não encontrada no resultado")
        expected = dict(zip(ref_keys, reference.column(check.metric), strict=True))
        got = dict(zip(act_keys, actual.column_at(metric_idx), strict=True))
        wrong = [
            k for k, v in expected.items() if k not in got or not _close(v, got[k], check.rel_tol)
        ]
        ok = not wrong and len(got) == len(expected)
        return Verdict(ok, "mapeamento confere" if ok else f"divergem: {wrong[:5]}")

    expected_values = (
        reference.column(check.metric)[:top] if top else reference.column(check.metric)
    )
    metric_idx = _best_numeric_column(expected_values, actual, check.rel_tol)
    if metric_idx is None:
        return Verdict(False, f"métrica '{check.metric}' não encontrada no resultado")
    got_values = actual.column_at(metric_idx)

    if check.mode == "scalar":
        ok = _close(expected_values[0], got_values[0], check.rel_tol)
        return Verdict(ok, f"esperado {expected_values[0]}, obtido {got_values[0]}")

    # values: os top_n primeiros valores da métrica, na ordem (robusto a empates de chave)
    got_values = got_values[: len(expected_values)]
    ok = len(got_values) == len(expected_values) and all(
        _close(e, a, check.rel_tol) for e, a in zip(expected_values, got_values, strict=True)
    )
    return Verdict(
        ok, "valores conferem" if ok else f"esperado {expected_values}, obtido {got_values}"
    )


# ----------------------------------------------------------------- execução de um caso
class CaseResult(BaseModel):
    case_id: str
    category: str
    model: str
    reasoning: str
    passed: bool
    detail: str
    answer: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    sql: str | None = None
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    error: str | None = None


def reference_table(case: GoldenCase, settings: Settings) -> Table:
    if not case.sql:
        return Table([], [])
    result = run_query(
        case.sql,
        db_path=settings.db_path,
        max_rows=settings.max_rows,
        timeout_seconds=settings.query_timeout_seconds,
    )
    return Table(result.columns, result.rows)


async def run_case(
    agent: Agent[AgentDeps, AgentOutput], case: GoldenCase, settings: Settings, model_label: str
) -> CaseResult:
    """Executa um caso do golden set (incluindo o histórico, se houver) e o avalia."""
    base = {
        "case_id": case.id,
        "category": case.category,
        "model": model_label,
        "reasoning": settings.reasoning_effort,
    }
    history = None
    requests = input_tokens = output_tokens = 0
    latency = 0.0
    try:
        for previous in [*case.history, case.question]:
            response, history = await ask(
                agent,
                previous,
                deps=AgentDeps.from_settings(settings),
                max_requests=settings.max_requests_per_question,
                message_history=history,
            )
            requests += response.usage.requests
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            latency += response.latency_ms
    except AgentError as exc:
        return CaseResult(**base, passed=False, detail=exc.detail, error=str(exc))

    actual = Table(response.columns, response.rows) if response.sql else None
    verdict = compare(case, reference_table(case, settings), actual)
    return CaseResult(
        **base,
        passed=verdict.passed,
        detail=verdict.detail,
        answer=response.answer,
        assumptions=response.assumptions,
        sql=response.sql,
        requests=requests,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=round(latency, 1),
    )
