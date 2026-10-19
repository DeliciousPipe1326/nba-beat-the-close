"""Leakage self-checks for the point-in-time features.

1. Truncation: for a sample of games, delete every games and team_box row dated
   on or after the game's date (and blank the game's own score), rebuild the
   features from what is left, and require bit-identical values. This covers the
   team windows, the league averages, the shrinkage priors and rest/back-to-back.

2. Correlation: a feature that secretly includes the game it is predicting
   correlates with that game's total far more than the same feature as it stood
   at the team's previous game. Require the difference to stay small, and show
   (with a deliberately leaky version) that the check would catch a leak.

Run against the maintainer's legacy DB with
`python -m nbatotals.evaluate.leakage` (needs NBA_LEGACY_DB).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nbatotals.features.pointintime import FEATURE_COLUMNS, STATS, WINDOWS, History, build_features

CORR_FEATURES = [f"{s}_{w}" for s in STATS for w in WINDOWS] + list(STATS)
PHASES = ("early", "mid", "late")


def stratified_sample(games: pd.DataFrame, per_cell: int, seed: int = 0) -> pd.DataFrame:
    """Final games sampled evenly across seasons and early / mid / late season.

    Each season's dates are split into thirds. Opening night of every season is
    always included, since that is where season-boundary leaks would show.
    """
    rng = np.random.default_rng(seed)
    final = games[games["status"] == "final"].copy()
    picks = []
    for season, g in final.groupby("season"):
        dates = np.sort(g["game_date"].unique())
        cuts = np.array_split(dates, 3)
        for phase, ds in zip(PHASES, cuts):
            cell = g[g["game_date"].isin(ds)]
            take = min(per_cell, len(cell))
            picks.append(cell.iloc[rng.choice(len(cell), size=take, replace=False)].assign(phase=phase))
        picks.append(g[g["game_date"] == dates[0]].assign(phase="opening_night"))
    out = pd.concat(picks).drop_duplicates("id")
    return out.sort_values(["game_date", "id"]).reset_index(drop=True)


def _same(a, b) -> bool:
    if isinstance(a, (bool, np.bool_)) or isinstance(b, (bool, np.bool_)):
        return bool(a) == bool(b)
    if pd.isna(a) and pd.isna(b):
        return True
    return a == b


def truncation_check(games: pd.DataFrame, box: pd.DataFrame, params: dict, sample: pd.DataFrame) -> dict:
    """Recompute each sampled game's features from truncated history; compare bit for bit."""
    full = build_features(sample, games, box, params, history=History(games, box)).set_index("game_id")
    box_dates = box.merge(games[["id", "game_date"]], left_on="game_id", right_on="id")["game_date"]
    mismatches = []
    max_abs = 0.0
    for target in sample.itertuples(index=False):
        keep_games = games[games["game_date"] < target.game_date]
        keep_box = box[(box_dates < target.game_date).to_numpy()]
        blind = pd.DataFrame([target._asdict()]).assign(home_pts=np.nan, away_pts=np.nan)
        cut = build_features(blind, keep_games, keep_box, params).set_index("game_id").loc[target.id]
        ref = full.loc[target.id]
        for col in FEATURE_COLUMNS:
            a, b = ref[col], cut[col]
            if not _same(a, b):
                mismatches.append((target.id, col, a, b))
            elif not pd.isna(a) and not isinstance(a, (bool, np.bool_)):
                max_abs = max(max_abs, abs(float(a) - float(b)))
    return {
        "games": len(sample),
        "by_season_phase": sample.groupby(["season", "phase"]).size().to_dict(),
        "columns": len(FEATURE_COLUMNS),
        "values_compared": len(sample) * len(FEATURE_COLUMNS),
        "max_abs_diff": max_abs,
        "mismatches": mismatches,
    }


