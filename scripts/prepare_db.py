"""Valida e prepara o banco Gold para o agente (rodar uma vez após baixar o arquivo).

Uso:
    python scripts/prepare_db.py              # valida, cria índices e estatísticas
    python scripts/prepare_db.py --check      # só verifica; exit 1 se não estiver pronto
    python scripts/prepare_db.py --benchmark  # mede as consultas pesadas antes e depois
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from cinedata_agent import db_setup
from cinedata_agent.config import get_settings

# Consultas representativas das perguntas mais caras do enunciado (elenco e equipe).
BENCHMARK_QUERIES: dict[str, str] = {
    "dupla ator-diretor": """
        SELECT a.nome_pessoa, d.nome_pessoa, COUNT(*) AS filmes
        FROM bridge_movie_person ba
        JOIN dim_people a ON a.sk_person_id = ba.sk_person_id AND a.tipo_pessoa = 'Ator'
        JOIN bridge_movie_person bd ON bd.sk_movie_id = ba.sk_movie_id
        JOIN dim_people d ON d.sk_person_id = bd.sk_person_id AND d.tipo_pessoa = 'Diretor'
        GROUP BY a.sk_person_id, d.sk_person_id ORDER BY filmes DESC LIMIT 1""",
    "diretores por nota": """
        SELECT p.nome_pessoa, AVG(f.nota_imdb) AS nota
        FROM bridge_movie_person b
        JOIN dim_people p USING (sk_person_id)
        JOIN fact_movies_performance f USING (sk_movie_id)
        WHERE p.tipo_pessoa = 'Diretor' AND f.nota_imdb IS NOT NULL
        GROUP BY p.sk_person_id HAVING COUNT(*) >= 5 ORDER BY nota DESC LIMIT 1""",
}

DOWNLOAD_HINT = (
    "Baixe o cinerocket.db no link do Drive da atividade e salve em data/cinerocket.db "
    "(ou ajuste DB_PATH no .env)."
)


def run_benchmark(db_path: Path, label: str) -> None:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        for pragma in db_setup.READ_PRAGMAS:
            conn.execute(pragma)
        for name, query in BENCHMARK_QUERIES.items():
            start = time.perf_counter()
            conn.execute(query).fetchall()
            print(f"  [{label}] {name:<20} {time.perf_counter() - start:6.2f} s")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, help="caminho do banco (padrão: DB_PATH do .env)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="apenas verifica, sem alterar")
    mode.add_argument("--benchmark", action="store_true", help="mede antes e depois")
    args = parser.parse_args()

    db_path: Path = (args.db or get_settings().db_path).resolve()
    if not db_path.is_file():
        print(f"[ERRO] Banco não encontrado em {db_path}.\n{DOWNLOAD_HINT}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db_path)
    try:
        if missing := db_setup.missing_tables(conn):
            print(f"[ERRO] Tabelas ausentes: {sorted(missing)}. Arquivo errado ou corrompido?")
            return 1

        if args.check:
            ready = db_setup.is_prepared(conn)
            print(f"[{'OK' if ready else 'PENDENTE'}] {db_path.name}")
            if not ready:
                print("  Rode: python scripts/prepare_db.py")
            return 0 if ready else 1

        conn.close()
        if args.benchmark:
            run_benchmark(db_path, "antes ")
        conn = sqlite3.connect(db_path)

        print(f"Preparando {db_path} ...")
        start = time.perf_counter()
        report = db_setup.prepare(conn)
        elapsed = time.perf_counter() - start
    finally:
        conn.close()

    created = ", ".join(report.created_indexes) or "nenhum (já existiam)"
    print(f"  índices criados: {created}")
    print(f"  estatísticas (ANALYZE): {'atualizadas' if report.analyzed else 'já existiam'}")
    print(f"  journal_mode: {report.journal_mode}")
    print(f"[OK] Banco pronto em {elapsed:.1f} s.")

    if args.benchmark:
        run_benchmark(db_path, "depois")
    return 0


if __name__ == "__main__":
    sys.exit(main())
