"""The Tier A pace x efficiency formula as a projector (the pre-registered model).

`fit` runs the declared grid (nbatotals/evaluate/fit.py) on earlier seasons and
keeps the lowest-RMSE point; `predict` builds point-in-time features and applies
the formula in nbatotals/model/projection.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nbatotals.evaluate import fit
from nbatotals.features.pointintime import build_features
from nbatotals.model.projection import project

DEFAULT_POINT = dict(l3=0.3, l10=0.5, season=0.2, shrinkage=5, pace_weight=1.0, home_court_total=0,
                     b2b_total_per_team=0)
LOG_ORDER = ["l3", "l10", "season", "shrinkage", "pace_weight", "test_season", "home_court_total",
             "b2b_total_per_team"]


class PaceEff:
    name = "pace_eff"

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        test_season = int(train_games["season"].max()) + 1
        log, chosen, _ = fit.search(train_games, train_box, params, (test_season,), progress=progress)
        row = chosen[test_season]
        dmask = np.ones(len(log), dtype=bool)
        for k, v in DEFAULT_POINT.items():
            dmask &= np.isclose(log[k].to_numpy(dtype=float), v)
        summary = {
            "train_n": int(row["train_n"]), "l3": row["l3"], "l10": row["l10"], "season_w": row["season"],
            "shrinkage": int(row["shrinkage"]), "pace_weight": row["pace_weight"],
            "home_court_total": row["home_court_total"], "b2b_total_per_team": row["b2b_total_per_team"],
            "train_rmse_chosen": row["train_rmse"], "train_rmse_default": float(log.loc[dmask, "train_rmse"].iloc[0]),
        }
        return {"row": row, "summary": summary, "log": log}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        prm = params if state is None else fit.params_for(params, state["row"])
        return project(build_features(targets, games, box, prm), prm)[["game_id", "total_proj"]]

    @staticmethod
    def combine_logs(logs: list[pd.DataFrame]) -> pd.DataFrame:
        """Grid order across test seasons, as the log was first written."""
        return pd.concat(logs).sort_values(LOG_ORDER, kind="mergesort").reset_index(drop=True)
