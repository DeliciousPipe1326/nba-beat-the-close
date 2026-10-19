"""Capture times for the legacy odds, from the raw The Odds API historical payloads.

The legacy `odds_truth` table has no capture timestamps, but each row names the
raw file it was parsed from (`raw_json_file`) and the provider's event id
(`api_game_id`). Those files (the maintainer's private lake, never copied into
this repository; path from NBA_LEGACY_ODDS_LAKE) carry, per file, the snapshot
time, and per event its `commence_time` and each book's `last_update`.

`read_lake` returns one row per (file, event, book) with the totals quote as the
file states it, so the adapter can attach capture time and tip time to every
legacy row and check that the parsed line and prices match the source.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd

ENV_VAR = "NBA_LEGACY_ODDS_LAKE"
FILE_KEY = re.compile(r"date=\d{4}-\d{2}-\d{2}/snapshot=[a-z_]+/odds\.json$")


def lake_path(path: str | os.PathLike | None = None) -> Path:
    path = path or os.environ.get(ENV_VAR)
    if not path:
        raise RuntimeError(f"set {ENV_VAR} to the legacy odds lake (…/data/lake/odds/temporal)")
    path = Path(path)
    if not path.is_dir():
        raise FileNotFoundError(path)
    return path


def file_key(raw_json_file: str) -> str | None:
    m = FILE_KEY.search(raw_json_file or "")
    return m.group(0) if m else None


def read_lake(path: str | os.PathLike | None = None) -> pd.DataFrame:
    root = lake_path(path)
    rows = []
    for f in sorted(root.glob("date=*/snapshot=*/odds.json")):
        key = file_key(str(f))
        payload = json.loads(f.read_text())
        snap = payload["timestamp"]
        for ev in payload.get("data", []):
            base = dict(file_key=key, snapshot_utc=snap, event_id=ev["id"], commence_utc=ev["commence_time"],
                        home_name=ev["home_team"], away_name=ev["away_team"])
            books = ev.get("bookmakers", [])
            if not books:
                rows.append(dict(base, book=None))
            for b in books:
                row = dict(base, book=b["key"], book_last_update=b.get("last_update"))
                for m in b.get("markets", []):
                    if m["key"] != "totals":
                        continue
                    for o in m["outcomes"]:
                        side = o["name"].lower()
                        row[f"{side}_point"] = o.get("point")
                        row[f"{side}_price"] = o.get("price")
                    row["totals_last_update"] = m.get("last_update")
                rows.append(row)
    return pd.DataFrame(rows)


# Partition D's three files, by the snapshot folder the provider fetch was saved under.
ANCHOR_BY_FOLDER = {"open": "early", "noon_local": "overnight", "close": "afternoon"}
LEGACY_ANCHORS = ("early", "overnight", "afternoon")
LEGACY_LABELS = {"early": "early (~23h)", "overnight": "overnight (~17h)", "afternoon": "afternoon (~6h)"}
MIN_AFTERNOON_LEAD_HOURS = 1.0


def anchor_quotes(lake: pd.DataFrame, games: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Totals quotes per game and anchor, rebuilt from the raw payloads (Amendment 1).

    Returns (quotes, counts). Quotes have the odds_snapshots columns plus
    commence_utc and lead_hours, with `anchor` in LEGACY_ANCHORS.
    """
    from nbatotals.teams import FULL_NAME_TO_ALIAS

    lk = lake.drop_duplicates(["file_key", "event_id", "book"], keep="first").copy()
    lk = lk[lk["book"].notna()]
    tip = pd.to_datetime(lk["commence_utc"], utc=True)
    snap = pd.to_datetime(lk["snapshot_utc"], utc=True)
    lk["tip_date"] = tip.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    lk["home"] = lk["home_name"].map(FULL_NAME_TO_ALIAS)
    lk["away"] = lk["away_name"].map(FULL_NAME_TO_ALIAS)
    lk["partition"] = lk["file_key"].str.extract(r"date=(\d{4}-\d{2}-\d{2})", expand=False)
    lk["anchor"] = lk["file_key"].str.extract(r"snapshot=([a-z_]+)", expand=False).map(ANCHOR_BY_FOLDER)
    lk["lead_hours"] = (tip - snap).dt.total_seconds() / 3600.0
    lk["last_update_after_tip"] = pd.to_datetime(lk["book_last_update"], utc=True) > tip

    g = games[["id", "game_date", "home", "away"]].rename(columns={"id": "game_id"})
    m = lk.merge(g, left_on=["tip_date", "home", "away"], right_on=["game_date", "home", "away"], how="inner")
    counts = {"lake_events": int(lk["event_id"].nunique()),
              "events_matched_to_a_game": int(m["event_id"].nunique())}
    m = m[m["partition"] == m["game_date"]]
    pre = m["lead_hours"] > 0
    counts["rows_in_game_partition"] = len(m)
    counts["rows_in_play"] = int((~pre).sum())
    m = m[pre]
    counts["rows_last_update_after_tip"] = int(m["last_update_after_tip"].sum())
    m = m[~m["last_update_after_tip"]]
    bad_points = m["over_point"].isna() | (m["over_point"] != m["under_point"]) | m["over_price"].isna() | m["under_price"].isna()
    counts["rows_without_a_clean_totals_quote"] = int(bad_points.sum())
    m = m[~bad_points]
    late = (m["anchor"] == "afternoon") & (m["lead_hours"] < MIN_AFTERNOON_LEAD_HOURS)
    counts["afternoon_rows_lead_under_1h"] = int(late.sum())
    counts["afternoon_games_lead_under_1h"] = int(m.loc[late, "game_id"].nunique())
    m = m[~late]
    out = pd.DataFrame({
        "game_id": m["game_id"].astype(int), "book": m["book"], "market": "totals", "anchor": m["anchor"],
        "captured_utc": m["snapshot_utc"], "commence_utc": m["commence_utc"], "lead_hours": m["lead_hours"],
        "line": m["over_point"].astype(float), "over_price": m["over_price"].astype(float),
        "under_price": m["under_price"].astype(float), "source": "legacy_lake",
    })
    return out.reset_index(drop=True), counts
