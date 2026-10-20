from typing import Any

import numpy as np
import pandas as pd
import pytest

from nbatotals import params as params_io
from nbatotals.evaluate import backtest
from nbatotals.model import base, registry
from nbatotals.model.elo_total import EloTotal
from tests.fixtures import synthetic


@pytest.fixture(scope="module")
def league():
    return synthetic.generate(seasons=(2021, 2022), days=40, games_per_day=6, seed=5)


@pytest.fixture(scope="module")
def prm():
    return params_io.load()


def test_registry_lists_and_validates():
    assert registry.DEFAULT == "pace_eff"
    assert {"pace_eff", "league_avg", "elo_total"} <= set(registry.PROJECTORS)
    for name in registry.PROJECTORS:
        p = registry.get(name)
        assert isinstance(p, base.Projector) and p.name == name
    with pytest.raises(KeyError, match="registered"):
        registry.get("nope")


@pytest.mark.parametrize("name", sorted(registry.PROJECTORS))
def test_every_projector_fits_and_predicts(league, prm, name):
    games, box = league
    p = synthetic.projector(name, games)
    train = games[games.season == 2021]
    state = p.fit(train, box[box.game_id.isin(train.id)], prm)
    targets = games[games.season == 2022]
    for st in (None, state):
        out = base.check_output(p.predict(targets, games, box, st, prm), targets)
        assert np.isfinite(out.total_proj).all() and out.total_proj.between(150, 300).all()


def test_harness_gives_fit_only_earlier_seasons(league, prm):
    games, box = league
    seen = []

    class Spy:
        name = "spy"

        def fit(self, train_games, train_box, params, progress=None):
            seen.append((int(train_games.season.max()), set(train_box.game_id) <= set(train_games.id)))
            return {"summary": {"train_n": len(train_games)}}

        def predict(self, targets, games, box, state, params):
            return pd.DataFrame({"game_id": targets["id"].to_numpy(), "total_proj": 220.0})

    pred, fits, log_rows = backtest.predictions(games, box, prm, test_seasons=(2022,), projector=Spy())
    assert seen == [(2021, True)]
    assert set(pred.season) == {2022} and (pred.proj == 220.0).all() and log_rows == 0
    assert list(fits.columns[:3]) == ["test_season", "trained_on", "train_n"]


def test_check_output_rejects_bad_predictions(league):
    games, _ = league
    t = games.head(3)
    with pytest.raises(ValueError):
        base.check_output(pd.DataFrame({"game_id": t.id, "total": 1.0}), t)
    with pytest.raises(ValueError):
        base.check_output(pd.DataFrame({"game_id": t.id.iloc[:2], "total_proj": 1.0}), t)
    with pytest.raises(ValueError):
        base.check_output(pd.DataFrame({"game_id": t.id, "total_proj": [1.0, None, 2.0]}), t)


def test_elo_fit_picks_lowest_rmse_in_declared_grid(league, prm):
    games, box = league
    train = games[games.season == 2021]
    state = EloTotal().fit(train, box, prm)
    log = state["log"]
    assert list(log.k) == prm["models"]["elo_total"]["k_grid"]
    assert state["k"] == log.loc[log.train_rmse.idxmin(), "k"]


def test_readme_example_projector_runs_and_is_point_in_time(league, prm):
    import re
    from pathlib import Path

    from nbatotals.evaluate import leakage

    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    section = readme[readme.index("## Building on this"):]
    match = re.search(r"```python\n(.*?)```", section, re.S)
    assert match is not None
    code = match.group(1)
    ns: dict[str, Any] = {}
    exec(code, ns)
    p = ns["TeamPaceOnly"]()
    assert isinstance(p, base.Projector)
    games, box = league
    targets = games[games.season == 2022]
    base.check_output(p.predict(targets, games, box, p.fit(games, box, prm), prm), targets)
    sample = leakage.stratified_sample(games, per_cell=5)
    assert leakage.projector_truncation_check(p, games, box, prm, sample)["mismatches"] == []
