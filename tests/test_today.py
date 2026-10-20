import datetime as dt
import re
from pathlib import Path

import pandas as pd
import pytest

from nbatotals import cli, store, today
from nbatotals import params as params_io
from tests.fixtures import synthetic

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def filled(tmp_path):
    games, box = synthetic.generate(seasons=(2025,), days=30, games_per_day=6, seed=4)
    db = tmp_path / "s.db"
    con = store.connect(db)
    games.to_sql("games", con, if_exists="append", index=False)
    box.to_sql("team_box", con, if_exists="append", index=False)
    day = (dt.date.fromisoformat(games["game_date"].max()) + dt.timedelta(days=1)).isoformat()
    fixtures = [(90001, "BOS", "NYK"), (90002, "LAL", "GSW")]
    for gid, h, a in fixtures:
        con.execute("INSERT INTO games (id, game_date, tip_utc, season, home, away, status, source) "
                    "VALUES (?, ?, ?, 2025, ?, ?, 'scheduled', 't')", (gid, day, f"{day}T23:30:00Z", h, a))
    for book, line in (("a", 221.5), ("b", 222.0), ("c", 222.0)):
        con.execute("INSERT INTO odds_snapshots (event_id, game_id, book, market, anchor, captured_utc, commence_utc, "
                    "lead_minutes, home, away, line, over_price, under_price, source) VALUES "
                    "('evX', 90001, ?, 'totals', 'close', ?, ?, 20, 'BOS', 'NYK', ?, 1.91, 1.91, 'theoddsapi')",
                    (book, f"{day}T23:10:00Z", f"{day}T23:30:00Z", line))
    con.commit()
    return con, db, day


def test_today_csv(filled, tmp_path):
    con, db, day = filled
    df = today.build(con, day, params_io.load())
    assert list(df.columns) == today.COLUMNS and len(df) == 2
    bos = df[df.home == "BOS"].iloc[0]
    assert bos.market_line == 222.0 and bos.books == 3 and bos.market_anchor == "close"
    assert bos.edge == pytest.approx(round(bos.projected_total - 222.0, 1), abs=0.051)
    lal = df[df.home == "LAL"].iloc[0]
    assert pd.isna(lal.market_line) and pd.isna(lal.edge)  # no odds stored for it
    out = tmp_path / "t.csv"
    assert cli.main(["today", "--db", str(db), "--date", day, "--out", str(out)]) == 0
    first = out.read_text().splitlines()[0]
    assert first == today.HEADER
    assert len(pd.read_csv(out, comment="#")) == 2


def test_headline_numbers_match_results():
    """The CSV header and the README quote RESULTS.md; fail if they drift apart."""
    results = (ROOT / "docs" / "RESULTS.md").read_text()
    readme = (ROOT / "README.md").read_text()
    for number in re.findall(r"\d+\.\d+%", today.HEADER):
        assert number in results
    must = ["48.9%", "47.3–50.5%", "−6.7%", "49.5%", "−3.8%", "−0.117", "+0.39", "0.80¢", "−0.02"]
    for m in must:
        assert m in results, m
        assert m in readme, m
