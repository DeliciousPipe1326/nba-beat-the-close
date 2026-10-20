"""Leakage self-test. See nbatotals/evaluate/leakage.py for what each check means."""

import os

import pandas as pd
import pytest

from nbatotals import params as params_io
from nbatotals.evaluate import leakage
from nbatotals.model import registry
from tests.fixtures import synthetic

# The literal rule "same-game correlation must not exceed the previous-game
# correlation" fails for honest features: at game g a window holds one more
# earlier game than it did at the previous game, so it is slightly more
# informative. Honest features show an excess of at most ~0.02 (synthetic and
# legacy data); features whose cut-off is one day late show at least ~0.04.
CORR_TOLERANCE = 0.03


@pytest.fixture(scope="module")
def league():
    return synthetic.generate(seasons=(2021, 2022), days=160, games_per_day=8, seed=0)


@pytest.fixture(scope="module")
def prm():
    return params_io.load()


def test_truncation_bit_identical_on_200_plus_games(league, prm):
    games, box = league
    sample = leakage.stratified_sample(games, per_cell=35)
    assert len(sample) >= 200
    assert set(sample["phase"]) == {"early", "mid", "late", "opening_night"}
    assert sample["season"].nunique() == 2
    res = leakage.truncation_check(games, box, prm, sample)
    assert res["mismatches"] == []
    assert res["max_abs_diff"] == 0.0


@pytest.mark.parametrize("overrides", [
    {"features.home_away_split": True},
    {"features.team_carryover_weight": 0.5},
    {"league.prior_source": "constant"},
])
def test_truncation_holds_for_every_knob(league, prm, overrides):
    games, box = league
    sample = leakage.stratified_sample(games, per_cell=8, seed=3)
    res = leakage.truncation_check(games, box, params_io.with_overrides(prm, overrides), sample)
    assert res["mismatches"] == []


@pytest.mark.parametrize("name", sorted(registry.PROJECTORS))
def test_every_registered_projector_passes_truncation(league, prm, name):
    games, box = league
    sample = leakage.stratified_sample(games, per_cell=35)
    assert len(sample) >= 200
    res = leakage.projector_truncation_check(synthetic.projector(name, games), games, box, prm, sample)
    assert res["mismatches"] == []


def test_truncation_check_catches_a_leaky_projector(league, prm):
    games, box = league

    class Peeks:  # uses each game's own final score: must be caught
        name = "peeks"

        def predict(self, targets, games, box, state, params):
            g = games.set_index("id")
            tot = [g.loc[i, "home_pts"] + g.loc[i, "away_pts"] if i in g.index else 0.0 for i in targets["id"]]
            return pd.DataFrame({"game_id": targets["id"].to_numpy(), "total_proj": tot})

    sample = leakage.stratified_sample(games, per_cell=3)
    assert leakage.projector_truncation_check(Peeks(), games, box, prm, sample)["mismatches"]


def test_correlation_check_passes_and_catches_a_leak(league, prm):
    games, box = league
    honest = leakage.correlation_check(games, box, prm)
    assert (honest["excess"] < CORR_TOLERANCE).all(), honest
    leaky = leakage.correlation_check(games, box, prm, shift_days=1)
    assert (leaky["excess"] > CORR_TOLERANCE).all(), leaky


@pytest.mark.skipif(not os.environ.get("NBA_LEGACY_DB"), reason="maintainer-only: needs the private legacy DB")
def test_leakage_on_real_legacy_data(prm):
    from nbatotals.evaluate.adapters import legacy_nba_db

    frames = legacy_nba_db.load()
    games = frames["games"][frames["games"]["season"] <= 2024]
    box = frames["team_box"].drop(columns=["legacy_pace"])
    sample = leakage.stratified_sample(games, per_cell=20)
    assert len(sample) >= 200
    res = leakage.truncation_check(games, box, prm, sample)
    assert res["mismatches"] == [] and res["max_abs_diff"] == 0.0
    honest = leakage.correlation_check(games, box, prm)
    assert (honest["excess"] < CORR_TOLERANCE).all(), honest
    leaky = leakage.correlation_check(games, box, prm, shift_days=1)
    assert (leaky["excess"] > CORR_TOLERANCE).all(), leaky
