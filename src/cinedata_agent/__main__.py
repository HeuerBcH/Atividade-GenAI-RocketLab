"""Interface de linha de comando do agente.

Uso:
    python -m cinedata_agent "Quais são os 5 filmes mais populares?"
    python -m cinedata_agent "..." --trace      # mostra os passos do ReAct
    python -m cinedata_agent "..." --json       # resposta completa em JSON
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .agent import AgentDeps, AgentError, ask, build_agent, build_model
from .config import get_settings
from .models import AskResponse

MAX_TABLE_ROWS = 10
MAX_COL_WIDTH = 40


def _table(columns: list[str], rows: list[list[object]]) -> str:
    def cell(value: object) -> str:
        text = "" if value is None else str(value)
        return text if len(text) <= MAX_COL_WIDTH else text[: MAX_COL_WIDTH - 3] + "..."

    shown = [[cell(v) for v in row] for row in rows[:MAX_TABLE_ROWS]]
    widths = [max([len(c), *(len(r[i]) for r in shown)]) for i, c in enumerate(columns)]

    def line(values: list[str]) -> str:
        return " | ".join(v.ljust(w) for v, w in zip(values, widths, strict=True))

    out = [line(columns), "-+-".join("-" * w for w in widths), *(line(r) for r in shown)]
    if len(rows) > MAX_TABLE_ROWS:
        out.append(f"... (+{len(rows) - MAX_TABLE_ROWS} linhas)")
    return "\n".join(out)


def _print(response: AskResponse, show_trace: bool) -> None:
    print(f"\n{response.answer}\n")
    if response.assumptions:
        print("Premissas:")
        print("\n".join(f"  - {a}" for a in response.assumptions))
    if response.columns:
        print(f"\n{_table(response.columns, response.rows)}")
    if response.sql:
        print(f"\nSQL executada:\n{response.sql}")
    if show_trace:
        print("\nPassos (ReAct):")
        for step in response.steps:
            print(f"  [{step.kind}] {step.content}")
    usage = response.usage
    print(
        f"\n[{response.model} | {usage.requests} chamada(s) ao LLM | "
        f"{usage.input_tokens}+{usage.output_tokens} tokens | {response.latency_ms / 1000:.1f} s]"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Pergunte ao agente CineData.")
    parser.add_argument("question", help="pergunta em linguagem natural")
    parser.add_argument("--trace", action="store_true", help="mostra os passos do ReAct")
    parser.add_argument("--json", action="store_true", help="imprime a resposta em JSON")
    args = parser.parse_args()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    settings = get_settings()
    try:
        agent = build_agent(build_model(settings))
        response, _ = asyncio.run(
            ask(
                agent,
                args.question,
                deps=AgentDeps.from_settings(settings),
                max_requests=settings.max_requests_per_question,
            )
        )
    except AgentError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        if args.trace:
            print(f"Causa técnica: {exc.detail}", file=sys.stderr)
            for step in exc.steps:
                print(f"  [{step.kind}] {step.content}", file=sys.stderr)
        return 1

    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        _print(response, args.trace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
