"""The Odds API ingester: NBA odds snapshots at fixed anchors before tip.

Run `python -m nbatotals poll-odds` on a schedule (every 5 to 10 minutes is
enough). Each run:

1. lists today's and upcoming NBA events (the `/events` endpoint, which The
   Odds API does not charge for) to get every event's `commence_time`;
2. works out which anchors are due: `opening` the first time an event is seen,
   then each `t-...` anchor once the event is within that many minutes of tip
   (offsets in params.yaml, defaulting to the buckets the backtest graded);
3. only if something is due (or `--force`), fetches odds for all events in one
   call, which costs `markets x regions` credits;
4. stores every book's quote for every due anchor, plus `close`, which is
   overwritten on every pre-tip poll and so ends up holding the last snapshot
   taken before tip.

Every row keeps the poll time (`captured_utc`) and the event's `commence_time`.
Nothing polled at or after tip is stored. This is the lesson of the legacy data
(docs/RESULTS.md, Appendix B): fixed-clock snapshots catch earlier games in play.

Totals feed the model; spreads and h2h are stored but unused. The key comes from
THEODDS_API_KEY only, and quota headers are logged to the api_usage table.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pandas as pd

from nbatotals.ingest import common
from nbatotals.teams import FULL_NAME_TO_ALIAS

PROVIDER = "theoddsapi"
KEY_VAR = "THEODDS_API_KEY"
BASE = "https://api.the-odds-api.com/v4"


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fetch_events(session, key: str, sport: str):
    return common.get_json(session, f"{BASE}/sports/{sport}/events", params={"apiKey": key, "dateFormat": "iso"},
                           provider=PROVIDER, redact=key)


def fetch_odds(session, key: str, sport: str, regions: str, markets: str):
    params = {"apiKey": key, "regions": regions, "markets": markets, "oddsFormat": "decimal", "dateFormat": "iso"}
    return common.get_json(session, f"{BASE}/sports/{sport}/odds", params=params, provider=PROVIDER, redact=key)


_EMPTY_QUOTE = dict(line=None, over_price=None, under_price=None, home_price=None, away_price=None)
_NOT_A_MARKET = object()  # a market this ingester does not store


def _totals_fields(out: dict) -> dict | None:
    o, u = out.get("Over"), out.get("Under")
    if not o or not u or o.get("point") is None or o.get("point") != u.get("point"):
        return None
    return dict(line=float(o["point"]), over_price=float(o["price"]), under_price=float(u["price"]))


def _sides_fields(out: dict, ev: dict, market: str) -> dict | None:
    h, a = out.get(ev["home_team"]), out.get(ev["away_team"])
    if not h or not a:
        return None
    line = float(h["point"]) if market == "spreads" and h.get("point") is not None else None
    return dict(home_price=float(h["price"]), away_price=float(a["price"]), line=line)


def _market_fields(m: dict, ev: dict):
    """The quote's stored fields; None for an unclean quote; _NOT_A_MARKET for an unstored market."""
    out = {o["name"]: o for o in m.get("outcomes", [])}
    if m["key"] == "totals":
        return _totals_fields(out)
    if m["key"] in ("spreads", "h2h"):
        return _sides_fields(out, ev, m["key"])
    return _NOT_A_MARKET


def _event_base(ev: dict, captured: dt.datetime, skipped: dict) -> dict | None:
    """Fields shared by every quote of a pre-tip event with known teams; None (and counted) otherwise."""
    tip = _ts(ev["commence_time"])
    if tip <= captured:
        skipped["in_play_events"] += 1
        return None
    home, away = FULL_NAME_TO_ALIAS.get(ev["home_team"]), FULL_NAME_TO_ALIAS.get(ev["away_team"])
    if home is None or away is None:
        skipped["unknown_team_events"] += 1
        return None
    return dict(event_id=ev["id"], commence_utc=common.iso(tip), captured_utc=common.iso(captured),
                lead_minutes=(tip - captured).total_seconds() / 60.0, home=home, away=away, source=PROVIDER)


def _book_rows(ev: dict, b: dict, base: dict, skipped: dict) -> list[dict]:
    if b.get("last_update") and _ts(b["last_update"]) > _ts(ev["commence_time"]):
        skipped["book_updated_after_tip"] += 1
        return []
    rows = []
    for m in b.get("markets", []):
        fields = _market_fields(m, ev)
        if fields is _NOT_A_MARKET:
            continue
        if fields is None:
            skipped["unclean_quotes"] += 1
            continue
        rows.append(dict(base, book=b["key"], market=m["key"], **_EMPTY_QUOTE) | fields)
    return rows


def parse_odds(payload: list, captured: dt.datetime) -> tuple[list[dict], dict]:
    """One row per (event, book, market) from a /odds response. Pre-tip quotes only."""
    rows: list[dict] = []
    skipped = {"in_play_events": 0, "unknown_team_events": 0, "book_updated_after_tip": 0, "unclean_quotes": 0}
    for ev in payload:
        base = _event_base(ev, captured, skipped)
        if base is None:
            continue
        for b in ev.get("bookmakers", []):
            rows += _book_rows(ev, b, base, skipped)
    return rows, skipped


