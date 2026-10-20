"""Name -> projector class. Add yours here (see README, "Building on this")."""

from __future__ import annotations

from nbatotals.model.base import Projector
from nbatotals.model.elo_total import EloTotal
from nbatotals.model.league_avg import LeagueAvg
from nbatotals.model.lineup_pace_eff import LineupPaceEff
from nbatotals.model.pace_eff import PaceEff

DEFAULT = "pace_eff"
PROJECTORS: dict[str, type] = {
    PaceEff.name: PaceEff,      # the pre-registered Tier A formula
    LeagueAvg.name: LeagueAvg,  # no-information baseline
    EloTotal.name: EloTotal,    # example: Elo-style team ratings on totals
    LineupPaceEff.name: LineupPaceEff,  # Experiment 2: projected minutes x player ratings (needs player inputs)
}


def get(name: str = DEFAULT, **kwargs) -> Projector:
    """`kwargs` go to the projector's constructor (e.g. `inputs=` for lineup_pace_eff)."""
    try:
        projector = PROJECTORS[name](**kwargs)
    except KeyError:
        raise KeyError(f"unknown model {name!r}; registered: {', '.join(sorted(PROJECTORS))}") from None
    if not isinstance(projector, Projector):
        raise TypeError(f"{name} does not implement the Projector interface (nbatotals/model/base.py)")
    return projector
