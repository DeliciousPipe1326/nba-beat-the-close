"""Experiment 2 projector: lineup-aware pace x efficiency (not pre-registered for the main test).

The pace_eff formula shape with each team's pace, offence and defence taken from
that game's projected minutes and its players' ratings instead of box-score
windows. Spec: docs/experiments/info_latency/PREREGISTRATION.md, "Phase B".

For game G on Eastern date D:

    O, Dv, P  = minutes-weighted team values over G's projected players:
                O = 5·Σ m·oepm / Σ m, Dv = 5·Σ m·depm / Σ m, P = Σ m·p_t_poss_48 / Σ m
    ref_X     = mean of X over every team-game dated before D this season, shrunk
                towards last season's mean as if it were `league.shrinkage_team_games`
                team-games
    λ         = n / (n + k), n = the team's games before D this season
    pace      = L_pace + λ_h (P_h − ref_P) + λ_a (P_a − ref_P)
    off_home  = L_ortg + s·λ_h (O_h − ref_O) − s·λ_a (Dv_a − ref_D)   (and the same for away)
    total     = pace·(off_home + off_away)/100 + home_court_total + b2b·(home_b2b + away_b2b)

L_pace, L_ortg and the back-to-back flags are pace_eff's point-in-time features.
`fit` picks s (`scale_grid`) and k (`shrinkage_grid`) by RMSE on earlier seasons.
Settings: `models.lineup_pace_eff` in params.yaml.

Point-in-time: the only rows dated D that a projection reads are G's own
projected minutes and ratings, whose pre-game timing is tested separately
(docs/experiments/info_latency/GATE.md); everything else is dated before D.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from nbatotals.features.pointintime import build_features
from nbatotals.features.players import PlayerInputs, dnt_games

VALUES = ("O", "Dv", "P")


class LineupPaceEff:
    name = "lineup_pace_eff"
    needs_player_inputs = True

    def __init__(self, inputs: PlayerInputs | None = None):
        self._inputs = inputs

    @property
    def inputs(self) -> PlayerInputs:
        if self._inputs is None:
            self._inputs = PlayerInputs.from_env()
        return self._inputs

    # ------------------------------------------------------------------ components

    def components(self, targets, games, box, params) -> pd.DataFrame:
        """Everything the formula needs except s and k, one row per target."""
        f = build_features(targets, games, box, params)
        tv = self.inputs.team_values()
        # target games -> DnT games (own rows, dated D)
        tmap = dnt_games(self.inputs.dnt[self.inputs.dnt["date"].isin(set(targets["game_date"]))], targets)
        own = tmap.merge(tv, on="dnt_game_id")
        # earlier games -> DnT games (reference means, dated before D)
        gmap = dnt_games(self.inputs.dnt[self.inputs.dnt["date"].isin(set(games["game_date"]))], games)
        hist = gmap.merge(tv, on="dnt_game_id").merge(
            games[["id", "season"]].rename(columns={"id": "game_id"}), on="game_id")
        refs = _references(f[["game_id", "game_date", "season"]], hist, own,
                           params["league"]["shrinkage_team_games"])
        out = f[["game_id", "league_pace", "league_ortg", "home_b2b", "away_b2b", "home_n", "away_n",
                 "home", "away"]].merge(refs, on="game_id", how="left")
        for side in ("home", "away"):
            o = own[["game_id", "team"] + list(VALUES)].rename(columns={"team": side})
            o = o.rename(columns={v: f"{side}_{v}" for v in VALUES})
            out = out.merge(o, on=["game_id", side], how="left")
            out[f"{side}_has_lineup"] = out[f"{side}_O"].notna()
            for v in VALUES:
                out[f"{side}_d{v}"] = (out[f"{side}_{v}"] - out[f"ref_{v}"]).fillna(0.0)
        return out

    @staticmethod
    def total(c: pd.DataFrame, s: float, k: float, cfg: dict) -> np.ndarray:
        lam = {side: (np.ones(len(c)) if k == 0 else c[f"{side}_n"].to_numpy(float) / (c[f"{side}_n"].to_numpy(float) + k))
               for side in ("home", "away")}
        h, a = lam["home"], lam["away"]
        pace = c["league_pace"] + h * c["home_dP"] + a * c["away_dP"]
        off_home = c["league_ortg"] + s * h * c["home_dO"] - s * a * c["away_dDv"]
        off_away = c["league_ortg"] + s * a * c["away_dO"] - s * h * c["home_dDv"]
        b2b = c["home_b2b"].astype(int) + c["away_b2b"].astype(int)
        return (pace * (off_home + off_away) / 100.0 + cfg["home_court_total"]
                + cfg["b2b_total_per_team"] * b2b).to_numpy(float)

    # ------------------------------------------------------------------ interface

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        cfg = params["models"]["lineup_pace_eff"]
        reg = train_games[(train_games["status"] == "final") & (train_games["postseason"] == 0)]
        c = self.components(reg, train_games, train_box, params).set_index("game_id").loc[reg["id"]]
        actual = (reg["home_pts"] + reg["away_pts"]).to_numpy(float)
        test_season = int(train_games["season"].max()) + 1
        rows = []
        for s, k in itertools.product(cfg["scale_grid"], cfg["shrinkage_grid"]):
            e = self.total(c, s, k, cfg) - actual
            rows.append({"test_season": test_season, "scale": s, "shrinkage": k,
                         "train_rmse": float(np.sqrt((e ** 2).mean())), "train_n": len(reg)})
        log = pd.DataFrame(rows)
        best = log.loc[log["train_rmse"].idxmin()]  # first minimum in grid order
        dflt = log[np.isclose(log["scale"], cfg["scale"]) & np.isclose(log["shrinkage"], cfg["shrinkage"])]
        summary = {"train_n": len(reg), "scale": float(best["scale"]), "shrinkage": int(best["shrinkage"]),
                   "train_rmse_chosen": float(best["train_rmse"]),
                   "train_rmse_default": float(dflt["train_rmse"].iloc[0]) if len(dflt) else float("nan"),
                   "train_games_without_lineup": int((~c["home_has_lineup"] | ~c["away_has_lineup"]).sum())}
        return {"scale": float(best["scale"]), "shrinkage": float(best["shrinkage"]), "summary": summary, "log": log}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        cfg = params["models"]["lineup_pace_eff"]
        s, k = (cfg["scale"], cfg["shrinkage"]) if state is None else (state["scale"], state["shrinkage"])
        c = self.components(targets, games, box, params).set_index("game_id").loc[targets["id"]]
        return pd.DataFrame({"game_id": targets["id"].to_numpy(), "total_proj": self.total(c, s, k, cfg)})


def _references(f: pd.DataFrame, hist: pd.DataFrame, own: pd.DataFrame, k_league: float) -> pd.DataFrame:
    """Point-in-time league reference for O, Dv and P, per target game."""
    hist = hist.sort_values(["date", "dnt_game_id", "team"], kind="mergesort")
    by_season = {s: h for s, h in hist.groupby("season")}
    rows = []
    for (season, date), grp in f.groupby(["season", "game_date"], sort=True):
        cur = by_season.get(season)
        cur = cur[cur["date"] < date] if cur is not None else hist.iloc[:0]
        prev = by_season.get(season - 1)
        prev = prev[prev["date"] < date] if prev is not None else hist.iloc[:0]
        if len(prev):
            prior = prev[list(VALUES)].mean()
        elif len(cur):
            prior = cur[cur["date"] == cur["date"].min()][list(VALUES)].mean()
        else:
            prior = None
        n = cur[list(VALUES)].notna().sum()
        mean = cur[list(VALUES)].mean()
        for gid in grp["game_id"]:
            if prior is None:  # very first date in the data: centre on the game itself
                g = own[own["game_id"] == gid]
                ref = {"O": 0.0, "Dv": 0.0, "P": g["P"].mean() if len(g) else np.nan}
            else:
                ref = {v: (n[v] * (mean[v] if n[v] else 0.0) + k_league * prior[v]) / (n[v] + k_league)
                       if (n[v] + k_league) > 0 else prior[v] for v in VALUES}
            rows.append({"game_id": gid, **{f"ref_{v}": ref[v] for v in VALUES}})
    return pd.DataFrame(rows, columns=["game_id"] + [f"ref_{v}" for v in VALUES])
