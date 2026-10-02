"""Gera o índice de embeddings das sinopses usado pela busca semântica do agente.

Roda uma única vez (alguns minutos na CPU). Lê o banco somente leitura e salva o índice em
data/, sem alterar o cinerocket.db. Na primeira execução baixa o modelo (~65 MB).

Uso:
    python scripts/build_synopsis_index.py
"""

from __future__ import annotations

import sys
import time

from cinedata_agent.config import PROJECT_ROOT, get_settings
from cinedata_agent.db import DatabaseUnavailable, check_database
from cinedata_agent.synopsis import MODEL_NAME, build_index, load_embedder


def main() -> int:
    settings = get_settings()
    try:
        check_database(settings.db_path)
    except DatabaseUnavailable as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1

    print(f"Modelo: {MODEL_NAME} (baixado em {settings.embedding_cache_dir} se preciso)")
    embedder = load_embedder(settings.embedding_cache_dir)
    start = time.perf_counter()

    def progress(done: int, total: int) -> None:
        elapsed = time.perf_counter() - start
        eta = elapsed / done * (total - done)
        print(f"\r  {done:>6}/{total} sinopses · {elapsed:4.0f} s · faltam ~{eta:4.0f} s", end="")

    total = build_index(
        settings.db_path, settings.synopsis_index_path, embedder, on_progress=progress
    )
    size_mb = settings.synopsis_index_path.stat().st_size / 1e6
    print(
        f"\n[OK] {total} sinopses indexadas em {time.perf_counter() - start:.0f} s: "
        f"{settings.synopsis_index_path.relative_to(PROJECT_ROOT)} ({size_mb:.0f} MB)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
