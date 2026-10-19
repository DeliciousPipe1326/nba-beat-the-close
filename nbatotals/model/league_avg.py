"""Example projector: the no-information baseline.

Every game is projected at the point-in-time league average total (league pace x
league points per 100, both teams), with no team information at all. Its
results show what "knowing nothing" looks like through the same harness.
"""

from __future__ import annotations

import pandas as pd

from nbatotals.features.pointintime import build_features


class LeagueAvg:
    name = "league_avg"

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        reg = train_games[(train_games["status"] == "final") & (train_games["postseason"] == 0)]
        return {"summary": {"train_n": len(reg), "parameters": "none"}}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        f = build_features(targets, games, box, params)
        return pd.DataFrame({"game_id": f["game_id"], "total_proj": f["league_pace"] * 2 * f["league_ortg"] / 100.0})
