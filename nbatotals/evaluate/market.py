"""Market consensus for totals, exactly as pre-registered (docs/PREREGISTRATION.md).

For each game and anchor, from totals quotes with both prices:
1. drop a book whose line is more than `outlier_points` from the median line of
   all books for that game and anchor;
2. consensus line = median of the remaining books' lines (may be a quarter point);
3. each book devigged multiplicatively, p_over = (1/o) / (1/o + 1/u);
   consensus p_over = mean of the books' p_over;
4. real price per side = median of the books' decimal prices for that side;
5. at least `min_books` books after step 1, or the game is not scored at that anchor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ANCHOR_LABELS = {"opening": "opening", "t-10h": "T−10h", "t-5h": "T−5h", "t-3h": "T−3h", "t-2h": "T−2h",
                 "t-1h": "T−1h", "t-15m": "T−15 min", "close": "close (last pre-tip poll)"}


def consensus(odds: pd.DataFrame, params: dict) -> pd.DataFrame:
    m = params["market"]
    t = odds[(odds["market"] == "totals") & odds["over_price"].notna() & odds["under_price"].notna()
             & odds["line"].notna()].copy()
    t["raw_median"] = t.groupby(["game_id", "anchor"])["line"].transform("median")
    t = t[(t["line"] - t["raw_median"]).abs() <= m["outlier_points"]]
    inv_o, inv_u = 1.0 / t["over_price"], 1.0 / t["under_price"]
    t["p_over"] = inv_o / (inv_o + inv_u)
    extra = {}
    if "captured_utc" in t:
        extra["captured_utc"] = ("captured_utc", "max")
    out = t.groupby(["game_id", "anchor"]).agg(
        **extra,
        books=("book", "nunique"),
        line=("line", "median"),
        p_over=("p_over", "mean"),
        over_price=("over_price", "median"),
        under_price=("under_price", "median"),
    ).reset_index()
    out = out[out["books"] >= m["min_books"]].reset_index(drop=True)
    out["p_under"] = 1.0 - out["p_over"]
    return out


def consensus_spreads(odds: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Spreads consensus (Experiment 5 pre-registration), same rules as totals.

    Input rows: market "spreads", `line` = the book's home spread, `home_price`,
    `away_price`. Per game and anchor: drop a book whose home spread is more than
    `outlier_points` from the median; consensus home spread = median; each book
    devigged multiplicatively, p_home = (1/h) / (1/h + 1/a), consensus = mean;
    real price per side = median; at least `min_books` books.

    Returned with the totals column names so the totals grading code applies
    unchanged, with home in the role of over: `line` = the home margin the
    market implies (minus the home spread), `p_over` = p_home_cover,
    `over_price`/`under_price` = home/away. `home_spread` is kept as well.
    """
    m = params["market"]
    t = odds[(odds["market"] == "spreads") & odds["home_price"].notna() & odds["away_price"].notna()
             & odds["line"].notna()].copy()
    t["raw_median"] = t.groupby(["game_id", "anchor"])["line"].transform("median")
    t = t[(t["line"] - t["raw_median"]).abs() <= m["outlier_points"]]
    return _sides(t, m["min_books"], with_line=True)


