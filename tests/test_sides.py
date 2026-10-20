"""Experiment 5 (spreads and moneyline): consensus, grading arithmetic, calibration, leakage."""

import json

import numpy as np
import pandas as pd
import pytest

from nbatotals import params as params_io
from nbatotals.evaluate import backtest, leakage, market, metrics, sides
from nbatotals.evaluate.adapters import legacy_multiregion as mr
from nbatotals.model import registry
from tests.fixtures import synthetic


def side_quotes(market_name, rows):
    return pd.DataFrame([dict(game_id=g, book=b, market=market_name, anchor=a, line=line, home_price=h, away_price=w)
                         for g, b, a, line, h, w in rows])


def test_spreads_consensus_rules():
    prm = params_io.load()
    odds = side_quotes("spreads", [
        (1, "a", "true_close", -4.5, 1.91, 1.91),
        (1, "b", "true_close", -5.0, 1.87, 1.95),
        (1, "c", "true_close", -5.0, 1.95, 1.87),
        (1, "d", "true_close", 9.0, 1.91, 1.91),    # 14 points from the median: dropped by the outlier rule
        (1, "e", "true_close", -5.5, 1.90, None),   # missing price: ignored
        (2, "a", "true_close", 3.0, 1.91, 1.91),    # two books only: not scored
        (2, "b", "true_close", 3.5, 1.91, 1.91),
    ])
    c = market.consensus_spreads(odds, prm).set_index("game_id")
    assert list(c.index) == [1]
    row = c.loc[1]
    assert row["books"] == 3 and row["home_spread"] == -5.0
    assert row["line"] == 5.0  # the home margin the market implies
    p = [0.5, (1 / 1.87) / (1 / 1.87 + 1 / 1.95), (1 / 1.95) / (1 / 1.95 + 1 / 1.87)]
    assert row["p_over"] == pytest.approx(sum(p) / 3)
    assert row["p_under"] == pytest.approx(1 - row["p_over"])
    assert row["over_price"] == 1.91 and row["under_price"] == 1.91


def test_h2h_devig_is_multiplicative_mean_over_books():
    prm = params_io.load()
    odds = side_quotes("h2h", [
        (1, "a", "true_close", None, 1.50, 2.70),
        (1, "b", "true_close", None, 1.45, 2.85),
        (1, "c", "true_close", None, 1.52, 2.60),
    ])
    row = market.consensus_h2h(odds, prm).iloc[0]
    expected = np.mean([(1 / h) / (1 / h + 1 / a) for h, a in ((1.50, 2.70), (1.45, 2.85), (1.52, 2.60))])
    assert row["p_over"] == pytest.approx(expected)
    assert row["over_price"] == 1.50 and row["under_price"] == 2.70  # medians
    assert np.isnan(row["line"])
    # a fair two-way price devigs to itself
    fair = market.consensus_h2h(side_quotes("h2h", [(1, b, "true_close", None, 1.25, 5.0) for b in "abc"]), prm)
    assert fair["p_over"].iloc[0] == pytest.approx(0.8)


def _wide(rows):
    """Wide consensus rows: (game_id, anchor, implied home margin, p_home, home price, away price)."""
    cons = pd.DataFrame([dict(game_id=g, anchor=a, books=3, line=line, p_over=p, p_under=1 - p, over_price=h,
                              under_price=w) for g, a, line, p, h, w in rows])
    return market.wide(cons)


def test_spread_push_cover_and_roi_arithmetic():
    pred = pd.DataFrame({"game_id": [1, 2, 3, 4], "season": 2022, "proj": [6.0, 6.0, 1.0, 6.0],
                         "actual": [4.0, 5.0, 2.0, 3.0]})
    w = _wide([
        (1, "true_close", 3.5, 0.5, 1.90, 1.92),  # home -3.5, model +6: bet home; won by 4: covers
        (2, "true_close", 5.0, 0.5, 1.90, 1.92),  # home -5, won by 5: push
        (3, "true_close", 2.5, 0.48, 1.95, 1.87), # model +1 < 2.5: bet away; home won by 2: away covers
        (4, "true_close", 3.5, 0.52, 1.88, 1.94), # bet home; home won by 3: loses
    ])
    d = backtest._bets(pred, w, "true_close", "proj", sides.SPREADS).set_index("game_id")
    assert list(d["over"]) == [True, True, False, True]
    assert list(d["push"]) == [False, True, False, False]
    assert d.loc[1, "win"] and d.loc[3, "win"] and not d.loc[4, "win"]
    assert d.loc[1, "fair_ret"] == pytest.approx(1 / 0.5 - 1)
    assert d.loc[1, "real_ret"] == pytest.approx(0.90)
    assert d.loc[3, "p_side"] == pytest.approx(0.52) and d.loc[3, "real_ret"] == pytest.approx(0.87)
    assert d.loc[4, "fair_ret"] == -1.0 and d.loc[4, "real_ret"] == -1.0
    g = backtest._grade(d.reset_index(), "true_close", sides.SPREADS)
    assert (g["bets"], g["pushes"], g["n"], g["wins"]) == (4, 1, 3, 2)
    assert g["real_roi"] == pytest.approx((0.90 + 0.87 - 1) / 3)


