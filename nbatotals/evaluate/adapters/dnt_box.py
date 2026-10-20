"""Dunks & Threes per-player game projections ("game-predictions-box"), read by date.

Layout (private, licensed to whoever fetched it, never copied into this
repository; path from NBA_DNT_BOX): <root>/<YYYY-MM-DD>/dunksandthrees_game_predictions_box.json,
a JSON list with one row per player per game: game_id (NBA Stats form),
team_id (NBA Stats), player_id, player_name, p_mp, p_pts, p_pace, p_fg2a, ...

The files carry no home/away flag and no timestamp. Games are joined to this
project's games by the folder's date (US Eastern schedule date) plus both team
aliases. See docs/experiments/dnt_benchmark/ for what is known about when the
projections were made.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from nbatotals.teams import NBA_STATS_ID_TO_ALIAS

ENV_VAR = "NBA_DNT_BOX"
FILE = "dunksandthrees_game_predictions_box.json"
COLUMNS = ("game_id", "team_id", "player_id", "player_name", "p_mp", "p_pts", "p_pace", "p_fg2a", "p_fg3a",
           "p_fta", "p_orb", "p_tov")


def root_path(path: str | os.PathLike | None = None) -> Path:
    path = path or os.environ.get(ENV_VAR)
    if not path:
        raise RuntimeError(f"set {ENV_VAR} to the Dunks & Threes date-folder root")
    path = Path(path)
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def read_day(root: Path, date: str) -> pd.DataFrame:
    """Rows of the file dated `date` only (empty frame if there is none)."""
    f = Path(root) / date / FILE
    rows = json.loads(f.read_text()) if f.exists() else []
    df = pd.DataFrame(rows)[list(COLUMNS)] if rows else pd.DataFrame(columns=list(COLUMNS))
    df = df.assign(date=date, team=df["team_id"].map(NBA_STATS_ID_TO_ALIAS))
    if df["team"].isna().any():
        raise ValueError(f"{f}: team id outside NBA_STATS_ID_TO_ALIAS")
    return df


def read_all(root: str | os.PathLike | None = None) -> pd.DataFrame:
    root = root_path(root)
    days = sorted(p.name for p in root.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")
    return pd.concat([read_day(root, d) for d in days], ignore_index=True)


def game_keys(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per DnT game: date, DnT game_id and the frozenset of both aliases."""
    k = rows.groupby(["date", "game_id"])["team"].agg(lambda s: frozenset(s)).reset_index(name="teams")
    if (k["teams"].map(len) != 2).any():
        raise ValueError("a Dunks & Threes game does not have exactly two teams")
    return k


def match_games(rows: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """DnT game -> this project's game id, by Eastern date and both aliases."""
    k = game_keys(rows)
    g = games.assign(teams=[frozenset(t) for t in zip(games["home"], games["away"], strict=True)])
    m = k.merge(g[["game_date", "teams", "id"]], left_on=["date", "teams"], right_on=["game_date", "teams"],
                how="inner")
    if m["id"].duplicated().any() or m["game_id"].duplicated().any():
        raise ValueError("ambiguous Dunks & Threes game join")
    return m[["date", "game_id", "teams", "id"]]
