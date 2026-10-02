"""Compara o resultado do agente com o da SQL de referência (execution accuracy)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .agent import AgentDeps, AgentError, ask
from .config import Settings
from .db import run_query
from .golden import GoldenCase
from .models import AgentOutput, AskResponse
from .synopsis import IndexUnavailable, get_index

PERCENT_SCALES = (1.0, 100.0)
SEMANTIC_POOL = 100  # filmes mais parecidos com o tema de referência
SEMANTIC_MIN_SHARE = 0.5  # fração mínima dos filmes do agente que precisa estar nesse grupo


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


_YEAR_SUFFIX = re.compile(r"\s*\(\d{4}\)$")


def _norm_text(value: object) -> str:
    # o agente às vezes junta o ano ao título: "Blue Beetle (2023)"
    return _YEAR_SUFFIX.sub("", str(value).strip()).casefold()


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


def _best_numeric_column(
    expected: list[object], table: Table, rel_tol: float, name: str | None = None
) -> int | None:
    # coluna com o mesmo nome da métrica tem prioridade: várias colunas numéricas (nota_tmdb,
    # nota_imdb, divergencia) podem coincidir em alguns valores e confundir a escolha
    if name in table.columns:
        return table.columns.index(name)
    # sem esse nome, procura em qualquer posição; a ordem é conferida depois
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

        metric_idx = _best_numeric_column(
            reference.column(check.metric), actual, check.rel_tol, check.metric
        )
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
    metric_idx = _best_numeric_column(expected_values, actual, check.rel_tol, check.metric)
    if metric_idx is None:
        return Verdict(False, f"métrica '{check.metric}' não encontrada no resultado")
    got_values = actual.column_at(metric_idx)

    if check.mode == "scalar":
        ok = _close(expected_values[0], got_values[0], check.rel_tol)
        return Verdict(ok, f"esperado {expected_values[0]}, obtido {got_values[0]}")

    # values: compara só os valores da métrica, assim empates de título não importam
    got_values = got_values[: len(expected_values)]
    ok = len(got_values) == len(expected_values) and all(
        _close(e, a, check.rel_tol) for e, a in zip(expected_values, got_values, strict=True)
    )
    return Verdict(
        ok, "valores conferem" if ok else f"esperado {expected_values}, obtido {got_values}"
    )


def compare_semantic(
    case: GoldenCase, reference_titles: set[str], response: AskResponse
) -> Verdict:
    """Agente híbrido: o tema não tem SQL exata, então confere o caminho e a pertinência."""
    used = any(
        s.kind == "acao" and s.content.startswith("buscar_por_sinopse(") for s in response.steps
    )
    if not used:
        return Verdict(False, "não usou a busca por sinopse")
    actual = Table(response.columns, response.rows)
    column = _best_text_column(list(reference_titles), actual)
    if column is None:
        return Verdict(False, f"nenhum filme do tema '{case.check.query}' no resultado")
    titles = [_norm_text(v) for v in actual.column_at(column)]
    hits = sum(t in reference_titles for t in titles)
    ok = hits / len(titles) >= SEMANTIC_MIN_SHARE
    return Verdict(ok, f"{hits}/{len(titles)} filmes do tema '{case.check.query}'")


def semantic_reference(case: GoldenCase, settings: Settings) -> set[str]:
    index = get_index(settings.synopsis_index_path, settings.embedding_cache_dir)
    ids = [m.id_filme for m in index.search(case.check.query or "", SEMANTIC_POOL)]
    result = run_query(
        f"SELECT titulo FROM dim_movies WHERE id_filme IN ({', '.join('?' * len(ids))})",
        db_path=settings.db_path,
        max_rows=len(ids),
        timeout_seconds=settings.query_timeout_seconds,
        params=ids,
    )
    return {_norm_text(row[0]) for row in result.rows}


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
    evaluated_at: str | None = None
    # hash da pergunta + gabarito: se o golden.yaml mudar, o resultado deixa de valer
    case_fingerprint: str | None = None


def fingerprint(case: GoldenCase) -> str:
    content = case.model_dump(include={"question", "history", "sql", "check"})
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:12]


def is_current(result: CaseResult, case: GoldenCase) -> bool:
    return result.case_fingerprint == fingerprint(case)


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
    agent: Agent[AgentDeps, AgentOutput | str],
    case: GoldenCase,
    settings: Settings,
    model_label: str,
) -> CaseResult:
    base = {
        "case_id": case.id,
        "category": case.category,
        "model": model_label,
        "reasoning": settings.reasoning_effort,
        "evaluated_at": datetime.now().isoformat(timespec="minutes"),
        "case_fingerprint": fingerprint(case),
    }
    history: list = []
    requests = input_tokens = output_tokens = 0
    latency = 0.0
    try:
        for previous in [*case.history, case.question]:
            response, new_messages = await ask(
                agent,
                previous,
                deps=AgentDeps.from_settings(settings),
                max_requests=settings.max_requests_per_question,
                message_history=history or None,
                timeout_seconds=settings.question_timeout_seconds,
            )
            history += new_messages
            requests += response.usage.requests
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            latency += response.latency_ms
    except AgentError as exc:
        return CaseResult(**base, passed=False, detail=exc.detail, error=str(exc))

    if case.check.mode == "semantic":
        try:
            verdict = compare_semantic(case, semantic_reference(case, settings), response)
        except IndexUnavailable as exc:
            verdict = Verdict(False, str(exc))
    else:
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


CATEGORY_LABELS = {
    "bilheteria_financas": "Bilheteria e Finanças",
    "popularidade_engajamento": "Popularidade e Engajamento",
    "elenco_equipe": "Elenco e Equipe",
    "generos_produtoras": "Gêneros e Produtoras",
    "avaliacoes_usuarios": "Avaliações dos Usuários",
    "robustez": "Robustez (extras)",
    "busca_semantica": "Busca por tema (sinopses)",
}


def _pct(hits: int, total: int) -> str:
    return f"{hits}/{total} ({100 * hits / total:.0f}%)" if total else "-"


def build_report(results: list[CaseResult], cases: list[GoldenCase], generated_at: str) -> str:
    by_id = {c.id: c for c in cases}
    known = [r for r in results if r.case_id in by_id]
    done = [r for r in known if is_current(r, by_id[r.case_id])]
    stale = [r for r in known if not is_current(r, by_id[r.case_id])]
    hits = sum(r.passed for r in done)
    from_assignment = [r for r in done if by_id[r.case_id].source == "enunciado"]
    answered = [r for r in done if not r.error]
    assignment_hits = sum(r.passed for r in from_assignment)

    lines = [
        "# Relatório de avaliação",
        "",
        f"Gerado em {generated_at}. Critério: o resultado da SQL do agente precisa bater com o "
        "da SQL de referência (`eval/golden.yaml`); recusas não podem executar consulta.",
        "",
        "## Resumo",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Acerto geral | {_pct(hits, len(done))} |",
        f"| Perguntas do enunciado | {_pct(assignment_hits, len(from_assignment))} |",
        f"| Casos avaliados / total | {len(done)}/{len(cases)} |",
    ]
    if dates := sorted(r.evaluated_at[:10] for r in done if r.evaluated_at):
        lines.append(f"| Período das execuções | {dates[0]} a {dates[-1]} |")
    if answered:
        n = len(answered)
        requests = sum(r.requests for r in answered) / n
        tokens = sum(r.input_tokens + r.output_tokens for r in answered) / n
        seconds = sum(r.latency_ms for r in answered) / n / 1000
        lines += [
            f"| Chamadas ao LLM por pergunta (média) | {requests:.1f} |",
            f"| Tokens por pergunta (média) | {tokens:,.0f} |",
            f"| Latência por pergunta (média) | {seconds:.1f} s |",
        ]
    models = sorted({r.model for r in answered})
    if models:
        lines.append(f"| Modelo(s) | {', '.join(models)} |")

    lines += ["", "## Por categoria", "", "| Categoria | Acertos |", "|---|---|"]
    for key, label in CATEGORY_LABELS.items():
        group = [r for r in done if by_id[r.case_id].category == key]
        if group:
            lines.append(f"| {label} | {_pct(sum(r.passed for r in group), len(group))} |")

    pending = [c.id for c in cases if c.id not in {r.case_id for r in done}]
    if pending:
        lines += [
            "",
            "## Pendentes",
            "",
            "Sem resultado válido para a versão atual do gabarito"
            + (
                " (gabarito alterado depois da execução: "
                + ", ".join(r.case_id for r in stale)
                + ")"
                if stale
                else ""
            )
            + f": {', '.join(pending)}. Rode `python scripts/run_eval.py --resume`.",
        ]

    lines += ["", "## Casos", ""]
    for r in done:
        case = by_id[r.case_id]
        status = "OK" if r.passed else "FALHA"
        lines += [f"### {r.case_id} — {status}", "", f"**Pergunta:** {case.question}", ""]
        if case.history:
            lines += [f"**Histórico:** {' → '.join(case.history)}", ""]
        lines.append(f"- Verificação: {r.error or r.detail}")
        if r.evaluated_at:
            lines.append(f"- Avaliado em: {r.evaluated_at.replace('T', ' ')}")
        if r.answer:
            lines.append(f"- Resposta: {r.answer}")
        if r.assumptions:
            lines.append(f"- Premissas: {'; '.join(r.assumptions)}")
        if not r.error:
            lines.append(
                f"- Custo: {r.requests} chamada(s), {r.input_tokens + r.output_tokens:,} tokens, "
                f"{r.latency_ms / 1000:.1f} s"
            )
        if r.sql:
            lines += ["", "```sql", r.sql, "```"]
        lines.append("")
    return "\n".join(lines)
