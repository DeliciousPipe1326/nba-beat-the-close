"""Experiment 3: soft books against Pinnacle at the same poll.

Rules: docs/experiments/book_lag/PREREGISTRATION.md (committed before this code).

Input is a long frame of quotes, one row per (game, market, bucket, book), in a
source-agnostic shape (see `adapters.legacy_multiregion.market_quotes`):

    game_id, season, market ('totals' | 'spreads' | 'h2h'), bucket, book,
    polled_utc, commence_utc, last_update (tz-aware datetimes),
    a_point, b_point, a_price, b_price (decimal), names_ok

Side `a` is Over (totals) or the home team (spreads, h2h); `a_point` is the
total or the home handicap. Fair value is Pinnacle's two-way multiplicative
devig (`market.devig_two_way`) at the same bucket. For a side priced at decimal
`d`, edge = p_fair * d - 1; at most one bet per (book, game, bucket, market),
on the side with the larger edge. Settled at the soft book's own line from
final scores (overtime included), pushes excluded. CLV in cents is Pinnacle's
devigged true-close probability of the bet side at the bet's line minus p_fair.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from nbatotals.evaluate import market, metrics

PINNACLE = "pinnacle"
EXCHANGES = frozenset({"betfair_ex_uk", "betfair_ex_eu", "betfair_ex_au", "matchbook"})
BET_BUCKETS = ("opening", "noon", "afternoon", "early_evening", "late_evening", "near_close")
REF = "true_close"
ORDER = BET_BUCKETS + (REF,)
MARKETS = ("totals", "spreads", "h2h")
THRESHOLDS = (0.01, 0.02, 0.03, 0.05)
MAIN_THRESHOLD = 0.02
STALE_MINUTES = 30
MAX_CONVERT = 0.5
SD = {"totals": 18.0, "spreads": 13.5}
TEST_SEASONS = ("2022-23", "2023-24", "2024-25")
DESCRIPTIVE_SEASONS = ("2021-22",)
MIN_BETS_FOR_BAR = 500
N_PRIMARY_CELLS = 120  # about 40 books x 3 markets, as pre-registered
BONFERRONI_Z = NormalDist().inv_cdf(1 - 0.05 / N_PRIMARY_CELLS / 2)
MIN_N_FOR_CI = 30
KEYS = ["game_id", "market", "bucket"]


# ---------------------------------------------------------------- hygiene

def clean(q: pd.DataFrame, stale_minutes: float = STALE_MINUTES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop unusable quotes; return (kept, drop counts by reason, market and book).

    Each dropped row is counted once, under the first reason it fails in this order.
    """
    q = q.reset_index(drop=True)
    lag_min = (q["polled_utc"] - q["last_update"]).dt.total_seconds() / 60.0
    tot, spr = q["market"] == "totals", q["market"] == "spreads"
    malformed = (
        q["a_price"].isna() | q["b_price"].isna() | ~q["names_ok"].astype(bool)
        | ((tot | spr) & (q["a_point"].isna() | q["b_point"].isna()))
        | (tot & (q["a_point"] != q["b_point"]))
        | (spr & (q["a_point"] != -q["b_point"]))
    )
    reasons = [
        ("file polled at or after tip", q["polled_utc"] >= q["commence_utc"]),
        ("no last_update", q["last_update"].isna()),
        ("last_update at or after tip", q["last_update"] >= q["commence_utc"]),
        ("last_update after poll", q["last_update"] > q["polled_utc"]),
        (f"stale (> {stale_minutes:g} min before poll)", lag_min > stale_minutes),
        ("malformed quote", malformed),
    ]
    why = pd.Series(pd.NA, index=q.index, dtype="object")
    for name, mask in reasons:
        why = why.mask(why.isna() & mask.fillna(False).astype(bool), name)
    live = why.isna()
    dup = pd.Series(False, index=q.index)
    dup[live] = q[live].duplicated(["game_id", "market", "bucket", "book"], keep="first")
    why = why.mask(dup, "duplicate (game, bucket, market, book)")
    drops = (pd.DataFrame({"reason": why, "market": q["market"], "book": q["book"]})
             .dropna(subset=["reason"]).value_counts().rename("n").reset_index())
    kept = q[why.isna()].copy()
    kept["lag_min"] = lag_min[why.isna()]
    kept["lead_min"] = (kept["commence_utc"] - kept["polled_utc"]).dt.total_seconds() / 60.0
    return kept.reset_index(drop=True), drops


# ---------------------------------------------------------------- arithmetic

def move_prob_a(mkt, p_a, from_line, to_line):
    """Probability of side a at `to_line`, given p_a at `from_line` (normal approximation).

    totals: side a is Over, P(total > L).
    spreads: side a is the home team with handicap h, P(margin + h > 0) = P(margin > -h).
    h2h: no line, p_a returned unchanged.
    """
    mkt = np.asarray(mkt)
    p_a, from_line, to_line = (np.asarray(v, dtype=float) for v in (p_a, from_line, to_line))
    out = p_a.copy()
    for m, sign in (("totals", 1.0), ("spreads", -1.0)):
        sel = (mkt == m) & ~np.isnan(from_line) & ~np.isnan(to_line)
        same = sel & (from_line == to_line)
        move = sel & ~same
        if move.any():
            out[move] = metrics.prob_over_at(sign * to_line[move], sign * from_line[move], p_a[move], sd=SD[m])
    return out