def due_anchors(con: sqlite3.Connection, events: list, now: dt.datetime, offsets: dict,
                opening_recheck_minutes: float = 0) -> dict[str, set]:
    """Anchors (other than `close`) that the next fetch should record, per event id.

    `opening` is due for an event with no stored odds, but an opening-only fetch
    waits `opening_recheck_minutes` after the last odds call, so an event that no
    book has priced yet does not spend credits on every poll.
    """
    last = con.execute("SELECT MAX(called_utc) FROM api_usage WHERE provider = ? AND endpoint = 'odds'",
                       (PROVIDER,)).fetchone()[0]
    opening_ok = last is None or (now - _ts(last)).total_seconds() / 60.0 >= opening_recheck_minutes
    have: dict[str, set[str]] = {}
    for event_id, anchor in con.execute("SELECT DISTINCT event_id, anchor FROM odds_snapshots WHERE source = ?",
                                        (PROVIDER,)):
        have.setdefault(event_id, set()).add(anchor)
    due = {}
    for ev in events:
        minutes = (_ts(ev["commence_time"]) - now).total_seconds() / 60.0
        if minutes <= 0:
            continue
        got = have.get(ev["id"], set())
        want = {name for name, offset in offsets.items() if minutes <= offset and name not in got}
        if "opening" not in got and (opening_ok or want):
            want.add("opening")
        if want:
            due[ev["id"]] = want
    return due


def _games_lookup(con: sqlite3.Connection) -> dict:
    return {(d, h, a): gid for gid, d, h, a in con.execute("SELECT id, game_date, home, away FROM games")}


def _game_id(lookup, commence_utc: str, home: str, away: str):
    et_date = _ts(commence_utc).astimezone(_eastern()).strftime("%Y-%m-%d")
    return lookup.get((et_date, home, away))


def _eastern():
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")


def resolve_game_ids(con: sqlite3.Connection) -> int:
    """Attach BallDontLie game ids to odds rows by Eastern tip date and team aliases."""
    lookup = _games_lookup(con)
    rows = con.execute("SELECT DISTINCT event_id, commence_utc, home, away FROM odds_snapshots "
                       "WHERE game_id IS NULL AND commence_utc IS NOT NULL AND home IS NOT NULL").fetchall()
    n = 0
    for event_id, commence, home, away in rows:
        gid = _game_id(lookup, commence, home, away)
        if gid is not None:
            n += con.execute("UPDATE odds_snapshots SET game_id = ? WHERE event_id = ? AND game_id IS NULL",
                             (gid, event_id)).rowcount
    return n


COLUMNS = ["event_id", "game_id", "book", "market", "anchor", "captured_utc", "commence_utc", "lead_minutes",
           "home", "away", "line", "over_price", "under_price", "home_price", "away_price", "source"]


def store_rows(con: sqlite3.Connection, rows: list[dict], due: dict[str, set]) -> int:
    """First capture wins for named anchors; `close` is replaced on every pre-tip poll."""
    lookup = _games_lookup(con)
    n = 0
    for r in rows:
        r = dict(r, game_id=_game_id(lookup, r["commence_utc"], r["home"], r["away"]))
        for anchor in sorted(due.get(r["event_id"], set())) + ["close"]:
            verb = "INSERT OR REPLACE" if anchor == "close" else "INSERT OR IGNORE"
            values = [r[c] if c != "anchor" else anchor for c in COLUMNS]
            n += con.execute(f"{verb} INTO odds_snapshots ({', '.join(COLUMNS)}) VALUES "
                             f"({', '.join('?' * len(COLUMNS))})", values).rowcount
    return n


def poll(con: sqlite3.Connection, params: dict, *, session=None, key: str | None = None, now=None,
         force: bool = False) -> dict:
    """One polling pass. Returns a summary; never prints the key."""
    cfg = params["ingest"]["theodds"]
    key = key or common.get_key(KEY_VAR)
    session = session or common.default_session()
    clock = now or common.now_utc
    t0 = clock() if callable(clock) else clock
    events, headers = fetch_events(session, key, cfg["sport"])
    common.log_usage(con, PROVIDER, "events", headers, t0)
    due = due_anchors(con, events, t0, cfg["anchors_minutes_before_tip"], cfg["opening_recheck_minutes"])
    summary = {"events": len(events), "events_with_due_anchors": len(due),
               "due": {e: sorted(a) for e, a in due.items()}, "fetched": False, "rows_written": 0}
    if not due and not force:
        con.commit()
        return summary
    remaining = common.last_remaining(con, PROVIDER)
    if remaining is not None and remaining < cfg["min_requests_remaining"]:
        con.commit()
        raise common.ApiError(f"The Odds API quota low ({remaining} left, floor {cfg['min_requests_remaining']} "
                              "in params.yaml); not fetching odds")
    t1 = clock() if callable(clock) else clock
    payload, headers = fetch_odds(session, key, cfg["sport"], cfg["regions"], cfg["markets"])
    usage = common.log_usage(con, PROVIDER, "odds", headers, t1)
    rows, skipped = parse_odds(payload, t1)
    summary.update(fetched=True, credits_used=usage["cost"], credits_remaining=usage["remaining"], skipped=skipped,
                   rows_written=store_rows(con, rows, due))
    con.commit()
    return summary


def snapshots(con: sqlite3.Connection, market: str = "totals") -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM odds_snapshots WHERE market = ? AND source = ?", con,
                             params=(market, PROVIDER))
