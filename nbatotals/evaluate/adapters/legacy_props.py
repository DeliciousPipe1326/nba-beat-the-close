"""Player-prop quotes and player box scores from the maintainer's private legacy data.

Nothing here is copied into the repository. Paths come only from environment
variables:

- NBA_LEGACY_PROPS: the multi-region player-props folder, laid out as
  <region>/<YYYY-MM-DD>/event_<id>_player_<market>_<YYYYMMDDTHHMM>.json, each a
  The Odds API historical event-odds payload with its own `timestamp` and the
  event's `commence_time`.
- NBA_LEGACY_PROPS_DB: the legacy props SQLite (`player_game_logs`).
- NBA_LEGACY_DB: the legacy games SQLite (`games`, `balldontlie_players`).

Experiment 4 (docs/experiments/props_market/PREREGISTRATION.md) reads these;
all the rules live in nbatotals/evaluate/props_market.py.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd

from nbatotals import store
from nbatotals.evaluate.adapters import legacy_nba_db

ENV_PROPS = "NBA_LEGACY_PROPS"
ENV_PROPS_DB = "NBA_LEGACY_PROPS_DB"
REGIONS = ("us", "us_ex", "au", "eu", "uk")
MARKETS = ("player_points", "player_rebounds", "player_assists")


def _path(var: str, path=None, is_dir: bool = False) -> Path:
    path = path or os.environ.get(var)
    if not path:
        raise RuntimeError(f"set {var}")
    path = Path(path)
    if not (path.is_dir() if is_dir else path.exists()):
        raise FileNotFoundError(path)
    return path


def read_files(path: str | os.PathLike | None = None) -> tuple[pd.DataFrame, dict]:
    """One row per outcome (book, player, side, line, price) as the file states it."""
    root = _path(ENV_PROPS, path, is_dir=True)
    rows, files, empty = [], 0, 0
    for region in REGIONS:
        for f in sorted((root / region).glob("*/event_*_player_*.json")):
            files += 1
            payload = json.loads(f.read_text())
            ev = payload["data"]
            base = dict(region=region, file=f"{region}/{f.parent.name}/{f.name}", captured_utc=payload["timestamp"],
                        event_id=ev["id"], commence_utc=ev["commence_time"], home_name=ev["home_team"],
                        away_name=ev["away_team"])
            books = ev.get("bookmakers") or []
            empty += not books
            for b in books:
                for m in b.get("markets", []):
                    if m["key"] not in MARKETS:
                        continue
                    for o in m.get("outcomes", []):
                        rows.append(dict(base, book=b["key"], market=m["key"],
                                         book_last_update=b.get("last_update"),
                                         last_update=m.get("last_update") or b.get("last_update"),
                                         player=o.get("description"), side=o["name"].lower(), line=o.get("point"),
                                         american=o.get("price")))
    return pd.DataFrame(rows), {"files": files, "files_without_bookmakers": empty}


def read_games(path: str | os.PathLike | None = None) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{legacy_nba_db.legacy_path(path)}?mode=ro", uri=True)
    try:
        return legacy_nba_db.read_games(con)
    finally:
        con.close()


def read_player_box(props_db=None, nba_db=None, seasons=(2024,)) -> pd.DataFrame:
    """Per player per game: BallDontLie ids, the player's BallDontLie name, minutes and stats."""
    con = sqlite3.connect(f"file:{_path(ENV_PROPS_DB, props_db)}?mode=ro", uri=True)
    try:
        con.execute("ATTACH DATABASE ? AS n", (f"file:{legacy_nba_db.legacy_path(nba_db)}?mode=ro",))
        q = f"""SELECT l.game_id, l.player_id, p.full_name AS name, l.team_abbreviation AS team, l.season,
                       l.game_date, l.minutes_decimal AS minutes, l.is_dnp, l.points, l.rebounds, l.assists
                FROM player_game_logs l LEFT JOIN n.balldontlie_players p ON p.player_id = l.player_id
                WHERE l.season IN ({store.placeholders(len(seasons))})"""  # nosec B608: only '?' placeholders
        return pd.read_sql_query(q, con, params=list(seasons))
    finally:
        con.close()