def consensus_h2h(odds: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Moneyline consensus (Experiment 5 pre-registration): each book devigged
    multiplicatively, consensus p_home = mean; real price per side = median; at
    least `min_books` books. No line, so no outlier rule. Columns as in
    `consensus_spreads` (`p_over` = p_home, `line` NaN)."""
    t = odds[(odds["market"] == "h2h") & odds["home_price"].notna() & odds["away_price"].notna()].copy()
    return _sides(t, params["market"]["min_books"], with_line=False)


def _sides(t: pd.DataFrame, min_books: int, with_line: bool) -> pd.DataFrame:
    inv_h, inv_a = 1.0 / t["home_price"], 1.0 / t["away_price"]
    t["p_home"] = inv_h / (inv_h + inv_a)
    extra = {}
    if "captured_utc" in t:
        extra["captured_utc"] = ("captured_utc", "max")
    if with_line:
        extra["home_spread"] = ("line", "median")
    out = t.groupby(["game_id", "anchor"]).agg(
        **extra,
        books=("book", "nunique"),
        p_over=("p_home", "mean"),
        over_price=("home_price", "median"),
        under_price=("away_price", "median"),
    ).reset_index()
    out = out[out["books"] >= min_books].reset_index(drop=True)
    out["line"] = -out["home_spread"] if with_line else np.nan
    out["p_under"] = 1.0 - out["p_over"]
    return out


def wide(cons: pd.DataFrame) -> pd.DataFrame:
    """One row per game with columns like line_close, p_over_open, ..."""
    w = cons.pivot(index="game_id", columns="anchor",
                   values=["books", "line", "p_over", "p_under", "over_price", "under_price"])
    w.columns = [f"{v}_{a}" for v, a in w.columns]
    return w.reset_index()


def enforce_anchor_order(cons: pd.DataFrame, ref: str) -> tuple[pd.DataFrame, int]:
    """Drop any other anchor's consensus captured at or after the same game's `ref` capture.

    An anchor that CLV is measured from must precede the reference it is
    measured against. Uses capture times only, never outcomes. Returns the kept
    rows and the number dropped.
    """
    if "captured_utc" not in cons or cons["captured_utc"].isna().all():
        return cons, 0
    ref_at = cons[cons["anchor"] == ref].set_index("game_id")["captured_utc"]
    later = (cons["anchor"] != ref) & (cons["captured_utc"] >= cons["game_id"].map(ref_at))
    return cons[~later].reset_index(drop=True), int(later.sum())


def sanity_table(cons: pd.DataFrame, games: pd.DataFrame, labels: dict = ANCHOR_LABELS) -> pd.DataFrame:
    g = games[(games["status"] == "final") & (games["postseason"] == 0)][["id", "season", "home_pts", "away_pts"]]
    c = cons.merge(g, left_on="game_id", right_on="id")
    c["actual"] = c["home_pts"] + c["away_pts"]
    c["quarter"] = (c["line"] * 2) % 1 != 0
    rows = []
    for (season, anchor), x in c.groupby(["season", "anchor"]):
        rows.append({
            "season": season, "anchor": labels[anchor], "games": len(x),
            "books_median": float(x["books"].median()),
            "line_mean": x["line"].mean(), "line_sd": x["line"].std(),
            "p_over_mean": x["p_over"].mean(), "quarter_share": x["quarter"].mean(),
            "mae_vs_actual": (x["line"] - x["actual"]).abs().mean(),
            "mean_error": (x["actual"] - x["line"]).mean(),
        })
    out = pd.DataFrame(rows)
    order = {v: i for i, v in enumerate(labels.values())}
    return out.sort_values(["season", "anchor"], key=lambda s: s.map(order) if s.name == "anchor" else s)


def movement_table(cons: pd.DataFrame, games: pd.DataFrame, labels: dict = ANCHOR_LABELS) -> pd.DataFrame:
    """How often and how far the consensus moves between anchors (live anchor names)."""
    w = wide(cons).merge(games[games["postseason"] == 0][["id", "season"]], left_on="game_id", right_on="id")
    rows = []
    for season, x in w.groupby("season"):
        for a, b in (("opening", "close"), ("t-10h", "close"), ("opening", "t-10h")):
            ok = x[f"line_{a}"].notna() & x[f"line_{b}"].notna()
            d = (x.loc[ok, f"line_{b}"] - x.loc[ok, f"line_{a}"])
            rows.append({"season": season, "from": labels[a], "to": labels[b], "games": int(ok.sum()),
                         "share_moved": float((d != 0).mean()), "mean_abs_move": float(d.abs().mean()),
                         "mean_move": float(d.mean())})
    return pd.DataFrame(rows)
