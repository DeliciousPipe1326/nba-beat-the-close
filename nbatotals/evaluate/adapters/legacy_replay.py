"""Maintainer only: replay recorded The Odds API historical responses through the backfill-odds code path.

Used by tests/test_replay_legacy.py, which is skipped unless the private
folders are configured. No request is made. Each recorded per-event response
(the maintainer's nba_odds lake; never copied into this repository) is treated
as the reply to the request the backfill planner would have made at the
response's requested time, and runs through the same functions as a live
backfill (`nbatotals.ingest.theodds_history.parse_snapshot` and `store_rows`):
the per-event commence-time join, the in-play drop, the (event, book, market,
anchor) dedupe and the store write.

A recorded file carries `_metadata` {bucket_name, requested_timestamp,
api_game_id, ...} and the provider's payload ({timestamp, data: [event]},
possibly wrapped once more under "data"). The requested game is the event
`api_game_id`, identified from its own commence_time and team names; the
anchor is the recorded bucket name; the nominal lead is tip − requested time.
Events at or before the snapshot (in play) and events more than the planner's
maximum lead (36 h) after it are counted and store nothing. Files without
metadata are counted and skipped.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from nbatotals.ingest import common, theodds, theodds_history

ENV_VAR = "NBA_LEGACY_REPLAY_EVENTS"  # folder of recorded per-event responses (nba_odds lake)
MAX_LEAD_MINUTES = max(max(leads) for leads in theodds_history.DEFAULT_ANCHORS.values())  # 36 h


@dataclass
class Recorded:
    path: Path
    payload: dict  # {"timestamp": ..., "data": [events]}
    requested_at: dt.datetime
    bucket: str
    target_event: str


def _unwrap(d: dict) -> dict:
    x = d
    while isinstance(x.get("data"), dict):
        x = x["data"]
    return x


def season_of(path: Path, snapshot: dt.datetime) -> int:
    """NBA season start year: from a season=YYYY-YY folder, else from the snapshot date (Aug-Dec = that year)."""
    m = re.search(r"season=(\d{4})-\d{2}", str(path))
    if m:
        return int(m.group(1))
    return snapshot.year if snapshot.month >= 8 else snapshot.year - 1


def read_recorded(root: str | Path, season: int | None, skipped: Counter) -> Iterator[Recorded]:
    for f in sorted(Path(root).rglob("*.json")):
        d = json.loads(f.read_text())
        meta = d.get("_metadata") if isinstance(d, dict) else None
        payload = _unwrap(d) if isinstance(d, dict) else {}
        if "timestamp" not in payload or not isinstance(payload.get("data"), list):
            skipped["not_a_snapshot"] += 1
            continue
        if not meta or not all(meta.get(k) for k in ("bucket_name", "requested_timestamp", "api_game_id")):
            skipped["no_metadata"] += 1
            continue
        if season is not None and season_of(f, theodds._ts(payload["timestamp"])) != season:
            continue
        yield Recorded(f, payload, theodds._ts(meta["requested_timestamp"]), meta["bucket_name"], meta["api_game_id"])


def request_for(rec: Recorded, lookup: dict) -> tuple[theodds_history.Request | None, Counter]:
    """The planner request this recorded reply answers, and the file's event counts."""
    snap = theodds._ts(rec.payload["timestamp"])
    counts: Counter = Counter()
    req = None
    for ev in rec.payload["data"]:
        counts["events"] += 1
        tip = theodds._ts(ev["commence_time"])
        lead = (tip - snap).total_seconds() / 60.0
        if lead <= 0:
            counts["in_play"] += 1
        elif lead > MAX_LEAD_MINUTES:
            counts["beyond_max_lead"] += 1
        elif ev.get("id") != rec.target_event:
            counts["not_the_requested_event"] += 1
        elif (gid := theodds_history._event_game(ev, lookup)) is None:
            counts["not_in_store"] += 1
        else:
            counts["requested"] += 1
            nominal = round((tip - rec.requested_at).total_seconds() / 60.0)
            req = theodds_history.Request(rec.bucket, nominal, rec.requested_at, ((gid, tip),))
    return req, counts


def replay(con, root: str | Path, season: int | None = None, now=None) -> dict:
    """Replay every recorded response under `root` (optionally one season) into the store."""
    lookup = theodds._games_lookup(con)
    clock = now or common.now_utc
    summary: dict = {"files": 0, "rows_written": 0, "events": Counter(), "skipped": Counter()}
    for rec in read_recorded(root, season, summary["skipped"]):
        req, counts = request_for(rec, lookup)
        summary["files"] += 1
        summary["events"].update(counts)
        common.log_usage(con, theodds_history.PROVIDER, "historical_odds (replay)", {}, clock())
        if req is not None:
            rows, _, _ = theodds_history.parse_snapshot(rec.payload, req, lookup)
            summary["rows_written"] += theodds_history.store_rows(con, rows)
        con.commit()
    return summary


def agreement(con, true_close_quotes, params: dict) -> dict:
    """The replayed store's reference anchor (built by the --store backtest's own functions) against the
    multi-region true close, game by game."""
    from nbatotals.evaluate import backtest, market

    q = backtest.store_quotes(con)
    leads = q.groupby("anchor")["lead_minutes"].median().to_dict()
    spec = backtest.store_spec(q["anchor"].unique(), leads)
    cons, _ = market.enforce_anchor_order(market.consensus(q, params), spec.ref)
    ref = cons[cons["anchor"] == spec.ref]
    tc = market.consensus(true_close_quotes, params)
    j = ref.merge(tc[tc["anchor"] == "true_close"], on="game_id", suffixes=("", "_tc"))
    return {
        "ref_anchor": spec.ref,
        "games_compared": len(j),
        "line_within_half_point": float(((j["line"] - j["line_tc"]).abs() <= 0.5).mean()),
        "ref_p_over_mean": float(ref["p_over"].mean()),
        "rows_at_or_after_tip": int((q["captured_utc"] >= q["commence_utc"]).sum()),
    }
