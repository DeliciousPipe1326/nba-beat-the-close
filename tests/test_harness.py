import numpy as np
import pandas as pd
import pytest

from nbatotals import params as P
from nbatotals.evaluate import backtest, fit, metrics
from nbatotals.features.pointintime import build_features
from nbatotals.model.projection import project
from tests.fixtures import synthetic


def test_wilson_known_value():
    lo, hi = metrics.wilson(55, 100)
    assert lo == pytest.approx(0.4524, abs=1e-4) and hi == pytest.approx(0.6438, abs=1e-4)


def test_prob_over_at_reproduces_close_and_moves_with_line():
    p = metrics.prob_over_at(np.array([220.0, 222.0]), np.array([220.0, 220.0]), np.array([0.52, 0.52]))
    assert p[0] == pytest.approx(0.52)
    assert p[1] < 0.52


def test_blend_grid_and_size():
    g = fit.blend_grid()
    assert len(g) == 66 and len(set(g)) == 66
    assert all(abs(sum(b) - 1) < 1e-9 for b in g)
    assert fit.grid_size() == 34_650


def test_closed_form_rmse_matches_direct_projection():
    games, box = synthetic.generate(seasons=(2021, 2022), days=40, games_per_day=6, seed=2)
    base = P.load()
    log, chosen, feats = fit.search(games, box, base, test_seasons=(2022,))
    row = log[(log.l3 == 0.2) & (log.l10 == 0.3) & (log.shrinkage == 10) & (log.pace_weight == 0.75)
              & (log.home_court_total == 1) & (log.b2b_total_per_team == -2)].iloc[0]
    prm = fit.params_for(base, row)
    targets = games[games.season == 2021]
    f = build_features(targets, games, box, prm)
    e = project(f, prm)["total_proj"].to_numpy() - (targets.home_pts + targets.away_pts).to_numpy()
    assert row.train_rmse == pytest.approx(np.sqrt((e ** 2).mean()), rel=1e-10)
    assert chosen[2022].train_rmse == log[log.test_season == 2022].train_rmse.min()


def test_grading_rules_on_hand_built_bets():
    pred = pd.DataFrame({"game_id": [1, 2, 3, 4], "season": 2022, "proj": [230.0, 210.0, 225.0, 220.0],
                         "proj_default": 220.0, "actual": [228, 215, 224, 220], "both_10": True})
    w = pd.DataFrame({"game_id": [1, 2, 3, 4], "line_afternoon": [225.0, 212.0, 224.0, 221.0],
                      "p_over_afternoon": 0.5, "p_under_afternoon": 0.5, "over_price_afternoon": 1.91,
                      "under_price_afternoon": 1.91})
    d = backtest._bets(pred, w, "afternoon", "proj", backtest.TEMPORAL)
    # game 1: over 225, actual 228 -> win; game 2: under 212, actual 215 -> loss;
    # game 3: over 224, actual 224 -> push; game 4: under 221, actual 220 -> win
    assert d["over"].tolist() == [True, False, True, False]
    assert d["push"].tolist() == [False, False, True, False]
    r = backtest._grade(d, "afternoon", backtest.TEMPORAL)
    assert (r["n"], r["wins"], r["pushes"]) == (3, 2, 1)
    assert r["fair_roi"] == pytest.approx((1 + 1 - 1) / 3)
    assert r["real_roi"] == pytest.approx((0.91 + 0.91 - 1) / 3)


def test_clv_sign():
    pred = pd.DataFrame({"game_id": [1, 2], "season": 2022, "proj": [230.0, 200.0], "proj_default": 0.0,
                         "actual": [0, 0], "both_10": True})
    w = pd.DataFrame({"game_id": [1, 2], "line_early": [220.0, 220.0], "line_afternoon": [222.0, 222.0],
                      "p_over_early": 0.5, "p_under_early": 0.5, "over_price_early": 1.91, "under_price_early": 1.91,
                      "p_over_afternoon": 0.5, "p_under_afternoon": 0.5})
    d = backtest._bets(pred, w, "early", "proj", backtest.TEMPORAL)
    assert d["clv_pts"].tolist() == [2.0, -2.0]  # over gained 2 points, under lost 2
    assert d["clv_cents"].iloc[0] > 0 > d["clv_cents"].iloc[1]


def test_pinnacle_grading_at_an_earlier_anchor():
    """Graded against Pinnacle's own line and price at the anchor asked for; default is the reference."""
    pred = pd.DataFrame({"game_id": [1, 2], "season": 2022, "proj": [230.0, 210.0], "proj_default": 0.0,
                         "actual": [226, 215], "both_10": True})
    rows = []
    for gid, early, late in ((1, 224.0, 228.0), (2, 216.0, 213.0)):
        for anchor, line, price in (("early", early, 2.0), ("afternoon", late, 1.9)):
            rows.append(dict(game_id=gid, book="pinnacle", market="totals", anchor=anchor, line=line,
                             over_price=price, under_price=price))
    odds = pd.DataFrame(rows)
    base = P.load()
    early = backtest.pinnacle_grading(pred, odds, base, backtest.TEMPORAL, anchor="early")
    late = backtest.pinnacle_grading(pred, odds, base, backtest.TEMPORAL)
    e = early[(early.threshold == 0) & (early.season == "pooled")].iloc[0]
    l_ = late[(late.threshold == 0) & (late.season == "pooled")].iloc[0]
    # early: over 224 (226 wins), under 216 (215 wins); afternoon: over 228 (loses), under 213 (loses)
    assert (e["n"], e["wins"]) == (2, 2) and e["real_roi"] == pytest.approx(1.0)
    assert (l_["n"], l_["wins"]) == (2, 0) and l_["real_roi"] == pytest.approx(-1.0)
