"""Mostra quantas requisições gratuitas do OpenRouter ainda restam hoje.

Não consome cota. Rode antes de cada bateria de testes/avaliação:
    python scripts/check_quota.py
"""

from __future__ import annotations

import sys

from cinedata_agent.config import get_settings
from cinedata_agent.quota import QuotaError, fetch_quota


def main() -> int:
    try:
        status = fetch_quota(get_settings())
    except QuotaError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1

    if status.remaining is None:
        print("[AVISO] A resposta não trouxe `free_model_daily_requests`; confira em")
        print("        https://openrouter.ai/activity")
    else:
        print(
            f"Requisições gratuitas hoje: {status.used}/{status.limit} usadas, "
            f"{status.remaining} restantes."
        )
    reset_local = status.resets_at.astimezone()
    print(f"Próximo reset: {reset_local:%d/%m %H:%M} (horário local).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
