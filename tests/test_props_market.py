import json

import numpy as np
import pandas as pd
import pytest

from nbatotals.evaluate import props_market as pm
from nbatotals.evaluate.adapters import legacy_props

TIP = "2024-11-02T00:00:00Z"  # 20:00 ET on 2024-11-01
T3H, CLOSE = "2024-11-01T20:55:00Z", "2024-11-01T23:51:00Z"
GAMES = pd.DataFrame([dict(id=7, game_date="2024-11-01", season=2024, postseason=0, home="BOS", away="NYK")])
BOX = pd.DataFrame([
    dict(game_id=7, player_id=1, name="Jayson Tatum", minutes=36.0, is_dnp=0, points=30, rebounds=8, assists=5),
    dict(game_id=7, player_id=2, name="Jalen Brunson", minutes=0.0, is_dnp=1, points=0, rebounds=0, assists=0),
    dict(game_id=7, player_id=3, name="Luka Dončić Jr.", minutes=30.0, is_dnp=0, points=20, rebounds=10, assists=9),
])


def q(region, book, player, side, line, american, captured=T3H, market="player_points", last_update=None,
      file=None, commence=TIP):
    return dict(region=region, file=file or f"{region}/{market}/{captured}", captured_utc=captured, event_id="e1",
                commence_utc=commence, home_name="Boston Celtics", away_name="New York Knicks", book=book,
                market=market, book_last_update=last_update or captured, last_update=last_update or captured,
                player=player, side=side, line=line, american=american)


def pin(player, line, o, u, captured=T3H, market="player_points"):
    return [q("eu", "pinnacle", player, "over", line, o, captured, market),
            q("eu", "pinnacle", player, "under", line, u, captured, market)]


def test_normalise_name():
    assert pm.normalise_name("Luka Dončić Jr.") == "luka doncic"
    assert pm.normalise_name("P.J. Washington") == "pj washington"
    assert pm.normalise_name("Kentavious Caldwell-Pope") == "kentavious caldwell pope"
    assert pm.normalise_name("De'Aaron  Fox III") == "deaaron fox"
    assert pm.normalise_name(None) == ""


def test_devig_and_edge_arithmetic():
    assert pm.devig_over(1.909090909, 1.909090909) == pytest.approx(0.5)
    # -120 / +100: 1/1.8333 = 0.54545, 1/2 = 0.5 -> 0.54545 / 1.04545
    assert pm.devig_over(1 + 100 / 120, 2.0) == pytest.approx(0.545454 / 1.045454, rel=1e-5)
    assert pm.edge(0.55, 2.0) == pytest.approx(0.10)
    assert pm.edge(0.5, 1.909090909) == pytest.approx(-0.0454545, rel=1e-5)


def test_prepare_windows_dedupe_and_join():
    rows = (pin("Jayson Tatum", 25.5, -110, -110)
            + [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 105),
               q("us", "fanduel", "Jayson Tatum", "under", 25.5, -135),
               # BetOnline in us and eu: one copy kept (us)
               q("us", "betonlineag", "Jayson Tatum", "over", 25.5, -105),
               q("eu", "betonlineag", "Jayson Tatum", "over", 25.5, -105),
               # duplicate price for the same player-line-side in one file: player-line dropped
               q("us", "draftkings", "Jayson Tatum", "over", 25.5, -110),
               q("us", "draftkings", "Jayson Tatum", "over", 25.5, -115),
               q("us", "draftkings", "Jayson Tatum", "under", 25.5, -110),
               # updated after tip: dropped
               q("us", "betmgm", "Jayson Tatum", "over", 25.5, 120, last_update="2024-11-02T00:05:00Z"),
               # captured after tip: dropped with its file
               q("us", "bovada", "Jayson Tatum", "over", 25.5, 150, captured="2024-11-02T00:10:00Z"),
               # stale: last update 2 hours before capture
               q("au", "sportsbet", "Jayson Tatum", "over", 25.5, 110, last_update="2024-11-01T18:55:00Z")])
    quotes, c = pm.prepare(pd.DataFrame(rows), GAMES)
    assert c["files_at_or_after_tip"] == 1
    assert c["outcomes_last_update_after_tip"] == 1
    assert c["player_lines_dropped_duplicate_in_file"] == 1
    assert c["cross_region_duplicates_dropped"] == 1 and c["cross_region_duplicates_price_differs"] == 0
    assert set(quotes["book"]) == {"pinnacle", "fanduel", "betonlineag", "sportsbet"}
    assert quotes.loc[quotes["book"] == "betonlineag", "region"].tolist() == ["us"]
    assert (quotes["window"] == "t-3h").all() and (quotes["game_id"] == 7).all() and (quotes["split"] == "test").all()
    assert quotes.loc[quotes["book"] == "sportsbet", "stale"].all()
    assert not quotes.loc[quotes["book"] == "fanduel", "stale"].any()


