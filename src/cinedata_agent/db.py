"""Execução segura e somente leitura de consultas na camada Gold.

Toda SQL vinda do LLM passa por `run_query`, que aplica as três camadas de defesa descritas
em `guardrails.py`, um timeout aplicado pelo próprio motor e um teto de linhas.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from .db_setup import READ_PRAGMAS
from .guardrails import validate_sql

# Ações que o authorizer permite: só leitura. Todo o resto (INSERT, DELETE, ATTACH, PRAGMA,
# CREATE, transações, ...) é negado pelo próprio SQLite, independentemente do texto da SQL.
_ALLOWED_ACTIONS: frozenset[int] = frozenset(
    {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
)
_BLOCKED_FUNCTIONS: frozenset[str] = frozenset({"load_extension"})
_PROGRESS_STEPS = 10_000  # o handler de timeout roda a cada N instruções da VM do SQLite


class QueryError(RuntimeError):
    """Erro de execução com mensagem destinada ao LLM (para autocorreção)."""


class QueryTimeoutError(QueryError):
    """A consulta excedeu o tempo máximo."""


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


@contextmanager
def readonly_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Conexão somente leitura, com PRAGMAs de desempenho e o authorizer já instalado.

    Uma conexão por consulta: simples, segura entre threads (FastAPI) e barata, pois o
    `mmap` reaproveita o cache de páginas do sistema operacional.
    """
    if not db_path.is_file():
        raise FileNotFoundError(f"Banco não encontrado em {db_path}.")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        for pragma in READ_PRAGMAS:  # antes do authorizer, que bloqueia PRAGMA
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
    """Valida e executa a SQL, devolvendo no máximo `max_rows` linhas.

    Raises:
        GuardrailError: SQL rejeitada antes da execução.
        QueryTimeoutError: tempo esgotado.
        QueryError: erro do SQLite (coluna inexistente, operação não autorizada, ...).
    """
    statement = validate_sql(sql)
    start = time.perf_counter()
    deadline = start + timeout_seconds

    with readonly_connection(db_path) as conn:
        conn.set_progress_handler(lambda: int(time.perf_counter() > deadline), _PROGRESS_STEPS)
        try:
            cursor = conn.execute(statement, params)
            fetched = cursor.fetchmany(max_rows + 1)
        except sqlite3.Error as exc:
            # A classe da exceção varia (OperationalError, DatabaseError); a mensagem não.
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
