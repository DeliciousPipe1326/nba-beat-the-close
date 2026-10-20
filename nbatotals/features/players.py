"""Player-level inputs for lineup projectors: projected minutes and player ratings.

`PlayerInputs` holds two frames, one row per (player, game):

- `dnt`: projected minutes, columns date (US Eastern), game_id (the source's
  game id), team (alias), player_id, p_mp;
- `ratings`: player ratings, columns date, game_id, player_id, oepm, depm,
  p_t_poss_48.

Rows dated D are pre-game inputs for D's games. Whether a given source really
is pre-game has to be shown separately (for Dunks & Threes:
docs/experiments/info_latency/GATE.md); the projector only guarantees that a
game dated D reads no row dated after D and no other game's row dated D.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd


def dnt_games(dnt: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Map source game ids to this project's games by Eastern date plus both team aliases.

    Returns columns dnt_game_id, game_id, game_date, home, away (inner join;
    source games that match nothing, or match ambiguously, are dropped).
    """
    cols = ["dnt_game_id", "game_id", "game_date", "home", "away"]
    if len(dnt) == 0 or len(games) == 0:
        return pd.DataFrame(columns=cols)
    pairs = dnt[["date", "game_id", "team"]].drop_duplicates()
    pairs = pairs.groupby(["date", "game_id"])["team"].agg(lambda s: tuple(sorted(s))).reset_index()
    pairs = pairs[pairs["team"].map(len) == 2]
    g = games[["id", "game_date", "home", "away"]].copy()
    g["team"] = [tuple(sorted(x)) for x in zip(g["home"], g["away"])]
    m = pairs.merge(g, left_on=["date", "team"], right_on=["game_date", "team"])
    m = m[~m.duplicated("game_id", keep=False) & ~m.duplicated("id", keep=False)]
    return m.rename(columns={"game_id": "dnt_game_id", "id": "game_id"})[cols].reset_index(drop=True)


class PlayerInputs:
    def __init__(self, dnt: pd.DataFrame, ratings: pd.DataFrame):
        self.dnt = dnt.reset_index(drop=True)
        self.ratings = ratings.reset_index(drop=True)
        self._team_values = None

    @classmethod
    def from_folders(cls, dnt_dir, epm_dir) -> "PlayerInputs":
        from nbatotals.evaluate.adapters import legacy_players as LP

        return cls(LP.read_dnt_box(dnt_dir), LP.read_player_epm(epm_dir))

    @classmethod
    def from_env(cls) -> "PlayerInputs":
        from nbatotals.evaluate.adapters import legacy_players as LP

        missing = [v for v in (LP.DNT_ENV, LP.EPM_ENV) if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"lineup projectors need player inputs: set {', '.join(missing)} "
                               "(see nbatotals/evaluate/adapters/legacy_players.py)")
        return cls.from_folders(None, None)

    def with_minutes(self, minutes: pd.DataFrame) -> "PlayerInputs":
        """A copy whose p_mp is replaced from `minutes` (columns game_id, player_id, p_mp; absent = 0)."""
        d = self.dnt.drop(columns="p_mp").merge(minutes, on=["game_id", "player_id"], how="left")
        d["p_mp"] = d["p_mp"].fillna(0.0)
        return PlayerInputs(d, self.ratings)

    def team_values(self) -> pd.DataFrame:
        """Minutes-weighted O, Dv, P per (source game, team); a game's value reads only its own
        rows plus each player's latest rating dated before the game when its own rating is missing."""
        if self._team_values is None:
            self._team_values = _team_values(self.dnt, self.ratings)
        return self._team_values


def _team_values(dnt: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    cols = ["dnt_game_id", "team", "date", "O", "Dv", "P", "minutes", "rated_minutes_share"]
    if len(dnt) == 0:
        return pd.DataFrame(columns=cols)
    d = dnt[["date", "game_id", "team", "player_id", "p_mp"]]
    r = ratings[["date", "game_id", "player_id", "oepm", "depm", "p_t_poss_48"]]
    x = d.merge(r.drop(columns="date"), on=["game_id", "player_id"], how="left")
    x["rated"] = x["oepm"].notna()
    miss = ~x["rated"]
    if miss.any() and len(r):
        m = x.loc[miss, ["date", "player_id"]].copy()
        m["t"] = pd.to_datetime(m["date"])
        m["row"] = m.index
        rr = r.assign(t=pd.to_datetime(r["date"]))[["t", "player_id", "oepm", "depm", "p_t_poss_48"]]
        fb = pd.merge_asof(m.sort_values("t"), rr.sort_values("t"), on="t", by="player_id",
                           allow_exact_matches=False, direction="backward").set_index("row")
        for c in ("oepm", "depm", "p_t_poss_48"):
            x.loc[fb.index, c] = fb[c]
    x["oepm"] = x["oepm"].fillna(0.0)
    x["depm"] = x["depm"].fillna(0.0)
    m_ = x["p_mp"].to_numpy(float)
    x["w"] = m_
    x["wo"] = m_ * x["oepm"]
    x["wd"] = m_ * x["depm"]
    has_t = x["p_t_poss_48"].notna()
    x["wt"] = np.where(has_t, m_ * x["p_t_poss_48"].fillna(0.0), 0.0)
    x["w_t"] = np.where(has_t, m_, 0.0)
    x["w_rated"] = np.where(x["rated"], m_, 0.0)
    g = x.groupby(["game_id", "team", "date"], sort=True)[["w", "wo", "wd", "wt", "w_t", "w_rated"]].sum().reset_index()
    w = g["w"].where(g["w"] > 0)
    out = pd.DataFrame({
        "dnt_game_id": g["game_id"], "team": g["team"], "date": g["date"],
        "O": 5 * g["wo"] / w, "Dv": 5 * g["wd"] / w, "P": g["wt"] / g["w_t"].where(g["w_t"] > 0),
        "minutes": g["w"], "rated_minutes_share": g["w_rated"] / w,
    })
    return out[cols]
