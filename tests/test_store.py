import sqlite3

import pytest

from nbatotals import store


def test_schema_creates_all_tables(tmp_path):
    con = store.connect(tmp_path / "s.db")
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert {"games", "team_box", "odds_snapshots", "injuries", "api_usage"} <= names


def test_market_is_constrained_and_game_id_may_wait(tmp_path):
    con = store.connect(tmp_path / "s.db")
    # odds can arrive before the fixture is matched to a BallDontLie game
    con.execute("insert into odds_snapshots (event_id, book, market, anchor, source) values ('e1', 'b', 'totals', 't-1h', 't')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into odds_snapshots (event_id, book, market, anchor, source) values ('e1', 'b', 'props', 'close', 't')"
        )
