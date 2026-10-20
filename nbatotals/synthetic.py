"""A seeded, entirely made-up league, with made-up odds, in the store's shapes.

Used by the offline test suite and by `python -m nbatotals demo`. Teams get
hidden pace / offence / defence effects; games are drawn from them with noise.
Nothing here resembles real teams' results or real prices.
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


def fixtures(day: str, n: int, first_id: int, season: int, seed: int = 0) -> pd.DataFrame:
    """n scheduled (not yet played) games on `day`, tipping between 23:00 and 02:30 UTC."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(list(ALIASES))
    d = dt.date.fromisoformat(day)
    tips = [dt.datetime(d.year, d.month, d.day, 23, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=30 * (i % 8))
            for i in range(n)]
    rows = [dict(id=first_id + i, game_date=day, tip_utc=tips[i].strftime("%Y-%m-%dT%H:%M:%SZ"), season=season,
                 postseason=0, home=order[2 * i], away=order[2 * i + 1], home_pts=None, away_pts=None, periods=None,
                 status="scheduled", source="synthetic") for i in range(n)]
    return pd.DataFrame(rows)


SYNTHETIC_BOOKS = ("book_a", "book_b", "book_c", "book_d")
SYNTHETIC_ANCHORS = {"opening": 24 * 60, "t-10h": 600, "t-5h": 300, "t-1h": 60, "t-15m": 15, "close": 15}


def odds(games: pd.DataFrame, anchors: dict[str, int] | None = None, books=SYNTHETIC_BOOKS,
         seed: int = 0) -> pd.DataFrame:
    """Made-up totals quotes in the odds_snapshots shape, one per game, book and anchor.

    The synthetic market centres on the final total plus noise (SD about 14 points at the
    latest anchor, more at earlier ones) for played games, and on the league average for
    scheduled ones. Games need id, home, away, home_pts, away_pts and either tip_utc or
    game_date (a missing tip is taken as 00:00 UTC the next day).
    """
    anchors = anchors or SYNTHETIC_ANCHORS
    rng = np.random.default_rng(seed)
    league_total = 2 * LEAGUE_PACE * LEAGUE_ORTG / 100
    rows = []
    for g in games.itertuples():
        tip = (pd.Timestamp(g.tip_utc) if isinstance(g.tip_utc, str) and g.tip_utc
               else pd.Timestamp(g.game_date, tz="UTC") + pd.Timedelta(days=1))
        final = pd.notna(g.home_pts) and pd.notna(g.away_pts)
        centre = (g.home_pts + g.away_pts if final else league_total) + rng.normal(0, 13.5 if final else 6.0)
        for anchor, lead in sorted(anchors.items(), key=lambda kv: -kv[1]):
            drift = rng.normal(0, 0.004 * lead) if lead > 15 else 0.0
            captured = tip - pd.Timedelta(minutes=lead)
            for book in books:
                line = round(2 * (centre + drift + rng.normal(0, 0.5))) / 2
                over = round(1.91 + rng.normal(0, 0.03), 2)
                rows.append(dict(event_id=f"syn{g.id}", game_id=int(g.id), book=book, market="totals",
                                 anchor=anchor, captured_utc=captured.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 commence_utc=tip.strftime("%Y-%m-%dT%H:%M:%SZ"), lead_minutes=float(lead),
                                 home=g.home, away=g.away, line=line, over_price=over,
                                 under_price=round(3.82 - over, 2), source="synthetic"))
    return pd.DataFrame(rows)
