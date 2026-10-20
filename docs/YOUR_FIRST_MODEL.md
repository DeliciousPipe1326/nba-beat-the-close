# Your first model

A ten-minute walkthrough: write a totals model, check it for leakage, grade it
against the closing line, and read the result. You need Python and pandas; no
statistics beyond what is explained here.

## 1. What a model is here

One Python class with three things:

- `name`: the string you type after `--model`;
- `fit(train_games, train_box, params, progress=None)`: called once per test
  season with earlier seasons only; returns a dict (`state`), which may be empty;
- `predict(targets, games, box, state, params)`: returns one row per target game
  with columns `game_id` and `total_proj` (your projected total points).

`games` has one row per game (date, season, teams, scores when final) and `box`
one row per team per game (possessions, points, pace and ratings), both from
the local store; `params` is `config/params.yaml`; `targets` are the games to
project. The full contract is in [nbatotals/model/base.py](../nbatotals/model/base.py).

## 2. The smallest real example

This is the whole of [nbatotals/model/league_avg.py](../nbatotals/model/league_avg.py),
the no-information baseline:

```python
"""Example projector: the no-information baseline.

Every game is projected at the point-in-time league average total (league pace x
league points per 100, both teams), with no team information at all. Its
results show what "knowing nothing" looks like through the same harness.
"""

from __future__ import annotations

import pandas as pd

from nbatotals.features.pointintime import build_features


class LeagueAvg:
    name = "league_avg"

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        reg = train_games[(train_games["status"] == "final") & (train_games["postseason"] == 0)]
        return {"summary": {"train_n": len(reg), "parameters": "none"}}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        f = build_features(targets, games, box, params)
        return pd.DataFrame({"game_id": f["game_id"], "total_proj": f["league_pace"] * 2 * f["league_ortg"] / 100.0})
```

The docstring and imports say what the model is and bring in `build_features`,
which turns raw history into one row of point-in-time features per game. `fit`
learns nothing: it only counts the training games so the report's fit table has
something to show. `predict` projects every game at the league's average pace
times its average points per 100 possessions, for both teams, with no team
information at all.

## 3. A template for yours

`python -m nbatotals new-model my_model` writes exactly this to
`nbatotals/model/my_model.py` and registers it (step 4). Change the marked line:

```python
"""my_model: one line on the idea."""

from __future__ import annotations

import pandas as pd

from nbatotals.features.pointintime import build_features


class MyModel:
    name = "my_model"

    def fit(self, train_games, train_box, params, progress=None) -> dict:
        # Called once per test season with earlier seasons only, never odds. Tune here if you like;
        # what you return comes back to predict() as `state` (None means untuned).
        return {}

    def predict(self, targets, games, box, state, params) -> pd.DataFrame:
        f = build_features(targets, games, box, params)  # one row per target game, history dated before it
        # Columns of f (side is home or away):
        #   {side}_pace, {side}_ortg, {side}_drtg     blended (features.blend in params.yaml), never missing
        #   {side}_pace_l3, _l10, _season, and the same for ortg and drtg: last 3, last 10, season to date
        #                                             (missing before a team's first game of the season)
        #   {side}_rest_days, {side}_b2b               days off before this game; True on a back-to-back
        #   league_pace, league_ortg                  league averages to date
        total = f["league_pace"] * 2 * f["league_ortg"] / 100.0  # <- your arithmetic goes here
        return pd.DataFrame({"game_id": f["game_id"], "total_proj": total})
```

`fit` may tune anything on the training seasons and return it in `state`; the
harness hands that back to `predict`. Look at
[elo_total.py](../nbatotals/model/elo_total.py) for a model that does.

## 4. Where the file goes

Put the class in its own file under `nbatotals/model/`, for example
`nbatotals/model/my_model.py`, next to `pace_eff.py`, `league_avg.py` and
`elo_total.py`. Register it in
[nbatotals/model/registry.py](../nbatotals/model/registry.py) with one import and
one line in `PROJECTORS`:

