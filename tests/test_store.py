import sqlite3

import pytest

from nbatotals import store


def test_schema_creates_all_tables(tmp_path):
    con = store.connect(tmp_path / "s.db")
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"games", "team_box", "odds_snapshots", "injuries", "api_usage"} <= names


def test_anchor_and_market_are_constrained(tmp_path):
    con = store.connect(tmp_path / "s.db")
    con.execute(
        "insert into games (id, game_date, season, home, away, status, source) "
        "values (1, '2024-01-01', 2023, 'BOS', 'NYK', 'final', 't')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into odds_snapshots (game_id, book, market, anchor, source) "
            "values (1, 'b', 'totals', 'noon_local', 't')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into odds_snapshots (game_id, book, market, anchor, source) "
            "values (1, 'b', 'props', 'close', 't')"
        )
