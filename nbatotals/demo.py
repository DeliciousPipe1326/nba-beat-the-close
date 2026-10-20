"""`python -m nbatotals demo`: the whole pipeline offline, on a made-up league.

Builds a small store under data/demo/ from the synthetic league in
nbatotals/synthetic.py (two seasons of games and box scores, then a day of
scheduled fixtures with made-up totals quotes), projects that day with the
same `today` code the real pipeline uses, writes out/demo_today.csv and renders
out/demo_report.html with the `report` code. No API keys, no network, no real
data. Real projections need your own keys: see the README's Quick start.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from nbatotals import params as params_io
from nbatotals import report, store, synthetic, today

ROOT = Path(__file__).resolve().parents[1]

HEADER = ("# SYNTHETIC DEMO DATA: made-up teams' games and made-up odds from nbatotals/synthetic.py, "
          "not real results or prices, not betting advice. Real projections need your own API keys.")

GAME_COLUMNS = ["id", "game_date", "tip_utc", "season", "postseason", "home", "away", "home_pts", "away_pts",
                "periods", "status", "source"]


def build_store(path: Path, seed: int = 0) -> tuple[str, int]:
    """A fresh demo store; returns (the fixtures' date, number of fixtures)."""
    path = Path(path)
    if path.exists():
        path.unlink()
    games, box = synthetic.generate(seasons=(2024, 2025), days=100, games_per_day=7, seed=seed)
    day = (dt.date.fromisoformat(games["game_date"].max()) + dt.timedelta(days=1)).isoformat()
    fixtures = synthetic.fixtures(day, n=6, first_id=int(games["id"].max()) + 1, season=2025, seed=seed)
    quotes = synthetic.odds(fixtures, seed=seed)
    con = store.connect(path)
    try:
        pd.concat([games, fixtures])[GAME_COLUMNS].to_sql("games", con, if_exists="append", index=False)
        box.to_sql("team_box", con, if_exists="append", index=False)
        quotes.to_sql("odds_snapshots", con, if_exists="append", index=False)
        con.commit()
    finally:
        con.close()
    return day, len(fixtures)


def run(out_dir: Path = ROOT / "out", data_dir: Path = ROOT / "data" / "demo", seed: int = 0) -> dict:
    db = Path(data_dir) / "demo.db"
    day, n = build_store(db, seed)
    con = store.connect(db)
    try:
        df = today.build(con, day, params_io.load())
    finally:
        con.close()
    csv = Path(out_dir) / "demo_today.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    today.write_csv(df, csv, header=HEADER)
    html_path = report.write(csv, Path(out_dir) / "demo_report.html")
    return {"date": day, "fixtures": n, "store": db, "csv": csv, "html": html_path, "table": df}
