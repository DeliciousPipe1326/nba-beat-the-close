"""Point-in-time team features for the Tier A totals engine.

Cut-off rule for every feature: a game dated D sees only rows whose game_date
is strictly before D. The game's own row, and anything later that day, never
enters. Concretely:

    team windows (L3, L10, season)  team_box rows, same team, same season, date < D
    league averages                 team_box rows, all teams, same season, date < D,
                                    shrunk towards a base value (previous season's
                                    league average, or a constant)
    carry-over prior (optional)     the team's previous-season rows (all dated < D)
    rest days, back-to-back         the games table (schedule dates only), same
                                    team, same season, date < D

`build_features(targets, games, box, params)` returns one row per target game.
`targets` only needs id, game_date, season, home and away: scores in it are
ignored, so the same call works for tonight's fixtures.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

STATS = ("pace", "ortg", "drtg")
WINDOWS = {"l3": 3, "l10": 10, "season": None}


def _day_numbers(dates: pd.Series) -> np.ndarray:
    return pd.to_datetime(dates).to_numpy().astype("datetime64[D]").astype(np.int64)


class _Arrays:
    """Columns of a row set sorted by (date, game_id), as numpy arrays."""

    __slots__ = ("day", "season", "poss", "minutes", "pts", "opp_pts")

    def __init__(self, frame: pd.DataFrame):
        frame = frame.sort_values(["day", "game_id", "team"], kind="mergesort")
        self.day = frame["day"].to_numpy()
        self.season = frame["season"].to_numpy()
        self.poss = frame["possessions"].to_numpy(dtype=float)
        self.minutes = frame["minutes"].to_numpy(dtype=float)
        self.pts = frame["pts"].to_numpy(dtype=float)
        self.opp_pts = frame["opp_pts"].to_numpy(dtype=float)

    def before(self, day: int, season: int) -> tuple[int, int]:
        """Index range of rows in `season` dated strictly before `day`."""
        hi = int(np.searchsorted(self.day, day, side="left"))
        lo = int(np.searchsorted(self.season[:hi], season, side="left"))
        hi_s = int(np.searchsorted(self.season[:hi], season, side="right"))
        return lo, hi_s

    def rates(self, lo: int, hi: int) -> dict[str, float]:
        poss = self.poss[lo:hi].sum()
        return {
            "pace": 48.0 * poss / self.minutes[lo:hi].sum(),
            "ortg": 100.0 * self.pts[lo:hi].sum() / poss,
            "drtg": 100.0 * self.opp_pts[lo:hi].sum() / poss,
        }


class History:
    """Everything known up to the latest row passed in, indexed for date cut-offs."""

    def __init__(self, games: pd.DataFrame, box: pd.DataFrame):
        g = games[["id", "game_date", "season", "home", "away", "home_pts", "away_pts"]].copy()
        g["day"] = _day_numbers(g["game_date"])
        h = box.merge(g[["id", "day", "season", "home_pts", "away_pts"]], left_on="game_id", right_on="id")
        h["opp_pts"] = np.where(h["is_home"] == 1, h["away_pts"], h["home_pts"])

        self.team = {}
        for team, rows in h.groupby("team"):
            self.team[(team, "all")] = _Arrays(rows)
            self.team[(team, "home")] = _Arrays(rows[rows["is_home"] == 1])
            self.team[(team, "away")] = _Arrays(rows[rows["is_home"] == 0])
        self.league = {season: _Arrays(rows) for season, rows in h.groupby("season")}

        sched = pd.concat(
            [g[["day", "season", "home"]].rename(columns={"home": "team"}),
             g[["day", "season", "away"]].rename(columns={"away": "team"})]
        ).sort_values(["team", "day"], kind="mergesort")
        self.schedule = {
            team: (rows["day"].to_numpy(), rows["season"].to_numpy()) for team, rows in sched.groupby("team")
        }

    # League ------------------------------------------------------------------

    def league_ref(self, day: int, season: int, params: dict) -> dict[str, float]:
        lp = params["league"]
        base = {"pace": float(lp["fallback_pace"]), "ortg": float(lp["fallback_ortg"])}
        if lp["prior_source"] == "previous_season" and season - 1 in self.league:
            prev = self.league[season - 1]
            lo, hi = prev.before(day, season - 1)
            if hi > lo:
                r = prev.rates(lo, hi)
                base = {"pace": r["pace"], "ortg": r["ortg"]}
        cur = self.league.get(season)
        n = 0
        raw = None
        if cur is not None:
            lo, hi = cur.before(day, season)
            n = hi - lo
            if n:
                raw = cur.rates(lo, hi)
        k = float(lp["shrinkage_team_games"])
        out: dict[str, float] = {"n": n}
        for stat in ("pace", "ortg"):
            out[stat] = base[stat] if raw is None else (n * raw[stat] + k * base[stat]) / (n + k)
        return out

    # Team --------------------------------------------------------------------

    def team_features(self, team: str, role: str, day: int, season: int, league: dict, params: dict) -> dict:
        fp = params["features"]
        arr = self.team.get((team, role))
        out: dict[str, float] = {}
        lo, hi = arr.before(day, season) if arr is not None else (0, 0)
        n = hi - lo
        out["n"] = n
        windows = {}
        for name, size in WINDOWS.items():
            if n and arr is not None:
                start = lo if size is None else max(lo, hi - size)
                windows[name] = arr.rates(start, hi)
            for stat in STATS:
                out[f"{stat}_{name}"] = windows[name][stat] if n else np.nan

        league_value = {"pace": league["pace"], "ortg": league["ortg"], "drtg": league["ortg"]}
        prior = dict(league_value)
        w = float(fp["team_carryover_weight"])
        if w > 0 and arr is not None:
            plo, phi = arr.before(day, season - 1)
            if phi > plo:
                prev = arr.rates(plo, phi)
                prior = {s: w * prev[s] + (1 - w) * league_value[s] for s in STATS}

        k = float(fp["team_shrinkage_games"])
        blend = fp["blend"]
        for stat in STATS:
            if n:
                blended = sum(blend[name] * windows[name][stat] for name in WINDOWS)
                out[stat] = (n * blended + k * prior[stat]) / (n + k)
            else:
                out[stat] = prior[stat]
        return out

    def rest(self, team: str, day: int, season: int) -> tuple[float, bool]:
        days, seasons = self.schedule.get(team, (np.array([], dtype=np.int64), np.array([], dtype=np.int64)))
        i = int(np.searchsorted(days, day, side="left")) - 1
        if i < 0 or seasons[i] != season:
            return np.nan, False
        rest_days = float(day - days[i] - 1)
        return rest_days, rest_days == 0


def build_features(targets: pd.DataFrame, games: pd.DataFrame, box: pd.DataFrame, params: dict,
                   history: History | None = None) -> pd.DataFrame:
    """One row of features per target game, using only history dated before it."""
    hist = history or History(games, box)
    split = bool(params["features"]["home_away_split"])
    days = _day_numbers(targets["game_date"])
    rows = []
    for (gid, season, home, away), day in zip(
        targets[["id", "season", "home", "away"]].itertuples(index=False, name=None), days, strict=True
    ):
        day = int(day)
        season = int(season)
        league = hist.league_ref(day, season, params)
        row = {"game_id": gid, "league_pace": league["pace"], "league_ortg": league["ortg"], "league_n": league["n"]}
        for side, team in (("home", home), ("away", away)):
            role = side if split else "all"
            for key, value in hist.team_features(team, role, day, season, league, params).items():
                row[f"{side}_{key}"] = value
            rest_days, b2b = hist.rest(team, day, season)
            row[f"{side}_rest_days"] = rest_days
            row[f"{side}_b2b"] = b2b
        rows.append(row)
    out = pd.DataFrame(rows)
    meta = targets[["id", "game_date", "season", "home", "away"]].rename(columns={"id": "game_id"})
    return meta.merge(out, on="game_id", how="left", validate="one_to_one")


FEATURE_COLUMNS = (
    ["league_pace", "league_ortg", "league_n"]
    + [f"{side}_{c}" for side in ("home", "away")
       for c in (["n"] + [f"{s}_{w}" for s in STATS for w in WINDOWS] + list(STATS) + ["rest_days", "b2b"])]
)
