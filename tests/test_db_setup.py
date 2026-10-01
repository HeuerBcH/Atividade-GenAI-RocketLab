from __future__ import annotations

import sqlite3

from cinedata_agent import db_setup


def test_detects_missing_tables(mini_gold_conn: sqlite3.Connection) -> None:
    assert db_setup.missing_tables(mini_gold_conn) == set()

    mini_gold_conn.execute("DROP TABLE dim_reviews")
    assert db_setup.missing_tables(mini_gold_conn) == {"dim_reviews"}


def test_fresh_database_is_not_prepared(mini_gold_conn: sqlite3.Connection) -> None:
    assert not db_setup.is_prepared(mini_gold_conn)
    assert set(db_setup.missing_indexes(mini_gold_conn)) == set(db_setup.REQUIRED_INDEXES)


def test_prepare_creates_indexes_stats_and_leaves_wal(
    mini_gold_conn: sqlite3.Connection,
) -> None:
    report = db_setup.prepare(mini_gold_conn)

    assert sorted(report.created_indexes) == sorted(db_setup.REQUIRED_INDEXES)
    assert report.analyzed
    assert report.journal_mode == "delete"
    assert db_setup.is_prepared(mini_gold_conn)


def test_prepare_is_idempotent(mini_gold_conn: sqlite3.Connection) -> None:
    db_setup.prepare(mini_gold_conn)
    second = db_setup.prepare(mini_gold_conn)

    assert second.created_indexes == []
    assert not second.analyzed


def test_prepare_does_not_touch_data(mini_gold_conn: sqlite3.Connection) -> None:
    before = mini_gold_conn.execute("SELECT * FROM dim_people ORDER BY 1").fetchall()
    db_setup.prepare(mini_gold_conn)
    after = mini_gold_conn.execute("SELECT * FROM dim_people ORDER BY 1").fetchall()

    assert before == after


def test_prepared_database_opens_read_only(mini_gold_db, mini_gold_conn) -> None:
    db_setup.prepare(mini_gold_conn)
    mini_gold_conn.close()

    ro = sqlite3.connect(f"file:{mini_gold_db.as_posix()}?mode=ro", uri=True)
    try:
        for pragma in db_setup.READ_PRAGMAS:
            ro.execute(pragma)
        assert ro.execute("SELECT COUNT(*) FROM dim_people").fetchone() == (2,)
    finally:
        ro.close()
