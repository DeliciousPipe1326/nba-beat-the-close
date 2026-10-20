"""Market anchors from the maintainer's multi-region The Odds API payloads.

Layout (private, never copied into this repository; path from
NBA_LEGACY_MULTIREGION): season=YYYY-YY/date=YYYY-MM-DD/nba_game_id=<id>/
bucket=<bucket>/totals.json, each holding one event polled at a fixed offset
before tip, with `metadata.timestamp` (when polled) and `event.commence_time`.

Pre-registration Amendment 2: anchors are the seven buckets; a file counts
only if it was polled before commence_time; a book is dropped if its
last_update is after commence_time or its over/under points differ; games are
joined on commence_time's US Eastern date plus team names mapped to aliases.
The same folders hold spreads.json and h2h.json (same layout; outcomes named by
team); `side_quotes` reads them under the same rules for Experiment 5
(docs/experiments/other_markets/PREREGISTRATION.md).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from nbatotals import boxscore
from nbatotals.teams import FULL_NAME_TO_ALIAS

ENV_VAR = "NBA_LEGACY_MULTIREGION"
MARKETS = ("totals", "spreads", "h2h")
BUCKETS = ("opening", "noon", "afternoon", "early_evening", "late_evening", "near_close", "true_close")
LABELS = {
    "opening": "opening (~24h)", "noon": "noon (~10h)", "afternoon": "afternoon (~5h)",
    "early_evening": "early evening (~3h)", "late_evening": "late evening (~2h)",
    "near_close": "near close (~1h)", "true_close": "true close (T−15 min)",
}


def root_path(path: str | os.PathLike | None = None) -> Path:
    path = path or os.environ.get(ENV_VAR)
    if not path:
        raise RuntimeError(f"set {ENV_VAR} to the legacy multi_region_oct2024 folder")
    path = Path(path)
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def read_files(path: str | os.PathLike | None = None, market: str = "totals") -> pd.DataFrame:
    """One row per (file, book) with the quote as the file states it.

    `market` is "totals" (columns over_/under_point and _american), or "spreads"
    or "h2h" (columns home_/away_point and _american, matched by outcome name to
    the event's home and away team; `n_outcomes` and `names_ok` record whether
    the book's outcomes are exactly those two teams).
    """
    if market not in MARKETS:
        raise ValueError(f"market must be one of {MARKETS}")
    rows = []
    for f in sorted(root_path(path).glob(f"season=*/date=*/nba_game_id=*/bucket=*/{market}.json")):
        payload = json.loads(f.read_text())
        meta, ev = payload["metadata"], payload["event"]
        base = dict(file=str(f.relative_to(f.parents[4])), bucket=meta["bucket"], polled_utc=meta["timestamp"],
                    event_id=ev["id"], commence_utc=ev["commence_time"], home_name=ev["home_team"],
                    away_name=ev["away_team"])
        for b in payload.get("bookmakers", []):
            m = b.get("market") or {}
            row = dict(base, book=b["key"], book_last_update=b.get("last_update"))
            outcomes = m.get("outcomes", [])
            if market == "totals":
                for o in outcomes:
                    side = o["name"].lower()
                    row[f"{side}_point"] = o.get("point")
                    row[f"{side}_american"] = o.get("price")
            else:
                sides = {ev["home_team"]: "home", ev["away_team"]: "away"}
                row["n_outcomes"] = len(outcomes)
                row["names_ok"] = sorted(o.get("name") for o in outcomes) == sorted(sides)
                for o in outcomes:
                    side = sides.get(o.get("name"))
                    if side:
                        row[f"{side}_point"] = o.get("point")
                        row[f"{side}_american"] = o.get("price")
            rows.append(row)
    return pd.DataFrame(rows)


def _join(raw: pd.DataFrame, games: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Join files to games and drop in-play files and books updated after tip (any market)."""
    r = raw.copy()
    unknown = sorted(set(r["home_name"]).union(r["away_name"]) - set(FULL_NAME_TO_ALIAS))
    if unknown:
        raise KeyError(f"team names missing from FULL_NAME_TO_ALIAS: {unknown}")
    tip = pd.to_datetime(r["commence_utc"], utc=True)
    polled = pd.to_datetime(r["polled_utc"], utc=True)
    r["tip_date"] = tip.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    r["home"] = r["home_name"].map(FULL_NAME_TO_ALIAS)
    r["away"] = r["away_name"].map(FULL_NAME_TO_ALIAS)
    r["lead_hours"] = (tip - polled).dt.total_seconds() / 3600.0
    counts = {"files": int(r["file"].nunique()), "events": int(r["event_id"].nunique())}
    g = games[["id", "game_date", "home", "away"]].rename(columns={"id": "game_id"})
    m = r.merge(g, left_on=["tip_date", "home", "away"], right_on=["game_date", "home", "away"], how="inner")
    counts["events_matched_to_a_game"] = int(m["event_id"].nunique())
    counts["games_matched"] = int(m["game_id"].nunique())
    in_play = m["lead_hours"] <= 0
    counts["files_polled_at_or_after_tip"] = int(m.loc[in_play, "file"].nunique())
    m = m[~in_play]
    late = pd.to_datetime(m["book_last_update"], utc=True) > pd.to_datetime(m["commence_utc"], utc=True)
    counts["book_rows_last_update_after_tip"] = int(late.sum())
    return m[~late], counts


def anchor_quotes(raw: pd.DataFrame, games: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Totals quotes per game and bucket, with `anchor` = bucket name."""
    m, counts = _join(raw, games)
    bad = (m["over_point"].isna() | (m["over_point"] != m["under_point"])
           | m["over_american"].isna() | m["under_american"].isna())
    counts["book_rows_without_a_clean_quote"] = int(bad.sum())
    m = m[~bad]
    dup = m.duplicated(["game_id", "bucket", "book"], keep="first")
    counts["duplicate_game_bucket_book_rows"] = int(dup.sum())
    m = m[~dup]
    dec = lambda s: s.map(boxscore.american_to_decimal).astype(float)
    out = pd.DataFrame({
        "game_id": m["game_id"].astype(int), "book": m["book"], "market": "totals", "anchor": m["bucket"],
        "captured_utc": m["polled_utc"], "commence_utc": m["commence_utc"], "lead_hours": m["lead_hours"],
        "line": m["over_point"].astype(float), "over_price": dec(m["over_american"]),
        "under_price": dec(m["under_american"]), "source": "legacy_multiregion",
    })
    bad_price = out["over_price"].isna() | out["under_price"].isna()
    counts["book_rows_invalid_american_price"] = int(bad_price.sum())
    return out[~bad_price].reset_index(drop=True), counts


def side_quotes(raw: pd.DataFrame, games: pd.DataFrame, market: str) -> tuple[pd.DataFrame, dict]:
    """Spreads or h2h quotes per game and bucket (Experiment 5 pre-registration).

    A book counts when its outcomes are exactly the event's two teams with
    prices, and for spreads both points are present with home = -(away).
    `line` is the home spread for spreads and NaN for h2h.
    """
    m, counts = _join(raw, games)
    for col in ("home_point", "away_point", "home_american", "away_american"):
        if col not in m:
            m[col] = None
    bad = ~m["names_ok"].astype(bool) | (m["n_outcomes"] != 2) | m["home_american"].isna() | m["away_american"].isna()
    if market == "spreads":
        hp, ap = pd.to_numeric(m["home_point"]), pd.to_numeric(m["away_point"])
        bad |= hp.isna() | ap.isna() | (hp != -ap)
    counts["book_rows_without_a_clean_quote"] = int(bad.sum())
    m = m[~bad]
    dup = m.duplicated(["game_id", "bucket", "book"], keep="first")
    counts["duplicate_game_bucket_book_rows"] = int(dup.sum())
    m = m[~dup]
    dec = lambda s: s.map(boxscore.american_to_decimal).astype(float)
    out = pd.DataFrame({
        "game_id": m["game_id"].astype(int), "book": m["book"], "market": market, "anchor": m["bucket"],
        "captured_utc": m["polled_utc"], "commence_utc": m["commence_utc"], "lead_hours": m["lead_hours"],
        "line": pd.to_numeric(m["home_point"]).astype(float) if market == "spreads" else float("nan"),
        "home_price": dec(m["home_american"]), "away_price": dec(m["away_american"]), "source": "legacy_multiregion",
    })
    bad_price = out["home_price"].isna() | out["away_price"].isna()
    counts["book_rows_invalid_american_price"] = int(bad_price.sum())
    return out[~bad_price].reset_index(drop=True), counts
