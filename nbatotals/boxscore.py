"""Possession and rating arithmetic shared by every ingester.

All sources go through these functions so that a team box built from the
legacy DB and one built from the live BallDontLie API are computed the same
way. The possession estimator is the common box-score one
(FGA - ORB + TOV + 0.44 * FTA), which is what BallDontLie's advanced "pace"
column reports as raw possessions. These are fixed definitions, not tunable
model parameters.
"""

from __future__ import annotations

REGULATION_MINUTES = 48.0
OT_MINUTES = 5.0


def game_minutes(periods: int | None) -> float:
    """Minutes played in a game (per team, divided by five players)."""
    periods = 4 if periods is None else int(periods)
    return REGULATION_MINUTES + OT_MINUTES * max(0, periods - 4)


def team_possessions(fga, fta, orb, tov) -> float:
    """Box-score possession estimate for one side."""
    return fga - orb + tov + 0.44 * fta


def game_possessions(home: dict, away: dict) -> float:
    """Average of both sides' possession estimates (the usual convention)."""
    h = team_possessions(home["fga"], home["fta"], home["orb"], home["tov"])
    a = team_possessions(away["fga"], away["fta"], away["orb"], away["tov"])
    return 0.5 * (h + a)


def derive(home: dict, away: dict, periods: int | None) -> tuple[dict, dict]:
    """Return copies of both sides with possessions, pace, ortg and drtg filled in."""
    poss = game_possessions(home, away)
    minutes = game_minutes(periods)
    pace = REGULATION_MINUTES * poss / minutes
    out = []
    for me, opp in ((home, away), (away, home)):
        row = dict(me)
        row.update(
            minutes=minutes,
            possessions=poss,
            pace=pace,
            ortg=100.0 * me["pts"] / poss,
            drtg=100.0 * opp["pts"] / poss,
        )
        out.append(row)
    return out[0], out[1]


def american_to_decimal(price) -> float | None:
    if price is None:
        return None
    price = float(price)
    if price >= 100:
        return 1.0 + price / 100.0
    if price <= -100:
        return 1.0 + 100.0 / -price
    return None  # not a valid American price
