"""Experiment 3 arithmetic on synthetic quotes: devig, edge, conversion, settlement, CLV, hygiene, lag."""

import json
from statistics import NormalDist

import numpy as np
import pandas as pd
import pytest

from nbatotals.evaluate import market, metrics
from nbatotals.evaluate import market_vs_market as mvm
from nbatotals.evaluate.adapters import legacy_multiregion as mr

T0 = pd.Timestamp("2023-11-01T23:30:00Z")
LEADS = {"opening": 1440, "noon": 600, "afternoon": 300, "early_evening": 180, "late_evening": 120,
         "near_close": 60, "true_close": 15}


def dec(american):
    return 1 + (american / 100 if american > 0 else 100 / -american)


def q(game, mkt, bucket, book, a_point, a_am, b_am, b_point=None, age_min=2.0, season="2023-24", lead=None,
      names_ok=True):
    polled = T0 - pd.Timedelta(minutes=lead if lead is not None else LEADS[bucket])
    if b_point is None and a_point is not None:
        b_point = a_point if mkt == "totals" else -a_point
    return dict(game_id=game, season=season, market=mkt, bucket=bucket, book=book, event_id=f"e{game}",
                polled_utc=polled, commence_utc=T0, last_update=polled - pd.Timedelta(minutes=age_min),
                a_point=np.nan if a_point is None else float(a_point),
                b_point=np.nan if b_point is None else float(b_point),
                a_price=dec(a_am), b_price=dec(b_am), names_ok=names_ok)


GAMES = pd.DataFrame([dict(id=1, season=2023, status="final", postseason=0, home_pts=112, away_pts=109),
                      dict(id=2, season=2023, status="final", postseason=0, home_pts=100, away_pts=120)])


# ------------------------------------------------------------ arithmetic

def test_devig_two_way_matches_consensus_rule():
    assert market.devig_two_way(dec(-110), dec(-110)) == pytest.approx(0.5)
    a, b = dec(-150), dec(130)
    assert market.devig_two_way(a, b) == pytest.approx((1 / a) / (1 / a + 1 / b))
    assert market.devig_two_way(a, b) + market.devig_two_way(b, a) == pytest.approx(1.0)


def test_edge_is_p_fair_times_decimal_minus_one():
    e_a, e_b = mvm.edges(0.5, 2.10, 1.80)
    assert e_a == pytest.approx(0.05) and e_b == pytest.approx(-0.10)
    e_a, e_b = mvm.edges(0.6, 1.5, 2.6)
    assert e_a == pytest.approx(-0.10) and e_b == pytest.approx(0.04)


def test_settlement_totals_spreads_h2h_and_pushes():
    # totals: 221 points
    assert mvm.settle(["totals"] * 2, ["a", "b"], [220.5, 220.5], [111] * 2, [110] * 2).tolist() == [1.0, 0.0]
    r = mvm.settle(["totals", "totals"], ["a", "b"], [221.0, 221.5], [111, 111], [110, 110])
    assert np.isnan(r[0]) and r[1] == 1.0
    # spreads: home wins by 6; a_point is the home handicap
    assert mvm.settle(["spreads"] * 3, ["a", "a", "b"], [-5.5, -6.5, -5.5], [106] * 3, [100] * 3).tolist() == [1.0, 0.0, 0.0]
    assert np.isnan(mvm.settle(["spreads"], ["b"], [-6.0], [106], [100])[0])


def test_settlement_spread_underdog_cover_sign():
    # home +3.5, home loses by 3: home covers (a wins), away (b) loses
    assert mvm.settle(["spreads", "spreads"], ["a", "b"], [3.5, 3.5], [100, 100], [103, 103]).tolist() == [1.0, 0.0]
    assert mvm.settle(["h2h", "h2h"], ["a", "b"], [np.nan, np.nan], [100, 100], [103, 103]).tolist() == [0.0, 1.0]


def test_move_prob_same_line_is_identity_and_direction():
    p = mvm.move_prob_a(["totals", "spreads", "h2h"], [0.53, 0.47, 0.6], [220.0, -5.0, np.nan], [220.0, -5.0, np.nan])
    assert p == pytest.approx([0.53, 0.47, 0.6])
    up = mvm.move_prob_a(["totals"], [0.5], [220.0], [220.5])[0]
    mu = 220.0
    assert up == pytest.approx(1 - NormalDist(mu, 18.0).cdf(220.5))
    # home -5 at 50% -> home -5.5 is harder: P(margin > 5.5) with margin ~ N(5, 13.5)
    harder = mvm.move_prob_a(["spreads"], [0.5], [-5.0], [-5.5])[0]
    assert harder == pytest.approx(1 - NormalDist(5.0, 13.5).cdf(5.5))
    assert harder < 0.5


