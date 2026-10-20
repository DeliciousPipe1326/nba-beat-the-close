"""Backfill the store's odds_snapshots for past games from The Odds API historical endpoint.

    python -m nbatotals backfill-odds --season 2024 [--anchors ...] [--markets ...] [--books ...]
                                       [--max-credits N] [--dry-run] [--yes]

A head start for building your own backtest store, not a product: it was
exercised on synthetic responses and by replaying the author's recorded
historical responses (nbatotals/evaluate/adapters/legacy_replay.py), never
against the live API from this repository.

Every rule below comes from a data defect found in the author's earlier work
(README, "Lessons"; docs/RESULTS.md, Appendix B), and is enforced here rather
than left to the user:

- Anchors are defined per game, relative to that game's own tip (`games.tip_utc`,
  from `ingest-games`), never at fixed clock times. The snapshot for a game's
  anchor is requested at tip − lead. The provider returns the nearest snapshot at
  or before that time; its own timestamp is stored as captured_utc, the requested
  lead as nominal_lead_minutes and the measured lead as lead_minutes. `opening`
  asks at 36 h, and if the game is not listed yet, at 24 h, then 18 h.
- Every event in a response is joined to a game by the event's own
  commence_time (US Eastern date) and team names, never by the request time, and
  only events of the games requested are kept. A snapshot taken at or after the
  event's commence_time, or a book updated at or after it, is in play: dropped
  and counted.
- Games whose request times fall in the same 5-minute window share one call per
  anchor: the provider keeps snapshots at 5-minute marks (10 before September
  2022) and returns the one at or before the requested time, so every game in
  the window gets exactly the snapshot it would have got alone. A (game, anchor) already
  backfilled is never requested again, and rows are keyed (event, book, market,
  anchor), so re-runs are idempotent and cost nothing for work already done.
- Nothing is spent until the cost is printed and confirmed: calls x credits per
  call (the provider's published rate for historical odds is 10 per market per
  region, or per group of 10 bookmakers), checked against the credits remaining
  and --max-credits. --dry-run prints the plan and makes no request at all and
  needs no key. Every request is logged to api_usage.

TODO: re-price from the response headers after the first paid call
(x-requests-last is the cost of that call, x-requests-remaining the balance)
and stop early if the rest no longer fits. Today the worst-case estimate is
checked once, before the first paid call.

The data you fetch is licensed to you by the provider: keep it in your local
store; do not redistribute it.
"""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
from collections import deque
from dataclasses import dataclass, field

from nbatotals.ingest import common, theodds
from nbatotals.teams import FULL_NAME_TO_ALIAS

PROVIDER = theodds.PROVIDER
SOURCE = "theoddsapi_historical"
CREDITS_PER_MARKET_REGION = 10

# anchor -> leads in minutes, tried in order (only opening has fallbacks)
DEFAULT_ANCHORS: dict[str, tuple[int, ...]] = {
    "opening": (36 * 60, 24 * 60, 18 * 60), "t-10h": (600,), "t-5h": (300,), "t-1h": (60,), "t-15m": (15,)}
# the bucket names of the pre-registered legacy test, accepted as aliases
ANCHOR_ALIASES = {"noon": "t-10h", "afternoon": "t-5h", "near_close": "t-1h", "true_close": "t-15m"}

STORE_COLUMNS = theodds.COLUMNS + ["nominal_lead_minutes"]


SNAPSHOT_MINUTES = 5


@dataclass
class Request:
    """One historical call: the snapshot at or before `at`, for `games` ((game id, tip) pairs)."""
    anchor: str
    lead: int  # minutes before each game's tip
    at: dt.datetime
    games: tuple[tuple[int, dt.datetime], ...]
    fallback: tuple[int, ...] = field(default=())  # further leads for games not yet listed

    @property
    def game_ids(self) -> tuple[int, ...]:
        return tuple(g for g, _ in self.games)


def _window(t: dt.datetime) -> dt.datetime:
    """Floor to the provider's snapshot grid: any request time in a window returns the same snapshot."""
    return t.replace(minute=t.minute - t.minute % SNAPSHOT_MINUTES, second=0, microsecond=0)


def requests_for(anchor: str, leads: tuple[int, ...], games: list[tuple[int, dt.datetime]]) -> list[Request]:
    """Group games by the snapshot window of tip − lead (first lead); later leads become fallbacks."""
    lead, rest = leads[0], tuple(leads[1:])
    windows: dict[dt.datetime, list[tuple[int, dt.datetime]]] = {}
    for gid, tip in games:
        windows.setdefault(_window(tip - dt.timedelta(minutes=lead)), []).append((gid, tip))
    return [Request(anchor, lead, at, tuple(sorted(gs)), rest) for at, gs in windows.items()]


