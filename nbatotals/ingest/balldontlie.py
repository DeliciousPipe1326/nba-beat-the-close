"""BallDontLie ingester: fixtures, finals, team box scores, injuries.

Key from BALLDONTLIE_API_KEY only (sent as the Authorization header). Free
tiers are rate-limited, so requests are spaced by
`ingest.balldontlie.min_seconds_between_requests` in params.yaml.

Team box scores are built by summing the player rows from `/stats` per team
and game, then deriving possessions, pace and ratings with the same code the
backtest used (nbatotals/boxscore.py). Player sums leave out "team" turnovers
(shot-clock violations and the like), so possessions computed here can come out
a little lower than from an official team box score. The legacy backtest used
official team totals; this difference has not been measured.

Injuries (`/player_injuries`) need a BallDontLie plan that includes them. Tier A
does not use them; they are stored so you can build your own adjustment, and
past reports cannot be fetched later, so collect them as you go.
"""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict

from nbatotals import boxscore
from nbatotals.ingest import common
from nbatotals.teams import BDL_ID_TO_ALIAS

PROVIDER = "balldontlie"
KEY_VAR = "BALLDONTLIE_API_KEY"
BASE = "https://api.balldontlie.io/v1"
STAT_FIELDS = {"pts": "pts", "fgm": "fgm", "fga": "fga", "fg3m": "fg3m", "fg3a": "fg3a", "ftm": "ftm",
               "fta": "fta", "orb": "oreb", "drb": "dreb", "tov": "turnover"}


class Client:
    def __init__(self, params: dict, *, session=None, key: str | None = None, sleep=time.sleep):
        cfg = params["ingest"]["balldontlie"]
        self.key = key or common.get_key(KEY_VAR)
        self.session = session or common.default_session()
        self.gap = float(cfg["min_seconds_between_requests"])
        self.per_page = int(cfg["per_page"])
        self.sleep = sleep
        self._last = None

    def pages(self, path: str, params: dict):
        """Yield every row across cursor pages."""
        params = dict(params, per_page=self.per_page)
        while True:
            if self._last is not None and self.gap:
                wait = self.gap - (time.monotonic() - self._last)
                if wait > 0:
                    self.sleep(wait)
            self._last = time.monotonic()
            body, _ = common.get_json(self.session, f"{BASE}/{path}", params=params,
                                      headers={"Authorization": self.key}, provider=PROVIDER, redact=self.key)
            yield from body.get("data", [])
            cursor = (body.get("meta") or {}).get("next_cursor")
            if not cursor:
                return
            params = dict(params, cursor=cursor)


def _game_row(g: dict) -> dict:
    final = g.get("status") == "Final"
    tip = g.get("datetime")
    if tip and not tip.endswith("Z"):
        tip = tip.replace("+00:00", "Z")
    return {
        "id": int(g["id"]), "game_date": g["date"][:10], "tip_utc": tip, "season": int(g["season"]),
        "postseason": int(bool(g.get("postseason"))),
        "home": BDL_ID_TO_ALIAS[g["home_team"]["id"]], "away": BDL_ID_TO_ALIAS[g["visitor_team"]["id"]],
        "home_pts": g.get("home_team_score") if final else None,
        "away_pts": g.get("visitor_team_score") if final else None,
        "periods": g.get("period") if final else None,
        "status": "final" if final else "scheduled", "source": PROVIDER,
    }


def ingest_games(con: sqlite3.Connection, client: Client, *, dates=None, seasons=None) -> int:
    """Upsert fixtures and finals for the given dates (YYYY-MM-DD) or seasons (start years)."""
    params = {}
    if dates:
        params["dates[]"] = list(dates)
    if seasons:
        params["seasons[]"] = [int(s) for s in seasons]
    if not params:
        raise ValueError("give dates or seasons")
    cols = ["id", "game_date", "tip_utc", "season", "postseason", "home", "away", "home_pts", "away_pts",
            "periods", "status", "source"]
    n = 0
    for g in client.pages("games", params):
        if g["home_team"]["id"] not in BDL_ID_TO_ALIAS or g["visitor_team"]["id"] not in BDL_ID_TO_ALIAS:
            continue  # exhibition games against non-NBA teams
        row = _game_row(g)
        con.execute(f"INSERT OR REPLACE INTO games ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [row[c] for c in cols])
        n += 1
    con.commit()
    return n


def team_box_from_stats(stats: list[dict], games: dict[int, dict]) -> list[dict]:
    """Sum player rows into one row per team per game; derive possessions etc."""
    sums = defaultdict(lambda: defaultdict(float))
    for s in stats:
        gid, team = int(s["game"]["id"]), BDL_ID_TO_ALIAS.get(s["team"]["id"])
        if team is None:
            continue
        for ours, theirs in STAT_FIELDS.items():
            sums[(gid, team)][ours] += float(s.get(theirs) or 0)
    out = []
    for gid, g in games.items():
        h, a = sums.get((gid, g["home"])), sums.get((gid, g["away"]))
        if not h or not a:
            continue
        home = {k: int(v) for k, v in h.items()}
        away = {k: int(v) for k, v in a.items()}
        hb, ab = boxscore.derive(home, away, g["periods"])
        for row, opp, is_home in ((hb, g["away"], 1), (ab, g["home"], 0)):
            row.update(game_id=gid, team=g["home"] if is_home else g["away"], opp=opp, is_home=is_home,
                       source=PROVIDER)
            out.append(row)
    return out


def ingest_box(con: sqlite3.Connection, client: Client, *, game_ids=None, dates=None, seasons=None,
               missing_only: bool = True) -> int:
    """Fetch player stats for final games and store team box scores."""
    q = "SELECT id, home, away, periods, game_date, season FROM games WHERE status = 'final'"
    games = {r[0]: {"home": r[1], "away": r[2], "periods": r[3], "date": r[4], "season": r[5]}
             for r in con.execute(q)}
    if game_ids:
        games = {k: v for k, v in games.items() if k in set(game_ids)}
    if dates:
        games = {k: v for k, v in games.items() if v["date"] in set(dates)}
    if seasons:
        games = {k: v for k, v in games.items() if v["season"] in {int(s) for s in seasons}}
    if missing_only:
        have = {r[0] for r in con.execute("SELECT DISTINCT game_id FROM team_box")}
        games = {k: v for k, v in games.items() if k not in have}
    cols = ["game_id", "team", "opp", "is_home", "minutes", "pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
            "orb", "drb", "tov", "possessions", "pace", "ortg", "drtg", "source"]
    ids = sorted(games)
    n = 0
    for i in range(0, len(ids), 25):
        chunk = ids[i:i + 25]
        stats = list(client.pages("stats", {"game_ids[]": chunk}))
        for row in team_box_from_stats(stats, {k: games[k] for k in chunk}):
            con.execute(f"INSERT OR REPLACE INTO team_box ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        [row[c] for c in cols])
            n += 1
        con.commit()
    return n


def ingest_injuries(con: sqlite3.Connection, client: Client, *, observed=None) -> int:
    observed = common.iso(observed or common.now_utc())
    n = 0
    for r in client.pages("player_injuries", {}):
        p = r.get("player") or {}
        team = BDL_ID_TO_ALIAS.get(p.get("team_id"))
        con.execute(
            "INSERT OR REPLACE INTO injuries (observed_utc, player_id, team, player_name, status, description, "
            "return_date, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (observed, p.get("id"), team, f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
             r.get("status"), r.get("description"), r.get("return_date"), PROVIDER),
        )
        n += 1
    con.commit()
    return n
