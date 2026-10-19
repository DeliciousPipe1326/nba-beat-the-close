"""Read the maintainer's private legacy SQLite DB into this project's schema.

The legacy DB is NOT part of this repository and is never copied into it. Its
path comes only from the NBA_LEGACY_DB environment variable. It holds
BallDontLie games and team box scores and The Odds API historical snapshots
fetched under the maintainer's own keys; anyone else rebuilds the same shapes
with the ingesters in nbatotals.ingest.

Legacy tables read (read-only):
    games            -> games
    team_game_stats  -> team_box   (possessions/pace/ratings recomputed from counts)
    odds_truth       -> odds_snapshots  (anchors stored as legacy_open, legacy_noon_local,
                                         legacy_close: the labels are wrong, see docs/RESULTS.md)

Capture times: odds_truth has none. If NBA_LEGACY_ODDS_LAKE points at the raw
The Odds API payloads the rows were parsed from, every row is joined to its
source file and event (see legacy_lake.py) and gets the file's snapshot time
as captured_utc and the event's commence_time as its tip. Rows captured at or
after tip (in-play) or whose event commences on a different US Eastern date
than the game are then unusable.

Run `python -m nbatotals.evaluate.adapters.legacy_nba_db` to print the
verification report.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nbatotals import boxscore, store
from nbatotals.evaluate.adapters import legacy_lake
from nbatotals.teams import BDL_ID_TO_ALIAS

SOURCE = "legacy_nba_db"
# The legacy labels do not describe when the snapshots were taken (docs/RESULTS.md,
# Appendix B), so they are stored under names nobody will mistake for live anchors.
ANCHOR_MAP = {"open": "legacy_open", "noon_local": "legacy_noon_local", "close": "legacy_close"}
ENV_VAR = "NBA_LEGACY_DB"


def legacy_path(path: str | os.PathLike | None = None) -> Path:
    path = path or os.environ.get(ENV_VAR)
    if not path:
        raise RuntimeError(f"set {ENV_VAR} to the legacy SQLite path")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def read_games(con: sqlite3.Connection) -> pd.DataFrame:
    g = pd.read_sql_query(
        """SELECT id, date, season, status, period, postseason,
                  home_team_id, visitor_team_id, home_team_score, visitor_team_score,
                  scheduled_tip_utc
           FROM games""",
        con,
    )
    final = g["status"].eq("Final")
    out = pd.DataFrame(
        {
            "id": g["id"].astype(int),
            "game_date": g["date"].astype(str),
            "tip_utc": g["scheduled_tip_utc"],
            "season": g["season"].astype(int),
            "postseason": g["postseason"].fillna(0).astype(int),
            "home": g["home_team_id"].map(BDL_ID_TO_ALIAS),
            "away": g["visitor_team_id"].map(BDL_ID_TO_ALIAS),
            "home_pts": g["home_team_score"].where(final),
            "away_pts": g["visitor_team_score"].where(final),
            "periods": g["period"].where(final),
            "status": np.where(final, "final", "scheduled"),
            "source": SOURCE,
        }
    )
    if out[["home", "away"]].isna().any().any():
        raise ValueError("legacy games reference a team id outside BDL 1-30")
    return out


def read_team_box(con: sqlite3.Connection, games: pd.DataFrame) -> pd.DataFrame:
    t = pd.read_sql_query(
        """SELECT game_id, team_id, pts, fgm, fga, fg3m, fg3a, ftm, fta,
                  oreb AS orb, dreb AS drb, tov, pace AS legacy_pace
           FROM team_game_stats""",
        con,
    )
    t["team"] = t["team_id"].map(BDL_ID_TO_ALIAS)
    g = games.set_index("id")
    t = t[t["game_id"].isin(g.index[g["status"] == "final"])]
    rows = []
    for game_id, grp in t.groupby("game_id", sort=True):
        info = g.loc[game_id]
        sides = {r["team"]: r for r in grp.to_dict("records")}
        if set(sides) != {info["home"], info["away"]}:
            continue  # incomplete or mismatched pair; counted in verify()
        home, away = boxscore.derive(sides[info["home"]], sides[info["away"]], info["periods"])
        for row, opp, is_home in ((home, info["away"], 1), (away, info["home"], 0)):
            row.update(opp=opp, is_home=is_home, source=SOURCE)
            rows.append(row)
    cols = [
        "game_id", "team", "opp", "is_home", "minutes", "pts", "fgm", "fga", "fg3m", "fg3a",
        "ftm", "fta", "orb", "drb", "tov", "possessions", "pace", "ortg", "drtg", "source",
        "legacy_pace",
    ]
    return pd.DataFrame(rows, columns=cols)


def read_odds(con: sqlite3.Connection) -> pd.DataFrame:
    o = pd.read_sql_query(
        """SELECT CAST(game_id AS INTEGER) AS game_id, bookmaker AS book,
                  market_type AS market, snapshot_type, hours_before_game,
                  snapshot_timestamp, home_team_id, raw_json_file, api_game_id,
                  total_line, total_over_odds, total_under_odds,
                  spread_home, spread_home_odds, spread_away_odds,
                  ml_home_odds, ml_away_odds,
                  total_over_decimal, total_under_decimal, spread_home_decimal,
                  spread_away_decimal, ml_home_decimal, ml_away_decimal
           FROM odds_truth""",
        con,
    )

    # The provider sent decimal prices; the legacy American columns were rounded
    # from them (1.91 became -109). Use the decimal columns, which match the raw
    # payloads, and convert American only where a decimal is missing.
    def dec(american_col):
        decimal = o[american_col.replace("_odds", "_decimal")]
        return decimal.where(decimal.notna(), o[american_col].map(boxscore.american_to_decimal, na_action="ignore")).astype(float)

    totals = o["market"].eq("totals")
    spreads = o["market"].eq("spreads")
    h2h = o["market"].eq("h2h")
    out = pd.DataFrame(
        {
            "game_id": o["game_id"],
            "book": o["book"],
            "market": o["market"],
            "anchor": o["snapshot_type"].map(ANCHOR_MAP),
            "captured_utc": o["snapshot_timestamp"].replace("", None),
            "nominal_hours_before": o["hours_before_game"],
            "line": np.select([totals, spreads], [o["total_line"], o["spread_home"]], np.nan),
            "over_price": dec("total_over_odds").where(totals),
            "under_price": dec("total_under_odds").where(totals),
            "home_price": np.select(
                [spreads, h2h], [dec("spread_home_odds"), dec("ml_home_odds")], np.nan
            ),
            "away_price": np.select(
                [spreads, h2h], [dec("spread_away_odds"), dec("ml_away_odds")], np.nan
            ),
            "source": SOURCE,
            "legacy_home_team_id": o["home_team_id"],
            "raw_json_file": o["raw_json_file"],
            "api_game_id": o["api_game_id"],
        }
    )
    if out["anchor"].isna().any():
        raise ValueError(f"unmapped legacy snapshot types: {set(o.loc[out['anchor'].isna(), 'snapshot_type'])}")
    return out


def attach_capture_times(odds: pd.DataFrame, games: pd.DataFrame, lake: pd.DataFrame) -> pd.DataFrame:
    """Join each legacy row to its source file and event; add timing columns and flags."""
    odds = odds.copy()
    odds["file_key"] = odds["raw_json_file"].map(legacy_lake.file_key)
    cols = ["file_key", "event_id", "book", "snapshot_utc", "commence_utc", "over_point", "over_price", "under_price"]
    lk = lake[cols].rename(columns={"over_price": "file_over", "under_price": "file_under"})
    # One event is listed twice in one file (2025-03-20 close); keep the first listing.
    lk = lk.drop_duplicates(["file_key", "event_id", "book"], keep="first")
    out = odds.merge(lk, left_on=["file_key", "api_game_id", "book"], right_on=["file_key", "event_id", "book"],
                     how="left", validate="many_to_one")
    snap = pd.to_datetime(out["snapshot_utc"], utc=True)
    tip = pd.to_datetime(out["commence_utc"], utc=True)
    out["captured_utc"] = snap.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(snap.notna(), None)
    out["commence_utc"] = tip.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(tip.notna(), None)
    out["lead_hours"] = (tip - snap).dt.total_seconds() / 3600.0
    out["lake_match"] = snap.notna()
    out["in_play"] = out["lake_match"] & (out["lead_hours"] <= 0)
    tip_date = tip.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    game_date = out["game_id"].map(games.set_index("id")["game_date"])
    out["date_mismatch"] = out["lake_match"] & (tip_date != game_date)
    totals = out["market"].eq("totals") & out["lake_match"]
    out["parse_mismatch"] = totals & (
        (out["line"] != out["over_point"])
        | ((out["over_price"] - out["file_over"]).abs() > 1e-9)
        | ((out["under_price"] - out["file_under"]).abs() > 1e-9)
    )
    return out.drop(columns=["event_id", "snapshot_utc", "over_point", "file_over", "file_under"])


def tip_times(odds: pd.DataFrame) -> pd.Series:
    """Per game, the provider's commence_time from rows whose date matches the game."""
    ok = odds[odds["lake_match"] & ~odds["date_mismatch"]]
    return ok.groupby("game_id")["commence_utc"].agg(lambda s: s.mode().iloc[0])