```python
from nbatotals.model.my_model import MyModel
```

```python
    MyModel.name: MyModel,
```

`new-model` does both for you and refuses if the name is taken.

## 5. Check it, then grade it

```bash
pytest tests/test_leakage.py
```

```bash
python -m nbatotals backtest --store --model my_model
```

The first deletes every row dated on or after each sampled game and checks your
projection does not change. The second needs a store filled for at least two
seasons (see "Backfilling history" in the [README](../README.md#backfilling-history))
and writes `out/backtest_store_report_my_model.md`. The maintainer's path,
`python -m nbatotals backtest --legacy --model my_model`, runs on the author's
private data and writes `docs/backtest_legacy_report_my_model.md`.

## 6. Reading the result

The report leads with one row per test season and a pooled row. The included
model's pooled row ([docs/RESULTS.md](RESULTS.md)):

| season | n (true close (T−15 min)) | cover (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | opening (~24h) bets | CLV opening → true_close, points (95% CI) | noon (~10h) bets | CLV noon → true_close, points (95% CI) |
|---|---|---|---|---|---|---|---|---|---|
| pooled | 3,652 | 48.9% (47.3%–50.5%) | 50.1% | -2.4% (-5.7% to 0.8%) | -6.7% (-9.8% to -3.7%) | 3,220 | +0.39 (+0.29 to +0.49) | 3,655 | -0.02 (-0.08 to +0.05) |

- **Cover rate** is the share of bets on the model's side of the closing line
  (over when it projects above the line, under when below) that won, pushes
  excluded. Breakeven at the usual −110 price is 52.38%; a coin flip is 50%.
- **Real ROI** is profit per unit staked at each bet's real median book price,
  so it includes the bookmaker's margin. Betting at random loses about that
  margin, roughly −4.5%.
- **CLV** (closing line value) is how far the line moved toward your bet between
  the earlier anchor where you would have bet and the close, in points.
  Positive means the market later agreed with you.
- **Blend weight `c`** comes from regressing the actual total on the close and
  your model, `actual = a + b·close + c·model`. It is what your model adds once
  the closing line is known; near zero means nothing.

"No edge" looks like the row above: a cover interval around 50% whose lower
bound is nowhere near 52.38%, a real ROI near the margin, CLV around zero from
the anchors close to tip, and a `c` whose interval includes zero. The bar for an
edge was fixed in advance in [docs/PREREGISTRATION.md](PREREGISTRATION.md): a
cover lower bound above 52.38% over at least 1,000 bets in at least two seasons,
positive CLV and positive real ROI, all together.

## 7. The rules

Two are enforced by the tooling:

- `fit` sees only seasons before the one being tested, and never odds (the
  harness hands it nothing else);
- `predict` may use only rows dated before each game (the truncation test in
  `tests/test_leakage.py` runs on every registered model).

One it cannot enforce: do not keep changing your model after seeing the test
seasons. Every look at the result and every tweak afterwards makes the next
result less trustworthy. Write down the model, the settings you will search and
the bar it must clear before the first backtest, as
[docs/PREREGISTRATION.md](PREREGISTRATION.md) does, and treat anything you change
afterwards as a new hypothesis that needs a season it has not seen.

## 8. Spreads and moneyline

Add an optional `predict_margin(targets, games, box, state, params)` returning
`game_id` and `margin_proj` (projected home points minus away points), under the
same point-in-time rule. The harness turns a margin into a win probability
itself, with a home-court constant and a logistic scale fitted on earlier
seasons, so you do not provide one. Grade it with
`python -m nbatotals backtest --legacy --market-type spreads --model my_model`
(or `--market-type h2h` for the moneyline); today that path runs on the
maintainer's data only, and `backtest --store` grades totals.
`pace_eff.py` and `elo_total.py` both implement `predict_margin`.