def resolve_anchors(names: list[str] | None) -> dict[str, tuple[int, ...]]:
    if not names:
        return dict(DEFAULT_ANCHORS)
    out = {}
    for n in names:
        key = ANCHOR_ALIASES.get(n, n)
        if key not in DEFAULT_ANCHORS:
            raise ValueError(f"unknown anchor {n!r}; use {', '.join(DEFAULT_ANCHORS)} or {', '.join(ANCHOR_ALIASES)}")
        out[key] = DEFAULT_ANCHORS[key]
    return out


def plan(con: sqlite3.Connection, season: int, anchors: dict[str, tuple[int, ...]]) -> tuple[list[Request], dict]:
    """One request per (anchor, distinct tip time) over the season's games not yet backfilled at that anchor."""
    games = con.execute("SELECT id, tip_utc FROM games WHERE season = ?", (season,)).fetchall()
    done = set(con.execute("SELECT DISTINCT game_id, anchor FROM odds_snapshots WHERE source = ?", (SOURCE,)))
    counts = {"games": len(games), "games_without_tip_time": sum(1 for _, t in games if not t),
              "game_anchors_already_stored": 0}
    requests = []
    for anchor, leads in anchors.items():
        todo = []
        for gid, tip in games:
            if not tip:
                continue
            if (gid, anchor) in done:
                counts["game_anchors_already_stored"] += 1
                continue
            todo.append((gid, theodds._ts(tip)))
        requests += requests_for(anchor, leads, todo)
    requests.sort(key=lambda r: (r.at, r.anchor))
    counts["calls"] = len(requests)
    return requests, counts


def credits_per_call(markets: list[str], regions: list[str], books: list[str] | None) -> int:
    groups = math.ceil(len(books) / 10) if books else len(regions)
    return CREDITS_PER_MARKET_REGION * len(markets) * groups


def estimate(requests: list[Request], per_call: int) -> dict:
    fallbacks = sum(len(r.fallback) for r in requests)
    return {"calls": len(requests), "credits_per_call": per_call, "credits": len(requests) * per_call,
            "worst_case_calls": len(requests) + fallbacks, "worst_case_credits": (len(requests) + fallbacks) * per_call}


def plan_text(season: int, counts: dict, est: dict, anchors: dict, markets, regions, books) -> str:
    where = f"bookmakers {','.join(books)}" if books else f"regions {','.join(regions)}"
    return "\n".join([
        f"Backfill plan, season {season}-{str(season + 1)[-2:]}: anchors {', '.join(anchors)}; markets "
        f"{','.join(markets)}; {where}.",
        f"Games {counts['games']:,} ({counts['games_without_tip_time']:,} without a tip time, skipped); "
        f"(game, anchor) pairs already stored: {counts['game_anchors_already_stored']:,}.",
        f"Calls: {est['calls']:,} (games in the same 5-minute snapshot window share a call), "
        f"up to {est['worst_case_calls']:,} if openings need later snapshots.",
        f"Credits: {est['credits_per_call']} per call (10 x markets x regions, the provider's published rate) "
        f"= {est['credits']:,}; worst case {est['worst_case_credits']:,}.",
        "This is the published rate; the real cost of each call is in its x-requests-last header and is "
        "logged to api_usage.",
    ])


def per_game_plan(requests: list[Request]) -> list[dict]:
    """One row per (game, anchor): when it would be requested and with which other games it shares the call."""
    rows = []
    for r in requests:
        for gid, tip in r.games:
            rows.append({"game_id": gid, "tip_utc": common.iso(tip), "anchor": r.anchor, "lead_minutes": r.lead,
                         "request_at_utc": common.iso(r.at), "games_in_call": len(r.games),
                         "fallback_leads": ",".join(str(x) for x in r.fallback)})
    return sorted(rows, key=lambda x: (x["tip_utc"], x["game_id"], -x["lead_minutes"]))


def per_game_text(rows: list[dict], limit: int = 12) -> str:
    head = "game_id  tip (UTC)             anchor   lead  request at (UTC)      games in call  fallbacks"
    lines = [head] + [f"{r['game_id']:<8} {r['tip_utc']}  {r['anchor']:<8} {r['lead_minutes']:>5}  "
                      f"{r['request_at_utc']}  {r['games_in_call']:>13}  {r['fallback_leads']}" for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit:,} more (game, anchor) rows in the full plan file")
    return "\n".join(lines)


def fetch_snapshot(session, key: str, sport: str, at: dt.datetime, markets, regions, books):
    params = {"apiKey": key, "markets": ",".join(markets), "oddsFormat": "decimal", "dateFormat": "iso",
              "date": common.iso(at)}
    if books:
        params["bookmakers"] = ",".join(books)
    else:
        params["regions"] = ",".join(regions)
    return common.get_json(session, f"{theodds.BASE}/historical/sports/{sport}/odds", params=params,
                           provider=PROVIDER, redact=key)


def _event_game(ev: dict, lookup: dict) -> int | None:
    """The store game an event is, by its own commence_time (Eastern date) and team names."""
    home, away = FULL_NAME_TO_ALIAS.get(ev.get("home_team", "")), FULL_NAME_TO_ALIAS.get(ev.get("away_team", ""))
    if home is None or away is None:
        return None
    return theodds._game_id(lookup, ev["commence_time"], home, away)


