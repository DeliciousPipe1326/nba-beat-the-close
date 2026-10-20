"""Synthetic API payloads and a fake HTTP session, so ingesters are tested offline.

Shapes follow The Odds API v4 and BallDontLie v1 responses; every value is made up.
"""

from __future__ import annotations

FAKE_ODDS_KEY = "test-odds-key-not-real-0000"
FAKE_BDL_KEY = "test-bdl-key-not-real-0000"


class FakeResponse:
    def __init__(self, body, status=200, headers=None, text=""):
        self._body, self.status_code, self.headers, self.text = body, status, headers or {}, text

    def json(self):
        return self._body


class FakeSession:
    """Routes GETs by URL suffix to queued responses; records every call."""

    def __init__(self, routes: dict):
        self.routes = {k: list(v) if isinstance(v, list) else [v] for k, v in routes.items()}
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        for suffix, queue in self.routes.items():
            if url.endswith(suffix):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected URL {url}")


# --------------------------------------------------------------------------- The Odds API

EVENTS = [
    {"id": "evA", "sport_key": "basketball_nba", "commence_time": "2025-11-05T00:00:00Z",
     "home_team": "Boston Celtics", "away_team": "New York Knicks"},
    {"id": "evB", "sport_key": "basketball_nba", "commence_time": "2025-11-05T03:00:00Z",
     "home_team": "Los Angeles Lakers", "away_team": "Golden State Warriors"},
]


def odds_event(event: dict, total: float, books=("fanduel", "draftkings", "betmgm"),
               last_update="2025-11-04T01:00:00Z"):
    out = dict(event, bookmakers=[])
    for i, b in enumerate(books):
        out["bookmakers"].append({
            "key": b, "title": b, "last_update": last_update,
            "markets": [
                {"key": "totals", "outcomes": [{"name": "Over", "price": 1.91, "point": total + 0.5 * (i == 2)},
                                               {"name": "Under", "price": 1.91, "point": total + 0.5 * (i == 2)}]},
                {"key": "spreads", "outcomes": [{"name": event["home_team"], "price": 1.91, "point": -4.5},
                                                {"name": event["away_team"], "price": 1.91, "point": 4.5}]},
                {"key": "h2h", "outcomes": [{"name": event["home_team"], "price": 1.6},
                                            {"name": event["away_team"], "price": 2.4}]},
            ],
        })
    return out


def quota_headers(used, remaining, last):
    return {"x-requests-used": str(used), "x-requests-remaining": str(remaining), "x-requests-last": str(last)}


# --------------------------------------------------------------------------- BallDontLie

def bdl_team(team_id):
    return {"id": team_id}


def bdl_game(gid, date, home_id, away_id, status="Final", hs=110, as_=104, period=4, season=2025):
    return {"id": gid, "date": date, "datetime": f"{date}T23:30:00.000Z", "season": season, "status": status,
            "period": period, "postseason": False, "home_team": bdl_team(home_id), "visitor_team": bdl_team(away_id),
            "home_team_score": hs if status == "Final" else 0, "visitor_team_score": as_ if status == "Final" else 0}


def bdl_stat(gid, team_id, **kw):
    row = {"game": {"id": gid}, "team": {"id": team_id}, "pts": 0, "fgm": 0, "fga": 0, "fg3m": 0, "fg3a": 0,
           "ftm": 0, "fta": 0, "oreb": 0, "dreb": 0, "turnover": 0}
    row.update(kw)
    return row
