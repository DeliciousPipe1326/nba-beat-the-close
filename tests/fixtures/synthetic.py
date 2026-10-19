"""A seeded, entirely made-up league in the store's shapes.

Used so the test suite runs with no API keys and no legacy DB. Teams get hidden
pace / offence / defence effects; games are drawn from them with noise. Nothing
here resembles real results.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from nbatotals import boxscore
from nbatotals.teams import ALIASES

LEAGUE_PACE = 99.0
LEAGUE_ORTG = 113.0


def generate(seasons=(2021, 2022), days: int = 160, games_per_day: int = 8, seed: int = 0):
    """Return (games, box) DataFrames for `seasons`, all games final."""
    rng = np.random.default_rng(seed)
    teams = list(ALIASES)
    games, box = [], []
    gid = 1000
    for season in seasons:
        eff = {
            t: dict(pace=rng.normal(0, 2), off=rng.normal(0, 3), dfn=rng.normal(0, 3)) for t in teams
        }
        start = dt.date(season, 10, 20)
        for d in range(days):
            day = start + dt.timedelta(days=d)
            order = rng.permutation(teams)
            for i in range(games_per_day):
                home, away = order[2 * i], order[2 * i + 1]
                periods = 5 if rng.random() < 0.06 else 4
                minutes = boxscore.game_minutes(periods)
                poss = (LEAGUE_PACE + eff[home]["pace"] + eff[away]["pace"] + rng.normal(0, 4)) * minutes / 48
                sides = {}
                for team, opp, is_home in ((home, away, 1), (away, home, 0)):
                    ortg = LEAGUE_ORTG + eff[team]["off"] + eff[opp]["dfn"] + (1.5 if is_home else -1.5)
                    pts = int(round(poss * (ortg + rng.normal(0, 10)) / 100))
                    fta = int(rng.poisson(21))
                    orb = int(rng.poisson(10))
                    tov = int(rng.poisson(13))
                    fga = int(round(poss + orb - tov - 0.44 * fta + rng.normal(0, 1)))
                    fg3a = int(round(0.4 * fga))
                    sides[team] = dict(
                        game_id=gid, team=team, pts=pts, fgm=int(round(0.47 * fga)), fga=fga,
                        fg3m=int(round(0.36 * fg3a)), fg3a=fg3a, ftm=int(round(0.78 * fta)), fta=fta,
                        orb=orb, drb=int(rng.poisson(33)), tov=tov,
                    )
                h, a = boxscore.derive(sides[home], sides[away], periods)
                h.update(opp=away, is_home=1, source="synthetic")
                a.update(opp=home, is_home=0, source="synthetic")
                box += [h, a]
                games.append(
                    dict(id=gid, game_date=day.isoformat(), tip_utc=None, season=season, postseason=0,
                         home=home, away=away, home_pts=h["pts"], away_pts=a["pts"], periods=periods,
                         status="final", source="synthetic")
                )
                gid += 1
    return pd.DataFrame(games), pd.DataFrame(box)
