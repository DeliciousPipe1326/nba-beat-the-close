"""backfill-odds and backtest --store, on synthetic API payloads and the synthetic league (no live calls)."""

import datetime as dt

import pytest

from nbatotals import cli, store, synthetic
from nbatotals import params as params_io
from nbatotals.ingest import theodds_history as hist
from tests.fixtures.api_payloads import FAKE_ODDS_KEY, FakeResponse, FakeSession, odds_event, quota_headers

BOS_NYK = {"id": "evA", "home_team": "Boston Celtics", "away_team": "New York Knicks"}
LAL_GSW = {"id": "evB", "home_team": "Los Angeles Lakers", "away_team": "Golden State Warriors"}
TIP1 = "2025-01-11T00:30:00Z"  # 19:30 Eastern on 2025-01-10
TIP2 = "2025-01-11T03:00:00Z"  # 22:00 Eastern on 2025-01-10


def utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture
def con(tmp_path):
    c = store.connect(tmp_path / "s.db")
    rows = [(1, "2025-01-10", TIP1, "BOS", "NYK"), (2, "2025-01-10", TIP2, "LAL", "GSW"),
            (3, "2025-01-10", TIP1, "MIA", "ORL"), (4, "2025-01-12", None, "DEN", "UTA")]
    for gid, day, tip, home, away in rows:
        c.execute("INSERT INTO games (id, game_date, tip_utc, season, home, away, status, source) "
                  "VALUES (?, ?, ?, 2024, ?, ?, 'final', 't')", (gid, day, tip, home, away))
    c.commit()
    return c


def snapshot(at: str, events: list) -> FakeResponse:
    return FakeResponse({"timestamp": at, "data": events}, headers=quota_headers(100, 900, 20))


def test_anchor_times_are_per_game_and_grouped_by_tip(con):
    requests, counts = hist.plan(con, 2024, hist.resolve_anchors(["true_close", "noon"]))
    assert counts["games_without_tip_time"] == 1  # game 4
    by = {(r.anchor, r.at): r for r in requests}
    r = by[("t-15m", utc(TIP1) - dt.timedelta(minutes=15))]
    assert r.game_ids == (1, 3)  # same snapshot window -> one call
    assert by[("t-10h", utc("2025-01-10T17:00:00Z"))].game_ids == (2,)
    assert len(requests) == 4  # 2 anchors x 2 windows
    # tips a few minutes apart land in one 5-minute snapshot window; the window is floored
    near = hist.requests_for("t-15m", (15,), [(7, utc("2025-01-11T00:11:34Z")), (8, utc("2025-01-11T00:10:51Z"))])
    assert len(near) == 1 and near[0].at == utc("2025-01-10T23:55:00Z") and near[0].game_ids == (7, 8)
    with pytest.raises(ValueError, match="unknown anchor"):
        hist.resolve_anchors(["midnight"])


def test_cost_estimate():
    assert hist.credits_per_call(["totals"], ["us", "eu"], None) == 20
    assert hist.credits_per_call(["totals", "spreads", "h2h"], ["us"], None) == 30
    assert hist.credits_per_call(["totals"], ["us"], [f"b{i}" for i in range(12)]) == 20  # 2 groups of 10
    g = ((1, utc(TIP1)),)
    reqs = [hist.Request("opening", 2160, utc(TIP1), g, (1440, 1080)), hist.Request("t-1h", 60, utc(TIP1), g)]
    est = hist.estimate(reqs, 20)
    assert (est["calls"], est["credits"], est["worst_case_calls"], est["worst_case_credits"]) == (2, 40, 4, 80)


