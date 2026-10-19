"""Name -> projector class. Add yours here (see README, "Building on this")."""

from __future__ import annotations

from nbatotals.model.base import Projector
from nbatotals.model.elo_total import EloTotal
from nbatotals.model.league_avg import LeagueAvg
from nbatotals.model.pace_eff import PaceEff

DEFAULT = "pace_eff"
PROJECTORS: dict[str, type] = {
    PaceEff.name: PaceEff,      # the pre-registered Tier A formula
    LeagueAvg.name: LeagueAvg,  # no-information baseline
    EloTotal.name: EloTotal,    # example: Elo-style team ratings on totals
}


def get(name: str = DEFAULT) -> Projector:
    try:
        projector = PROJECTORS[name]()
    except KeyError:
        raise KeyError(f"unknown model {name!r}; registered: {', '.join(sorted(PROJECTORS))}") from None
    if not isinstance(projector, Projector):
        raise TypeError(f"{name} does not implement the Projector interface (nbatotals/model/base.py)")
    return projector
