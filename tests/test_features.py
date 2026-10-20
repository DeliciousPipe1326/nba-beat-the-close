import numpy as np
import pandas as pd
import pytest

from nbatotals import params as params_io
from nbatotals.features.pointintime import build_features
from nbatotals.model.projection import project
from tests.fixtures import synthetic


@pytest.fixture(scope="module")
def league():
    return synthetic.generate(seasons=(2021, 2022), days=60, games_per_day=8, seed=1)


@pytest.fixture(scope="module")
def prm():
    return params_io.load()


def team_history(games, box, team, before, season):
    g = games.set_index("id")
    rows = box[box["team"] == team].copy()
    rows["game_date"] = g.loc[rows["game_id"], "game_date"].to_numpy()
    rows["season"] = g.loc[rows["game_id"], "season"].to_numpy()
    at = g.loc[rows["game_id"]]
    rows["opp_pts"] = np.where(rows["is_home"] == 1, at["away_pts"], at["home_pts"])
    rows = rows[(rows["game_date"] < before) & (rows["season"] == season)]
    return rows.sort_values(["game_date", "game_id"])


def rates(rows):
    poss = rows["possessions"].sum()
    return dict(pace=48 * poss / rows["minutes"].sum(), ortg=100 * rows["pts"].sum() / poss,
                drtg=100 * rows["opp_pts"].sum() / poss)


def test_opening_night_is_pure_prior_and_resets_at_season_boundary(league, prm):
    games, box = league
    opener = games[games["game_date"] == games.loc[games["season"] == 2022, "game_date"].min()]
    f = build_features(opener, games, box, prm)
    assert (f["home_n"] == 0).all() and (f["away_n"] == 0).all()
    assert f["home_pace_season"].isna().all() and f["away_ortg_l10"].isna().all()
    for side in ("home", "away"):
        assert (f[f"{side}_pace"] == f["league_pace"]).all()
        assert (f[f"{side}_ortg"] == f["league_ortg"]).all()
        assert (f[f"{side}_drtg"] == f["league_ortg"]).all()
    # league base on opening night = the whole previous season's league average
    prev = box.merge(games[["id", "season"]], left_on="game_id", right_on="id")
    prev = prev[prev["season"] == 2021]
    assert f["league_n"].eq(0).all()
    assert f["league_pace"].iloc[0] == pytest.approx(48 * prev["possessions"].sum() / prev["minutes"].sum())
    assert f["league_ortg"].iloc[0] == pytest.approx(100 * prev["pts"].sum() / prev["possessions"].sum())


def test_first_season_falls_back_to_constants(league, prm):
    games, box = league
    opener = games[games["game_date"] == games["game_date"].min()]
    f = build_features(opener, games, box, prm)
    assert (f["league_pace"] == prm["league"]["fallback_pace"]).all()
    assert (f["league_ortg"] == prm["league"]["fallback_ortg"]).all()


def test_carryover_is_an_explicit_knob(league, prm):
    games, box = league
    p = params_io.with_overrides(prm, {"features.team_carryover_weight": 0.5})
    opener = games[games["game_date"] == games.loc[games["season"] == 2022, "game_date"].min()]
    f = build_features(opener.iloc[:1], games, box, p)
    team = opener.iloc[0]["home"]
    last = rates(team_history(games, box, team, "2099-01-01", 2021))
    assert f["home_pace"].iloc[0] == pytest.approx(0.5 * last["pace"] + 0.5 * f["league_pace"].iloc[0])
    assert f["home_drtg"].iloc[0] == pytest.approx(0.5 * last["drtg"] + 0.5 * f["league_ortg"].iloc[0])


