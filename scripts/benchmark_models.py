"""Compara modelos (e níveis de raciocínio) em casos do golden set, respeitando a cota.

Cada modelo roda ISOLADO (sem fallback), para que o resultado seja atribuível a ele.
Consome cota real: confira antes com `python scripts/check_quota.py`.

Uso:
    python scripts/benchmark_models.py
    python scripts/benchmark_models.py --models "a:free,b:free" --cases BIL-01,ELE-03
    python scripts/benchmark_models.py --reasoning low
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
from cinedata_agent.evaluation import CaseResult, run_case
from cinedata_agent.golden import load_golden
from cinedata_agent.quota import QuotaError, fetch_quota

DEFAULT_CASES = "BIL-01,ELE-03,EXT-02"  # fácil, join pesado, resolução de entidade
WORST_CASE_REQUESTS = 5  # teto por pergunta (max_requests_per_question)


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _summary(results: list[CaseResult]) -> str:
    groups: dict[tuple[str, str], list[CaseResult]] = {}
    for r in results:
        groups.setdefault((r.model, r.reasoning), []).append(r)
    lines = [
        f"{'modelo':<45} {'raciocínio':<10} {'acertos':>8} {'req/perg':>9} {'s/perg':>7}",
        "-" * 83,
    ]
    for (model, reasoning), rs in groups.items():
        hits = sum(r.passed for r in rs)
        req = sum(r.requests for r in rs) / len(rs)
        sec = sum(r.latency_ms for r in rs) / len(rs) / 1000
        lines.append(f"{model:<45} {reasoning:<10} {hits:>4}/{len(rs):<3} {req:>9.1f} {sec:>7.1f}")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    settings = get_settings()
    parser.add_argument("--models", default=",".join(settings.model_chain))
    parser.add_argument("--cases", default=DEFAULT_CASES)
    parser.add_argument("--reasoning", default=settings.reasoning_effort)
    parser.add_argument("--reserve", type=int, default=5, help="cota mínima a preservar")
    parser.add_argument("--pause", type=float, default=0, help="segundos entre perguntas")
    args = parser.parse_args()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    golden = {case.id: case for case in load_golden().cases}
    cases = [golden[case_id] for case_id in _split(args.cases)]
    results: list[CaseResult] = []
    out = PROJECT_ROOT / "eval" / "results" / f"benchmark-{datetime.now():%Y%m%d-%H%M%S}.json"

    for model_name in _split(args.models):
        run_settings = settings.model_copy(
            update={"model_name": [model_name], "reasoning_effort": args.reasoning}
        )
        agent = build_agent(build_model(run_settings))
        for case in cases:
            remaining = None
            if settings.llm_provider == "openrouter":
                try:
                    remaining = fetch_quota(settings).remaining
                except QuotaError as exc:
                    print(f"[AVISO] não foi possível checar a cota: {exc}")
            if remaining is not None and remaining - WORST_CASE_REQUESTS < args.reserve:
                print(f"[PARADA] cota restante ({remaining}) abaixo da reserva ({args.reserve}).")
                break
            if results and args.pause:
                await asyncio.sleep(args.pause)  # limite de tokens/minuto do Groq
            result = await run_case(agent, case, run_settings, model_name)
            results.append(result)
            status = "OK  " if result.passed else "FALHA"
            print(
                f"[{status}] {model_name} | {case.id} | {result.requests} req | "
                f"{result.latency_ms / 1000:.1f}s | {result.error or result.detail}"
            )
            out.write_text(
                json.dumps([r.model_dump() for r in results], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            continue
        break

    print(f"\n{_summary(results)}\n\nResultados completos: {out.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
