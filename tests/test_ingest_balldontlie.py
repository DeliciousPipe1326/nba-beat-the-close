import pytest

from nbatotals import boxscore, store
from nbatotals import params as params_io
from nbatotals.ingest import balldontlie, dunksandthrees
from nbatotals.ingest import common
from tests.fixtures.api_payloads import FAKE_BDL_KEY, FakeResponse, FakeSession, bdl_game, bdl_stat


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "s.db")


def client(routes, waits=None):
    session = FakeSession(routes)
    c = balldontlie.Client(params_io.load(), session=session, key=FAKE_BDL_KEY,
                           sleep=(waits.append if waits is not None else (lambda s: None)))
    return c, session


def test_games_paginate_map_and_skip_exhibitions(con):
    page1 = {"data": [bdl_game(1, "2025-11-03", 2, 20), bdl_game(2, "2025-11-03", 14, 10, period=5, hs=121, as_=119)],
             "meta": {"next_cursor": 77}}
    page2 = {"data": [bdl_game(3, "2025-11-04", 2, 14, status="7:30 pm ET"), bdl_game(4, "2025-11-04", 2, 99)],
             "meta": {}}
    waits: list[float] = []
    c, s = client({"/games": [FakeResponse(page1), FakeResponse(page2)]}, waits)
    assert balldontlie.ingest_games(con, c, seasons=[2025]) == 3
    assert s.calls[1]["params"]["cursor"] == 77
    assert all(call["headers"]["Authorization"] == FAKE_BDL_KEY for call in s.calls)
    assert len(waits) == 1  # the second request waited for the rate-limit gap
    rows = {r[0]: r[1:] for r in con.execute("SELECT id, home, away, status, home_pts, periods FROM games")}
    assert rows[1] == ("BOS", "NYK", "final", 110, 4)
    assert rows[2][3:] == (121, 5)
    assert rows[3] == ("BOS", "LAL", "scheduled", None, None)


def test_box_scores_sum_players_and_derive(con):
    c, _ = client({"/games": FakeResponse({"data": [bdl_game(1, "2025-11-03", 2, 20)], "meta": {}})})
    balldontlie.ingest_games(con, c, dates=["2025-11-03"])
    stats = [bdl_stat(1, 2, pts=60, fgm=22, fga=45, fta=10, ftm=8, oreb=5, dreb=18, turnover=7),
             bdl_stat(1, 2, pts=50, fgm=19, fga=43, fta=8, ftm=6, oreb=4, dreb=17, turnover=5),
             bdl_stat(1, 20, pts=104, fgm=39, fga=90, fta=20, ftm=15, oreb=12, dreb=33, turnover=14),
             bdl_stat(1, 20, pts=None)]  # a DNP row with nulls
    c, _ = client({"/stats": FakeResponse({"data": stats, "meta": {}})})
    assert balldontlie.ingest_box(con, c, dates=["2025-11-03"]) == 2
    got = dict(con.execute("SELECT team, possessions FROM team_box").fetchall())
    home = dict(pts=110, fgm=41, fga=88, fta=18, orb=9, drb=35, tov=12)
    away = dict(pts=104, fgm=39, fga=90, fta=20, orb=12, drb=33, tov=14)
    expected = boxscore.derive(home, away, 4)[0]["possessions"]
    assert got["BOS"] == pytest.approx(expected) and got["NYK"] == pytest.approx(expected)
    # already stored: a second run fetches nothing
    c2, s2 = client({"/stats": FakeResponse({"data": [], "meta": {}})})
    assert balldontlie.ingest_box(con, c2, dates=["2025-11-03"]) == 0 and s2.calls == []


def test_injuries_and_no_key_in_store(con):
    inj = {"data": [{"player": {"id": 5, "first_name": "Test", "last_name": "Player", "team_id": 2},
                     "status": "Out", "description": "made up", "return_date": "Nov 10"}], "meta": {}}
    c, _ = client({"/player_injuries": FakeResponse(inj)})
    assert balldontlie.ingest_injuries(con, c) == 1
    row = con.execute("SELECT team, player_name, status FROM injuries").fetchone()
    assert row == ("BOS", "Test Player", "Out")
    dump = " ".join(str(v) for t in ("games", "injuries", "api_usage")
                    for r in con.execute(f"SELECT * FROM {t}") for v in r)
    assert FAKE_BDL_KEY not in dump


def test_tier_b_stub_is_explicit(monkeypatch):
    monkeypatch.setenv(dunksandthrees.KEY_VAR, "x")
    with pytest.raises(NotImplementedError, match="stub"):
        dunksandthrees.fetch_player_epm()
    monkeypatch.delenv(dunksandthrees.KEY_VAR)
    monkeypatch.setattr(common, "read_dotenv", lambda path=None: {})
    with pytest.raises(common.MissingKeyError):
        dunksandthrees.fetch_player_epm()