def test_line_move_sign():
    # over taken at 220, Pinnacle closes 222: +2 for the over, -2 for the under
    assert mvm.line_move(["totals", "totals"], ["a", "b"], [220, 220], [222, 222]).tolist() == [2.0, -2.0]
    # home +5.5 taken, home closes +4.5: home got a point (+1); away -5.5 taken vs close -4.5 for away: -1
    assert mvm.line_move(["spreads", "spreads"], ["a", "b"], [5.5, 5.5], [4.5, 4.5]).tolist() == [1.0, -1.0]
    assert np.isnan(mvm.line_move(["h2h"], ["a"], [np.nan], [np.nan])[0])


def test_cluster_bootstrap_resamples_groups():
    x = np.array([1.0, 1.0, -1.0, -1.0])
    lo, hi, se = metrics.bootstrap_cluster_mean_ci(x, [1, 1, 2, 2], n_boot=2000)
    # only two clusters with means +1 and -1: resampled means are -1, 0 or +1
    assert lo == -1.0 and hi == 1.0 and se > 0
    lo2, hi2, _ = metrics.bootstrap_cluster_mean_ci(np.arange(100.0), np.arange(100), n_boot=2000)
    assert lo2 < 49.5 < hi2


# ------------------------------------------------------------ hygiene

def test_clean_drops_by_reason():
    rows = [
        q(1, "totals", "noon", "fanduel", 220.5, -110, -110),                       # kept
        q(1, "totals", "noon", "bovada", 220.5, -110, -110, age_min=31),            # stale
        q(1, "totals", "noon", "betus", 220.5, -110, -110, age_min=-1),             # last_update after poll
        q(1, "spreads", "noon", "fanduel", -5.5, -110, -110, b_point=5.0),          # spread points not opposite
        q(1, "h2h", "noon", "fanduel", None, -150, 130, names_ok=False),            # wrong outcome names
        q(1, "totals", "noon", "fanduel", 221.0, -110, -110),                       # duplicate
        q(1, "totals", "opening", "fanduel", 220.5, -110, -110, lead=-5),           # polled after tip
    ]
    late = q(1, "totals", "afternoon", "fanduel", 220.5, -110, -110)
    late["last_update"] = T0 + pd.Timedelta(minutes=1)
    rows.append(late)
    kept, drops = mvm.clean(pd.DataFrame(rows))
    assert len(kept) == 1 and kept.iloc[0]["book"] == "fanduel" and kept.iloc[0]["a_point"] == 220.5
    by = drops.groupby("reason")["n"].sum().to_dict()
    assert by == {"stale (> 30 min before poll)": 1, "last_update after poll": 1, "malformed quote": 2,
                  "duplicate (game, bucket, market, book)": 1, "file polled at or after tip": 1,
                  "last_update at or after tip": 1}
    kept10, _ = mvm.clean(pd.DataFrame([q(1, "totals", "noon", "a", 220.5, -110, -110, age_min=15)]),
                          stale_minutes=10)
    assert kept10.empty


# ------------------------------------------------------------ pairing, bets, CLV end to end

def _game1():
    return [
        # Pinnacle noon: over 220.5 at -105 / -115; true close moves to 222.5 at -110 / -110
        q(1, "totals", "noon", "pinnacle", 220.5, -105, -115),
        q(1, "totals", "true_close", "pinnacle", 222.5, -110, -110),
        q(1, "totals", "noon", "softbook", 220.5, 110, -140),     # over at +110: edge positive
        q(1, "totals", "noon", "slowbook", 221.0, 105, -135),     # half a point off: converted mode only
        q(1, "totals", "noon", "farbook", 222.0, 105, -135),      # 1.5 points off: never compared
        # h2h: Pinnacle home -150 / +130; soft book home -150 / +150 -> bet away
        q(1, "h2h", "noon", "pinnacle", None, -150, 130),
        q(1, "h2h", "true_close", "pinnacle", None, -160, 140),
        q(1, "h2h", "noon", "softbook", None, -150, 150),
        # spreads: Pinnacle home -2.5 at -110/-110; soft book home -2.5 at +105/-125 -> bet home
        q(1, "spreads", "noon", "pinnacle", -2.5, -110, -110),
        q(1, "spreads", "true_close", "pinnacle", -3.5, -110, -110),
        q(1, "spreads", "noon", "softbook", -2.5, 105, -125),
    ]


