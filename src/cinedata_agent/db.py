"""Execução segura e somente leitura de consultas na camada Gold."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from .guardrails import validate_sql

EXPECTED_TABLES = frozenset(
    {
        "dim_movies",
        "fact_movies_performance",
        "dim_genres",
        "dim_people",
        "dim_companies",
        "dim_reviews",
        "movie_reviews",
        "bridge_movie_genre",
        "bridge_movie_person",
        "bridge_movie_company",
    }
)

# não alteram o arquivo e deixam a consulta mais pesada ~8x mais rápida (docs/decisoes.md)
READ_PRAGMAS = (
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -262144",  # 256 MiB
    "PRAGMA mmap_size = 1073741824",  # 1 GiB
)

# o authorizer só libera leitura; INSERT, ATTACH, PRAGMA etc. o próprio SQLite nega
_ALLOWED_ACTIONS: frozenset[int] = frozenset(
    {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
)
_BLOCKED_FUNCTIONS: frozenset[str] = frozenset({"load_extension"})
_PROGRESS_STEPS = 10_000


class DatabaseUnavailable(RuntimeError):
    pass


class QueryError(RuntimeError):
    """A mensagem volta para o LLM corrigir a consulta."""


class QueryTimeoutError(QueryError):
    pass


class QueryResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[object]]
    truncated: bool
    elapsed_ms: float

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _authorizer(action: int, arg1: str | None, arg2: str | None, *_: object) -> int:
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _BLOCKED_FUNCTIONS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise DatabaseUnavailable(
            f"Banco não encontrado em {db_path}. Baixe o cinerocket.db da atividade e salve "
            "em data/cinerocket.db (ou ajuste DB_PATH no .env)."
        )
    # immutable=1 ignora o arquivo -wal, então ele precisa estar vazio para não perder dados
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.is_file() and wal.stat().st_size > 0:
        raise DatabaseUnavailable(
            f"{wal.name} tem transações pendentes; abra o banco uma vez em modo escrita."
        )
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True)


def check_database(db_path: Path) -> None:
    """Falha cedo, com mensagem clara, se o arquivo não for a camada Gold esperada."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    except sqlite3.DatabaseError as exc:
        raise DatabaseUnavailable(f"{db_path.name} não é um banco SQLite válido: {exc}") from exc
    finally:
        conn.close()
    if missing := EXPECTED_TABLES - {name for (name,) in rows}:
        raise DatabaseUnavailable(f"{db_path.name} não tem as tabelas {sorted(missing)}.")


@contextmanager
def readonly_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    # uma conexão por consulta: segura entre threads e barata por causa do mmap
    conn = _connect(db_path)
    try:
        for pragma in READ_PRAGMAS:  # antes do authorizer, senão o PRAGMA é bloqueado
            conn.execute(pragma)
        conn.set_authorizer(_authorizer)
        yield conn
    finally:
        conn.close()


def _serialize(value: object) -> object:
    if isinstance(value, bytes):
        return f"<blob de {len(value)} bytes>"
    return value


def run_query(
    sql: str,
    *,
    db_path: Path,
    max_rows: int,
    timeout_seconds: float,
    params: Sequence[object] = (),
) -> QueryResult:
    statement = validate_sql(sql)
    start = time.perf_counter()
    deadline = start + timeout_seconds

    with readonly_connection(db_path) as conn:
        conn.set_progress_handler(lambda: int(time.perf_counter() > deadline), _PROGRESS_STEPS)
        try:
            cursor = conn.execute(statement, params)
            fetched = cursor.fetchmany(max_rows + 1)
        except sqlite3.Error as exc:
            # a classe da exceção varia (OperationalError/DatabaseError), a mensagem não
            message = str(exc).lower()
            if "interrupted" in message:
                raise QueryTimeoutError(
                    f"A consulta excedeu {timeout_seconds:.0f} s e foi interrompida. "
                    "Simplifique-a: filtre antes de juntar tabelas e agregue por chaves sk_*."
                ) from exc
            if "not authorized" in message:
                raise QueryError(
                    "Operação não autorizada: o acesso é somente leitura. Use apenas SELECT."
                ) from exc
            raise QueryError(f"Erro do SQLite: {exc}") from exc
        columns = [d[0] for d in cursor.description or ()]

    return QueryResult(
        sql=statement,
        columns=columns,
        rows=[[_serialize(v) for v in row] for row in fetched[:max_rows]],
        truncated=len(fetched) > max_rows,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 1),
    )