def test_join_by_commence_time_and_in_play_drops(con):
    lookup = hist.theodds._games_lookup(con)
    req = hist.Request("t-15m", 15, utc("2025-01-11T00:15:00Z"), ((1, utc(TIP1)), (3, utc(TIP1))))
    rescheduled = dict(BOS_NYK, id="evOld", commence_time="2025-01-12T00:30:00Z")  # another Eastern date
    other = dict(LAL_GSW, commence_time=TIP2)  # a game in the snapshot, not requested
    late_book = odds_event(dict(BOS_NYK, commence_time=TIP1), 221.5, books=("fanduel", "draftkings"),
                           last_update=TIP1)  # updated exactly at tip: in play
    ok = odds_event(dict(BOS_NYK, commence_time=TIP1), 221.5, books=("betmgm",),
                    last_update="2025-01-11T00:10:00Z")
    ev = dict(late_book, bookmakers=late_book["bookmakers"] + ok["bookmakers"])
    payload = {"timestamp": "2025-01-11T00:15:00Z",
               "data": [ev, odds_event(rescheduled, 210.0), odds_event(other, 230.0)]}
    rows, counts, missing = hist.parse_snapshot(payload, req, lookup)
    assert {r["book"] for r in rows} == {"betmgm"}
    assert {r["game_id"] for r in rows} == {1} and missing == {3}
    assert counts["book_updated_after_tip"] == 2 and counts["events_for_games_not_requested"] == 2
    r = rows[0]
    assert r["captured_utc"] == "2025-01-11T00:15:00Z" and r["lead_minutes"] == 15.0
    assert r["nominal_lead_minutes"] == 15.0 and r["commence_utc"] == TIP1 and r["anchor"] == "t-15m"
    in_play = {"timestamp": "2025-01-11T00:31:00Z", "data": [odds_event(dict(BOS_NYK, commence_time=TIP1), 221.5)]}
    rows, counts, _ = hist.parse_snapshot(in_play, req, lookup)
    assert rows == [] and counts["in_play_events"] == 1


def _backfill(con, session, **kw):
    kw.setdefault("anchors", ["t-15m"])
    return hist.backfill(con, params_io.load(), 2024, session=session, key=FAKE_ODDS_KEY, confirm=lambda t: True,
                         now=lambda: utc("2026-10-20T12:00:00Z"), out=lambda s: None, **kw)


def test_backfill_is_idempotent_and_logs_usage(con):
    snaps = [snapshot("2025-01-11T00:15:00Z", [odds_event(dict(BOS_NYK, commence_time=TIP1), 221.5,
                                                             last_update="2025-01-11T00:10:00Z")]),
             snapshot("2025-01-11T02:45:00Z", [odds_event(dict(LAL_GSW, commence_time=TIP2), 230.5,
                                                             last_update="2025-01-11T02:40:00Z")])]
    s = FakeSession({"/sports": FakeResponse([], headers=quota_headers(80, 920, 0)), "/odds": snaps})
    out = _backfill(con, s)
    assert out["calls"] == 2 and out["rows_written"] == 2 * 3 * 3  # per call: one game, 3 books x 3 markets
    assert out["game_anchors_not_listed"] == 1  # game 3 (MIA-ORL) is in no snapshot
    assert con.execute("SELECT COUNT(*) FROM api_usage").fetchone()[0] == 3
    assert {c["params"]["date"] for c in s.calls[1:]} == {"2025-01-11T00:15:00Z", "2025-01-11T02:45:00Z"}
    again = _backfill(con, FakeSession({}), dry_run=True)  # a re-run skips games 1 and 2; only game 3 is asked again
    assert again["plan"]["game_anchors_already_stored"] == 2 and again["estimate"]["calls"] == 1
    n = con.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    assert hist.store_rows(con, [dict(r) for r in _rows(con)]) == 0  # (event, book, market, anchor) is the key
    assert con.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0] == n


def _rows(con):
    cur = con.execute(f"SELECT {', '.join(hist.STORE_COLUMNS)} FROM odds_snapshots")
    return [dict(zip(hist.STORE_COLUMNS, row, strict=True)) for row in cur]


def test_dry_run_and_gates_spend_nothing(con):
    assert _backfill(con, FakeSession({}), dry_run=True)["calls"] == 0  # any request would fail the test
    poor = FakeSession({"/sports": FakeResponse([], headers=quota_headers(990, 10, 0))})
    out = _backfill(con, poor)
    assert out["stopped"].startswith("refused before any paid call") and len(poor.calls) == 1
    capped = FakeSession({"/sports": FakeResponse([], headers=quota_headers(0, 5000, 0))})
    assert "max-credits" in _backfill(con, capped, max_credits=10)["stopped"]
    no = FakeSession({"/sports": FakeResponse([], headers=quota_headers(0, 5000, 0))})
    out = hist.backfill(con, params_io.load(), 2024, anchors=["t-15m"], session=no, key=FAKE_ODDS_KEY,
                        confirm=lambda t: False, out=lambda s: None)
    assert out["stopped"] == "not confirmed" and len(no.calls) == 1