def test_pair_bets_settlement_and_clv():
    kept, _ = mvm.clean(pd.DataFrame(_game1()))
    p = mvm.settle_frame(mvm.pair(kept, "exact"), GAMES)
    assert set(zip(p["market"], p["book"])) == {("totals", "softbook"), ("h2h", "softbook"), ("spreads", "softbook")}

    t = p[p["market"] == "totals"].iloc[0]
    p_fair_over = market.devig_two_way(dec(-105), dec(-115))
    assert t["side"] == "a" and t["p_fair"] == pytest.approx(p_fair_over)
    assert t["edge"] == pytest.approx(p_fair_over * 2.10 - 1)
    # actual total 221 > 220.5: over wins at +110
    assert t["win"] == 1.0 and t["profit"] == pytest.approx(1.10)
    p_close_over = 1 - NormalDist(222.5, 18.0).cdf(220.5)  # close 50% at 222.5, moved to the bet's 220.5
    assert t["clv_cents"] == pytest.approx(100 * (p_close_over - p_fair_over))
    assert t["line_move"] == pytest.approx(2.0)
    assert t["edge_at_close"] == pytest.approx(p_close_over * 2.10 - 1)

    h = p[p["market"] == "h2h"].iloc[0]
    p_home = market.devig_two_way(dec(-150), dec(130))
    assert h["side"] == "b" and h["p_fair"] == pytest.approx(1 - p_home)
    assert h["edge"] == pytest.approx((1 - p_home) * 2.5 - 1)
    assert h["win"] == 0.0 and h["profit"] == -1.0  # home won 112-109
    assert h["clv_cents"] == pytest.approx(100 * ((1 - market.devig_two_way(dec(-160), dec(140))) - (1 - p_home)))

    s = p[p["market"] == "spreads"].iloc[0]
    assert s["side"] == "a" and s["edge"] == pytest.approx(0.5 * 2.05 - 1)
    assert s["win"] == 1.0  # home by 3 covers -2.5
    assert s["line_move"] == pytest.approx(1.0)  # took -2.5, closed -3.5: a point better
    p_close_home = 1 - NormalDist(3.5, 13.5).cdf(2.5)
    assert s["clv_cents"] == pytest.approx(100 * (p_close_home - 0.5))


def test_bet_polled_after_the_close_gets_no_clv():
    rows = [q(1, "totals", "near_close", "pinnacle", 220.5, -105, -115, lead=10),
            q(1, "totals", "true_close", "pinnacle", 222.5, -110, -110),
            q(1, "totals", "near_close", "softbook", 220.5, 110, -140, lead=10)]
    kept, _ = mvm.clean(pd.DataFrame(rows))
    p = mvm.pair(kept, "exact")
    assert len(p) == 1 and bool(p["polled_after_close"].iloc[0]) and np.isnan(p["clv_cents"].iloc[0])
    assert p["edge"].iloc[0] > 0  # still a bet for ROI


def test_converted_mode_includes_half_point_only():
    kept, _ = mvm.clean(pd.DataFrame(_game1()))
    p = mvm.pair(kept, "converted")
    tot = p[p["market"] == "totals"].set_index("book")
    assert set(tot.index) == {"softbook", "slowbook"}
    p_pin = market.devig_two_way(dec(-105), dec(-115))
    expect = metrics.prob_over_at(np.array([221.0]), np.array([220.5]), np.array([p_pin]), sd=18.0)[0]
    assert tot.loc["slowbook", "p_fair_a"] == pytest.approx(expect)
    assert bool(tot.loc["slowbook", "converted"]) and not bool(tot.loc["softbook", "converted"])


def test_one_bet_per_book_game_bucket_market_and_no_pinnacle_bets():
    kept, _ = mvm.clean(pd.DataFrame(_game1()))
    p = mvm.pair(kept, "exact")
    assert not p.duplicated(["game_id", "market", "bucket", "book"]).any()
    assert (p["book"] != "pinnacle").all()
    assert (p["bucket"] != "true_close").all()


def test_soft_quote_without_pinnacle_same_bucket_is_not_compared():
    rows = [q(2, "totals", "afternoon", "softbook", 230.5, 120, -150),
            q(2, "totals", "noon", "pinnacle", 230.5, -110, -110)]
    kept, _ = mvm.clean(pd.DataFrame(rows))
    assert mvm.pair(kept, "exact").empty


def test_lag_table_detects_a_book_that_copies_pinnacle_one_bucket_late():
    rng = np.random.default_rng(0)
    rows = []
    for g in range(1, 61):
        pin = 220 + np.cumsum(rng.choice([-1.0, 0.0, 1.0], size=len(mvm.ORDER)))
        for i, b in enumerate(mvm.ORDER):
            rows.append(q(g, "totals", b, "pinnacle", pin[i], -110, -110))
            rows.append(q(g, "totals", b, "laggard", pin[i - 1] if i else pin[0], -110, -110))
            rows.append(q(g, "totals", b, "copier", pin[i], -110, -110))
    kept, _ = mvm.clean(pd.DataFrame(rows))
    lt = mvm.lag_table(kept).set_index("book")
    assert lt.loc["laggard", "corr_next"] == pytest.approx(1.0)
    assert abs(lt.loc["copier", "corr_next"] - lt.loc["pinnacle (own momentum)", "corr_next"]) < 1e-9
    assert lt.loc["copier", "corr_same_period"] == pytest.approx(1.0)


