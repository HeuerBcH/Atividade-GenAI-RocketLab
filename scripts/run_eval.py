"""Roda o golden set contra o agente e gera eval/report.md.

Consome cota real do provedor. O progresso é salvo a cada caso; se a cota diária acabar,
o script para e basta rodar de novo com --resume depois.

Uso:
    python scripts/run_eval.py                      # todos os casos
    python scripts/run_eval.py --source enunciado   # só as 14 perguntas do enunciado
    python scripts/run_eval.py --ids BIL-01,ELE-03
    python scripts/run_eval.py --resume             # pula os casos que já passaram
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

from cinedata_agent.agent import build_agent, build_model
from cinedata_agent.config import PROJECT_ROOT, get_settings
from cinedata_agent.evaluation import CaseResult, build_report, run_case
from cinedata_agent.golden import load_golden

RESULTS = PROJECT_ROOT / "eval" / "results" / "latest.json"
REPORT = PROJECT_ROOT / "eval" / "report.md"
DAILY_LIMIT_HINTS = ("tokens per day", "requests per day", "TPD", "RPD")


def _load_previous() -> dict[str, CaseResult]:
    if not RESULTS.is_file():
        return {}
    return {r["case_id"]: CaseResult(**r) for r in json.loads(RESULTS.read_text(encoding="utf-8"))}


def _save(results: dict[str, CaseResult]) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    payload = [r.model_dump() for r in results.values()]
    RESULTS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ids", help="ids separados por vírgula")
    parser.add_argument("--source", choices=["enunciado", "extra"])
    parser.add_argument("--resume", action="store_true", help="pula casos que já passaram")
    parser.add_argument("--pause", type=float, default=20, help="segundos entre perguntas")
    args = parser.parse_args()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    settings = get_settings()
    cases = load_golden().cases
    selected = [
        c
        for c in cases
        if (not args.ids or c.id in args.ids.split(","))
        and (not args.source or c.source == args.source)
    ]
    results = _load_previous()  # rodar só alguns casos não apaga o resultado dos outros
    agent = build_agent(build_model(settings))
    label = ",".join(settings.model_chain)

    stopped = False
    for i, case in enumerate(selected):
        if args.resume and case.id in results and results[case.id].passed:
            continue
        if i and args.pause:
            await asyncio.sleep(args.pause)  # respeita o limite de tokens por minuto
        result = await run_case(agent, case, settings, label)
        results[case.id] = result
        _save(results)
        status = "OK   " if result.passed else "FALHA"
        print(f"[{status}] {case.id} | {result.requests} req | {result.error or result.detail}")
        if result.error and any(h in (result.detail or "") for h in DAILY_LIMIT_HINTS):
            print("\nCota diária do provedor esgotada. Rode de novo com --resume mais tarde.")
            stopped = True
            break

    ordered = [results[c.id] for c in cases if c.id in results]
    REPORT.write_text(
        build_report(ordered, cases, datetime.now().strftime("%d/%m/%Y %H:%M")), encoding="utf-8"
    )
    passed = sum(r.passed for r in ordered)
    print(
        f"\n{passed}/{len(ordered)} casos corretos. Relatório: {REPORT.relative_to(PROJECT_ROOT)}"
    )
    return 1 if stopped else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
