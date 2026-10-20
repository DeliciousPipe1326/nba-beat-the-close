"""Maintainer only: replay one season of recorded The Odds API historical responses and check them.

Needs the private folders (never in this repository): NBA_LEGACY_DB, NBA_LEGACY_MULTIREGION and
NBA_LEGACY_REPLAY_EVENTS (the per-event nba_odds lake). Run with `pytest -s` to see the counts.
"""

import os

import pytest

from nbatotals.evaluate.adapters import legacy_replay

NEEDED = ("NBA_LEGACY_DB", "NBA_LEGACY_MULTIREGION", legacy_replay.ENV_VAR)
pytestmark = pytest.mark.skipif(not all(os.environ.get(v) for v in NEEDED),
                                reason="maintainer-only: needs the private recorded responses")

SEASON = 2024


def test_one_recorded_season_replays_cleanly_and_agrees_with_the_true_close(tmp_path):
    from nbatotals import params as params_io
    from nbatotals import store
    from nbatotals.evaluate.adapters import legacy_lake, legacy_multiregion, legacy_nba_db

    saved = os.environ.pop(legacy_lake.ENV_VAR, None)  # games only; no lake quotes
    try:
        games = legacy_nba_db.load()["games"]
    finally:
        if saved is not None:
            os.environ[legacy_lake.ENV_VAR] = saved
    con = store.connect(tmp_path / "replay.db")
    games.to_sql("games", con, if_exists="append", index=False)
    con.commit()
    s = legacy_replay.replay(con, os.environ[legacy_replay.ENV_VAR], SEASON)
    tc, _ = legacy_multiregion.anchor_quotes(legacy_multiregion.read_files(), games)
    tc = tc[tc["game_id"].isin(games.loc[games["season"] == SEASON, "id"])]
    a = legacy_replay.agreement(con, tc, params_io.load())
    con.close()
    print(f"\n{SEASON}: {s['files']:,} responses; dropped in play {s['events']['in_play']}, "
          f"beyond 36 h {s['events']['beyond_max_lead']}; rows stored {s['rows_written']:,}")
    print(f"{a['ref_anchor']} within 0.5 of the true close on {a['line_within_half_point']:.1%} of "
          f"{a['games_compared']:,} games; mean devigged p_over {a['ref_p_over_mean']:.3f}")
    assert s["rows_written"] > 100_000 and a["rows_at_or_after_tip"] == 0
    assert a["games_compared"] > 1200 and a["line_within_half_point"] > 0.7  # different books and poll minutes
    assert 0.48 < a["ref_p_over_mean"] < 0.52
