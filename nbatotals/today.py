"""Build the `today` research CSV: fixtures, projected totals, market line, edge.

Everything comes from the local store: fill it first with the ingesters
(`ingest-games`, `ingest-box`, `poll-odds`). This is research output. The
pre-registered backtest found no edge against the closing line
(docs/RESULTS.md), and the header line of every file says so.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from nbatotals import data
from nbatotals.evaluate import market
from nbatotals.features.pointintime import build_features
from nbatotals.model.projection import project

HEADER = ("# Research output, not betting advice. In a pre-registered walk-forward backtest (docs/RESULTS.md) "
          "this model covered 48.9% against the true closing total and lost 6.7% at real prices: no edge.")

COLUMNS = ["game_date", "tip_utc", "away", "home", "projected_total", "projected_pace", "home_pts_proj",
           "away_pts_proj", "market_line", "market_anchor", "market_captured_utc", "market_lead_minutes",
           "books", "p_over_devig", "edge", "games_played_home", "games_played_away"]


def build(con: sqlite3.Connection, date: str, params: dict) -> pd.DataFrame:
    games, box = data.load_frames(con)
    targets = games[games["game_date"] == date]
    if targets.empty:
        return pd.DataFrame(columns=COLUMNS)
    feats = build_features(targets, games, box, params)
    proj = project(feats, params)
    out = targets[["id", "game_date", "tip_utc", "away", "home"]].merge(
        proj, left_on="id", right_on="game_id").merge(
        feats[["game_id", "home_n", "away_n"]], on="game_id")
    anchor = params["today"]["market_anchor"]
    odds = pd.read_sql_query(
        "SELECT * FROM odds_snapshots WHERE market = 'totals' AND anchor = ? AND game_id IN "
        f"({', '.join('?' * len(out))})", con, params=[anchor, *out["game_id"].astype(int).tolist()])
    if not odds.empty:
        cons = market.consensus(odds, params)
        lead = odds.groupby("game_id")["lead_minutes"].min().rename("market_lead_minutes")
        cons = cons.merge(lead, on="game_id", how="left")
        out = out.merge(cons[["game_id", "line", "captured_utc", "books", "p_over", "market_lead_minutes"]],
                        on="game_id", how="left")
    else:
        out = out.assign(line=None, captured_utc=None, books=None, p_over=None, market_lead_minutes=None)
    out = out.rename(columns={"total_proj": "projected_total", "pace_proj": "projected_pace", "line": "market_line",
                              "captured_utc": "market_captured_utc", "p_over": "p_over_devig",
                              "home_n": "games_played_home", "away_n": "games_played_away"})
    out["market_anchor"] = anchor
    out["edge"] = out["projected_total"] - pd.to_numeric(out["market_line"])
    for c in ("projected_total", "projected_pace", "home_pts_proj", "away_pts_proj", "edge"):
        out[c] = pd.to_numeric(out[c]).round(1)
    out["p_over_devig"] = pd.to_numeric(out["p_over_devig"]).round(3)
    return out[COLUMNS].sort_values(["tip_utc", "home"], na_position="last").reset_index(drop=True)


def write_csv(df: pd.DataFrame, path) -> None:
    with open(path, "w") as fh:
        fh.write(HEADER + "\n")
        df.to_csv(fh, index=False)