def projector_truncation_check(projector, games: pd.DataFrame, box: pd.DataFrame, params: dict,
                               sample: pd.DataFrame, state=None) -> dict:
    """The truncation test for any projector: each sampled game's projection from
    history cut at its date (own score blanked) must equal the full-history one."""
    full = projector.predict(sample, games, box, state, params).set_index("game_id")["total_proj"]
    box_dates = box.merge(games[["id", "game_date"]], left_on="game_id", right_on="id")["game_date"]
    mismatches = []
    for target in sample.itertuples(index=False):
        keep_games = games[games["game_date"] < target.game_date]
        keep_box = box[(box_dates < target.game_date).to_numpy()]
        blind = pd.DataFrame([target._asdict()]).assign(home_pts=np.nan, away_pts=np.nan)
        cut = projector.predict(blind, keep_games, keep_box, state, params).set_index("game_id")["total_proj"]
        if not _same(full.loc[target.id], cut.loc[target.id]):
            mismatches.append((target.id, full.loc[target.id], cut.loc[target.id]))
    return {"games": len(sample), "mismatches": mismatches}


def _team_rows(feats: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Long format: one row per team per game with its features and the game total."""
    totals = games.set_index("id")
    rows = []
    for side in ("home", "away"):
        cols = {f"{side}_{c}": c for c in CORR_FEATURES}
        part = feats[["game_id", "game_date", "season", side] + list(cols)].rename(columns={side: "team", **cols})
        rows.append(part)
    long = pd.concat(rows)
    long["total"] = (totals.loc[long["game_id"], "home_pts"] + totals.loc[long["game_id"], "away_pts"]).to_numpy()
    return long.sort_values(["team", "game_date", "game_id"]).reset_index(drop=True)


def correlation_check(games: pd.DataFrame, box: pd.DataFrame, params: dict, shift_days: int = 0) -> pd.DataFrame:
    """corr(feature at game g, total of g) vs corr(feature at the team's previous game, total of g).

    `shift_days=1` builds the features as if each game were a day later, so
    they include the game itself: the deliberately leaky control.
    """
    final = games[(games["status"] == "final") & games["home_pts"].notna()]
    targets = final
    if shift_days:
        targets = final.assign(
            game_date=(pd.to_datetime(final["game_date"]) + pd.Timedelta(days=shift_days)).dt.strftime("%Y-%m-%d")
        )
    feats = build_features(targets, games, box, params)
    long = _team_rows(feats, final)
    prev = long.groupby(["team", "season"])[CORR_FEATURES].shift(1)
    out = []
    for col in CORR_FEATURES:
        ok = long[col].notna() & prev[col].notna()
        same = np.corrcoef(long.loc[ok, col], long.loc[ok, "total"])[0, 1]
        lag = np.corrcoef(prev.loc[ok, col], long.loc[ok, "total"])[0, 1]
        out.append({"feature": col, "n": int(ok.sum()), "corr_same_game": same, "corr_prev_game": lag,
                    "excess": same - lag})
    return pd.DataFrame(out)


def main() -> int:
    from nbatotals import params as P
    from nbatotals.evaluate.adapters import legacy_nba_db

    frames = legacy_nba_db.load()
    games, box = frames["games"], frames["team_box"].drop(columns=["legacy_pace"])
    games = games[games["season"] <= 2024]
    prm = P.load()
    sample = stratified_sample(games, per_cell=20)
    res = truncation_check(games, box, prm, sample)
    print(f"truncation: {res['games']} games, {res['values_compared']} values, "
          f"max abs diff {res['max_abs_diff']}, mismatches {len(res['mismatches'])}")
    print(pd.Series(res["by_season_phase"]).to_string())
    pd.set_option("display.width", 160)
    print("\ncorrelation, real features:")
    print(correlation_check(games, box, prm).round(4).to_string(index=False))
    print("\ncorrelation, deliberately leaky control (cut-off one day late):")
    print(correlation_check(games, box, prm, shift_days=1).round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