def edges(p_fair_a, a_price, b_price):
    """Edge on each side, p_fair * decimal - 1."""
    p_fair_a = np.asarray(p_fair_a, float)
    return p_fair_a * np.asarray(a_price, float) - 1.0, (1.0 - p_fair_a) * np.asarray(b_price, float) - 1.0


def settle(mkt, side, line, home_pts, away_pts):
    """1 win, 0 loss, NaN push, for side 'a'/'b' at the soft book's line."""
    mkt, side = np.asarray(mkt), np.asarray(side)
    line = np.asarray(line, float)
    home_pts, away_pts = np.asarray(home_pts, float), np.asarray(away_pts, float)
    margin_a = np.where(mkt == "totals", home_pts + away_pts - line,
                        np.where(mkt == "spreads", home_pts - away_pts + line, home_pts - away_pts))
    margin = np.where(side == "a", margin_a, -margin_a)
    return np.where(margin > 0, 1.0, np.where(margin < 0, 0.0, np.nan))


def line_move(mkt, side, line, close_line):
    """Points of Pinnacle's true-close line relative to the bet's line, positive favouring the bet."""
    mkt, side = np.asarray(mkt), np.asarray(side)
    d = np.asarray(close_line, float) - np.asarray(line, float)
    # totals: over gains when the close is higher; spreads: home (a) gains when the
    # close handicap for home is smaller than the one taken, i.e. close - line < 0.
    sgn = np.where(mkt == "totals", np.where(side == "a", 1.0, -1.0), np.where(side == "a", -1.0, 1.0))
    return np.where(mkt == "h2h", np.nan, sgn * d)


# ---------------------------------------------------------------- pairing and bets

def pair(c: pd.DataFrame, mode: str = "exact") -> pd.DataFrame:
    """Every surviving soft-book quote at a betting bucket, beside Pinnacle's at the same bucket.

    mode 'exact': lines must match (h2h always matches). 'converted': lines within
    MAX_CONVERT points, Pinnacle's probability moved to the soft line.
    """
    pin = c[c["book"] == PINNACLE]
    pin_now = pin[KEYS + ["a_point", "a_price", "b_price", "polled_utc"]].rename(columns={
        "a_point": "pin_line", "a_price": "pin_a_price", "b_price": "pin_b_price", "polled_utc": "pin_polled_utc"})
    pin_now["pin_p_a"] = market.devig_two_way(pin_now["pin_a_price"], pin_now["pin_b_price"])
    close = pin[pin["bucket"] == REF][["game_id", "market", "a_point", "a_price", "b_price", "polled_utc"]].rename(
        columns={"a_point": "close_line", "polled_utc": "close_polled_utc"})
    close["close_p_a"] = market.devig_two_way(close.pop("a_price"), close.pop("b_price"))
    soft = c[(c["book"] != PINNACLE) & c["bucket"].isin(BET_BUCKETS)]
    p = soft.merge(pin_now, on=KEYS, how="inner").merge(close, on=["game_id", "market"], how="left")
    diff = p["a_point"] - p["pin_line"]
    is_h2h = p["market"] == "h2h"
    p["line_diff"] = diff.where(~is_h2h)
    exact = is_h2h | (diff == 0)
    keep = exact if mode == "exact" else (exact | (diff.abs() <= MAX_CONVERT + 1e-9))
    p = p[keep].reset_index(drop=True)
    p["converted"] = ~((p["market"] == "h2h") | (p["line_diff"] == 0))
    p["p_fair_a"] = move_prob_a(p["market"], p["pin_p_a"], p["pin_line"], p["a_point"])
    p["p_book_a"] = market.devig_two_way(p["a_price"], p["b_price"])
    p["disagree_cents"] = 100 * (p["p_book_a"] - p["p_fair_a"])
    p["gap_a_cents"] = 100 * (p["p_fair_a"] - 1 / p["a_price"])
    p["gap_b_cents"] = 100 * ((1 - p["p_fair_a"]) - 1 / p["b_price"])
    e_a, e_b = edges(p["p_fair_a"], p["a_price"], p["b_price"])
    p["edge_a"], p["edge_b"] = e_a, e_b
    p["side"] = np.where(e_a >= e_b, "a", "b")
    p["edge"] = np.maximum(e_a, e_b)
    p["price"] = np.where(p["side"] == "a", p["a_price"], p["b_price"])
    p["p_fair"] = np.where(p["side"] == "a", p["p_fair_a"], 1 - p["p_fair_a"])
    # CLV needs a close polled after the bet; a betting-bucket snapshot polled at or
    # after the same game's true close gets no CLV (it is kept for ROI).
    p["polled_after_close"] = p["polled_utc"] >= p["close_polled_utc"]
    for col in ("close_p_a", "close_line"):
        p[col] = p[col].where(~p["polled_after_close"])
    p_close_a = move_prob_a(p["market"], p["close_p_a"], p["close_line"], p["a_point"])
    p["p_close"] = np.where(p["side"] == "a", p_close_a, 1 - p_close_a)
    p["clv_cents"] = 100 * (p["p_close"] - p["p_fair"])
    p["edge_at_close"] = p["p_close"] * p["price"] - 1
    p["line_move"] = line_move(p["market"], p["side"], p["a_point"], p["close_line"])
    p["exchange"] = p["book"].isin(EXCHANGES)
    return p


