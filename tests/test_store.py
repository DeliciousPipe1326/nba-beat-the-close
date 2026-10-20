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
    con.execute("insert into odds_snapshots (event_id, book, market, anchor, source) "
                "values ('e1', 'b', 'totals', 't-1h', 't')")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "insert into odds_snapshots (event_id, book, market, anchor, source) "
            "values ('e1', 'b', 'props', 'close', 't')"
        )


def test_placeholders_bind_every_value(tmp_path):
    con = store.connect(tmp_path / "s.db")
    con.executemany("insert into games (id, game_date, season, home, away, status, source) "
                    "values (?, '2024-01-01', 2023, 'BOS', 'NYK', 'final', 't')", [(i,) for i in (1, 2, 3)])
    ids = [1, 3]
    rows = con.execute(f"select id from games where id in ({store.placeholders(len(ids))}) order by id", ids)
    assert [r[0] for r in rows] == [1, 3]
    with pytest.raises(ValueError):
        store.placeholders(0)