def test_spread_clv_sign_in_points_and_cents():
    pred = pd.DataFrame({"game_id": [1, 2], "season": 2022, "proj": [8.0, -2.0], "actual": [0.0, 0.0]})
    w = _wide([
        (1, "opening", 3.0, 0.5, 1.91, 1.91), (1, "true_close", 4.5, 0.5, 1.91, 1.91),  # home bet, home -3 -> -4.5
        (2, "opening", 3.0, 0.5, 1.91, 1.91), (2, "true_close", 4.5, 0.5, 1.91, 1.91),  # away bet, same move
    ])
    d = backtest._bets(pred, w, "opening", "proj", sides.SPREADS).set_index("game_id")
    assert d.loc[1, "clv_pts"] == pytest.approx(1.5) and d.loc[2, "clv_pts"] == pytest.approx(-1.5)
    assert d.loc[1, "clv_cents"] > 0 > d.loc[2, "clv_cents"]
    # cents use the pre-registered margin SD of 12 points
    expected = 100 * (metrics.prob_over_at(np.array([3.0]), np.array([4.5]), np.array([0.5]), sd=12.0)[0] - 0.5)
    assert d.loc[1, "clv_cents"] == pytest.approx(expected)


def test_h2h_bets_returns_and_clv():
    pred = pd.DataFrame({"game_id": [1, 2, 3], "season": 2022, "p_model": [0.70, 0.30, 0.61],
                         "home_win": [True, True, False], "both_10": True})
    w = _wide([
        (1, "noon", np.nan, 0.60, 1.60, 2.40), (1, "true_close", np.nan, 0.64, 1.55, 2.50),
        (2, "noon", np.nan, 0.40, 2.40, 1.60), (2, "true_close", np.nan, 0.38, 2.50, 1.55),
        (3, "noon", np.nan, 0.60, 1.60, 2.40), (3, "true_close", np.nan, 0.60, 1.60, 2.40),
    ])
    d = sides._bets_h2h(pred, w, "noon", "p_model").set_index("game_id")
    assert list(d["over"]) == [True, False, True]  # home, away, home
    assert list(d["win"]) == [True, False, False]
    assert d.loc[1, "real_ret"] == pytest.approx(0.60) and d.loc[1, "fair_ret"] == pytest.approx(1 / 0.6 - 1)
    assert d.loc[2, "p_side"] == pytest.approx(0.60) and d.loc[2, "real_ret"] == -1.0
    assert d.loc[1, "clv_cents"] == pytest.approx(4.0)   # home 0.60 -> 0.64
    assert d.loc[2, "clv_cents"] == pytest.approx(2.0)   # away 0.60 -> 0.62
    assert d.loc[3, "clv_cents"] == pytest.approx(0.0)
    # thresholds are strict: |edge| > t
    assert list(sides._h2h_select(d.reset_index(), 0.02)["game_id"]) == [1, 2]
    assert list(sides._h2h_select(d.reset_index(), 0.11)["game_id"]) == []


def test_brier_log_loss_and_logistic_fits():
    assert metrics.brier([0.7], [1])[0] == pytest.approx(0.09)
    assert metrics.log_loss([0.7], [0])[0] == pytest.approx(-np.log(0.3))
    rng = np.random.default_rng(1)
    m = rng.normal(0, 10, 40_000)
    y = rng.random(40_000) < 1 / (1 + np.exp(-m / 8.0))
    assert metrics.fit_logistic_scale(m, y) == pytest.approx(8.0, rel=0.05)
    x1, x2 = rng.normal(size=40_000), rng.normal(size=40_000)
    y = rng.random(40_000) < 1 / (1 + np.exp(-(0.3 + 1.0 * x1 + 0.0 * x2)))
    r = metrics.logistic_regression(y, {"a": x1, "b": x2})
    assert r["a"]["coef"] == pytest.approx(1.0, abs=0.05) and r["b"]["lo"] < 0 < r["b"]["hi"]
    assert r["const"]["coef"] == pytest.approx(0.3, abs=0.05)


