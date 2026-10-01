"""Gera docs/dicionario_dados.md a partir da camada semântica (fonte única de verdade).

Uso:
    python scripts/gen_data_dictionary.py
"""

from __future__ import annotations

from cinedata_agent.config import PROJECT_ROOT
from cinedata_agent.semantic_layer import render_data_dictionary

OUTPUT = PROJECT_ROOT / "docs" / "dicionario_dados.md"


def main() -> None:
    OUTPUT.write_text(render_data_dictionary(), encoding="utf-8", newline="\n")
    print(f"[OK] {OUTPUT.relative_to(PROJECT_ROOT)} atualizado.")


if __name__ == "__main__":
    main()