def test_superseded_file_keeps_latest():
    rows = [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 105, captured="2024-11-01T20:30:00Z"),
            q("us", "fanduel", "Jayson Tatum", "over", 25.5, 110, captured="2024-11-01T21:00:00Z")]
    quotes, c = pm.prepare(pd.DataFrame(rows), GAMES)
    assert c["files_superseded_in_window"] == 1 and quotes["american"].tolist() == [110]


def test_playin_and_later_season_are_not_test():
    g = pd.DataFrame([dict(id=8, game_date="2025-04-15", season=2024, postseason=0, home="BOS", away="NYK")])
    rows = [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 105, captured="2025-04-15T20:55:00Z",
              commence="2025-04-16T00:00:00Z")]
    quotes, _ = pm.prepare(pd.DataFrame(rows), g)
    assert quotes["split"].tolist() == ["other"]


def _pipeline(rows):
    quotes, _ = pm.prepare(pd.DataFrame(rows), GAMES)
    quotes, mc = pm.match_players(quotes, BOX)
    fair = pm.pinnacle_fair(quotes)
    pairs, pc = pm.pair_with_fair(quotes, fair)
    return pm.settle(pm.add_clv(pairs, fair)), pc, mc


def test_same_line_only_and_edge_sign():
    rows = (pin("Jayson Tatum", 25.5, -120, +100)
            + [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 105),   # edge = 0.5217 * 2.05 - 1 > 0
               q("us", "fanduel", "Jayson Tatum", "under", 25.5, -135),
               q("us", "draftkings", "Jayson Tatum", "over", 26.5, 120)])  # other line: never compared
    bets, pc, _ = _pipeline(rows)
    assert pc["retail_sides_pinnacle_other_line"] == 1 and pc["retail_sides_same_line"] == 2
    p_over = (1 / (1 + 100 / 120)) / (1 / (1 + 100 / 120) + 1 / 2.0)
    over = bets[bets["side"] == "over"].iloc[0]
    assert over["p_fair"] == pytest.approx(p_over)
    assert over["edge"] == pytest.approx(p_over * 2.05 - 1)
    under = bets[bets["side"] == "under"].iloc[0]
    assert under["p_fair"] == pytest.approx(1 - p_over)
    assert under["edge"] < 0


def test_settlement_win_loss_push_void_unmatched():
    rows = (pin("Jayson Tatum", 25.5, -110, -110) + pin("Jalen Brunson", 24.5, -110, -110)
            + pin("Luka Doncic", 9.0, -110, -110, market="player_assists")
            + pin("Nobody Known", 10.5, -110, -110)
            + [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 100),     # 30 > 25.5: win, profit 1.0
               q("us", "fanduel", "Jayson Tatum", "under", 25.5, -120),   # loss
               q("us", "fanduel", "Jalen Brunson", "over", 24.5, 100),    # 0 minutes: void
               q("us", "fanduel", "Luka Doncic", "under", 9.0, 100, market="player_assists"),  # 9 = 9: push
               q("us", "fanduel", "Nobody Known", "over", 10.5, 100)])     # not in the box score: unmatched
    bets, _, mc = _pipeline(rows)
    res = dict(zip(bets["player"] + "/" + bets["side"], bets["result"]))
    assert res == {"Jayson Tatum/over": "win", "Jayson Tatum/under": "loss", "Jalen Brunson/over": "void",
                   "Luka Doncic/under": "push", "Nobody Known/over": "unmatched"}
    assert bets.loc[bets["result"] == "win", "profit"].iloc[0] == pytest.approx(1.0)
    assert bets.loc[bets["result"] == "loss", "profit"].iloc[0] == -1.0
    assert bets.loc[bets["result"].isin(["void", "push", "unmatched"]), "profit"].isna().all()
    assert mc["event_players"] == 4 and mc["event_players_matched"] == 3
    s = pm.summarise(bets)
    assert (s["n"], s["wins"], s["voids"], s["pushes"]) == (2, 1, 1, 1)
    assert s["roi"] == pytest.approx(0.0)


