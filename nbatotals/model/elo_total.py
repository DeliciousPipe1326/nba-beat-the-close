"""Example projector: Elo-style team ratings on totals.

Each team has a rating in points of total. A game's expected total is the
point-in-time league average total plus both teams' ratings; after each game
both teams move by K x (actual - expected). Ratings are multiplied by
`season_carry` at each new season. A margin-based Elo carries no information
about totals, so the Elo update rule is applied to the total's residual instead.
`fit` picks K from a small declared grid by RMSE on earlier seasons only.
Settings: `models.elo_total` in params.yaml.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _expected(games: pd.DataFrame, targets: pd.DataFrame, k: float, cfg: dict) -> pd.Series:
    """Expected total per target, using only games dated before each target's date."""
    hist = games[(games["status"] == "final") & games["home_pts"].notna()]
    hist = hist.sort_values(["game_date", "id"], kind="mergesort")
    by_date = {d: g for d, g in hist.groupby("game_date")}
    tg = {d: g for d, g in targets.groupby("game_date")}
    rating, season, prev_mean, cur_sum, cur_n, out = {}, None, None, 0.0, 0, {}
    for d in sorted(set(by_date) | set(tg)):
        day_season = int((tg[d] if d in tg else by_date[d])["season"].iloc[0])
        if day_season != season:
            if season is not None and cur_n:
                prev_mean = cur_sum / cur_n
            rating = {t: r * cfg["season_carry"] for t, r in rating.items()}
            season, cur_sum, cur_n = day_season, 0.0, 0
        base = cfg["fallback_total"] if prev_mean is None else prev_mean
        league = (cur_sum + cfg["league_prior_games"] * base) / (cur_n + cfg["league_prior_games"])
        for r in (tg[d].itertuples() if d in tg else ()):
            out[r.id] = league + rating.get(r.home, 0.0) + rating.get(r.away, 0.0)
        for r in (by_date[d].itertuples() if d in by_date else ()):
            actual = r.home_pts + r.away_pts
            err = actual - (league + rating.get(r.home, 0.0) + rating.get(r.away, 0.0))
            rating[r.home] = rating.get(r.home, 0.0) + k * err
            rating[r.away] = rating.get(r.away, 0.0) + k * err
            cur_sum, cur_n = cur_sum + actual, cur_n + 1
    return pd.Series(out)


class EloTotal:
    name = "elo_total"

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        cfg = params["models"]["elo_total"]
        reg = train_games[(train_games["status"] == "final") & (train_games["postseason"] == 0)]
        actual = (reg["home_pts"] + reg["away_pts"]).to_numpy(dtype=float)
        test_season = int(train_games["season"].max()) + 1
        rows = []
        for k in cfg["k_grid"]:
            e = _expected(train_games, reg, k, cfg).loc[reg["id"]].to_numpy() - actual
            rows.append({"test_season": test_season, "k": k, "train_rmse": float(np.sqrt((e ** 2).mean())),
                         "train_n": len(reg)})
        log = pd.DataFrame(rows)
        best = log.loc[log["train_rmse"].idxmin()]  # first minimum in grid order
        default = log.loc[np.isclose(log["k"], cfg["k"]), "train_rmse"]
        summary = {"train_n": len(reg), "k": float(best["k"]), "train_rmse_chosen": float(best["train_rmse"]),
                   "train_rmse_default": float(default.iloc[0]) if len(default) else float("nan")}
        return {"k": float(best["k"]), "summary": summary, "log": log}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        cfg = params["models"]["elo_total"]
        k = cfg["k"] if state is None else state["k"]
        exp = _expected(games, targets, k, cfg)
        return pd.DataFrame({"game_id": targets["id"].to_numpy(), "total_proj": exp.loc[targets["id"]].to_numpy()})
