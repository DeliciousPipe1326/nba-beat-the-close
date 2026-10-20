"""Local SQLite store. Schema is documented in docs/schema.md; keep them in sync.

The store lives under data/ (git-ignored). Nothing in it is ever committed.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path("data") / "nbatotals.db"

# Live anchors written by nbatotals.ingest.theodds. Offsets live in params.yaml.
LIVE_ANCHORS = ("opening", "t-10h", "t-5h", "t-3h", "t-2h", "t-1h", "t-15m", "close")
MARKETS = ("totals", "spreads", "h2h")

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY,   -- BallDontLie game id
    game_date    TEXT NOT NULL,         -- NBA schedule date (US Eastern), YYYY-MM-DD
    tip_utc      TEXT,                  -- scheduled tip, ISO-8601 UTC; NULL if unknown
    season       INTEGER NOT NULL,      -- start year: 2024 = 2024-25
    postseason   INTEGER NOT NULL DEFAULT 0,  -- 1 for play-in and playoffs
    home         TEXT NOT NULL,         -- 3-letter alias
    away         TEXT NOT NULL,
    home_pts     INTEGER,               -- NULL until final
    away_pts     INTEGER,
    periods      INTEGER,               -- 4 = regulation, 5 = one OT, ...
    status       TEXT NOT NULL,         -- 'final' or 'scheduled' (normalised)
    source       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_games_date ON games(game_date);
CREATE INDEX IF NOT EXISTS ix_games_season ON games(season);

CREATE TABLE IF NOT EXISTS team_box (
    game_id      INTEGER NOT NULL REFERENCES games(id),
    team         TEXT NOT NULL,
    opp          TEXT NOT NULL,
    is_home      INTEGER NOT NULL,
    minutes      REAL NOT NULL,         -- team minutes / 5, i.e. 48 + 5 per OT
    pts          INTEGER NOT NULL,
    fgm          INTEGER NOT NULL,
    fga          INTEGER NOT NULL,
    fg3m         INTEGER,
    fg3a         INTEGER,
    ftm          INTEGER,
    fta          INTEGER NOT NULL,
    orb          INTEGER NOT NULL,
    drb          INTEGER NOT NULL,
    tov          INTEGER NOT NULL,
    possessions  REAL NOT NULL,         -- game possessions, averaged over both teams
    pace         REAL NOT NULL,         -- possessions per 48 minutes
    ortg         REAL NOT NULL,         -- points scored per 100 possessions
    drtg         REAL NOT NULL,         -- points allowed per 100 possessions
    source       TEXT NOT NULL,
    PRIMARY KEY (game_id, team)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    event_id     TEXT NOT NULL,         -- the odds provider's event id
    game_id      INTEGER REFERENCES games(id),  -- BallDontLie id; NULL until the fixture is matched
    book         TEXT NOT NULL,
    market       TEXT NOT NULL CHECK (market IN ('totals','spreads','h2h')),
    anchor       TEXT NOT NULL,         -- live: opening, t-10h ... t-15m, close; legacy: legacy_* (see docs/schema.md)
    captured_utc TEXT,                  -- when the provider was polled; NULL only for unmatched legacy rows
    commence_utc TEXT,                  -- the event's scheduled tip as the provider reported it at that poll
    lead_minutes REAL,                  -- commence_utc - captured_utc, in minutes (always > 0 for live rows)
    home         TEXT,                  -- aliases as the provider named the teams
    away         TEXT,
    line         REAL,                  -- totals: the total; spreads: home spread; h2h: NULL
    over_price   REAL,                  -- totals only, decimal odds
    under_price  REAL,
    home_price   REAL,                  -- spreads/h2h only, decimal odds
    away_price   REAL,
    source       TEXT NOT NULL,
    PRIMARY KEY (event_id, book, market, anchor)
);
CREATE INDEX IF NOT EXISTS ix_odds_market ON odds_snapshots(market, anchor);
CREATE INDEX IF NOT EXISTS ix_odds_game ON odds_snapshots(game_id);

CREATE TABLE IF NOT EXISTS injuries (
    observed_utc TEXT NOT NULL,
    player_id    INTEGER NOT NULL,
    team         TEXT,
    player_name  TEXT,
    status       TEXT,                  -- as reported, e.g. 'Out', 'Day-To-Day'
    description  TEXT,
    return_date  TEXT,
    source       TEXT NOT NULL,
    PRIMARY KEY (observed_utc, player_id)
);

CREATE TABLE IF NOT EXISTS api_usage (
    called_utc   TEXT NOT NULL,
    provider     TEXT NOT NULL,
    endpoint     TEXT NOT NULL,
    requests_used      INTEGER,
    requests_remaining INTEGER,
    cost         INTEGER
);
"""


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
