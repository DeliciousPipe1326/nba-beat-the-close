"""Build a tiny SQLite DB in the legacy layout from made-up numbers.

Only the columns the legacy adapter reads are created. Every value is synthetic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

GAMES = [
    # id, date, season, status, period, postseason, home_id, away_id, home_score, away_score
    (101, "2023-10-24", 2023, "Final", 4, 0, 2, 20, 108, 104),   # BOS v NYK
    (102, "2023-10-25", 2023, "Final", 5, 0, 14, 10, 121, 119),  # LAL v GSW, one OT
    (103, "2023-10-26", 2023, "2023-10-27T00:00:00Z", 0, 0, 20, 2, None, None),
]

# game_id, team_id, pts, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, tov
BOX = [
    (101, 2, 108, 40, 88, 14, 40, 14, 18, 10, 35, 12),
    (101, 20, 104, 39, 90, 11, 33, 15, 20, 12, 33, 14),
    (102, 14, 121, 45, 95, 12, 35, 19, 24, 11, 38, 15),
    (102, 10, 119, 44, 97, 17, 42, 14, 16, 9, 36, 13),
]


def _provider_decimal(american):
    """The provider sends 2-dp decimal prices; legacy American columns were derived from them."""
    if american is None:
        return None
    return round(1 + (american / 100 if american > 0 else 100 / -american), 2)


GAME_DATES = {101: "2023-10-24", 102: "2023-10-25"}


def _legacy_pace(rows, gid):
    """What the legacy 'pace' column holds: raw game possessions."""
    sides = [r for r in rows if r[0] == gid]
    poss = [r[4] - r[9] + r[11] + 0.44 * r[8] for r in sides]
    return sum(poss) / 2


def _odds_rows():
    rows = []
    books = [("fanduel", -110, -110), ("draftkings", -112, -108), ("betmgm", -105, -115)]
    for gid, home_id, line in ((101, 2, 221.5), (102, 14, 230.0)):
        for anchor, hrs, shift in (("open", 18.0, -1.0), ("noon_local", 12.0, -0.5), ("close", 0.5, 0.0)):
            for book, o, u in books:
                rows.append((f"{gid}_{book}_totals_{anchor}", str(gid), "totals", anchor, book, hrs,
                             home_id, line + shift, o, u, None, None, None, None, None))
            rows.append((f"{gid}_fanduel_spreads_{anchor}", str(gid), "spreads", anchor, "fanduel", hrs,
                         home_id, None, None, None, -3.5, -110, -110, None, None))
            rows.append((f"{gid}_fanduel_h2h_{anchor}", str(gid), "h2h", anchor, "fanduel", hrs,
                         home_id, None, None, None, None, None, None, -160, 140))
    # one quote missing a price, one half-game total filed as full game
    rows.append(("101_gtbets_totals_close", "101", "totals", "close", "gtbets", 0.5, 2, 221.0, -110, None,
                 None, None, None, None, None))
    rows.append(("101_mybookieag_totals_close", "101", "totals", "close", "mybookieag", 0.5, 2, 55.0, -110, -110,
                 None, None, None, None, None))
    return rows


def build(path: str | Path) -> Path:
    path = Path(path)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE games (id INTEGER PRIMARY KEY, date DATE, season INTEGER, status TEXT,
            period INTEGER, postseason BOOLEAN, home_team_id INTEGER, visitor_team_id INTEGER,
            home_team_score INTEGER, visitor_team_score INTEGER, scheduled_tip_utc TEXT);
        CREATE TABLE team_game_stats (id INTEGER PRIMARY KEY, game_id INTEGER, team_id INTEGER,
            pace FLOAT, pts INTEGER, fgm INTEGER, fga INTEGER, fg3m INTEGER, fg3a INTEGER,
            ftm INTEGER, fta INTEGER, oreb INTEGER, dreb INTEGER, tov INTEGER);
        CREATE TABLE odds_truth (odds_id TEXT PRIMARY KEY, game_id TEXT, market_type TEXT,
            snapshot_type TEXT, bookmaker TEXT, hours_before_game REAL, home_team_id INTEGER,
            total_line REAL, total_over_odds INTEGER, total_under_odds INTEGER,
            spread_home REAL, spread_home_odds INTEGER, spread_away_odds INTEGER,
            ml_home_odds INTEGER, ml_away_odds INTEGER, snapshot_timestamp TIMESTAMP,
            raw_json_file TEXT, api_game_id TEXT,
            total_over_decimal REAL, total_under_decimal REAL, spread_home_decimal REAL,
            spread_away_decimal REAL, ml_home_decimal REAL, ml_away_decimal REAL);
        """
    )
    con.executemany("INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,NULL)", GAMES)
    con.executemany(
        "INSERT INTO team_game_stats (game_id, team_id, pace, pts, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, tov) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r[0], r[1], _legacy_pace(BOX, r[0]), *r[2:]) for r in BOX],
    )
    con.executemany(
        "INSERT INTO odds_truth VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,NULL,NULL,NULL,NULL)",
        [r + (f"/x/date={GAME_DATES[int(r[1])]}/snapshot={r[3]}/odds.json", f"ev{r[1]}",
              _provider_decimal(r[8]), _provider_decimal(r[9])) for r in _odds_rows()],
    )
    con.commit()
    con.close()
    return path


# Snapshot times per anchor for the synthetic lake. Game 101 tips 23:30Z on
# 2023-10-24 (19:30 ET); its "open" file is captured after tip (in-play).
SNAPSHOTS = {
    (101, "open"): "2023-10-25T00:25:00Z",
    (101, "noon_local"): "2023-10-24T06:25:00Z",
    (101, "close"): "2023-10-24T18:55:00Z",
    (102, "open"): "2023-10-24T00:25:00Z",
    (102, "noon_local"): "2023-10-25T06:25:00Z",
    (102, "close"): "2023-10-25T18:55:00Z",
}
COMMENCE = {101: "2023-10-24T23:30:00Z", 102: "2023-10-26T02:00:00Z"}
NAMES = {101: ("Boston Celtics", "New York Knicks"), 102: ("Los Angeles Lakers", "Golden State Warriors")}


def build_lake(root: str | Path) -> Path:
    """Raw-payload files matching the odds rows above, in the provider's layout."""
    import json

    root = Path(root)
    by_file = {}
    for r in _odds_rows():
        _, gid, market, anchor, book, _, _, total, o, u, *_ = r
        if market != "totals":
            continue
        gid = int(gid)
        key = (GAME_DATES[gid], anchor)
        ev = by_file.setdefault(key, {}).setdefault(gid, {
            "id": f"ev{gid}", "commence_time": COMMENCE[gid], "home_team": NAMES[gid][0],
            "away_team": NAMES[gid][1], "bookmakers": [],
        })
        outcomes = [{"name": "Over", "price": _provider_decimal(o), "point": total},
                    {"name": "Under", "price": _provider_decimal(u), "point": total}]
        ev["bookmakers"].append({"key": book, "last_update": SNAPSHOTS[(gid, anchor)],
                                 "markets": [{"key": "totals", "outcomes": outcomes}]})
    for (date, anchor), events in by_file.items():
        gid = next(iter(events))
        d = root / f"date={date}" / f"snapshot={anchor}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "odds.json").write_text(json.dumps({"timestamp": SNAPSHOTS[(gid, anchor)], "data": list(events.values())}))
    return root
