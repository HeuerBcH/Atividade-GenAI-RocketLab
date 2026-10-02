"""Interface de linha de comando do agente.

Uso:
    python -m cinedata_agent "Quais são os 5 filmes mais populares?"
    python -m cinedata_agent "..." --trace      # mostra os passos do ReAct
    python -m cinedata_agent "..." --json       # resposta completa em JSON
    python -m cinedata_agent                    # modo conversa (com memória)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .agent import AgentError
from .config import get_settings
from .models import AskResponse
from .service import CineDataService

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
    if response.cached:
        print("\n[resposta do cache, sem chamada ao LLM]")
        return
    usage = response.usage
    print(
        f"\n[{response.model} | {usage.requests} chamada(s) ao LLM | "
        f"{usage.input_tokens}+{usage.output_tokens} tokens | {response.latency_ms / 1000:.1f} s]"
    )


def _print_error(exc: AgentError, show_trace: bool) -> None:
    print(f"[ERRO] {exc}", file=sys.stderr)
    if show_trace:
        print(f"Causa técnica: {exc.detail}", file=sys.stderr)
        for step in exc.steps:
            print(f"  [{step.kind}] {step.content}", file=sys.stderr)


async def _chat(svc: CineDataService, show_trace: bool) -> None:
    print("CineData Analyst - pergunte sobre o catálogo. /nova reinicia a conversa, /sair encerra.")
    while True:
        try:
            question = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if question in {"/sair", "sair", "exit"}:
            return
        if question == "/nova":
            svc.reset("cli")
            print("Conversa reiniciada.")
            continue
        if not question:
            continue
        try:
            _print(await svc.ask(question, "cli"), show_trace)
        except AgentError as exc:
            _print_error(exc, show_trace)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pergunte ao agente CineData.")
    parser.add_argument("question", nargs="?", help="pergunta; sem ela, abre o modo conversa")
    parser.add_argument("--trace", action="store_true", help="mostra os passos do ReAct")
    parser.add_argument("--json", action="store_true", help="imprime a resposta em JSON")
    args = parser.parse_args()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    try:
        svc = CineDataService(get_settings())
    except AgentError as exc:
        _print_error(exc, args.trace)
        return 1

    if not args.question:
        asyncio.run(_chat(svc, args.trace))
        return 0

    try:
        response = asyncio.run(svc.ask(args.question, "cli"))
    except AgentError as exc:
        _print_error(exc, args.trace)
        return 1
    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        _print(response, args.trace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
