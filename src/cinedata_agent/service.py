"""Orquestra o agente com memória por sessão, cache de respostas e log de execuções."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from .agent import AgentDeps, AgentError, ConfigurationError, ask, build_agent, build_model
from .config import PROJECT_ROOT, Settings
from .db import DatabaseUnavailable, check_database
from .models import AgentOutput, AskResponse
from .prompt import prompt_version

logger = logging.getLogger(__name__)

MAX_TURNS = 6
CACHE_TTL_SECONDS = 3600
LOG_PATH = PROJECT_ROOT / "logs" / "agent.jsonl"


def normalize_question(question: str) -> str:
    return " ".join(question.casefold().split()).rstrip("?!. ")


@dataclass
class _Session:
    # cada turno guarda as mensagens inteiras de uma pergunta, para nunca separar
    # uma chamada de ferramenta do seu resultado ao cortar o histórico
    turns: list[list[ModelMessage]] = field(default_factory=list)

    def history(self) -> list[ModelMessage]:
        return [m for turn in self.turns[-MAX_TURNS:] for m in turn]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._lock = Lock()

    def history(self, session_id: str) -> list[ModelMessage]:
        with self._lock:
            session = self._sessions.get(session_id)
            return session.history() if session else []

    def add_turn(self, session_id: str, messages: list[ModelMessage]) -> None:
        with self._lock:
            session = self._sessions.setdefault(session_id, _Session())
            session.turns.append(messages)
            del session.turns[:-MAX_TURNS]

    def reset(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


class ResponseCache:
    """Só para perguntas sem histórico: um follow-up depende do contexto da conversa."""

    def __init__(self, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._items: dict[str, tuple[float, AskResponse, list[ModelMessage]]] = {}
        self._lock = Lock()

    @staticmethod
    def key(question: str) -> str:
        # a versão do prompt entra na chave: mudou o prompt, o cache antigo não vale mais
        return f"{prompt_version()}:{normalize_question(question)}"

    def get(self, question: str) -> tuple[AskResponse, list[ModelMessage]] | None:
        with self._lock:
            item = self._items.get(self.key(question))
            if item is None or time.monotonic() - item[0] > self._ttl:
                return None
            return item[1], item[2]

    def put(self, question: str, response: AskResponse, messages: list[ModelMessage]) -> None:
        with self._lock:
            self._items[self.key(question)] = (time.monotonic(), response, messages)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class CineDataService:
    def __init__(
        self,
        settings: Settings,
        agent: Agent[AgentDeps, AgentOutput | str] | None = None,
        log_path: Path | None = LOG_PATH,
    ) -> None:
        try:
            check_database(settings.db_path)
        except DatabaseUnavailable as exc:
            raise ConfigurationError(str(exc)) from exc
        self.settings = settings
        self.agent = agent or build_agent(build_model(settings))
        self.sessions = SessionStore()
        self.cache = ResponseCache()
        self._log_path = log_path

    async def ask(self, question: str, session_id: str = "default") -> AskResponse:
        history = self.sessions.history(session_id)
        if not history and (hit := self.cache.get(question)):
            cached, messages = hit
            response = cached.model_copy(update={"session_id": session_id, "cached": True})
            self.sessions.add_turn(session_id, messages)  # o follow-up continua funcionando
            self._log(session_id, response, cached=True)
            return response

        try:
            response, new_messages = await ask(
                self.agent,
                question,
                deps=AgentDeps.from_settings(self.settings),
                max_requests=self.settings.max_requests_per_question,
                message_history=history or None,
                timeout_seconds=self.settings.question_timeout_seconds,
            )
        except AgentError as exc:
            self._log(session_id, None, question=question, error=str(exc), detail=exc.detail)
            raise

        response = response.model_copy(update={"session_id": session_id})
        self.sessions.add_turn(session_id, new_messages)
        if not history:
            self.cache.put(question, response, new_messages)
        self._log(session_id, response)
        return response

    def reset(self, session_id: str) -> bool:
        return self.sessions.reset(session_id)

    def _log(
        self,
        session_id: str,
        response: AskResponse | None,
        *,
        cached: bool = False,
        question: str | None = None,
        error: str | None = None,
        detail: str | None = None,
    ) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "session_id": session_id,
            "prompt_version": prompt_version(),
            "question": response.question if response else question,
            "cached": cached,
            "error": error,
            "detail": detail,
        }
        if response:
            record |= {
                "sql": response.sql,
                "rows": len(response.rows),
                "model": response.model,
                "requests": 0 if cached else response.usage.requests,
                "input_tokens": 0 if cached else response.usage.input_tokens,
                "output_tokens": 0 if cached else response.usage.output_tokens,
                "latency_ms": 0 if cached else response.latency_ms,
            }
        if error:
            logger.warning("falha ao responder %r: %s", record["question"], detail)
        if self._log_path is None:
            return
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("não foi possível gravar o log em %s", self._log_path)
