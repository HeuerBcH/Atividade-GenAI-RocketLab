"""Lista os modelos disponíveis no provedor configurado (LLM_PROVIDER). Não consome cota.

Uso:
    python scripts/list_models.py
"""

from __future__ import annotations

import sys

from cinedata_agent.config import get_settings
from cinedata_agent.quota import GROQ_LIMITS_URL, QuotaError, list_models


def main() -> int:
    settings = get_settings()
    try:
        models = list_models(settings)
    except QuotaError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1

    print(f"Provedor: {settings.llm_provider} | {len(models)} modelos disponíveis\n")
    for model in models:
        tools = {True: "tools", False: "sem tools", None: ""}[model.supports_tools]
        context = f"{model.context_window:>9,} tokens" if model.context_window else ""
        chosen = "  <- em uso" if model.id in settings.model_chain else ""
        print(f"  {model.id:<55} {context:<16} {tools}{chosen}")
    if settings.llm_provider == "groq":
        print(f"\nLimites do plano gratuito por modelo: {GROQ_LIMITS_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
