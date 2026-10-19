import json

import pandas as pd
import pytest

from nbatotals.evaluate import market
from nbatotals.evaluate.adapters import legacy_multiregion as mr

GAMES = pd.DataFrame([
    dict(id=1, game_date="2023-11-01", season=2023, home="BOS", away="NYK"),
    dict(id=2, game_date="2023-11-01", season=2023, home="LAL", away="GSW"),
])


def write(root, game, bucket, polled, commence, home, away, books):
    d = root / "season=2023-24" / "date=2023-11-01" / f"nba_game_id={game}" / f"bucket={bucket}"
    d.mkdir(parents=True)
    payload = {
        "metadata": {"timestamp": polled, "bucket": bucket, "market": "totals"},
        "event": {"id": f"ev{game}", "commence_time": commence, "home_team": home, "away_team": away},
        "bookmakers": [{"key": k, "last_update": polled,
                        "market": {"key": "totals", "outcomes": [{"name": "Over", "price": o, "point": line},
                                                                 {"name": "Under", "price": u, "point": line}]}}
                       for k, line, o, u in books],
    }
    (d / "totals.json").write_text(json.dumps(payload))


@pytest.fixture
def raw(tmp_path):
    books = [("a", 220.5, -110, -110), ("b", 221.0, -105, -115), ("c", 221.0, -115, -105)]
    # game 1 tips 23:30Z (19:30 ET); game 2 tips 02:30Z next day (22:30 ET on 2023-11-01)
    write(tmp_path, 1, "opening", "2023-11-01T05:30:00Z", "2023-11-01T23:30:00Z", "Boston Celtics", "New York Knicks", books)
    write(tmp_path, 1, "true_close", "2023-11-01T23:15:00Z", "2023-11-01T23:30:00Z", "Boston Celtics", "New York Knicks", books)
    write(tmp_path, 1, "late_evening", "2023-11-01T23:40:00Z", "2023-11-01T23:30:00Z", "Boston Celtics", "New York Knicks", books)
    write(tmp_path, 2, "true_close", "2023-11-02T02:15:00Z", "2023-11-02T02:30:00Z", "Los Angeles Lakers", "Golden State Warriors",
          books + [("d", 230.0, -110, None)])
    return mr.read_files(tmp_path)


def test_join_lead_and_in_play(raw):
    q, counts = mr.anchor_quotes(raw, GAMES)
    assert counts["events_matched_to_a_game"] == 2
    assert counts["files_polled_at_or_after_tip"] == 1  # game 1's late_evening file
    assert counts["book_rows_without_a_clean_quote"] == 1  # book d has no under price
    assert set(zip(q.game_id, q.anchor)) == {(1, "opening"), (1, "true_close"), (2, "true_close")}
    assert q.loc[(q.game_id == 1) & (q.anchor == "true_close"), "lead_hours"].iloc[0] == pytest.approx(0.25)
    assert q.loc[q.book == "a", "over_price"].iloc[0] == pytest.approx(1 + 100 / 110)


def test_unknown_team_name_is_reported(raw):
    with pytest.raises(KeyError, match="Seattle"):
        mr.anchor_quotes(raw.assign(home_name="Seattle SuperSonics"), GAMES)


def test_anchor_order_drops_anchor_captured_after_reference():
    cons = pd.DataFrame({"game_id": [1, 1, 1], "anchor": ["noon", "late_evening", "true_close"],
                         "captured_utc": ["2023-11-01T13:30:00Z", "2023-11-01T23:20:00Z", "2023-11-01T23:15:00Z"]})
    kept, dropped = market.enforce_anchor_order(cons, "true_close")
    assert dropped == 1 and set(kept["anchor"]) == {"noon", "true_close"}
