"""The pace_eff projector's walk-forward parameter search, as declared in docs/RESULTS.md before it ran.

Objective: RMSE of projected vs actual total on the training seasons'
regular-season games, pooled. No odds are read here. Lives in the model layer
because the projector's `fit` calls it (models never import the evaluator).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nbatotals import params as params_io
from nbatotals.features.pointintime import History, build_features

SHRINKAGE = (0, 2, 5, 10, 20)
PACE_WEIGHT = (0.5, 0.75, 1.0)
HOME_COURT = (-2, -1, 0, 1, 2)
B2B = (-3, -2, -1, 0, 1, 2, 3)


def blend_grid() -> list[tuple[float, float, float]]:
    """Every (l3, l10, season) on the 0.1-step simplex, ascending: 66 points."""
    pts = []
    for i in range(11):
        for j in range(11 - i):
            pts.append((i / 10, j / 10, (10 - i - j) / 10))
    return sorted(pts)


def grid_size() -> int:
    return len(blend_grid()) * len(SHRINKAGE) * len(PACE_WEIGHT) * len(HOME_COURT) * len(B2B)


def _blend_params(base: dict, blend, k) -> dict:
    return params_io.with_overrides(base, {
        "features.blend": {"l3": blend[0], "l10": blend[1], "season": blend[2]},
        "features.team_shrinkage_games": k,
    })


def _core_total(f: pd.DataFrame, pace_weight: float, base: dict) -> np.ndarray:
    """Projected total before the home-court and B2B terms (see model/projection.py)."""
    p = base["projection"]
    lp, lo = f["league_pace"].to_numpy(), f["league_ortg"].to_numpy()
    pace = lp + pace_weight * ((f["home_pace"].to_numpy() - lp) + (f["away_pace"].to_numpy() - lp))
    off_h = lo + p["off_weight"] * (f["home_ortg"].to_numpy() - lo) + p["def_weight"] * (f["away_drtg"].to_numpy() - lo)
    off_a = lo + p["off_weight"] * (f["away_ortg"].to_numpy() - lo) + p["def_weight"] * (f["home_drtg"].to_numpy() - lo)
    return pace * (off_h + off_a) / 100.0


def search(games: pd.DataFrame, box: pd.DataFrame, base: dict, test_seasons, progress=None):
    """Evaluate the full grid for every test season. Returns (log, chosen, features_by_blend)."""
    targets = games[(games["status"] == "final") & (games["postseason"] == 0)].reset_index(drop=True)
    actual = (targets["home_pts"] + targets["away_pts"]).to_numpy(dtype=float)
    seasons = targets["season"].to_numpy()
    train_masks = {s: seasons < s for s in test_seasons}
    hist = History(games, box)
    hc = np.array(HOME_COURT, dtype=float)[:, None]
    b2 = np.array(B2B, dtype=float)[None, :]
    log = []
    features = {}
    for bi, blend in enumerate(blend_grid()):
        for k in SHRINKAGE:
            prm = _blend_params(base, blend, k)
            f = build_features(targets, games, box, prm, history=hist)
            features[(blend, k)] = f
            b2b = (f["home_b2b"].astype(int) + f["away_b2b"].astype(int)).to_numpy(dtype=float)
            for pw in PACE_WEIGHT:
                core = _core_total(f, pw, base)
                for s, mask in train_masks.items():
                    resid = core[mask] - actual[mask]            # n
                    cnt = b2b[mask]
                    n = mask.sum()
                    # RMSE for every (home court, b2b) pair at once: residual + hc + b2b*count
                    s1 = resid.sum()
                    s2 = (resid ** 2).sum()
                    sc = (resid * cnt).sum()
                    c1 = cnt.sum()
                    c2 = (cnt ** 2).sum()
                    sse = s2 + 2 * hc * s1 + n * hc ** 2 + 2 * b2 * sc + 2 * hc * b2 * c1 + b2 ** 2 * c2
                    rmse = np.sqrt(sse / n)
                    for hi, h in enumerate(HOME_COURT):
                        for bj, b in enumerate(B2B):
                            log.append((s, blend[0], blend[1], blend[2], k, pw, h, b, float(rmse[hi, bj]), int(n)))
        if progress:
            progress(bi + 1, len(blend_grid()))
    log = pd.DataFrame(log, columns=["test_season", "l3", "l10", "season", "shrinkage", "pace_weight",
                                     "home_court_total", "b2b_total_per_team", "train_rmse", "train_n"])
    chosen = {}
    for s, grp in log.groupby("test_season", sort=True):
        # grid order is the order rows were appended; ties within 1e-9 go to the first
        best = grp["train_rmse"].min()
        row = grp[grp["train_rmse"] <= best + 1e-9].iloc[0]
        chosen[s] = row
    return log, chosen, features


def params_for(base: dict, row) -> dict:
    return params_io.with_overrides(base, {
        "features.blend": {"l3": float(row["l3"]), "l10": float(row["l10"]), "season": float(row["season"])},
        "features.team_shrinkage_games": int(row["shrinkage"]),
        "projection.pace_weight": float(row["pace_weight"]),
        "projection.home_court_total": float(row["home_court_total"]),
        "projection.b2b_total_per_team": float(row["b2b_total_per_team"]),
    })
