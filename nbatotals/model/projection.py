"""Tier A projection: a formula, no machine learning.

    pace_proj = L_pace + pace_weight * ((home_pace - L_pace) + (away_pace - L_pace))
    off_home  = L_ortg + off_weight * (home_ortg - L_ortg) + def_weight * (away_drtg - L_ortg)
    off_away  = L_ortg + off_weight * (away_ortg - L_ortg) + def_weight * (home_drtg - L_ortg)
    total     = pace_proj * (off_home + off_away) / 100
                + home_court_total
                + b2b_total_per_team * (home_b2b + away_b2b)

L_pace and L_ortg are the point-in-time league averages from the features.
Every coefficient comes from config/params.yaml.
"""

from __future__ import annotations

import pandas as pd


def project(features: pd.DataFrame, params: dict) -> pd.DataFrame:
    p = params["projection"]
    f = features
    lp, lo = f["league_pace"], f["league_ortg"]
    pace = lp + p["pace_weight"] * ((f["home_pace"] - lp) + (f["away_pace"] - lp))
    off_home = lo + p["off_weight"] * (f["home_ortg"] - lo) + p["def_weight"] * (f["away_drtg"] - lo)
    off_away = lo + p["off_weight"] * (f["away_ortg"] - lo) + p["def_weight"] * (f["home_drtg"] - lo)
    b2b = f["home_b2b"].astype(int) + f["away_b2b"].astype(int)
    total = pace * (off_home + off_away) / 100.0 + p["home_court_total"] + p["b2b_total_per_team"] * b2b
    return pd.DataFrame(
        {
            "game_id": f["game_id"],
            "pace_proj": pace,
            "off_home": off_home,
            "off_away": off_away,
            "home_pts_proj": pace * off_home / 100.0,
            "away_pts_proj": pace * off_away / 100.0,
            "total_proj": total,
        }
    )
