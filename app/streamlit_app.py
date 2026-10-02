"""Interface de chat do agente. Rode com: streamlit run app/streamlit_app.py"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from collections.abc import Coroutine
from typing import Any

import pandas as pd
import streamlit as st

from cinedata_agent.agent import AgentError
from cinedata_agent.config import get_settings
from cinedata_agent.models import AskResponse
from cinedata_agent.service import CineDataService

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

EXAMPLES = {
    "Bilheteria e Finanças": [
        "Quais são os 10 filmes com maior receita em R$?",
        "Qual o lucro médio por gênero, considerando apenas filmes com receita informada?",
    ],
    "Popularidade": [
        "Quais são os 5 filmes mais populares?",
        "Qual a nota média IMDb por ano de lançamento?",
    ],
    "Elenco e Equipe": [
        "Qual dupla ator-diretor mais trabalhou junta?",
        "Quais diretores têm a maior nota média, considerando um mínimo de 5 filmes?",
    ],
    "Gêneros e Produtoras": [
        "Qual a quantidade de filmes por gênero?",
        "Qual produtora teve o maior lucro total?",
    ],
    "Avaliações dos Usuários": [
        "Quais filmes foram mais avaliados pelos usuários?",
    ],
}
MAX_CHART_ROWS = 30


@st.cache_resource
def _runtime() -> tuple[CineDataService, asyncio.AbstractEventLoop]:
    # O Streamlit reexecuta o script a cada interação; um loop fixo numa thread mantém
    # vivas as conexões HTTP do cliente do Groq entre uma pergunta e outra.
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return CineDataService(get_settings()), loop


def _run(coro: Coroutine[Any, Any, AskResponse]) -> AskResponse:
    _, loop = _runtime()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def _chart(response: AskResponse) -> None:
    if len(response.columns) != 2 or not 1 < len(response.rows) <= MAX_CHART_ROWS:
        return
    df = pd.DataFrame(response.rows, columns=response.columns)
    label, value = response.columns
    if not pd.api.types.is_numeric_dtype(df[value]):
        return
    if "ano" in label.lower():
        st.line_chart(df, x=label, y=value)
    else:
        st.bar_chart(df, x=label, y=value, horizontal=True, sort=f"-{value}")


def _render(response: AskResponse) -> None:
    st.markdown(response.answer)
    if response.assumptions:
        st.caption("Premissas: " + " · ".join(response.assumptions))
    if response.rows:
        _chart(response)
        st.dataframe(
            pd.DataFrame(response.rows, columns=response.columns),
            hide_index=True,
            use_container_width=True,
        )
        if response.truncated:
            st.caption("Resultado truncado no limite de linhas.")
    if response.sql:
        with st.expander("SQL executada"):
            st.code(response.sql, language="sql")
    if response.steps:
        with st.expander("Passos do agente (ReAct)"):
            for step in response.steps:
                st.markdown(f"**{step.kind}** — {step.content}")
    if response.cached:
        st.caption("Resposta do cache (sem nova chamada ao modelo).")
    else:
        st.caption(
            f"{response.model} · {response.usage.requests} chamada(s) · "
            f"{response.latency_ms / 1000:.1f} s"
        )


def main() -> None:
    st.set_page_config(page_title="CineData Analyst", page_icon="🎬", layout="wide")
    st.session_state.setdefault("session_id", uuid.uuid4().hex)
    st.session_state.setdefault("history", [])

    try:
        service, _ = _runtime()
    except AgentError as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.header("CineData Analyst")
        st.caption("Pergunte em português sobre o catálogo de filmes.")
        if st.button("Nova conversa", use_container_width=True):
            service.reset(st.session_state.session_id)
            st.session_state.history = []
            st.rerun()
        st.subheader("Exemplos")
        for category, questions in EXAMPLES.items():
            with st.expander(category):
                for question in questions:
                    if st.button(question, key=question, use_container_width=True):
                        st.session_state.pending = question
        st.caption(f"Modelo: {', '.join(service.settings.model_chain)}")

    st.title("🎬 CineData Analyst")
    for item in st.session_state.history:
        with st.chat_message(item["role"]):
            if item["role"] == "user":
                st.markdown(item["content"])
            elif "error" in item:
                st.error(item["error"])
            else:
                _render(item["response"])

    question = st.chat_input("Ex.: quais os 10 filmes com maior receita em R$?")
    question = question or st.session_state.pop("pending", None)
    if not question:
        return

    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"), st.spinner("Consultando o banco..."):
        try:
            response = _run(service.ask(question, st.session_state.session_id))
        except AgentError as exc:
            st.error(str(exc))
            st.session_state.history.append({"role": "assistant", "error": str(exc)})
            return
        _render(response)
    st.session_state.history.append({"role": "assistant", "response": response})


main()
