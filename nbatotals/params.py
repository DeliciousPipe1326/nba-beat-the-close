"""Load and validate config/params.yaml."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "params.yaml"


def load(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_PATH) as fh:
        params = yaml.safe_load(fh)
    validate(params)
    return params


def validate(params: dict) -> None:
    blend = params["features"]["blend"]
    if set(blend) != {"l3", "l10", "season"}:
        raise ValueError("features.blend needs exactly l3, l10 and season")
    if any(w < 0 for w in blend.values()) or abs(sum(blend.values()) - 1.0) > 1e-9:
        raise ValueError(f"features.blend weights must be >= 0 and sum to 1, got {blend}")
    if params["features"]["team_shrinkage_games"] < 0:
        raise ValueError("features.team_shrinkage_games must be >= 0")
    if not 0 <= params["features"]["team_carryover_weight"] <= 1:
        raise ValueError("features.team_carryover_weight must be in [0, 1]")
    if params["league"]["prior_source"] not in ("previous_season", "constant"):
        raise ValueError("league.prior_source must be previous_season or constant")
    if params["league"]["shrinkage_team_games"] < 0:
        raise ValueError("league.shrinkage_team_games must be >= 0")


def with_overrides(params: dict, overrides: dict) -> dict:
    """Return a copy with dotted-path overrides, e.g. {'projection.pace_weight': 0.8}."""
    out = copy.deepcopy(params)
    for dotted, value in overrides.items():
        node = out
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node[key]
        if leaf not in node:
            raise KeyError(f"unknown parameter {dotted}")
        node[leaf] = value
    validate(out)
    return out
