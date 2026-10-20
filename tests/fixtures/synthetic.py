"""Test fixtures: the synthetic league (nbatotals/synthetic.py) plus made-up player inputs.

Nothing here resembles real results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nbatotals.synthetic import LEAGUE_ORTG, LEAGUE_PACE, generate
from nbatotals.teams import ALIASES

__all__ = ["LEAGUE_ORTG", "LEAGUE_PACE", "generate", "player_frames", "write_player_files", "player_inputs",
           "projector"]


# --------------------------------------------------------------------------- player inputs (Experiment 2)

MINUTES_PROFILE = (34, 33, 31, 29, 27, 23, 19, 15, 11, 7, 3, 0, 0)


def player_frames(games: pd.DataFrame, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Made-up projected minutes and player ratings for every game, in the Dunks & Threes shapes.

    Returns (dnt, ratings): dnt has date, game_id, team_id, team, player_id,
    player_name, p_mp; ratings has the lake player_epm columns. Ratings drift as a
    random walk per player; about 1 in 12 games a player is projected out.
    Some rating rows are left out so the projector's fallback path is exercised.
    """
    from nbatotals.teams import NBA_STATS_ID_TO_ALIAS

    team_id = {a: i for i, a in NBA_STATS_ID_TO_ALIAS.items()}
    rng = np.random.default_rng(seed)
    rating: dict[int, tuple[float, float, float]] = {}
    dnt, rat = [], []
    for g in games.sort_values(["game_date", "id"]).itertuples():
        for team in (g.home, g.away):
            base = ALIASES.index(team) * 100
            mins = np.array(MINUTES_PROFILE, dtype=float) + rng.normal(0, 2, len(MINUTES_PROFILE))
            mins[rng.random(len(mins)) < 1 / 12] = 0.0
            mins = np.clip(mins, 0, 44)
            for j, m in enumerate(mins):
                pid = base + j
                o, d, t = rating.get(pid, (rng.normal(0, 2), rng.normal(0, 1.5), 99 + rng.normal(0, 1.5)))
                o, d, t = o + rng.normal(0, 0.1), d + rng.normal(0, 0.1), t + rng.normal(0, 0.1)
                rating[pid] = (o, d, t)
                row = dict(date=g.game_date, game_id=9_000_000 + int(g.id), team_id=team_id[team], team=team,
                           player_id=pid, player_name=f"Player {pid}")
                dnt.append(dict(row, p_mp=round(float(m), 4)))
                if rng.random() < 0.97:
                    rat.append(dict(row, season=int(g.season) + 1, game_dt=g.game_date, game_optimized=0,
                                    oepm=o, depm=d, epm=o + d, p_t_poss_48=t, p_mp_48=float(m)))
    return pd.DataFrame(dnt), pd.DataFrame(rat).drop(columns="date")


def write_player_files(dnt: pd.DataFrame, ratings: pd.DataFrame, root) -> tuple:
    """Write the frames in the private folders' layouts: <dnt>/<date>/..._box.json and
    <epm>/season=<start year>/<date>.parquet. Returns (dnt_dir, epm_dir)."""
    import json
    from pathlib import Path

    from nbatotals.evaluate.adapters.legacy_players import DNT_BOX_FILE

    root = Path(root)
    dnt_dir, epm_dir = root / "dunksandthrees", root / "player_epm"
    for date, rows in dnt.groupby("date"):
        (dnt_dir / date).mkdir(parents=True, exist_ok=True)
        recs = rows.drop(columns=["date", "team"]).to_dict("records")
        (dnt_dir / date / DNT_BOX_FILE).write_text(json.dumps(recs))
    for (season, date), rows in ratings.groupby(["season", "game_dt"]):
        part = epm_dir / f"season={season - 1}"
        part.mkdir(parents=True, exist_ok=True)
        rows.drop(columns=["team"]).to_parquet(part / f"{date}.parquet", index=False)
    return dnt_dir, epm_dir


def player_inputs(games: pd.DataFrame, seed: int = 0):
    from nbatotals.features.players import PlayerInputs

    dnt, ratings = player_frames(games, seed)
    return PlayerInputs(dnt, ratings.rename(columns={"game_dt": "date"}))


def projector(name: str, games: pd.DataFrame, seed: int = 0):
    """A registered projector, with synthetic player inputs if it needs them."""
    from nbatotals.model import registry

    if getattr(registry.PROJECTORS[name], "needs_player_inputs", False):
        return registry.get(name, inputs=player_inputs(games, seed))
    return registry.get(name)
