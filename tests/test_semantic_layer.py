from __future__ import annotations

import pytest

from cinedata_agent import semantic_layer
from cinedata_agent.config import PROJECT_ROOT
from cinedata_agent.db import EXPECTED_TABLES


def test_describes_every_table_and_the_dictionary_is_up_to_date() -> None:
    assert {t.name for t in semantic_layer.TABLES} == EXPECTED_TABLES
    assert all(c.description.strip() for t in semantic_layer.TABLES for c in t.columns)

    committed = (PROJECT_ROOT / "docs" / "dicionario_dados.md").read_text(encoding="utf-8")
    assert committed == semantic_layer.render_data_dictionary(), (
        "rode python scripts/gen_data_dictionary.py"
    )


@pytest.mark.db
def test_matches_the_real_database(gold_conn) -> None:
    described = {(t.name, c.name) for t in semantic_layer.TABLES for c in t.columns}
    actual = {
        (table, row[1])
        for table in EXPECTED_TABLES
        for row in gold_conn.execute(f"PRAGMA table_info({table})")
    }
    assert actual == described

    genres = {name for (name,) in gold_conn.execute("SELECT nome_genero FROM dim_genres")}
    assert set(semantic_layer.GENRE_TRANSLATIONS.values()) == genres