def load(path: str | os.PathLike | None = None, lake: str | os.PathLike | None = None) -> dict[str, pd.DataFrame]:
    """Return {'games', 'team_box', 'odds_raw'} in the new schema's shapes.

    'odds_raw' still contains unusable rows (a missing price; with the lake,
    in-play or wrong-date quotes); `usable_odds` drops them so they can be
    counted first. The lake join runs when `lake` or NBA_LEGACY_ODDS_LAKE is set.
    """
    con = _connect_ro(legacy_path(path))
    try:
        games = read_games(con)
        team_box = read_team_box(con, games)
        odds = read_odds(con)
    finally:
        con.close()
    if lake or os.environ.get(legacy_lake.ENV_VAR):
        odds = attach_capture_times(odds, games, legacy_lake.read_lake(lake))
        games["tip_utc"] = games["id"].map(tip_times(odds)).where(lambda s: s.notna(), games["tip_utc"])
    return {"games": games, "team_box": team_box, "odds_raw": odds}


def usable_odds(odds: pd.DataFrame) -> pd.DataFrame:
    totals = odds["market"].eq("totals")
    ok_totals = odds["line"].notna() & odds["over_price"].notna() & odds["under_price"].notna()
    ok_other = odds["home_price"].notna() & odds["away_price"].notna()
    ok = np.where(totals, ok_totals, ok_other)
    if "lake_match" in odds:
        ok = ok & odds["lake_match"] & ~odds["in_play"] & ~odds["date_mismatch"] & ~odds["parse_mismatch"]
    return odds[ok]


