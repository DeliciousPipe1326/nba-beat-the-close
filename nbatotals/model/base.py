"""The projector interface: what any totals model must provide to use the harness.

A projector turns history into a projected total for each target game. The
harness (nbatotals/evaluate/backtest.py) and the `today` command call only these
two methods, so a new model never needs to touch them.

Rules the harness relies on:

- `fit` is called once per test season with only the games and box scores of
  *earlier* seasons. It may tune anything it likes on them, or do nothing. It
  must not read odds. It returns a `state` dict the harness passes back to
  `predict`. Optional keys: `summary` (a flat dict shown in the report's fit
  table) and `log` (a DataFrame of every candidate it evaluated, written next to
  the report).
- `predict(targets, games, box, state, params)` returns one row per target game
  with columns `game_id` and `total_proj`. `games` and `box` may contain rows on
  or after a target's date (including other targets' results). The projection
  for a game dated D must use only rows dated strictly before D, and must not
  read the target's own score. The truncation test in tests/test_leakage.py
  checks this for every registered projector. `state=None` means "untuned":
  use the values in params.yaml.

Optional, for spreads and moneyline (Experiment 5,
docs/experiments/other_markets/PREREGISTRATION.md); the totals harness never
calls them:

- `predict_margin(targets, games, box, state, params)` returns columns
  `game_id` and `margin_proj` (projected home points minus away points), under
  the same point-in-time rule as `predict`.
- `fit_margin(train_games, train_box, params, state)` may tune margin-only
  settings on earlier seasons; its dict is merged over `state`. Without it,
  `predict_margin` receives the totals `fit` state.

The harness turns a margin into a win probability itself (a home-court
constant and a logistic scale, both fitted on earlier seasons), so a projector
does not provide one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class Projector(Protocol):
    name: str

    def fit(self, train_games: pd.DataFrame, train_box: pd.DataFrame, params: dict, progress=None) -> dict:
        ...

    def predict(self, targets: pd.DataFrame, games: pd.DataFrame, box: pd.DataFrame, state: dict | None,
                params: dict) -> pd.DataFrame:
        ...


def check_output(out: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Validate a predict() result: one finite total per target game."""
    if list(out.columns[:2]) != ["game_id", "total_proj"]:
        raise ValueError("predict() must return columns game_id, total_proj")
    if set(out["game_id"]) != set(targets["id"]) or out["game_id"].duplicated().any():
        raise ValueError("predict() must return exactly one row per target game")
    if not pd.api.types.is_numeric_dtype(out["total_proj"]) or out["total_proj"].isna().any():
        raise ValueError("predict() returned a missing or non-numeric total_proj")
    return out[["game_id", "total_proj"]]


def check_margin_output(out: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Validate a predict_margin() result: one finite margin per target game."""
    if list(out.columns[:2]) != ["game_id", "margin_proj"]:
        raise ValueError("predict_margin() must return columns game_id, margin_proj")
    if set(out["game_id"]) != set(targets["id"]) or out["game_id"].duplicated().any():
        raise ValueError("predict_margin() must return exactly one row per target game")
    if not pd.api.types.is_numeric_dtype(out["margin_proj"]) or out["margin_proj"].isna().any():
        raise ValueError("predict_margin() returned a missing or non-numeric margin_proj")
    return out[["game_id", "margin_proj"]]