def settle_frame(p: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    g = games[["id", "home_pts", "away_pts"]].rename(columns={"id": "game_id"})
    p = p.merge(g, on="game_id", how="inner")
    p["win"] = settle(p["market"], p["side"], p["a_point"], p["home_pts"], p["away_pts"])
    p["profit"] = np.where(p["win"] == 1, p["price"] - 1, np.where(p["win"] == 0, -1.0, np.nan))
    return p


# ---------------------------------------------------------------- summaries

def cell(b: pd.DataFrame, clv: bool = True, ci: bool = True) -> dict:
    """Stats for a set of bets; bootstrap resamples games."""
    s = b[b["win"].notna()]
    n = len(s)
    out = {"bets": n, "pushes": int(b["win"].isna().sum()), "games": int(s["game_id"].nunique()),
           "mean_edge": float(s["edge"].mean()) if n else np.nan,
           "cover": float(s["win"].mean()) if n else np.nan,
           "baseline": float(s["p_fair"].mean()) if n else np.nan,
           "roi": float(s["profit"].mean()) if n else np.nan}
    out["cover_lo"], out["cover_hi"] = metrics.wilson(int(s["win"].sum()), n)
    if ci and n >= MIN_N_FOR_CI:
        out["roi_lo"], out["roi_hi"], out["roi_se"] = metrics.bootstrap_cluster_mean_ci(s["profit"], s["game_id"])
    else:
        out["roi_lo"] = out["roi_hi"] = out["roi_se"] = np.nan
    c = s[s["clv_cents"].notna()]
    out["clv_bets"] = len(c)
    out["clv_cents"] = float(c["clv_cents"].mean()) if len(c) else np.nan
    out["line_move"] = float(c["line_move"].mean()) if len(c) and c["line_move"].notna().any() else np.nan
    out["edge_at_close"] = float(c["edge_at_close"].mean()) if len(c) else np.nan
    if clv and ci and len(c) >= MIN_N_FOR_CI:
        out["clv_lo"], out["clv_hi"], _ = metrics.bootstrap_cluster_mean_ci(c["clv_cents"], c["game_id"])
    else:
        out["clv_lo"] = out["clv_hi"] = np.nan
    return out


def per_book_anchor(bets: pd.DataFrame, threshold: float = MAIN_THRESHOLD) -> pd.DataFrame:
    rows = []
    b = bets[bets["edge"] >= threshold]
    for (mkt, book, bucket), x in b.groupby(["market", "book", "bucket"], observed=True):
        rows.append({"market": mkt, "book": book, "bucket": bucket, **cell(x)})
    out = pd.DataFrame(rows)
    return out.sort_values(["market", "bets"], ascending=[True, False]).reset_index(drop=True) if len(out) else out


def per_book_pooled(bets: pd.DataFrame, thresholds=THRESHOLDS, clv_thresholds=(MAIN_THRESHOLD,)) -> pd.DataFrame:
    rows = []
    for t in thresholds:
        b = bets[bets["edge"] >= t]
        for (mkt, book), x in b.groupby(["market", "book"], observed=True):
            rows.append({"threshold": t, "market": mkt, "book": book, **cell(x, clv=t in clv_thresholds)})
    out = pd.DataFrame(rows)
    if len(out):
        out["bonf_lo"] = out["roi"] - BONFERRONI_Z * out["roi_se"]
        out["clears_bar"] = ((out["bets"] >= MIN_BETS_FOR_BAR) & (out["roi_lo"] > 0) & (out["clv_lo"] > 0))
        out["clears_bonferroni"] = out["clears_bar"] & (out["bonf_lo"] > 0)
    return out


def by_anchor(paired: pd.DataFrame, bets: pd.DataFrame, threshold: float = MAIN_THRESHOLD) -> pd.DataFrame:
    """Overall picture per market and bucket, pooled over books (bootstrap over games)."""
    rows = []
    for (mkt, bucket), x in paired.groupby(["market", "bucket"], observed=True):
        y = bets[(bets["market"] == mkt) & (bets["bucket"] == bucket) & (bets["edge"] >= threshold)]
        games_compared = x["game_id"].nunique()
        rows.append({"market": mkt, "bucket": bucket, "quotes": len(x), "games": games_compared,
                     "books_per_game": len(x) / games_compared if games_compared else np.nan,
                     "mean_abs_disagree_cents": float(x["disagree_cents"].abs().mean()),
                     "share_edge_ge": float((x["edge"] >= threshold).mean()),
                     "bets_per_game": len(y) / games_compared if games_compared else np.nan,
                     **cell(y)})
    out = pd.DataFrame(rows)
    out["order"] = out["bucket"].map({b: i for i, b in enumerate(ORDER)})
    return out.sort_values(["market", "order"]).drop(columns="order").reset_index(drop=True)


def discrepancy_by_book(paired: pd.DataFrame) -> pd.DataFrame:
    """Descriptive: where each soft book's prices sit against Pinnacle's fair value (all buckets)."""
    rows = []
    for (mkt, book), x in paired.groupby(["market", "book"], observed=True):
        best_gap = np.maximum(x["gap_a_cents"], x["gap_b_cents"])
        hold = 100 * (1 / x["a_price"] + 1 / x["b_price"] - 1)
        rows.append({"market": mkt, "book": book, "quotes": len(x), "games": x["game_id"].nunique(),
                     "hold_pct": float(hold.mean()),
                     "mean_disagree_cents": float(x["disagree_cents"].mean()),
                     "mean_abs_disagree_cents": float(x["disagree_cents"].abs().mean()),
                     "mean_best_gap_cents": float(best_gap.mean()),
                     "share_edge_ge_2": float((x["edge"] >= 0.02).mean())})
    return pd.DataFrame(rows).sort_values(["market", "share_edge_ge_2"], ascending=[True, False])


def lag_table(c: pd.DataFrame, seasons=TEST_SEASONS) -> pd.DataFrame:
    """corr(Pinnacle move over b-1 -> b, soft book move over b -> b+1), pooled over buckets and games."""
    c = c[c["season"].isin(seasons)]
    lvl = c.assign(level=np.where(c["market"] == "h2h", 100 * market.devig_two_way(c["a_price"], c["b_price"]),
                                  c["a_point"]))
    w = lvl.pivot_table(index=["game_id", "market", "book"], columns="bucket", values="level", aggfunc="first",
                        observed=True)
    w = w.reindex(columns=list(ORDER))
    pin = w.xs(PINNACLE, level="book")
    rows = []
    trip = [(ORDER[i - 1], ORDER[i], ORDER[i + 1]) for i in range(1, len(ORDER) - 1)]

    def stack(a_prev, a_next):
        x = pd.concat(a_prev, ignore_index=True)
        y = pd.concat(a_next, ignore_index=True)
        ok = x.notna() & y.notna()
        return x[ok].to_numpy(), y[ok].to_numpy()

    for mkt in MARKETS:
        if mkt not in pin.index.get_level_values("market"):
            continue
        pm = pin.xs(mkt, level="market")
        x, y = stack([pm[b] - pm[a] for a, b, _ in trip], [pm[n] - pm[b] for _, b, n in trip])
        rows.append(_lag_row(mkt, "pinnacle (own momentum)", x, y, np.nan, np.nan))
        books = sorted(set(w.xs(mkt, level="market").index.get_level_values("book")) - {PINNACLE})
        for book in books:
            sm = w.xs((mkt, book), level=("market", "book"))
            j = sm.join(pm, how="inner", rsuffix="_pin")
            prev = [j[f"{b}_pin"] - j[f"{a}_pin"] for a, b, _ in trip]
            nxt = [j[n] - j[b] for _, b, n in trip]
            same_pin = [j[f"{n}_pin"] - j[f"{b}_pin"] for _, b, n in trip]
            x, y = stack(prev, nxt)
            xs, ys = stack(same_pin, nxt)
            same = metrics.corr_ci(xs, ys)[0] if len(xs) > 3 and np.std(xs) > 0 and np.std(ys) > 0 else np.nan
            rows.append(_lag_row(mkt, book, x, y, same, len(xs)))
    return pd.DataFrame(rows)


def _lag_row(mkt, book, x, y, same, n_same):
    if len(x) > 3 and np.std(x) > 0 and np.std(y) > 0:
        r, lo, hi, n = metrics.corr_ci(x, y)
    else:
        r = lo = hi = np.nan
        n = len(x)
    return {"market": mkt, "book": book, "pairs": n, "corr_next": r, "lo": lo, "hi": hi,
            "share_book_moved": float((y != 0).mean()) if len(y) else np.nan,
            "corr_same_period": same}


PRICE_BANDS = (1.0, 1.5, 2.0, 3.0, 5.0, np.inf)


def by_price_band(bets: pd.DataFrame, threshold: float = MAIN_THRESHOLD) -> pd.DataFrame:
    """Descriptive (not pre-registered): bets by the decimal price taken, per market, all soft books."""
    b = bets[bets["edge"] >= threshold].copy()
    b["band"] = pd.cut(b["price"], PRICE_BANDS, right=False)
    rows = []
    for (mkt, band), x in b.groupby(["market", "band"], observed=True):
        rows.append({"market": mkt, "band": f"{band.left:g} to {band.right:g}", **cell(x)})
    return pd.DataFrame(rows)


def calibration(paired: pd.DataFrame) -> pd.DataFrame:
    """Sign check: Pinnacle's p_fair for side a vs how often side a won, on exact-line quotes, one per game/bucket.

    `paired` must already carry the scores (settle_frame).
    """
    p = paired[~paired["converted"]].drop_duplicates(["game_id", "market", "bucket"])
    p["win_a"] = settle(p["market"], np.full(len(p), "a"), p["a_point"], p["home_pts"], p["away_pts"])
    rows = []
    for mkt, x in p.groupby("market"):
        s = x[x["win_a"].notna()]
        hi = s[s["p_fair_a"] >= 0.5]
        lo = s[s["p_fair_a"] < 0.5]
        rows.append({"market": mkt, "n": len(s), "mean_p_fair_a": s["p_fair_a"].mean(), "win_rate_a": s["win_a"].mean(),
                     "n_p_ge_half": len(hi), "p_fair_a_when_ge_half": hi["p_fair_a"].mean(),
                     "win_a_when_ge_half": hi["win_a"].mean(), "n_p_lt_half": len(lo),
                     "p_fair_a_when_lt_half": lo["p_fair_a"].mean(), "win_a_when_lt_half": lo["win_a"].mean()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- run

def run(quotes: pd.DataFrame, games: pd.DataFrame, seasons=TEST_SEASONS, progress=None) -> dict:
    """Everything the report needs. `games` needs id, season, status, postseason, home_pts, away_pts."""
    log = progress or (lambda msg: None)
    g = games[(games["status"] == "final") & (games["postseason"] == 0)]
    res = {"input_rows": len(quotes)}
    q = quotes[quotes["game_id"].isin(g["id"])]
    res["rows_not_scored_game"] = len(quotes) - len(q)
    c, drops = clean(q)
    c10, _ = clean(q, stale_minutes=10)
    res["drops"], res["kept_rows"] = drops, len(c)
    res["pinnacle_coverage"] = _pinnacle_coverage(c)
    out = {}
    for mode in ("exact", "converted"):
        log(f"pairing ({mode})")
        p = settle_frame(pair(c, mode), g)
        out[mode] = p
    res["paired"] = out
    ex = out["exact"]
    res["polled_after_close"] = ex[ex["polled_after_close"]].groupby(["season", "bucket"]).size().rename("quotes").reset_index()
    test = {m: p[p["season"].isin(seasons)] for m, p in out.items()}
    desc = {m: p[p["season"].isin(DESCRIPTIVE_SEASONS)] for m, p in out.items()}
    log("per book and anchor")
    res["book_anchor"] = per_book_anchor(test["exact"])
    log("per book pooled")
    res["pooled"] = {m: per_book_pooled(t) for m, t in test.items()}
    res["pooled_desc"] = per_book_pooled(desc["exact"], thresholds=(MAIN_THRESHOLD,))
    log("by anchor")
    res["by_anchor"] = by_anchor(test["exact"], test["exact"])
    res["by_anchor_converted"] = by_anchor(test["converted"], test["converted"])
    res["by_season"] = _by_season(test["exact"])
    res["discrepancy"] = discrepancy_by_book(test["exact"])
    log("lag")
    res["lag"] = lag_table(c, seasons)
    res["calibration"] = calibration(test["exact"])
    res["price_band"] = by_price_band(test["exact"])
    log("bug-first checks")
    res["checks"] = bug_checks(res, c10, g, seasons)
    res["seasons"] = seasons
    return res


def _pinnacle_coverage(c):
    games_q = c.groupby(["market", "bucket"])["game_id"].nunique()
    games_p = c[c["book"] == PINNACLE].groupby(["market", "bucket"])["game_id"].nunique()
    return pd.DataFrame({"games": games_q, "with_pinnacle": games_p}).fillna(0).astype(int).reset_index()


def _by_season(bets, threshold=MAIN_THRESHOLD):
    rows = []
    b = bets[bets["edge"] >= threshold]
    for (mkt, season), x in b.groupby(["market", "season"]):
        rows.append({"market": mkt, "season": season, **cell(x)})
    return pd.DataFrame(rows)


def bug_checks(res: dict, c10: pd.DataFrame, games: pd.DataFrame, seasons) -> dict:
    """The pre-registered checks, for every book with positive realised ROI in a primary cell."""
    pooled = res["pooled"]["exact"]
    prim = pooled[pooled["threshold"] == MAIN_THRESHOLD]
    pos = prim[prim["roi"] > 0][["market", "book"]].itertuples(index=False)
    pos = [tuple(x) for x in pos]
    exact = res["paired"]["exact"]
    t = exact[exact["season"].isin(seasons) & (exact["edge"] >= MAIN_THRESHOLD)]
    p10 = settle_frame(pair(c10, "exact"), games)
    p10 = p10[p10["season"].isin(seasons) & (p10["edge"] >= MAIN_THRESHOLD)]
    conv = res["pooled"]["converted"]
    conv = conv[conv["threshold"] == MAIN_THRESHOLD].set_index(["market", "book"])
    rows = []
    for mkt, book in pos:
        b = t[(t["market"] == mkt) & (t["book"] == book)]
        s = b[b["win"].notna()]
        b10 = p10[(p10["market"] == mkt) & (p10["book"] == book)]
        s10 = b10[b10["win"].notna()]
        r10 = cell(b10, clv=False)
        dup = int(b.duplicated(["game_id", "market", "bucket", "book"]).sum())
        rows.append({
            "market": mkt, "book": book, "bets": len(s), "roi": s["profit"].mean(),
            "lag_median_min": b["lag_min"].median(), "lag_p90_min": b["lag_min"].quantile(0.9),
            "bets_10min_rule": len(s10), "roi_10min_rule": r10["roi"], "roi_10min_lo": r10["roi_lo"],
            "roi_10min_hi": r10["roi_hi"],
            "roi_converted": conv.loc[(mkt, book), "roi"] if (mkt, book) in conv.index else np.nan,
            "bets_converted": conv.loc[(mkt, book), "bets"] if (mkt, book) in conv.index else np.nan,
            "exact_line_mismatches": int((b["line_diff"].fillna(0) != 0).sum()),
            "cover": s["win"].mean(), "baseline_p_fair": s["p_fair"].mean(),
            "duplicate_bets": dup,
            "min_lead_min": b["lead_min"].min(),
            "max_last_update_minus_tip_min": ((b["polled_utc"] - b["commence_utc"]).dt.total_seconds() / 60
                                              - b["lag_min"]).max(),
            "max_poll_minus_tip_min": ((b["polled_utc"] - b["commence_utc"]).dt.total_seconds() / 60).max(),
            "pinnacle_poll_equals_book_poll": bool((b["pin_polled_utc"] == b["polled_utc"]).all()),
        })
    out = {"positive": pd.DataFrame(rows)}
    lead = exact[exact["season"].isin(seasons)].groupby("bucket")["lead_min"].agg(["min", "median", "max"])
    out["lead_by_bucket"] = lead.reindex([b for b in ORDER if b in lead.index])
    return out


# ---------------------------------------------------------------- report

LABELS = {"opening": "opening", "noon": "noon", "afternoon": "afternoon", "early_evening": "early evening",
          "late_evening": "late evening", "near_close": "near close", "true_close": "true close"}


def _pct(x, d=1):
    return "" if pd.isna(x) else f"{100 * x:.{d}f}%"


def _spct(x, d=1):
    return "" if pd.isna(x) else f"{100 * x:+.{d}f}%"


def _num(x, d=2, sign=True):
    return "" if pd.isna(x) else (f"{x:+.{d}f}" if sign else f"{x:.{d}f}")


def _ci(lo, hi, f):
    return "" if pd.isna(lo) else f"{f(lo)} to {f(hi)}"


def _book(b):
    return f"{b} (exchange, gross)" if b in EXCHANGES else b


def _table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def _cell_cols(r):
    return [f"{r['bets']:,}", _spct(r["mean_edge"]), _spct(r["roi"]), _ci(r["roi_lo"], r["roi_hi"], _spct),
            f"{_pct(r['cover'])} ({_pct(r['cover_lo'])}–{_pct(r['cover_hi'])})", _pct(r["baseline"]),
            _num(r["clv_cents"]) + ("¢" if pd.notna(r["clv_cents"]) else ""),
            _ci(r["clv_lo"], r["clv_hi"], lambda v: f"{v:+.2f}¢"), _num(r["line_move"]), _spct(r["edge_at_close"])]


CELL_HEAD = ["bets", "mean paper edge", "realised ROI", "ROI 95% CI", "cover (95% Wilson)", "baseline (mean p_fair)",
             "CLV", "CLV 95% CI", "line move, pts", "edge at close"]


def book_anchor_table(ba: pd.DataFrame, mkt: str, top: int | None = None, min_bets: int = 0) -> str:
    if ba.empty:
        return "No bets."
    x = ba[(ba["market"] == mkt) & (ba["bets"] >= min_bets)]
    if top:
        x = x.head(top)
    rows = [[_book(r["book"]), LABELS[r["bucket"]]] + _cell_cols(r) for _, r in x.iterrows()]
    return _table(["book", "anchor"] + CELL_HEAD, rows)


def pooled_table(pooled: pd.DataFrame, mkt: str, threshold: float = MAIN_THRESHOLD, top: int | None = None) -> str:
    if pooled.empty:
        return "No bets."
    x = pooled[(pooled["market"] == mkt) & (pooled["threshold"] == threshold)].sort_values("bets", ascending=False)
    if top:
        x = x.head(top)
    rows = [[_book(r["book"])] + _cell_cols(r) + [_spct(r["bonf_lo"]), "yes" if r["clears_bar"] else "no"]
            for _, r in x.iterrows()]
    return _table(["book"] + CELL_HEAD + ["Bonferroni ROI lower bound", "clears bar"], rows)


def report_markdown(res: dict) -> str:
    L = []
    w = L.append
    seasons = ", ".join(res["seasons"])
    w("# Experiment 3 report: soft books against Pinnacle at the same poll\n")
    w("Generated by `python -m nbatotals backtest-books --legacy` (maintainer only: needs the private "
      "multi-region payloads and legacy DB). Rules: [PREREGISTRATION.md](PREREGISTRATION.md). "
      f"Test seasons: {seasons}. Exact-line pairing unless a table says converted. Threshold 2% unless stated. "
      "ROI and CLV intervals: 95% bootstrap over games, 10,000 resamples, fixed seed. Cover: 95% Wilson. "
      "CLV = Pinnacle's devigged true-close probability of the bet side at the bet's line minus p_fair at bet time. "
      "Line move = Pinnacle's true-close line relative to the bet's line, positive favouring the bet. "
      "Edge at close = p_close × price − 1. Exchanges are gross of commission.\n")

    w("## Quote hygiene\n")
    w(f"Input quote rows (all markets, buckets, books, seasons read): {res['input_rows']:,}; "
      f"rows on games outside the scored set (not final, or postseason): {res['rows_not_scored_game']:,}; "
      f"kept after the pre-registered checks: {res['kept_rows']:,}.\n")
    d = res["drops"]
    if len(d):
        pv = d.pivot_table(index="reason", columns="market", values="n", aggfunc="sum", fill_value=0)
        pv["all"] = pv.sum(axis=1)
        w(_table(["reason"] + list(pv.columns), [[i] + [f"{v:,}" for v in r] for i, r in pv.iterrows()]))
        w("")
        st = d[d["reason"].str.startswith("stale")].groupby("book")["n"].sum().sort_values(ascending=False)
        w("Stale quotes dropped, by book (all markets; top 15):\n")
        w(_table(["book", "stale rows dropped"], [[b, f"{n:,}"] for b, n in st.head(15).items()]))
        w("")
    pc = res["pinnacle_coverage"]
    pc = pc[pc["bucket"].isin(ORDER)].copy()
    pc["order"] = pc["bucket"].map({b: i for i, b in enumerate(ORDER)})
    pc = pc.sort_values(["market", "order"])
    w("Games with a surviving Pinnacle quote (all seasons read):\n")
    w(_table(["market", "bucket", "games with any quote", "with Pinnacle"],
             [[r.market, LABELS[r.bucket], f"{r.games:,}", f"{r.with_pinnacle:,}"] for r in pc.itertuples()]))
    w("")

    pac = res.get("polled_after_close")
    if pac is not None and len(pac):
        w("Compared soft-book quotes (exact lines) at a betting bucket polled at or after the same game's Pinnacle "
          "true-close poll: these keep their ROI but get no CLV.\n")
        w(_table(["season", "bucket", "quotes"], [[r.season, LABELS[r.bucket], f"{r.quotes:,}"] for r in pac.itertuples()]))
        w("")

    w("## Evidence bar (2%, six buckets pooled, test seasons)\n")
    for mode in ("exact", "converted"):
        p = res["pooled"][mode]
        p2 = p[p["threshold"] == MAIN_THRESHOLD]
        clear = p2[p2["clears_bar"]]
        w(f"**{mode} lines:** {len(p2)} (book, market) cells; {len(clear)} clear the pre-registered bar; "
          f"{int(p2['clears_bonferroni'].sum())} also clear the Bonferroni bound.")
        for r in clear.itertuples():
            w(f"- {r.market} / {_book(r.book)}: {r.bets:,} bets, ROI {_spct(r.roi)} "
              f"({_spct(r.roi_lo)} to {_spct(r.roi_hi)}), CLV {r.clv_cents:+.2f}¢, Bonferroni lower {_spct(r.bonf_lo)}")
        w("")

    for mkt in MARKETS:
        w(f"## {mkt}: per book, six buckets pooled, 2% (exact lines)\n")
        w(pooled_table(res["pooled"]["exact"], mkt))
        w("")
        w(f"### {mkt}: same, converted lines (within 0.5 points, normal approximation)\n")
        w(pooled_table(res["pooled"]["converted"], mkt))
        w("")
        w(f"### {mkt}: realised ROI at every threshold (exact lines, buckets pooled)\n")
        p = res["pooled"]["exact"]
        p = p[p["market"] == mkt]
        books = p[p["threshold"] == min(THRESHOLDS)].sort_values("bets", ascending=False)["book"]
        rows = []
        for b in books:
            r = [_book(b)]
            for t in THRESHOLDS:
                x = p[(p["book"] == b) & (p["threshold"] == t)]
                if len(x):
                    x = x.iloc[0]
                    r.append(f"{x['bets']:,}: {_spct(x['roi'])} ({_ci(x['roi_lo'], x['roi_hi'], _spct)})")
                else:
                    r.append("")
            rows.append(r)
        w(_table(["book"] + [f"edge ≥ {t:.0%}: bets, ROI (CI)" for t in THRESHOLDS], rows))
        w("")
        w(f"### {mkt}: per book and anchor, 2% (exact lines), sorted by bets\n")
        w(book_anchor_table(res["book_anchor"], mkt))
        w("")

    w("## Overall picture by anchor (all soft books pooled, exact lines)\n")
    for key, title in (("by_anchor", "exact lines"), ("by_anchor_converted", "converted lines")):
        ba = res[key]
        rows = [[r["market"], LABELS[r["bucket"]], f"{r['quotes']:,}", f"{r['books_per_game']:.1f}",
                 f"{r['mean_abs_disagree_cents']:.2f}¢", _pct(r["share_edge_ge"]), f"{r['bets_per_game']:.2f}"]
                + _cell_cols(r) for _, r in ba.iterrows()]
        w(f"**{title}**\n")
        w(_table(["market", "anchor", "soft quotes compared", "books per game", "mean |disagreement|",
                  "share of quotes with edge ≥ 2%", "2% bets per game"] + CELL_HEAD, rows))
        w("")

    w("## By season (all soft books pooled, 2%, exact lines)\n")
    rows = [[r["market"], r["season"]] + _cell_cols(r) for _, r in res["by_season"].iterrows()]
    w(_table(["market", "season"] + CELL_HEAD, rows))
    w("")

    w("## Where each soft book's prices sit against Pinnacle (descriptive, exact lines, all buckets)\n")
    w("hold = the book's own overround; disagreement = book's devigged probability of the home/over side minus "
      "Pinnacle's; best gap = larger of p_fair − 1/price over the two sides.\n")
    rows = [[r.market, _book(r.book), f"{r.quotes:,}", f"{r.hold_pct:.2f}%", f"{r.mean_disagree_cents:+.2f}¢",
             f"{r.mean_abs_disagree_cents:.2f}¢", f"{r.mean_best_gap_cents:+.2f}¢", _pct(r.share_edge_ge_2)]
            for r in res["discrepancy"].itertuples()]
    w(_table(["market", "book", "quotes", "hold", "mean disagreement", "mean |disagreement|", "mean best gap",
              "share with edge ≥ 2%"], rows))
    w("")

    w("## Lag: Pinnacle's previous move against each book's next move\n")
    w("corr_next = correlation between Pinnacle's move over b−1 → b and the book's move over b → b+1, pooled over "
      "the five bucket triples and test-season games (95% Fisher interval). Moves are line points (totals, spreads) "
      "or devigged home probability in cents (h2h). The Pinnacle row is Pinnacle's own correlation between "
      "consecutive moves; a book lags if its corr_next clearly exceeds that row. corr_same = correlation of the "
      "book's and Pinnacle's moves over the same b → b+1.\n")
    for mkt in MARKETS:
        lt = res["lag"][res["lag"]["market"] == mkt]
        lt = pd.concat([lt[lt["book"].str.startswith("pinnacle")],
                        lt[~lt["book"].str.startswith("pinnacle")].sort_values("corr_next", ascending=False)])
        rows = [[_book(r.book), f"{r.pairs:,}", _num(r.corr_next, 3), _ci(r.lo, r.hi, lambda v: f"{v:+.3f}"),
                 _pct(r.share_book_moved), _num(r.corr_same_period, 3)] for r in lt.itertuples()]
        w(f"**{mkt}**\n")
        w(_table(["book", "pairs", "corr_next", "95% CI", "share of next moves non-zero", "corr_same"], rows))
        w("")

    w("## By price taken (descriptive, added after the first run; not pre-registered)\n")
    w("All soft books, 2%, exact lines, buckets pooled. Decimal price of the side bet.\n")
    rows = [[r["market"], r["band"]] + _cell_cols(r) for _, r in res["price_band"].iterrows()]
    w(_table(["market", "decimal price"] + CELL_HEAD, rows))
    w("")

    w("## Sign check: Pinnacle's fair probability against outcomes\n")
    w("Exact-line quotes, one per game and bucket, test seasons. Side a is Over (totals) or home (spreads, h2h). "
      "If p_fair were attached to the wrong side, the win rate would run opposite to p_fair.\n")
    rows = [[r.market, f"{r.n:,}", _pct(r.mean_p_fair_a), _pct(r.win_rate_a), f"{r.n_p_ge_half:,}",
             _pct(r.p_fair_a_when_ge_half), _pct(r.win_a_when_ge_half), f"{r.n_p_lt_half:,}",
             _pct(r.p_fair_a_when_lt_half), _pct(r.win_a_when_lt_half)] for r in res["calibration"].itertuples()]
    w(_table(["market", "n", "mean p_fair(a)", "side a won", "n p ≥ ½", "p_fair", "won", "n p < ½", "p_fair", "won"],
             rows))
    w("")

    w("## Bug-first checks on every book with positive realised ROI (2%, pooled, exact)\n")
    ck = res["checks"]["positive"]
    if len(ck):
        rows = [[r.market, _book(r.book), f"{r.bets:,}", _spct(r.roi), f"{r.lag_median_min:.1f} / {r.lag_p90_min:.1f}",
                 f"{r.bets_10min_rule:,}: {_spct(r.roi_10min_rule)} ({_ci(r.roi_10min_lo, r.roi_10min_hi, _spct)})",
                 f"{int(r.bets_converted) if pd.notna(r.bets_converted) else ''}: {_spct(r.roi_converted)}",
                 f"{r.exact_line_mismatches}", f"{_pct(r.cover)} vs {_pct(r.baseline_p_fair)}",
                 f"{r.duplicate_bets}", f"{r.min_lead_min:.0f}", f"{r.max_last_update_minus_tip_min:.0f}",
                 f"{r.max_poll_minus_tip_min:.0f}", "yes" if r.pinnacle_poll_equals_book_poll else "no"]
                for r in ck.itertuples()]
        w(_table(["market", "book", "bets", "ROI", "quote age at poll, median / p90 (min)",
                  "10-minute staleness rule: bets, ROI (CI)", "converted: bets, ROI", "line mismatches",
                  "cover vs mean p_fair", "duplicate bets", "min lead (min)", "max last_update − tip (min)",
                  "max poll − tip (min)", "Pinnacle quote from the same poll"], rows))
    else:
        w("No book had positive realised ROI.")
    w("")
    lb = res["checks"]["lead_by_bucket"]
    w("Minutes from poll to tip of every compared quote, by bucket (test seasons):\n")
    w(_table(["bucket", "min", "median", "max"],
             [[LABELS[b], f"{r['min']:.0f}", f"{r['median']:.0f}", f"{r['max']:.0f}"] for b, r in lb.iterrows()]))
    w("")

    w("## 2021-22 (descriptive only; incomplete season)\n")
    for mkt in MARKETS:
        w(f"**{mkt}**\n")
        w(pooled_table(res["pooled_desc"], mkt, top=10))
        w("")
    return "\n".join(L)