def write_store(frames: dict[str, pd.DataFrame], out: str | os.PathLike) -> Path:
    """Materialise into a local store (under data/, git-ignored)."""
    out = Path(out)
    if out.exists():
        out.unlink()
    con = store.connect(out)
    games = frames["games"]
    box = frames["team_box"].drop(columns=["legacy_pace"])
    odds = usable_odds(frames["odds_raw"]).rename(columns={"api_game_id": "event_id"})
    if "commence_utc" not in odds:
        odds["commence_utc"] = None
    lead = (pd.to_datetime(odds["commence_utc"], utc=True) - pd.to_datetime(odds["captured_utc"], utc=True))
    odds["lead_minutes"] = lead.dt.total_seconds() / 60.0
    odds = odds[["event_id", "game_id", "book", "market", "anchor", "captured_utc", "commence_utc", "lead_minutes",
                 "line", "over_price", "under_price", "home_price", "away_price", "source"]]
    odds = odds[odds["game_id"].isin(games["id"])]
    games.to_sql("games", con, if_exists="append", index=False)
    box.to_sql("team_box", con, if_exists="append", index=False)
    odds.to_sql("odds_snapshots", con, if_exists="append", index=False)
    con.commit()
    con.close()
    return out


def verify(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame | dict]:
    games, box, odds = frames["games"], frames["team_box"], frames["odds_raw"]
    final = games[games["status"] == "final"]

    per_season = final.groupby(["season", "postseason"]).agg(
        games=("id", "size"), first=("game_date", "min"), last=("game_date", "max")
    )
    box_games = box.groupby("game_id").size()
    per_season["box_pairs"] = final.groupby(["season", "postseason"])["id"].apply(
        lambda ids: int(box_games.reindex(ids).eq(2).sum())
    )

    tot = odds[odds["market"] == "totals"].merge(
        games[["id", "season", "postseason"]], left_on="game_id", right_on="id", how="left"
    )
    tot["has_both_prices"] = tot["over_price"].notna() & tot["under_price"].notna()
    totals_by = tot.groupby(["season", "anchor"]).agg(
        rows=("game_id", "size"),
        games=("game_id", "nunique"),
        books=("book", "nunique"),
        missing_a_price=("has_both_prices", lambda s: int((~s).sum())),
        captured_utc_present=("captured_utc", lambda s: int(s.notna().sum())),
        line_outside_150_300=("line", lambda s: int(((s < 150) | (s > 300)).sum())),
    )
    reg_final = final[final["postseason"] == 0]
    close_games = set(tot.loc[(tot["anchor"] == "legacy_close") & tot["has_both_prices"], "game_id"])
    coverage = (
        reg_final.assign(has_close=reg_final["id"].isin(close_games))
        .groupby("season")["has_close"]
        .agg(["size", "sum", "mean"])
        .rename(columns={"size": "reg_season_finals", "sum": "with_close_totals", "mean": "share"})
    )

    # The legacy "pace" column is raw game possessions (not per 48), so it
    # should equal our possessions in every game and our pace in regulation.
    diff = (box["possessions"] - box["legacy_pace"]).abs()
    reg = box["minutes"] == boxscore.REGULATION_MINUTES
    pace_check = {
        "rows": len(box),
        "possessions_max_abs_diff_vs_legacy_pace": float(diff.max()),
        "rows_possessions_off_by_more_than_0.01": int((diff > 0.01).sum()),
        "regulation_pace_max_abs_diff": float((box.loc[reg, "pace"] - box.loc[reg, "legacy_pace"]).abs().max()),
        "ot_rows_where_legacy_pace_is_not_per48": int((~reg).sum()),
    }
    # Box points must reproduce the game score.
    pts = box.merge(games[["id", "home_pts", "away_pts"]], left_on="game_id", right_on="id")
    pts["expected"] = np.where(pts["is_home"] == 1, pts["home_pts"], pts["away_pts"])
    home_mismatch = odds["legacy_home_team_id"].notna() & odds.merge(
        games[["id", "home"]], left_on="game_id", right_on="id", how="left"
    )["home"].ne(odds["legacy_home_team_id"].map(BDL_ID_TO_ALIAS)).to_numpy()
    integrity = {
        "box_points_mismatch": int((pts["pts"] != pts["expected"]).sum()),
        "final_games_without_box_pair": int(len(final) - box["game_id"].nunique()),
        "odds_rows_unknown_game": int(tot["id"].isna().sum()),
        "odds_rows_home_team_mismatch": int(home_mismatch.sum()),
        "duplicate_snapshot_keys": int(
            odds.duplicated(["game_id", "book", "market", "anchor"]).sum()
        ),
        "totals_rows_missing_a_price": int((~tot["has_both_prices"]).sum()),
    }
    timing = {}
    if "lake_match" in odds:
        t2 = odds[odds["market"] == "totals"].merge(games[["id", "season", "postseason"]], left_on="game_id",
                                                    right_on="id")
        t2 = t2[t2["postseason"] == 0]
        timing["lead_hours_by_season_anchor"] = t2[t2["lake_match"] & ~t2["date_mismatch"]].groupby(
            ["season", "anchor"])["lead_hours"].describe(percentiles=[0.05, 0.5, 0.95])[["count", "5%", "50%", "95%"]]
        timing["flags_by_season_anchor"] = t2.groupby(["season", "anchor"]).agg(
            rows=("game_id", "size"),
            not_in_lake=("lake_match", lambda s: int((~s).sum())),
            in_play_rows=("in_play", "sum"),
            in_play_games=("game_id", lambda s: int(s[t2.loc[s.index, "in_play"]].nunique())),
            wrong_date_rows=("date_mismatch", "sum"),
            parse_mismatch_rows=("parse_mismatch", "sum"),
        )
    return {
        **timing,
        "per_season": per_season,
        "totals_by_season_anchor": totals_by,
        "close_coverage": coverage,
        "pace_check": pace_check,
        "integrity": integrity,
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    frames = load()
    report = verify(frames)
    pd.set_option("display.width", 160)
    for key, value in report.items():
        print(f"\n== {key} ==")
        print(value if isinstance(value, pd.DataFrame) else "\n".join(f"{k}: {v}" for k, v in value.items()))
    if argv and argv[0] == "--write":
        out = argv[1] if len(argv) > 1 else store.DEFAULT_DB
        print(f"\nwrote {write_store(frames, out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