def test_clv_sign_and_line_moves():
    rows = (pin("Jayson Tatum", 25.5, -110, -110)
            + pin("Jayson Tatum", 25.5, -150, +130, captured=CLOSE)          # close moves towards the over
            + pin("Luka Doncic", 20.5, -110, -110)
            + pin("Luka Doncic", 21.5, -110, -110, captured=CLOSE)           # line moved up: towards an over
            + [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 105),
               q("us", "fanduel", "Jayson Tatum", "under", 25.5, -125),
               q("us", "fanduel", "Luka Doncic", "over", 20.5, 105),
               q("us", "fanduel", "Jayson Tatum", "over", 25.5, -140, captured=CLOSE)])
    bets, _, _ = _pipeline(rows)
    p_close = pm.devig_over(1 + 100 / 150, 2.3)
    early = bets[(bets["window"] == "t-3h") & (bets["player"] == "Jayson Tatum")].set_index("side")
    assert early.loc["over", "clv"] == pytest.approx(p_close - 0.5)
    assert early.loc["under", "clv"] == pytest.approx((1 - p_close) - 0.5)
    assert early.loc["over", "clv"] > 0 > early.loc["under", "clv"]
    luka = bets[bets["player"] == "Luka Doncic"].iloc[0]
    assert np.isnan(luka["clv"]) and luka["clv_status"] == "line moved" and luka["line_moved_toward"] == 1.0
    late = bets[bets["window"] == "close"].iloc[0]
    assert np.isnan(late["clv"]) and late["clv_status"] == "n/a (close bet)"


def test_capture_gap_drops_pair():
    rows = (pin("Jayson Tatum", 25.5, -110, -110, captured="2024-11-01T20:40:00Z")
            + [q("us", "fanduel", "Jayson Tatum", "over", 25.5, 105, captured="2024-11-01T21:00:00Z")])
    _, pc, _ = _pipeline(rows)
    assert pc["same_line_sides_dropped_capture_gap"] == 1 and pc["same_line_sides_used"] == 0


def test_cluster_bootstrap():
    lo, hi = pm.cluster_ratio_ci(np.full(40, 0.25), np.ones(40), np.repeat(np.arange(10), 4), n_boot=200)
    assert lo == pytest.approx(0.25) and hi == pytest.approx(0.25)
    x = np.r_[np.ones(50), -np.ones(50)]
    lo, hi = pm.cluster_ratio_ci(x, np.ones(100), np.arange(100), n_boot=2000)
    assert lo < 0 < hi


def test_bar_needs_n_roi_and_clv():
    base = {"n": 600, "roi_lo": 0.01, "clv_lo": 0.001}
    assert pm.meets_bar(base)
    assert not pm.meets_bar(base | {"n": 499})
    assert not pm.meets_bar(base | {"roi_lo": -0.001})
    assert not pm.meets_bar(base | {"clv_lo": np.nan})


def test_read_files_and_end_to_end(tmp_path):
    root = tmp_path / "props"

    def write(region, captured, books, market="player_points"):
        d = root / region / "2024-11-01"
        d.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": captured, "data": {
            "id": "e1", "commence_time": TIP, "home_team": "Boston Celtics", "away_team": "New York Knicks",
            "bookmakers": [{"key": k, "last_update": captured,
                            "markets": [{"key": market, "last_update": captured,
                                         "outcomes": [{"name": s, "description": "Jayson Tatum", "price": p, "point": 25.5}
                                                      for s, p in outs]}]} for k, outs in books]}}
        stamp = captured.replace("-", "").replace(":", "")[:13]
        (d / f"event_e1_{market}_{stamp}.json").write_text(json.dumps(payload))

    write("eu", T3H, [("pinnacle", [("Over", -110), ("Under", -110)])])
    write("us", T3H, [("fanduel", [("Over", 120), ("Under", -150)])])
    write("eu", CLOSE, [("pinnacle", [("Over", -130), ("Under", 110)])])
    write("uk", T3H, [])
    raw, rc = legacy_props.read_files(root)
    assert rc == {"files": 4, "files_without_bookmakers": 1}
    res = pm.run(raw, rc, GAMES, BOX)
    pairs = res["pairs"]
    over = pairs[pairs["side"] == "over"].iloc[0]
    assert over["edge"] == pytest.approx(0.5 * 2.2 - 1) and over["result"] == "win"
    assert over["clv"] == pytest.approx(pm.devig_over(1 + 100 / 130, 2.1) - 0.5)
    bar = res["bar"]
    assert set(bar["threshold"]) == {0.02, 0.03, 0.05, 0.08} and not bar["meets_bar"].any()
    md = pm.report_markdown(res)
    assert "fanduel" in md and "Pre-registered cells" in md