def test_opening_falls_back_to_later_snapshots(con):
    early = snapshot("2025-01-09T12:30:00Z", [])  # nothing listed 36 h out
    later = snapshot("2025-01-10T00:30:00Z", [odds_event(dict(BOS_NYK, commence_time=TIP1), 220.0,
                                                          last_update="2025-01-10T00:20:00Z")])
    s = FakeSession({"/sports": FakeResponse([], headers=quota_headers(0, 5000, 0)),
                     "/odds": [early, later, early, early, early, early]})
    out = _backfill(con, s, anchors=["opening"])
    stored = con.execute("SELECT DISTINCT game_id, nominal_lead_minutes FROM odds_snapshots "
                         "WHERE anchor = 'opening'").fetchall()
    assert stored == [(1, 1440.0)]
    assert out["calls"] >= 3


def test_backtest_store_mode_on_the_synthetic_league(tmp_path):
    games, box = synthetic.generate(seasons=(2021, 2022), days=40, games_per_day=6, seed=3)
    db = tmp_path / "s.db"
    c = store.connect(db)
    games.to_sql("games", c, if_exists="append", index=False)
    box.to_sql("team_box", c, if_exists="append", index=False)
    synthetic.odds(games[games["season"] == 2022], seed=3).to_sql("odds_snapshots", c, if_exists="append",
                                                                  index=False)
    c.commit()
    c.close()
    out = tmp_path / "r.md"
    rc = cli.main(["backtest", "--store", "--db", str(db), "--model", "league_avg", "--out", str(out),
                   "--log", str(tmp_path / "log.tsv.gz")])
    assert rc == 0
    md = out.read_text()
    assert "## Headline (primary cell: tuned model, T−15 min, every game)" in md
    assert "| 2022-23 |" in md and "opening" in md


# --------------------------------------------------------------------------- replay (synthetic recorded files)

def _write(path, payload):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_replay_runs_recorded_responses_through_the_backfill_path(con, tmp_path):
    from nbatotals.evaluate.adapters import legacy_replay

    def recorded(name, requested, snapshot, event, game_id="evA"):
        _write(tmp_path / "rec" / "season=2024-25" / name / "data.json",
               {"_metadata": {"bucket_name": "strict_close", "requested_timestamp": requested,
                              "api_game_id": game_id}, "data": {"timestamp": snapshot, "data": [event]}})

    # wrapped payload; the metadata names the requested event and the bucket
    recorded("a", "2025-01-11T00:27:00Z", "2025-01-11T00:25:00Z",
             odds_event(dict(BOS_NYK, commence_time=TIP1), 221.5, last_update="2025-01-11T00:20:00Z"))
    recorded("b", "2025-01-11T03:05:00Z", "2025-01-11T03:05:00Z",  # polled after tip: in play
             odds_event(dict(LAL_GSW, id="evB", commence_time=TIP2), 230.5), game_id="evB")
    recorded("c", "2025-01-09T00:00:00Z", "2025-01-09T00:00:00Z",  # 48 h before tip: beyond the planner's leads
             odds_event(dict(LAL_GSW, id="evC", commence_time=TIP2), 229.5), game_id="evC")
    _write(tmp_path / "rec" / "season=2024-25" / "d" / "data.json", {"timestamp": "2025-01-11T00:25:00Z", "data": []})
    s = legacy_replay.replay(con, tmp_path / "rec", season=2024, now=lambda: utc("2026-10-20T12:00:00Z"))
    assert s["files"] == 3 and s["skipped"]["no_metadata"] == 1
    assert s["events"]["in_play"] == 1 and s["events"]["beyond_max_lead"] == 1 and s["events"]["requested"] == 1
    rows = con.execute("SELECT DISTINCT game_id, anchor, nominal_lead_minutes, lead_minutes, captured_utc, "
                       "commence_utc FROM odds_snapshots").fetchall()
    # bucket kept as the anchor; nominal lead = tip - requested time (3 min), measured lead from the snapshot (5)
    assert rows == [(1, "strict_close", 3.0, 5.0, "2025-01-11T00:25:00Z", TIP1)]
    assert {r[0] for r in con.execute("SELECT endpoint FROM api_usage")} == {"historical_odds (replay)"}
    assert legacy_replay.replay(con, tmp_path / "rec", season=2024)["rows_written"] == 0  # idempotent
