"""Player-level inputs from the maintainer's private legacy folder (Experiment 2).

Nothing here is copied into the repository; every path comes from an
environment variable and every file is opened read-only.

- NBA_LEGACY_DNT: the raw Dunks & Threes folder, one sub-folder per US Eastern
  date holding `dunksandthrees_game_predictions_box.json` (per player per game:
  `p_mp` projected minutes, NBA Stats game, team and player ids).
- NBA_LEGACY_PLAYER_EPM: the lake `player_epm` folder (parquet, partition
  `season=<start year>`, one file per date; needs pyarrow). Rows are per player
  per game; only `game_optimized == 0` (the pure rating) is read. The first
  dates of 2024-25 appear in two partitions; duplicates are dropped by
  (player, game).
- NBA_LEGACY_PROPS_DB: the legacy `nba_props.db`, whose `player_game_logs` is
  the BallDontLie player box (actual minutes). Player names come from
  NBA_LEGACY_DB's `balldontlie_players`.

Both DnT readers accept `before`/`through` date bounds so a caller can read the
files as they stood on a date (the external-file truncation test does the same
by deleting files).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from nbatotals.features.players import PlayerInputs, dnt_games  # noqa: F401  (dnt_games re-exported for the gate)
from nbatotals.teams import BDL_ID_TO_ALIAS, NBA_STATS_ID_TO_ALIAS

DNT_ENV = "NBA_LEGACY_DNT"
EPM_ENV = "NBA_LEGACY_PLAYER_EPM"
PROPS_ENV = "NBA_LEGACY_PROPS_DB"
DNT_BOX_FILE = "dunksandthrees_game_predictions_box.json"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RATING_COLUMNS = ["oepm", "depm", "epm", "p_t_poss_48", "p_mp_48"]


def _path(path, env) -> Path:
    path = path or os.environ.get(env)
    if not path:
        raise RuntimeError(f"set {env}")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _in_range(date: str, through: str | None) -> bool:
    return through is None or date <= through


def read_dnt_box(path=None, through: str | None = None) -> pd.DataFrame:
    """DnT projected box rows, one per (player, game), with `date` = the folder's Eastern date."""
    root = _path(path, DNT_ENV)
    frames = []
    for d in sorted(p.name for p in root.iterdir() if DATE_RE.match(p.name)):
        f = root / d / DNT_BOX_FILE
        if not _in_range(d, through) or not f.exists():
            continue
        rows = json.loads(f.read_text())
        if rows:
            frames.append(pd.DataFrame(rows).assign(date=d))
    if not frames:
        return pd.DataFrame(columns=["date", "game_id", "team_id", "player_id", "player_name", "p_mp", "team"])
    out = pd.concat(frames, ignore_index=True)
    # A few fringe players carry no projection at all (103 rows, Oct 2024 on): no minutes projected.
    out["p_mp_missing"] = out["p_mp"].isna()
    out["p_mp"] = out["p_mp"].fillna(0.0)
    out["team"] = out["team_id"].map(NBA_STATS_ID_TO_ALIAS)
    if out["team"].isna().any():
        raise KeyError(f"unknown NBA Stats team ids: {sorted(out.loc[out['team'].isna(), 'team_id'].unique())}")
    return out.drop_duplicates(["player_id", "game_id"]).reset_index(drop=True)


def read_player_epm(path=None, through: str | None = None) -> pd.DataFrame:
    """Lake player EPM rows (game_optimized == 0), one per (player, game), `date` = game_dt."""
    root = _path(path, EPM_ENV)
    files = sorted(root.glob("season=*/*.parquet"))
    files = [f for f in files if _in_range(f.stem, through)]
    cols = ["game_dt", "game_id", "team_id", "player_id", "player_name", "game_optimized"] + RATING_COLUMNS
    if not files:
        return pd.DataFrame(columns=cols + ["date", "team"])
    out = pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)
    out = out[out["game_optimized"] == 0]
    out = out.drop_duplicates(["player_id", "game_id"]).rename(columns={"game_dt": "date"})
    out["team"] = out["team_id"].map(NBA_STATS_ID_TO_ALIAS)
    return out.sort_values(["date", "game_id", "player_id"]).reset_index(drop=True)


# --------------------------------------------------------------------------- actual player box (BallDontLie)