def parse_snapshot(payload: dict, req: Request, lookup: dict) -> tuple[list[dict], dict, set[int]]:
    """Rows for the requested games only; (rows, counts, requested games with no stored quote)."""
    snap = theodds._ts(payload["timestamp"])
    wanted = set(req.game_ids)
    game_of = {}
    for ev in payload.get("data", []):
        gid = _event_game(ev, lookup)
        if gid in wanted:
            game_of[ev["id"]] = gid
    events = [ev for ev in payload.get("data", []) if ev["id"] in game_of]
    rows, counts = theodds.parse_odds(events, snap)  # drops in-play events and books updated at or after tip
    counts["events_for_games_not_requested"] = len(payload.get("data", [])) - len(events)
    kept = [dict(r, game_id=game_of[r["event_id"]], anchor=req.anchor, nominal_lead_minutes=float(req.lead),
                 source=SOURCE) for r in rows]
    return kept, counts, wanted - {r["game_id"] for r in kept}


def store_rows(con: sqlite3.Connection, rows: list[dict]) -> int:
    sql = (f"INSERT OR IGNORE INTO odds_snapshots ({', '.join(STORE_COLUMNS)}) "
           f"VALUES ({', '.join('?' * len(STORE_COLUMNS))})")
    return sum(con.execute(sql, [r[c] for c in STORE_COLUMNS]).rowcount for r in rows)


def affordable(calls: int, per_call: int, remaining: int | None, cap: int | None) -> tuple[bool, str]:
    need = calls * per_call
    if remaining is not None and need > remaining:
        return False, f"needs up to {need:,} credits, {remaining:,} remain"
    if cap is not None and need > cap:
        return False, f"needs up to {need:,} credits, over --max-credits {cap:,}"
    return True, ""


def _remaining_credits(con, session, key: str, now) -> int | None:
    """The quota left, from a request the provider does not charge for (the sports list)."""
    _, headers = common.get_json(session, f"{theodds.BASE}/sports", params={"apiKey": key}, provider=PROVIDER,
                                 redact=key)
    return common.log_usage(con, PROVIDER, "sports", headers, now)["remaining"]


def _add(summary: dict, counts: dict) -> None:
    for k, v in counts.items():
        summary["drops"][k] = summary["drops"].get(k, 0) + v


def run_requests(con, queue: deque, fetch, now, summary: dict) -> dict:
    """Execute the queue (the worst-case cost was checked before the first call)."""
    lookup = theodds._games_lookup(con)
    while queue:
        req = queue.popleft()
        payload, headers = fetch(req)
        common.log_usage(con, PROVIDER, "historical_odds", headers, now())
        summary["calls"] += 1
        rows, counts, missing = parse_snapshot(payload, req, lookup)
        summary["rows_written"] += store_rows(con, rows)
        con.commit()
        _add(summary, counts)
        if missing and req.fallback:
            later = [(g, tip) for g, tip in req.games if g in missing]
            queue.extendleft(reversed(requests_for(req.anchor, req.fallback, later)))
        elif missing:
            summary["game_anchors_not_listed"] += len(missing)
    return summary


def backfill(con: sqlite3.Connection, params: dict, season: int, *, anchors=None, markets=("totals",),
             regions=("us",), books=None, max_credits=None, dry_run=False, confirm=None, session=None,
             key=None, now=None, out=print) -> dict:
    anchors = resolve_anchors(list(anchors) if anchors else None)
    requests, counts = plan(con, season, anchors)
    per_call = credits_per_call(list(markets), list(regions), list(books) if books else None)
    est = estimate(requests, per_call)
    out(plan_text(season, counts, est, anchors, markets, regions, books))
    summary = {"plan": counts, "estimate": est, "calls": 0, "rows_written": 0, "drops": {},
               "game_anchors_not_listed": 0, "stopped": None, "dry_run": dry_run,
               "per_game_plan": per_game_plan(requests)}
    if dry_run or not requests:
        out(per_game_text(summary["per_game_plan"]))
        out("Dry run: no request was made and no key is needed." if dry_run else "Nothing to fetch.")
        return summary
    key = key or common.get_key(theodds.KEY_VAR)
    session = session or common.default_session()
    clock = now or common.now_utc
    remaining = _remaining_credits(con, session, key, clock())
    ok, why = affordable(est["worst_case_calls"], per_call, remaining, max_credits)
    if not ok:
        summary["stopped"] = f"refused before any paid call: {why}"
        out(summary["stopped"])
        return summary
    ask = f"Spend up to {est['worst_case_credits']:,} credits ({remaining} remaining)? Type yes to continue: "
    if not (confirm or (lambda text: input(text).strip().lower() == "yes"))(ask):
        summary["stopped"] = "not confirmed"
        return summary

    def fetch(req: Request):
        return fetch_snapshot(session, key, params["ingest"]["theodds"]["sport"], req.at, markets, regions, books)

    return run_requests(con, deque(requests), fetch, clock, summary)
