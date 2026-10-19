import os
import sqlite3

import pytest

from nbatotals.evaluate.adapters import legacy_nba_db as legacy
from tests.fixtures import legacy_layout


@pytest.fixture
def frames(tmp_path, monkeypatch):
    path = legacy_layout.build(tmp_path / "legacy.db")
    monkeypatch.setenv(legacy.ENV_VAR, str(path))
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
    assert by.loc[(2023, "close"), "line_outside_150_300"] == 1
    assert set(by.index.get_level_values("anchor")) == {"open", "pretip", "close"}


def test_write_store_drops_unusable_rows(frames, tmp_path):
    out = legacy.write_store(frames, tmp_path / "store.db")
    con = sqlite3.connect(out)
    n_totals = con.execute("select count(*) from odds_snapshots where market='totals'").fetchone()[0]
    assert n_totals == 2 * 3 * 3 + 1  # 18 clean quotes + the 55.0 line (kept for the consensus rule)
    assert con.execute(
        "select count(*) from odds_snapshots where market='totals' and (over_price is null or under_price is null)"
    ).fetchone()[0] == 0
    row = con.execute(
        "select line, home_price, away_price from odds_snapshots where market='spreads' and game_id=101 and anchor='close'"
    ).fetchone()
    assert row[0] == -3.5 and row[1] == pytest.approx(1 + 100 / 110)


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
