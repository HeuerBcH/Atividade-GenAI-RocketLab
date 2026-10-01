"""Validação sintática da SQL gerada pelo LLM, antes de qualquer contato com o banco.

Esta é a primeira de três camadas de defesa (as outras ficam em `db.py`):

1. **Guardrail sintático (aqui):** um único comando, iniciado por SELECT ou WITH. As mensagens
   de erro são escritas para o LLM conseguir se corrigir sozinho.
2. **Authorizer do SQLite:** allowlist de operações de leitura, aplicada pelo próprio motor
   (bloqueia, p.ex., ``WITH x AS (...) DELETE ...``, que passaria por um filtro textual).
3. **Conexão ``mode=ro``:** mesmo que algo escape, o arquivo não pode ser alterado.

Não há lista de palavras proibidas por regex: ela rejeitaria consultas legítimas (um título como
'Drop Dead') e não seria a garantia real. A garantia real é o motor (camadas 2 e 3).
"""

from __future__ import annotations

import re

_READ_START = re.compile(r"^(SELECT|WITH)\b", re.IGNORECASE)


class GuardrailError(ValueError):
    """A SQL viola uma regra de segurança; a mensagem orienta a correção."""


def _strip_comments_and_split(sql: str) -> list[str]:
    """Separa comandos por ';' ignorando strings, identificadores e comentários.

    Devolve os comandos sem comentários (cada um com espaços nas pontas removidos).
    """
    statements: list[str] = []
    current: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"', "`"):  # literal ou identificador entre aspas ('' escapa ')
            end = i + 1
            while end < n:
                if sql[end] == ch:
                    if end + 1 < n and sql[end + 1] == ch:
                        end += 2
                        continue
                    break
                end += 1
            current.append(sql[i : end + 1])
            i = end + 1
        elif ch == "[":  # identificador no estilo [nome]
            end = sql.find("]", i)
            end = n - 1 if end == -1 else end
            current.append(sql[i : end + 1])
            i = end + 1
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            current.append(" ")
        elif ch == ";":
            statements.append("".join(current).strip())
            current = []
            i += 1
        else:
            current.append(ch)
            i += 1
    statements.append("".join(current).strip())
    return [s for s in statements if s]


def validate_sql(sql: str) -> str:
    """Valida a SQL e devolve o comando único, sem comentários nem ';' final.

    Raises:
        GuardrailError: com uma mensagem acionável para o LLM.
    """
    statements = _strip_comments_and_split(sql or "")
    if not statements:
        raise GuardrailError("A consulta está vazia. Envie um comando SELECT.")
    if len(statements) > 1:
        raise GuardrailError(
            f"Foram enviados {len(statements)} comandos. Envie apenas um SELECT por vez."
        )
    statement = statements[0]
    if not _READ_START.match(statement):
        first_word = statement.split(maxsplit=1)[0].upper()
        raise GuardrailError(
            f"Comando '{first_word}' não permitido: o acesso é somente leitura. "
            "Use apenas SELECT (ou WITH ... SELECT)."
        )
    return statement
