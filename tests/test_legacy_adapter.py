import os
import sqlite3

import pytest

from nbatotals.evaluate.adapters import legacy_lake
from nbatotals.evaluate.adapters import legacy_nba_db as legacy
from tests.fixtures import legacy_layout


@pytest.fixture
def frames(tmp_path, monkeypatch):
    path = legacy_layout.build(tmp_path / "legacy.db")
    monkeypatch.setenv(legacy.ENV_VAR, str(path))
    monkeypatch.delenv(legacy_lake.ENV_VAR, raising=False)
    return legacy.load()


def test_games_mapped_to_aliases(frames):
    g = frames["games"].set_index("id")
    assert g.loc[101, ["home", "away"]].tolist() == ["BOS", "NYK"]
    assert g.loc[103, "status"] == "scheduled"
    assert g.loc[103, ["home_pts", "away_pts"]].isna().all()


def test_team_box_recomputed_and_matches_legacy_possessions(frames):
    box = frames["team_box"]
    assert len(box) == 4
    assert (box["possessions"] - box["legacy_pace"]).abs().max() < 1e-9
    ot = box[box["game_id"] == 102]
    assert (ot["minutes"] == 53).all()
    assert (ot["pace"] < ot["legacy_pace"]).all()


def test_verify_counts_and_flags(frames):
    report = legacy.verify(frames)
    integrity = report["integrity"]
    assert integrity["box_points_mismatch"] == 0
    assert integrity["totals_rows_missing_a_price"] == 1
    assert integrity["odds_rows_home_team_mismatch"] == 0
    assert integrity["duplicate_snapshot_keys"] == 0
    assert report["pace_check"]["rows_possessions_off_by_more_than_0.01"] == 0
    by = report["totals_by_season_anchor"]
    assert by.loc[(2023, "legacy_close"), "line_outside_150_300"] == 1
    assert set(by.index.get_level_values("anchor")) == {"legacy_open", "legacy_noon_local", "legacy_close"}


def test_write_store_drops_unusable_rows(frames, tmp_path):
    out = legacy.write_store(frames, tmp_path / "store.db")
    con = sqlite3.connect(out)
    n_totals = con.execute("select count(*) from odds_snapshots where market='totals'").fetchone()[0]
    assert n_totals == 2 * 3 * 3 + 1  # 18 clean quotes + the 55.0 line (kept for the consensus rule)
    assert con.execute(
        "select count(*) from odds_snapshots where market='totals' and (over_price is null or under_price is null)"
    ).fetchone()[0] == 0
    row = con.execute(
        "select line, home_price, away_price from odds_snapshots "
        "where market='spreads' and game_id=101 and anchor='legacy_close'"
    ).fetchone()
    assert row[0] == -3.5 and row[1] == pytest.approx(1 + 100 / 110)  # no decimal column: American fallback
    over = con.execute(
        "select over_price from odds_snapshots "
        "where market='totals' and game_id=101 and anchor='legacy_close' and book='draftkings'"
    ).fetchone()[0]
    assert over == 1.89  # the provider's decimal, not the rounded American -112


def test_lake_join_flags_in_play_quotes(tmp_path, monkeypatch):
    path = legacy_layout.build(tmp_path / "legacy.db")
    lake = legacy_layout.build_lake(tmp_path / "lake")
    monkeypatch.setenv(legacy.ENV_VAR, str(path))
    frames = legacy.load(lake=lake)
    odds = frames["odds_raw"]
    totals = odds[odds["market"] == "totals"]
    assert totals["lake_match"].all()
    assert (totals["parse_mismatch"] == False).all()  # noqa: E712
    in_play = totals[totals["in_play"]]
    assert set(zip(in_play["game_id"], in_play["anchor"], strict=True)) == {(101, "legacy_open")}
    assert (in_play["lead_hours"] < 0).all()
    close = totals[(totals["game_id"] == 101) & (totals["anchor"] == "legacy_close")]
    assert close["lead_hours"].iloc[0] == pytest.approx(4 + 35 / 60)
    assert frames["games"].set_index("id").loc[101, "tip_utc"] == "2023-10-24T23:30:00Z"
    usable = legacy.usable_odds(odds)
    assert not ((usable["game_id"] == 101) & (usable["anchor"] == "legacy_open")).any()
    report = legacy.verify(frames)
    assert report["flags_by_season_anchor"].loc[(2023, "legacy_open"), "in_play_games"] == 1


def test_missing_env_var_is_a_clear_error(monkeypatch):
    monkeypatch.delenv(legacy.ENV_VAR, raising=False)
    with pytest.raises(RuntimeError, match="NBA_LEGACY_DB"):
        legacy.legacy_path()


@pytest.mark.skipif(not os.environ.get("NBA_LEGACY_DB"), reason="maintainer-only: needs the private legacy DB")
def test_real_legacy_db_invariants():
    frames = legacy.load()
    report = legacy.verify(frames)
    assert report["integrity"]["box_points_mismatch"] == 0
    assert report["integrity"]["odds_rows_unknown_game"] == 0
    assert report["integrity"]["duplicate_snapshot_keys"] == 0
    assert report["pace_check"]["rows_possessions_off_by_more_than_0.01"] == 0
    cov = report["close_coverage"]
    assert (cov.loc[[2022, 2023, 2024], "share"] == 1.0).all()


def test_anchor_quotes_rebuilt_from_lake(tmp_path, monkeypatch):
    path = legacy_layout.build(tmp_path / "legacy.db")
    lake_dir = legacy_layout.build_lake(tmp_path / "lake")
    monkeypatch.setenv(legacy.ENV_VAR, str(path))
    monkeypatch.delenv(legacy_lake.ENV_VAR, raising=False)
    games = legacy.load()["games"]
    quotes, counts = legacy_lake.anchor_quotes(legacy_lake.read_lake(lake_dir), games)
    got = set(zip(quotes["game_id"], quotes["anchor"], strict=True))
    # game 101's 01:25-style file was captured after tip: no early anchor for it
    assert (101, "early") not in got
    assert {(101, "overnight"), (101, "afternoon"), (102, "early"), (102, "overnight"), (102, "afternoon")} <= got
    assert counts["rows_in_play"] == 3  # the three books in 101's in-play file
    assert (quotes["lead_hours"] > 0).all()
    aft = quotes[(quotes["game_id"] == 102) & (quotes["anchor"] == "afternoon")]["lead_hours"].iloc[0]
    assert aft == pytest.approx(7 + 5 / 60)