def test_run_and_report_on_synthetic_games():
    rows = _game1()
    for i, r in enumerate(list(rows)):
        r2 = dict(r, game_id=2, event_id="e2")
        rows.append(r2)
    res = mvm.run(pd.DataFrame(rows), GAMES, seasons=("2023-24",))
    md = mvm.report_markdown(res)
    assert "## totals: per book, six buckets pooled" in md
    assert "Lag: Pinnacle's previous move" in md
    pooled = res["pooled"]["exact"]
    assert set(pooled["threshold"]) == set(mvm.THRESHOLDS)


# ------------------------------------------------------------ adapter for spreads and h2h

def _write(root, mkt, bucket, outcomes_by_book, polled="2023-11-01T13:30:00Z"):
    d = root / "season=2023-24" / "date=2023-11-01" / "nba_game_id=9" / f"bucket={bucket}"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": {"timestamp": polled, "bucket": bucket, "market": mkt},
               "event": {"id": "ev9", "commence_time": "2023-11-01T23:30:00Z", "home_team": "Boston Celtics",
                         "away_team": "New York Knicks"},
               "bookmakers": [{"key": k, "last_update": polled, "market": {"key": mkt, "outcomes": o}}
                              for k, o in outcomes_by_book.items()]}
    (d / f"{mkt}.json").write_text(json.dumps(payload))


def test_adapter_keeps_event_whose_commence_time_changes(tmp_path):
    out = [{"name": "Boston Celtics", "price": -200}, {"name": "New York Knicks", "price": 170}]
    _write(tmp_path, "h2h", "noon", {"pinnacle": out})
    _write(tmp_path, "h2h", "true_close", {"pinnacle": out}, polled="2023-11-02T00:00:00Z")
    p = tmp_path / "season=2023-24/date=2023-11-01/nba_game_id=9/bucket=true_close/h2h.json"
    payload = json.loads(p.read_text())
    payload["event"]["commence_time"] = "2023-11-02T00:15:00Z"  # tip delayed 45 minutes
    p.write_text(json.dumps(payload))
    raw = mr.read_market_files(tmp_path, markets=("h2h",))
    games = pd.DataFrame([dict(id=9, game_date="2023-11-01", home="BOS", away="NYK")])
    quotes, counts = mr.market_quotes(raw, games)
    assert counts["events whose commence_time changes between files"] == 1
    assert set(quotes["bucket"]) == {"noon", "true_close"}
    tc = quotes[quotes["bucket"] == "true_close"].iloc[0]
    assert tc["commence_utc"] == pd.Timestamp("2023-11-02T00:15:00Z")  # the later file keeps its own tip
    noon = quotes[quotes["bucket"] == "noon"].iloc[0]
    assert noon["commence_utc"] == pd.Timestamp("2023-11-01T23:30:00Z")  # earlier of own and latest


def test_adapter_reads_spreads_and_h2h_sides(tmp_path):
    _write(tmp_path, "spreads", "noon", {
        "pinnacle": [{"name": "New York Knicks", "price": -110, "point": 4.5},
                     {"name": "Boston Celtics", "price": -110, "point": -4.5}],
        "oddbook": [{"name": "Knicks", "price": -110, "point": 4.5},
                    {"name": "Boston Celtics", "price": -110, "point": -4.5}]})
    _write(tmp_path, "h2h", "noon", {"pinnacle": [{"name": "Boston Celtics", "price": -200},
                                                  {"name": "New York Knicks", "price": 170}]})
    raw = mr.read_market_files(tmp_path, markets=("spreads", "h2h"))
    games = pd.DataFrame([dict(id=9, game_date="2023-11-01", home="BOS", away="NYK")])
    quotes, counts = mr.market_quotes(raw, games)
    assert counts["events matched to a game"] == 1
    s = quotes[(quotes["market"] == "spreads") & (quotes["book"] == "pinnacle")].iloc[0]
    assert s["a_point"] == -4.5 and s["b_point"] == 4.5  # side a is home regardless of file order
    assert not quotes[(quotes["book"] == "oddbook")]["names_ok"].iloc[0]
    h = quotes[quotes["market"] == "h2h"].iloc[0]
    assert h["a_price"] == pytest.approx(1.5) and h["b_price"] == pytest.approx(2.7) and np.isnan(h["a_point"])
