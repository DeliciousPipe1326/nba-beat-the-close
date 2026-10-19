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
