"""Read games and team box scores out of a local store."""

from __future__ import annotations

import sqlite3

import pandas as pd


def load_frames(con: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame]:
    games = pd.read_sql_query("SELECT * FROM games ORDER BY game_date, id", con)
    box = pd.read_sql_query("SELECT * FROM team_box ORDER BY game_id, team", con)
    return games, box