def read_player_box(props_db=None, legacy_db=None) -> pd.DataFrame:
    """BallDontLie player box: one row per (player, game), actual minutes (DNP = 0) and game score inputs."""
    props = _path(props_db, PROPS_ENV)
    legacy = _path(legacy_db, "NBA_LEGACY_DB")
    con = sqlite3.connect(f"file:{props}?mode=ro", uri=True)
    try:
        box = pd.read_sql_query(
            """SELECT player_id, game_id, game_date, team_id, minutes_decimal, is_dnp, points,
                      field_goals_made, field_goals_attempted, free_throws_made, free_throws_attempted,
                      offensive_rebounds, defensive_rebounds, steals, assists, blocks, fouls, turnovers
               FROM player_game_logs""", con)
    finally:
        con.close()
    con = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    try:
        names = pd.read_sql_query("SELECT player_id, first_name, last_name FROM balldontlie_players", con)
    finally:
        con.close()
    box = box.merge(names, on="player_id", how="left")
    box["team"] = box["team_id"].map(BDL_ID_TO_ALIAS)
    box["minutes"] = np.where(box["is_dnp"].astype(bool), 0.0, box["minutes_decimal"].fillna(0.0))
    box["name_key"] = [normalise_name(f"{a} {b}") if isinstance(a, str) else None
                       for a, b in zip(box["first_name"], box["last_name"], strict=True)]
    return box


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv)\b")


def normalise_name(name: str) -> str:
    """Accents stripped, lower case, punctuation removed, Jr/Sr/II/III/IV dropped."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", "", s.lower().replace("-", " "))
    s = _SUFFIX.sub("", s)
    return " ".join(s.split())


def match_players(dnt: pd.DataFrame, box: pd.DataFrame, seasons: pd.Series) -> pd.DataFrame:
    """DnT (season, team, player_id) -> BallDontLie player_id by normalised name.

    A DnT player matches when exactly one BallDontLie player with that name
    appears for that team in that season. `seasons` maps an Eastern date to a
    season start year.
    """
    d = dnt[["date", "team", "player_id", "player_name"]].copy()
    d["season"] = d["date"].map(seasons)
    d["name_key"] = d["player_name"].map(normalise_name)
    d = d.drop_duplicates(["season", "team", "player_id"])
    b = box[["game_date", "team", "player_id", "name_key"]].dropna().copy()
    b["season"] = b["game_date"].map(seasons)
    b = b.drop_duplicates(["season", "team", "player_id"])
    cand = b.groupby(["season", "team", "name_key"])["player_id"].agg(list).reset_index()
    m = d.merge(cand, on=["season", "team", "name_key"], how="left")
    one = m["player_id_y"].map(lambda x: isinstance(x, list) and len(x) == 1)
    m["bdl_player_id"] = np.where(one, m["player_id_y"].map(lambda x: x[0] if isinstance(x, list) else -1), -1)
    return m.rename(columns={"player_id_x": "player_id"})[["season", "team", "player_id", "bdl_player_id"]]


def game_score_per36(box: pd.DataFrame) -> pd.Series:
    """Hollinger game score per 36 minutes (NaN under 10 minutes)."""
    gs = (box["points"] + 0.4 * box["field_goals_made"] - 0.7 * box["field_goals_attempted"]
          - 0.4 * (box["free_throws_attempted"] - box["free_throws_made"]) + 0.7 * box["offensive_rebounds"]
          + 0.3 * box["defensive_rebounds"] + box["steals"] + 0.7 * box["assists"] + 0.7 * box["blocks"]
          - 0.4 * box["fouls"] - box["turnovers"])
    return (36 * gs / box["minutes"]).where(box["minutes"] >= 10)


def player_inputs(dnt_dir=None, epm_dir=None) -> PlayerInputs:
    """Player inputs for lineup projectors, read from the private folders (paths default to the env vars)."""
    return PlayerInputs(read_dnt_box(dnt_dir), read_player_epm(epm_dir))


def player_inputs_from_env() -> PlayerInputs:
    missing = [v for v in (DNT_ENV, EPM_ENV) if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"lineup projectors need player inputs: set {', '.join(missing)} "
                           "(see nbatotals/evaluate/adapters/legacy_players.py)")
    return player_inputs()