def test_windows_blend_and_shrinkage_match_hand_computation(league, prm):
    games, box = league
    target = games[games["season"] == 2022].iloc[400]
    f = build_features(games[games["id"] == target["id"]], games, box, prm).iloc[0]
    hist = team_history(games, box, target["home"], target["game_date"], 2022)
    n = len(hist)
    assert f["home_n"] == n and n >= 10
    l3, l10, season = rates(hist.tail(3)), rates(hist.tail(10)), rates(hist)
    assert f["home_ortg_l3"] == pytest.approx(l3["ortg"])
    assert f["home_pace_l10"] == pytest.approx(l10["pace"])
    assert f["home_drtg_season"] == pytest.approx(season["drtg"])
    b = prm["features"]["blend"]
    k = prm["features"]["team_shrinkage_games"]
    blended = b["l3"] * l3["pace"] + b["l10"] * l10["pace"] + b["season"] * season["pace"]
    assert f["home_pace"] == pytest.approx((n * blended + k * f["league_pace"]) / (n + k))


def test_league_reference_uses_only_earlier_rows(league, prm):
    games, box = league
    target = games[games["season"] == 2022].iloc[300]
    f = build_features(games[games["id"] == target["id"]], games, box, prm).iloc[0]
    rows = box.merge(games[["id", "game_date", "season"]], left_on="game_id", right_on="id")
    cur = rows[(rows["season"] == 2022) & (rows["game_date"] < target["game_date"])]
    prev = rows[rows["season"] == 2021]
    k = prm["league"]["shrinkage_team_games"]
    n = len(cur)
    raw = 48 * cur["possessions"].sum() / cur["minutes"].sum()
    base = 48 * prev["possessions"].sum() / prev["minutes"].sum()
    assert f["league_n"] == n
    assert f["league_pace"] == pytest.approx((n * raw + k * base) / (n + k))


def test_rest_and_b2b_come_from_schedule_only(league, prm):
    games, box = league
    sample = games[games["season"] == 2022].iloc[::7]
    full = build_features(sample, games, box, prm)
    schedule_only = games.assign(home_pts=np.nan, away_pts=np.nan)
    empty_box = box.iloc[0:0]
    blind = build_features(sample, schedule_only, empty_box, prm)
    for col in ("home_rest_days", "away_rest_days", "home_b2b", "away_b2b"):
        pd.testing.assert_series_equal(full[col], blind[col])
    # hand check one back-to-back
    row = full[full["home_b2b"]].iloc[0]
    played = games[((games["home"] == row["home"]) | (games["away"] == row["home"]))
                   & (games["game_date"] < row["game_date"]) & (games["season"] == row["season"])]
    gap = (pd.Timestamp(row["game_date"]) - pd.Timestamp(played["game_date"].max())).days
    assert gap == 1 and row["home_rest_days"] == 0


def test_home_away_split_uses_only_matching_venue(league, prm):
    games, box = league
    p = params_io.with_overrides(prm, {"features.home_away_split": True})
    target = games[games["season"] == 2022].iloc[450]
    f = build_features(games[games["id"] == target["id"]], games, box, p).iloc[0]
    hist = team_history(games, box, target["home"], target["game_date"], 2022)
    home_only = hist[hist["is_home"] == 1]
    assert f["home_n"] == len(home_only)
    assert f["home_ortg_season"] == pytest.approx(rates(home_only)["ortg"])


def test_projection_formula(prm):
    f = pd.DataFrame([dict(game_id=1, league_pace=100.0, league_ortg=110.0, home_pace=102.0, away_pace=97.0,
                           home_ortg=115.0, home_drtg=108.0, away_ortg=111.0, away_drtg=113.0,
                           home_b2b=True, away_b2b=False)])
    p = params_io.with_overrides(prm, {"projection.pace_weight": 1.0, "projection.home_court_total": 1.5,
                               "projection.b2b_total_per_team": -2.0})
    out = project(f, p).iloc[0]
    pace = 100 + (2 - 3)
    off_home = 110 + 5 + 3
    off_away = 110 + 1 - 2
    assert out["pace_proj"] == pytest.approx(pace)
    assert out["total_proj"] == pytest.approx(pace * (off_home + off_away) / 100 + 1.5 - 2.0)


def test_params_validation(prm):
    with pytest.raises(ValueError):
        params_io.with_overrides(prm, {"features.blend": {"l3": 0.5, "l10": 0.5, "season": 0.5}})
    with pytest.raises(KeyError):
        params_io.with_overrides(prm, {"projection.intercept": 1.0})