def _write_side(root, market_name, game, bucket, polled, commence, books):
    d = root / "season=2023-24" / "date=2023-11-01" / f"nba_game_id={game}" / f"bucket={bucket}"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": {"timestamp": polled, "bucket": bucket, "market": market_name},
               "event": {"id": f"ev{game}", "commence_time": commence, "home_team": "Boston Celtics",
                         "away_team": "New York Knicks"},
               "bookmakers": [{"key": k, "last_update": polled, "market": {"key": market_name, "outcomes": o}}
                              for k, o in books]}
    (d / f"{market_name}.json").write_text(json.dumps(payload))


def test_side_quotes_map_outcomes_by_team_name(tmp_path):
    games = pd.DataFrame([dict(id=1, game_date="2023-11-01", season=2023, home="BOS", away="NYK")])
    bos, nyk = "Boston Celtics", "New York Knicks"
    _write_side(tmp_path, "spreads", 1, "true_close", "2023-11-01T23:15:00Z", "2023-11-01T23:30:00Z", [
        # away listed first
        ("a", [{"name": nyk, "price": 105, "point": 6.5}, {"name": bos, "price": -125, "point": -6.5}]),
        # points disagree
        ("b", [{"name": bos, "price": -110, "point": -6.0}, {"name": nyk, "price": -110, "point": 5.5}]),
    ])
    _write_side(tmp_path, "h2h", 1, "true_close", "2023-11-01T23:15:00Z", "2023-11-01T23:30:00Z", [
        ("a", [{"name": nyk, "price": 220}, {"name": bos, "price": -270}]),
        ("b", [{"name": bos, "price": -250}, {"name": nyk, "price": 200}, {"name": "Draw", "price": 1500}]),
    ])
    sp, c = mr.side_quotes(mr.read_files(tmp_path, market="spreads"), games, "spreads")
    assert c["book_rows_without_a_clean_quote"] == 1 and list(sp["book"]) == ["a"]
    assert sp["line"].iloc[0] == -6.5
    assert sp["home_price"].iloc[0] == pytest.approx(1 + 100 / 125) and sp["away_price"].iloc[0] == pytest.approx(2.05)
    ml, c = mr.side_quotes(mr.read_files(tmp_path, market="h2h"), games, "h2h")
    assert c["book_rows_without_a_clean_quote"] == 1 and list(ml["book"]) == ["a"]
    assert ml["home_price"].iloc[0] == pytest.approx(1 + 100 / 270) and ml["away_price"].iloc[0] == pytest.approx(3.2)


@pytest.fixture(scope="module")
def league():
    return synthetic.generate(seasons=(2021, 2022), days=60, games_per_day=6, seed=7)


@pytest.mark.parametrize("name", ["pace_eff", "elo_total"])
def test_predict_margin_passes_truncation(league, name):
    games, box = league
    prm = params_io.load()
    sample = leakage.stratified_sample(games, per_cell=10)
    res = leakage.projector_truncation_check(registry.get(name), games, box, prm, sample,
                                             method="predict_margin", column="margin_proj")
    assert res["mismatches"] == []


def test_margin_calibration_uses_earlier_seasons_only(league):
    games, box = league
    prm = params_io.load()
    proj = registry.get("elo_total")
    pred, fits = sides.margin_predictions(games, box, prm, proj, test_seasons=(2022,))
    # rewriting every 2022 result changes no fitted calibration constant
    g2 = games.copy()
    m = g2["season"] == 2022
    g2.loc[m, ["home_pts", "away_pts"]] = g2.loc[m, ["away_pts", "home_pts"]].to_numpy()
    _, fits2 = sides.margin_predictions(g2, box, prm, proj, test_seasons=(2022,))
    for c in ("h", "s", "margin_k", "h_default", "s_default"):
        assert fits[c].iloc[0] == fits2[c].iloc[0]
    assert set(pred["season"]) == {2022}
    assert np.allclose(pred["p_model"], 1 / (1 + np.exp(-pred["proj"] / fits["s"].iloc[0])))
    assert np.allclose(pred["proj"] - pred["proj_raw"], fits["h"].iloc[0])
