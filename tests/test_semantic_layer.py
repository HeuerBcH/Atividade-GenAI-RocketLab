from __future__ import annotations

import sqlite3

import pytest

from cinedata_agent import db_setup, semantic_layer
from cinedata_agent.config import PROJECT_ROOT

DESCRIBED = {(t.name, c.name) for t in semantic_layer.TABLES for c in t.columns}


def test_covers_exactly_the_expected_tables() -> None:
    assert {t.name for t in semantic_layer.TABLES} == db_setup.EXPECTED_TABLES


def test_every_column_has_a_description() -> None:
    assert all(c.description.strip() for t in semantic_layer.TABLES for c in t.columns)


def test_committed_data_dictionary_is_up_to_date() -> None:
    committed = (PROJECT_ROOT / "docs" / "dicionario_dados.md").read_text(encoding="utf-8")
    assert committed == semantic_layer.render_data_dictionary(), (
        "Rode: python scripts/gen_data_dictionary.py"
    )


@pytest.mark.db
def test_columns_match_real_database(gold_conn: sqlite3.Connection) -> None:
    actual = {
        (table, row[1])
        for table in db_setup.EXPECTED_TABLES
        for row in gold_conn.execute(f"PRAGMA table_info({table})")
    }
    assert actual - DESCRIBED == set(), "colunas do banco sem descrição"
    assert DESCRIBED - actual == set(), "colunas descritas que não existem no banco"


@pytest.mark.db
def test_genre_translations_match_real_genres(gold_conn: sqlite3.Connection) -> None:
    genres = {name for (name,) in gold_conn.execute("SELECT nome_genero FROM dim_genres")}
    assert set(semantic_layer.GENRE_TRANSLATIONS.values()) == genres
