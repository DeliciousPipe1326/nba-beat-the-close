"""Experiment 4: retail player-prop prices against Pinnacle's devigged fair value.

Every rule here is fixed in docs/experiments/props_market/PREREGISTRATION.md:

- two capture windows per event, from the payload's own timestamp:
  T−3h (lead 120–240 min) and close (lead above 0, at most 30 min);
- quotes updated after tip dropped; duplicate prices for one player, line and
  side at one book in one file dropped; the same book seen in several region
  files deduplicated on (book, event, market, player, line, side, window);
- fair value = Pinnacle's two-sided quote at the same player, line, market and
  window, devigged multiplicatively as in `market.py`; different lines are
  never converted;
- edge = p_fair × decimal price − 1, flat stakes, thresholds 2/3/5/8%;
- settled on the box score: DNP void, pushes excluded;
- CLV = Pinnacle's close probability of the bet side at the same line minus
  the T−3h p_fair.

The input frames are plain: quotes from `adapters/legacy_props.read_files`,
games from `legacy_nba_db.read_games`, player box rows from
`legacy_props.read_player_box`; tests build them synthetically.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from nbatotals import boxscore
from nbatotals.evaluate import metrics
from nbatotals.teams import FULL_NAME_TO_ALIAS

WINDOWS = {"t-3h": (120.0, 240.0), "close": (0.0, 30.0)}  # lead in minutes, (lo, hi]; close excludes lead 0
WINDOW_LABELS = {"t-3h": "T−3h", "close": "close (~T−9 min)"}
REGION_ORDER = ("us", "us_ex", "au", "eu", "uk")
FAIR_BOOK = "pinnacle"
STALE_MINUTES = 60
PAIR_MAX_MINUTES = 10
THRESHOLDS = (0.02, 0.03, 0.05, 0.08)
DESCRIPTIVE_THRESHOLD = 0.0  # every side with edge > 0; descriptive only
MIN_BETS = 500
TEST_SEASON = 2024
LAST_REGULAR_DAY = "2025-04-13"
STAT = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists"}
MARKET_LABELS = {"all": "all three", "player_points": "points", "player_rebounds": "rebounds",
                 "player_assists": "assists"}
_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv)$")


def normalise_name(name) -> str:
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace(".", "").replace("'", "").replace("’", "").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return _SUFFIX.sub("", s).strip()


def devig_over(over_price, under_price):
    """Multiplicative devig, exactly as market.consensus: (1/o) / (1/o + 1/u)."""
    inv_o, inv_u = 1.0 / np.asarray(over_price, float), 1.0 / np.asarray(under_price, float)
    return inv_o / (inv_o + inv_u)


def edge(p_fair, price):
    return np.asarray(p_fair, float) * np.asarray(price, float) - 1.0


# ---------------------------------------------------------------- preparation

def prepare(raw: pd.DataFrame, games: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Windowed, cleaned, deduplicated quotes joined to games. Returns quotes and counts."""
    c: dict = {}
    r = raw.copy()
    commence = pd.to_datetime(r["commence_utc"], utc=True)
    captured = pd.to_datetime(r["captured_utc"], utc=True)
    r["lead_min"] = (commence - captured).dt.total_seconds() / 60.0
    r["window"] = None
    for w, (lo, hi) in WINDOWS.items():
        r.loc[(r["lead_min"] > lo) & (r["lead_min"] <= hi), "window"] = w
    files = r.drop_duplicates("file")
    c["files_with_quotes"] = len(files)
    c["files_at_or_after_tip"] = int((files["lead_min"] <= 0).sum())
    c["files_outside_both_windows_before_tip"] = int(((files["lead_min"] > 0) & files["window"].isna()).sum())
    for w in WINDOWS:
        lead = files.loc[files["window"] == w, "lead_min"]
        c[f"lead_minutes_{w}"] = {"files": len(lead), "median": float(lead.median()) if len(lead) else np.nan,
                                  "min": float(lead.min()) if len(lead) else np.nan,
                                  "max": float(lead.max()) if len(lead) else np.nan}
    r = r[r["window"].notna()]
    # one file per region, event, market and window: the latest
    f = r.drop_duplicates("file")[["file", "region", "event_id", "market", "window", "captured_utc"]]
    f = f.sort_values("captured_utc")
    keep = f.drop_duplicates(["region", "event_id", "market", "window"], keep="last")["file"]
    c["files_superseded_in_window"] = int(len(f) - len(keep))
    r = r[r["file"].isin(set(keep))]
    c["files_used"] = int(r["file"].nunique())

    late = pd.to_datetime(r["last_update"], utc=True) > pd.to_datetime(r["commence_utc"], utc=True)
    c["outcomes_last_update_after_tip"] = int(late.sum())
    r = r[~late]
    r["price"] = r["american"].map(boxscore.american_to_decimal).astype(float)
    bad = r["price"].isna() | r["line"].isna() | r["player"].isna() | ~r["side"].isin(["over", "under"])
    c["outcomes_invalid"] = int(bad.sum())
    r = r[~bad].copy()
    r["line"] = r["line"].astype(float)
    age = (pd.to_datetime(r["captured_utc"], utc=True) - pd.to_datetime(r["last_update"], utc=True))
    r["stale"] = age.dt.total_seconds() / 60.0 > STALE_MINUTES

    key = ["file", "book", "player", "line", "side"]
    n_dup = r.groupby(key)["price"].transform("size")
    c["outcomes_duplicate_in_file"] = int((n_dup > 1).sum())
    c["player_lines_dropped_duplicate_in_file"] = int(
        r[n_dup > 1].drop_duplicates(["file", "book", "player", "line"]).shape[0])
    dup_pl = r[n_dup > 1][["file", "book", "player", "line"]].drop_duplicates()
    r = r.merge(dup_pl.assign(_dup=True), on=["file", "book", "player", "line"], how="left")
    r = r[r["_dup"].isna()].drop(columns="_dup")

    order = {g: i for i, g in enumerate(REGION_ORDER)}
    r = r.assign(_ro=r["region"].map(order)).sort_values(["_ro", "file"], kind="stable")
    xkey = ["book", "event_id", "market", "player", "line", "side", "window"]
    first_price = r.groupby(xkey)["price"].transform("first")
    dup = r.duplicated(xkey, keep="first")
    c["cross_region_duplicates_dropped"] = int(dup.sum())
    c["cross_region_duplicates_price_differs"] = int((dup & (r["price"] != first_price)).sum())
    c["cross_region_duplicates_same_last_update"] = int(r.duplicated(xkey + ["last_update"], keep="first").sum())
    c["cross_region_duplicates_by_book"] = r[dup].groupby("book").size().to_dict()
    r = r[~dup].drop(columns="_ro")

    # game join: US Eastern tip date and team names
    tip = pd.to_datetime(r["commence_utc"], utc=True)
    r["tip_date"] = tip.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    r["home"] = r["home_name"].map(FULL_NAME_TO_ALIAS)
    r["away"] = r["away_name"].map(FULL_NAME_TO_ALIAS)
    g = games[["id", "game_date", "home", "away", "season", "postseason"]].rename(columns={"id": "game_id"})
    r = r.merge(g, left_on=["tip_date", "home", "away"], right_on=["game_date", "home", "away"], how="left")
    ev = r.drop_duplicates("event_id")
    c["events"] = int(len(ev))
    c["events_matched_to_a_game"] = int(ev["game_id"].notna().sum())
    c["events_unmatched"] = sorted(ev.loc[ev["game_id"].isna(), "tip_date"].unique().tolist())
    r["split"] = "other"
    r.loc[r["tip_date"] >= "2025-07-01", "split"] = "2025-26"
    test = (r["season"] == TEST_SEASON) & (r["postseason"] == 0) & (r["tip_date"] <= LAST_REGULAR_DAY)
    r.loc[test, "split"] = "test"
    c["events_by_split"] = r.drop_duplicates("event_id")["split"].value_counts().to_dict()
    return r.reset_index(drop=True), c


def match_players(quotes: pd.DataFrame, box: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Attach the box-score row for each quote's player: exact normalised name within that game only."""
    b = box.copy()
    b["norm"] = b["name"].map(normalise_name)
    n_in_game = b.groupby(["game_id", "norm"])["player_id"].transform("nunique")
    uniq = b[n_in_game == 1].drop_duplicates(["game_id", "norm"])
    ambiguous = b[n_in_game > 1][["game_id", "norm"]].drop_duplicates()
    q = quotes.copy()
    q["norm"] = q["player"].map(normalise_name)
    cols = ["game_id", "norm", "player_id", "name", "minutes", "is_dnp", "points", "rebounds", "assists"]
    q = q.merge(uniq[cols], on=["game_id", "norm"], how="left")
    ep = q[q["game_id"].notna()].drop_duplicates(["event_id", "player"])
    amb = ep.merge(ambiguous, on=["game_id", "norm"]).shape[0]
    c = {
        "event_players": int(len(ep)),
        "event_players_matched": int(ep["player_id"].notna().sum()),
        "event_players_ambiguous": int(amb),
        "quotes_with_game": int(q["game_id"].notna().sum()),
        "quotes_matched": int(q["player_id"].notna().sum()),
        "exact_name_equal_share_of_matched": float((ep.loc[ep["player_id"].notna(), "player"]
                                                    == ep.loc[ep["player_id"].notna(), "name"]).mean())
        if ep["player_id"].notna().any() else np.nan,
        "unmatched_names": ep.loc[ep["player_id"].isna(), "player"].value_counts().head(25).to_dict(),
    }
    return q, c


# ---------------------------------------------------------------- fair value and pairs

def pinnacle_fair(quotes: pd.DataFrame) -> pd.DataFrame:
    """Pinnacle two-sided quotes per (event, market, window, player, line) with devigged p_over."""
    p = quotes[quotes["book"] == FAIR_BOOK]
    k = ["event_id", "market", "window", "player", "line"]
    w = p.pivot_table(index=k, columns="side", values="price", aggfunc="first")
    meta = p.groupby(k).agg(pin_captured=("captured_utc", "max"), pin_stale=("stale", "any")).reset_index()
    w = w.reset_index().merge(meta, on=k)
    w = w[w.get("over").notna() & w.get("under").notna()].rename(columns={"over": "pin_over", "under": "pin_under"})
    w["p_over_fair"] = devig_over(w["pin_over"], w["pin_under"])
    w.columns.name = None
    return w.reset_index(drop=True)


def pair_with_fair(quotes: pd.DataFrame, fair: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Retail sides at exactly Pinnacle's line, with p_fair and edge."""
    k = ["event_id", "market", "window", "player", "line"]
    retail = quotes[quotes["book"] != FAIR_BOOK]
    m = retail.merge(fair, on=k, how="left")
    pin_players = fair[["event_id", "market", "window", "player"]].drop_duplicates().assign(_pin_player=True)
    m = m.merge(pin_players, on=["event_id", "market", "window", "player"], how="left")
    pin_files = fair[["event_id", "market", "window"]].drop_duplicates().assign(_pin_file=True)
    m = m.merge(pin_files, on=["event_id", "market", "window"], how="left")
    same = m["p_over_fair"].notna()
    c = {
        "retail_sides": int(len(m)),
        "retail_sides_no_pinnacle_quote_for_event_market_window": int(m["_pin_file"].isna().sum()),
        "retail_sides_pinnacle_lacks_player": int((m["_pin_file"].notna() & m["_pin_player"].isna()).sum()),
        "retail_sides_pinnacle_other_line": int((m["_pin_player"].notna() & ~same).sum()),
        "retail_sides_same_line": int(same.sum()),
    }
    m = m[same].drop(columns=["_pin_player", "_pin_file"]).copy()
    m["pin_stale"] = m["pin_stale"].astype(bool)
    gap = (pd.to_datetime(m["captured_utc"], utc=True) - pd.to_datetime(m["pin_captured"], utc=True)).abs()
    far = gap.dt.total_seconds() / 60.0 > PAIR_MAX_MINUTES
    c["same_line_sides_dropped_capture_gap"] = int(far.sum())
    m = m[~far].copy()
    m["p_fair"] = np.where(m["side"] == "over", m["p_over_fair"], 1.0 - m["p_over_fair"])
    m["edge"] = edge(m["p_fair"], m["price"])
    c["same_line_sides_used"] = int(len(m))
    return m.reset_index(drop=True), c


def add_clv(pairs: pd.DataFrame, fair: pd.DataFrame) -> pd.DataFrame:
    """CLV for T−3h rows: Pinnacle close probability of the side at the same line minus p_fair."""
    out = pairs.copy()
    close = fair[fair["window"] == "close"]
    same = close[["event_id", "market", "player", "line", "p_over_fair"]].rename(columns={"p_over_fair": "_pc"})
    out = out.merge(same, on=["event_id", "market", "player", "line"], how="left")
    lines = close.groupby(["event_id", "market", "player"])["line"].agg(["min", "max", "size"]).reset_index()
    lines = lines.rename(columns={"min": "_cl_min", "max": "_cl_max", "size": "_cl_n"})
    out = out.merge(lines, on=["event_id", "market", "player"], how="left")
    early = out["window"] == "t-3h"
    p_close = np.where(out["side"] == "over", out["_pc"], 1.0 - out["_pc"])
    out["clv"] = np.where(early & out["_pc"].notna(), p_close - out["p_fair"], np.nan)
    moved = early & out["_pc"].isna() & (out["_cl_n"] == 1)
    out["close_line"] = np.where(moved, out["_cl_min"], np.nan)
    out["line_moved_toward"] = np.where(
        moved, np.where(out["side"] == "over", out["_cl_min"] > out["line"], out["_cl_min"] < out["line"]), np.nan)
    out["clv_status"] = np.select(
        [~early, out["_pc"].notna(), moved, early & out["_cl_n"].isna()],
        ["n/a (close bet)", "same line", "line moved", "no Pinnacle close"], "several close lines")
    return out.drop(columns=["_pc", "_cl_min", "_cl_max", "_cl_n"])


def settle(df: pd.DataFrame) -> pd.DataFrame:
    """result in {win, loss, push, void, unmatched}; profit per 1-unit stake (NaN unless win/loss)."""
    out = df.copy()
    stat = pd.Series(np.nan, index=out.index)
    for mkt, col in STAT.items():
        sel = out["market"] == mkt
        stat[sel] = out.loc[sel, col]
    out["stat"] = stat
    dnp = (out["minutes"].fillna(-1) == 0) | (out["is_dnp"].fillna(0).astype(bool))
    over = out["side"] == "over"
    win = np.where(over, out["stat"] > out["line"], out["stat"] < out["line"])
    out["result"] = np.select(
        [out["player_id"].isna(), dnp, out["stat"] == out["line"], win],
        ["unmatched", "void", "push", "win"], "loss")
    out["profit"] = np.select([out["result"] == "win", out["result"] == "loss"], [out["price"] - 1.0, -1.0], np.nan)
    return out


# ---------------------------------------------------------------- statistics

def cluster_ratio_ci(num, den, clusters, n_boot: int = metrics.N_BOOT, seed: int = metrics.SEED):
    """95% bootstrap interval for sum(num)/sum(den), resampling clusters (events) with replacement."""
    df = pd.DataFrame({"n": np.asarray(num, float), "d": np.asarray(den, float), "c": np.asarray(clusters)})
    if len(df) == 0:
        return (np.nan, np.nan)
    g = df.groupby("c")[["n", "d"]].sum()
    gn, gd = g["n"].to_numpy(), g["d"].to_numpy()
    k = len(gn)
    rng = np.random.default_rng(seed)
    est = np.empty(n_boot)
    chunk = max(1, min(n_boot, 2_000_000 // max(k, 1)))
    for start in range(0, n_boot, chunk):
        stop = min(n_boot, start + chunk)
        idx = rng.integers(0, k, size=(stop - start, k))
        est[start:stop] = gn[idx].sum(axis=1) / gd[idx].sum(axis=1)
    return (float(np.quantile(est, 0.025)), float(np.quantile(est, 0.975)))


def summarise(bets: pd.DataFrame) -> dict:
    s = bets[bets["result"].isin(["win", "loss"])]
    n = len(s)
    wins = int((s["result"] == "win").sum())
    row = {"n": n, "wins": wins, "voids": int((bets["result"] == "void").sum()),
           "pushes": int((bets["result"] == "push").sum()),
           "mean_edge": float(s["edge"].mean()) if n else np.nan,
           "p_fair_mean": float(s["p_fair"].mean()) if n else np.nan,
           "roi": float(s["profit"].mean()) if n else np.nan}
    row["roi_lo"], row["roi_hi"] = cluster_ratio_ci(s["profit"], np.ones(n), s["event_id"]) if n else (np.nan, np.nan)
    row["hit"] = wins / n if n else np.nan
    row["hit_lo"], row["hit_hi"] = metrics.wilson(wins, n)
    if "clv" in s:
        cl = s[s["clv"].notna()]
        row["clv_n"] = len(cl)
        row["clv"] = float(cl["clv"].mean()) if len(cl) else np.nan
        row["clv_lo"], row["clv_hi"] = (cluster_ratio_ci(cl["clv"], np.ones(len(cl)), cl["event_id"])
                                        if len(cl) else (np.nan, np.nan))
        mv = s[s["clv_status"] == "line moved"]
        row["line_moved_n"] = len(mv)
        row["line_moved_toward"] = float(mv["line_moved_toward"].astype(float).mean()) if len(mv) else np.nan
    return row


def meets_bar(row: dict) -> bool:
    return bool(row["n"] >= MIN_BETS and row["roi_lo"] > 0 and row.get("clv_lo", np.nan) > 0)


def cell_table(bets: pd.DataFrame, threshold: float, market: str = "all", side: str = "both",
               strict: bool = False) -> pd.DataFrame:
    """One row per (region, book) and per region pooled ('all books'), per window."""
    b = bets
    if market != "all":
        b = b[b["market"] == market]
    if side != "both":
        b = b[b["side"] == side]
    b = b[b["edge"] > threshold] if strict else b[b["edge"] >= threshold]
    rows = []
    for (region, window), x in b.groupby(["region", "window"]):
        for book, y in [("all books", x)] + list(x.groupby("book")):
            rows.append({"region": region, "book": book, "window": window} | summarise(y))
    out = pd.DataFrame(rows)
    if len(out):
        out = out.sort_values(["n", "region", "book", "window"], ascending=[False, True, True, True], kind="stable")
    return out.reset_index(drop=True)


def bar_cells(bets: pd.DataFrame) -> pd.DataFrame:
    """Every pre-registered cell: (region pooled, or book) × window × threshold, markets and sides pooled."""
    rows = []
    for t in THRESHOLDS:
        tab = cell_table(bets, t)
        if len(tab):
            tab.insert(0, "threshold", t)
            rows.append(tab)
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if len(out):
        out["meets_bar"] = [meets_bar(r) for r in out.to_dict("records")]
    return out


def distance_table(quotes: pd.DataFrame, fair: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """How far each retail book sits from Pinnacle, per window."""
    rows = []
    retail = quotes[quotes["book"] != FAIR_BOOK]
    pin_pl = fair[["event_id", "market", "window", "player", "line"]]
    for (region, book, window), x in retail.groupby(["region", "book", "window"]):
        bl = x[["event_id", "market", "window", "player", "line"]].drop_duplicates()
        pw = pin_pl[pin_pl["window"] == window]
        both = pw.merge(bl[["event_id", "market", "player"]].drop_duplicates(), on=["event_id", "market", "player"])
        both = both.merge(bl.rename(columns={"line": "book_line"}), on=["event_id", "market", "window", "player"])
        both["diff"] = (both["book_line"] - both["line"]).abs()
        nearest = both.groupby(["event_id", "market", "player", "line"])["diff"].min()
        p = pairs[(pairs["book"] == book) & (pairs["region"] == region) & (pairs["window"] == window)]
        two = p.pivot_table(index=["event_id", "market", "player", "line"], columns="side",
                            values=["price", "p_over_fair"], aggfunc="first")
        row = {"region": region, "book": book, "window": window, "pinnacle_player_lines": len(nearest),
               "same_line_share": float((nearest == 0).mean()) if len(nearest) else np.nan,
               "mean_abs_line_diff_when_different": (float(nearest[nearest > 0].mean()) if (nearest > 0).any()
                                                     else np.nan),
               "same_line_sides": len(p)}
        if len(two) and ("price", "over") in two and ("price", "under") in two:
            t = two.dropna(subset=[("price", "over"), ("price", "under")])
            po, pu = t[("price", "over")], t[("price", "under")]
            pb = devig_over(po, pu)
            pf = t[("p_over_fair", "over")]
            row |= {"two_sided_same_line": len(t), "hold": float((1 / po + 1 / pu - 1).mean()),
                    "mean_p_over_minus_pin": float((pb - pf).mean()),
                    "mean_abs_p_over_minus_pin": float(np.abs(pb - pf).mean())}
        for side in ("over", "under"):
            e = p.loc[p["side"] == side, "edge"]
            row[f"share_edge_2pct_{side}"] = float((e >= 0.02).mean()) if len(e) else np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values(["same_line_sides", "region", "book", "window"], ascending=[False, True, True, True],
                           kind="stable").reset_index(drop=True) if len(out) else out


def edge_share(pairs: pd.DataFrame) -> pd.DataFrame:
    """Share of same-line retail sides with paper edge at or above each threshold, by window and side."""
    rows = []
    for (window, side), x in pairs.groupby(["window", "side"]):
        rows.append({"window": window, "side": side, "sides": len(x)}
                    | {f">= {t:.0%}": float((x["edge"] >= t).mean()) for t in THRESHOLDS})
    for window, x in pairs.groupby("window"):
        rows.append({"window": window, "side": "both", "sides": len(x)}
                    | {f">= {t:.0%}": float((x["edge"] >= t).mean()) for t in THRESHOLDS})
    return pd.DataFrame(rows).sort_values(["window", "side"]).reset_index(drop=True)


def totals_benchmark(tq: pd.DataFrame, games: pd.DataFrame, buckets=("early_evening", "true_close")) -> pd.DataFrame:
    """The same share for game totals: retail sides at Pinnacle's line, 2024-25 regular season."""
    g = games[(games["season"] == TEST_SEASON) & (games["postseason"] == 0) & (games["game_date"] <= LAST_REGULAR_DAY)]
    q = tq[tq["game_id"].isin(set(g["id"])) & tq["anchor"].isin(buckets)]
    pin = q[q["book"] == FAIR_BOOK][["game_id", "anchor", "line", "over_price", "under_price"]]
    pin = pin.assign(p_over_fair=devig_over(pin["over_price"], pin["under_price"]))
    pin = pin[["game_id", "anchor", "line", "p_over_fair"]]
    m = q[q["book"] != FAIR_BOOK].merge(pin, on=["game_id", "anchor", "line"])
    sides = pd.concat([
        pd.DataFrame({"anchor": m["anchor"], "side": "over", "edge": edge(m["p_over_fair"], m["over_price"])}),
        pd.DataFrame({"anchor": m["anchor"], "side": "under", "edge": edge(1 - m["p_over_fair"], m["under_price"])}),
    ])
    def shares(x: pd.DataFrame) -> dict:
        return {f">= {t:.0%}": float((x["edge"] >= t).mean()) for t in THRESHOLDS}

    rows = []
    for (a, s), x in sides.groupby(["anchor", "side"]):
        rows.append({"bucket": a, "side": s, "sides": len(x)} | shares(x))
    for a, x in sides.groupby("anchor"):
        rows.append({"bucket": a, "side": "both", "sides": len(x)} | shares(x))
    return pd.DataFrame(rows).sort_values(["bucket", "side"]).reset_index(drop=True)


def pinnacle_calibration(settled_pin: pd.DataFrame) -> pd.DataFrame:
    """Pinnacle devigged p_over against the over's actual hit rate (pushes and voids excluded), by window."""
    rows = []
    s = settled_pin[settled_pin["result"].isin(["win", "loss"])]
    for window, x in s.groupby("window"):
        bins = x.groupby(pd.cut(x["p_over_fair"], [0, .4, .45, .5, .55, .6, 1]), observed=True)
        for lab, y in [("all", x)] + [(str(b), z) for b, z in bins]:
            w = int((y["result"] == "win").sum())
            lo, hi = metrics.wilson(w, len(y))
            rows.append({"window": window, "p_over bin": lab, "n": len(y),
                         "mean p_over": float(y["p_over_fair"].mean()), "over hit rate": w / len(y),
                         "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def pinnacle_overs(quotes: pd.DataFrame, fair: pd.DataFrame) -> pd.DataFrame:
    """Pinnacle quotes as 'over' bets for calibration: one row per Pinnacle player-line with box data."""
    k = ["event_id", "market", "window", "player", "line"]
    box_cols = ["player_id", "minutes", "is_dnp", "points", "rebounds", "assists", "split"]
    meta = quotes[quotes["book"] == FAIR_BOOK].drop_duplicates(k)[k + box_cols]
    df = fair.merge(meta, on=k)
    df = df.assign(side="over", price=df["pin_over"])
    return settle(df)


def unchanged_to_close(pairs: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Descriptive, added after pre-registration (the last_update rule cannot detect staleness here):
    for T−3h bets, does the same book quote the same line and side at the close, and at an unchanged price?"""
    k = ["book", "event_id", "market", "player", "line", "side"]
    close = quotes[quotes["window"] == "close"][k + ["price"]].drop_duplicates(k)
    close = close.rename(columns={"price": "close_price"})
    rows = []
    for t in THRESHOLDS:
        b = pairs[(pairs["window"] == "t-3h") & (pairs["edge"] >= t) & pairs["result"].isin(["win", "loss"])]
        b = b.merge(close, on=k, how="left")
        for side, x in [("both", b)] + list(b.groupby("side")):
            h = x["close_price"].notna()
            u = h & (x["close_price"] == x["price"])
            rows.append({"threshold": f">= {t:.0%}", "side": side, "bets": len(x),
                         "same line at close": float(h.mean()),
                         "price unchanged (of those)": float(u.sum() / h.sum()) if h.any() else np.nan,
                         "ROI, unchanged": float(x.loc[u, "profit"].mean()) if u.any() else np.nan,
                         "ROI, changed": float(x.loc[h & ~u, "profit"].mean()) if (h & ~u).any() else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- report

def _pct(x, d=1):
    return "" if pd.isna(x) else f"{100 * x:.{d}f}%"


def _ci(lo, hi, d=1):
    return "" if pd.isna(lo) else f"{100 * lo:+.{d}f} to {100 * hi:+.{d}f}"


def _cell_header(thr: bool, clv: bool) -> list[str]:
    head = (("| edge ≥ " if thr else "") + "| region | book | window | n | mean paper edge | realised ROI (95% CI) | "
            "hit rate (95% Wilson) | mean p_fair |")
    sep = ("|---" if thr else "") + "|---|---|---|---|---|---|---|---|"
    if clv:
        head += " CLV, prob. points (95% CI) [n] | Pinnacle line moved towards bet |"
        sep += "---|---|"
    return [head, sep]


def _clv_cells(r: dict) -> str:
    """The two CLV columns: only T−3h bets have a later Pinnacle quote to compare with."""
    if r["window"] == "t-3h" and r.get("clv_n", 0):
        s = f" {100 * r['clv']:+.2f} ({100 * r['clv_lo']:+.2f} to {100 * r['clv_hi']:+.2f}) [{r['clv_n']:,}] |"
    else:
        s = " n/a |"
    return s + (f" {_pct(r['line_moved_toward'], 0)} of {r['line_moved_n']:,} |"
                if r["window"] == "t-3h" and r.get("line_moved_n", 0) else " |")


def _cell_row(r: dict, thr: bool, clv: bool) -> str:
    s = (f"| {r['threshold']:.0%} " if thr else "") + (
        f"| {r['region']} | {r['book']} | {WINDOW_LABELS[r['window']]} | {r['n']:,} | {_pct(r['mean_edge'])} | "
        f"{_pct(r['roi'])} ({_ci(r['roi_lo'], r['roi_hi'])}) | "
        f"{_pct(r['hit'])} ({_pct(r['hit_lo'])}–{_pct(r['hit_hi'])}) | "
        f"{_pct(r['p_fair_mean'])} |")
    return s + _clv_cells(r) if clv else s


def _cell_md(tab: pd.DataFrame, clv: bool = True, max_rows: int | None = None) -> str:
    if not len(tab):
        return "_no bets_\n"
    thr = "threshold" in tab.columns
    t = tab if max_rows is None else tab.head(max_rows)
    lines = _cell_header(thr, clv) + [_cell_row(r, thr, clv) for r in t.to_dict("records")]
    if max_rows is not None and len(tab) > max_rows:
        lines.append(f"\n_{len(tab) - max_rows} smaller rows in the full report._")
    return "\n".join(lines) + "\n"


def _frame_md(df: pd.DataFrame, pct_cols=(), fmt=None) -> str:
    if not len(df):
        return "_none_\n"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.to_dict("records"):
        vals = []
        for col in cols:
            v = r[col]
            if col in pct_cols:
                vals.append(_pct(v))
            elif isinstance(v, float):
                vals.append("" if pd.isna(v) else (fmt.get(col, "{:.3f}") if fmt else "{:.3f}").format(v))
            elif isinstance(v, (int, np.integer)):
                vals.append(f"{v:,}")
            else:
                vals.append(str(WINDOW_LABELS.get(v, v)))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines) + "\n"


def run(raw: pd.DataFrame, read_counts: dict, games: pd.DataFrame, box: pd.DataFrame,
        totals_quotes: pd.DataFrame | None = None, drop_stale: bool = False) -> dict:
    quotes, c_prep = prepare(raw, games)
    quotes, c_match = match_players(quotes, box[box["game_id"].notna()])
    test_q = quotes[quotes["split"] == "test"]
    if drop_stale:
        test_q = test_q[~test_q["stale"]]
    fair = pinnacle_fair(test_q)
    pairs, c_pair = pair_with_fair(test_q, fair)
    if drop_stale:
        pairs = pairs[~pairs["pin_stale"].astype(bool)]
    pairs = settle(add_clv(pairs, fair))
    c_settle = pairs["result"].value_counts().to_dict()
    res = {"counts": {"read": read_counts, "prepare": c_prep, "match": c_match, "pair": c_pair,
                      "settle_same_line_sides": c_settle},
           "pairs": pairs, "fair": fair,
           "distance": distance_table(test_q, fair, pairs),
           "edge_share": edge_share(pairs),
           "bar": bar_cells(pairs),
           "calibration": pinnacle_calibration(pinnacle_overs(test_q, fair))}
    stale = test_q.groupby("book")["stale"].mean().rename("stale_share").reset_index()
    res["stale"] = stale.sort_values("stale_share", ascending=False).reset_index(drop=True)
    res["clv_status"] = pairs[pairs["window"] == "t-3h"]["clv_status"].value_counts().to_dict()
    res["unchanged"] = unchanged_to_close(pairs, test_q)
    age = (pd.to_datetime(test_q["captured_utc"], utc=True) - pd.to_datetime(test_q["last_update"], utc=True))
    res["last_update_age_minutes"] = age.dt.total_seconds().div(60).quantile([0.5, 0.99, 1.0]).round(2).to_dict()
    if totals_quotes is not None:
        res["totals_benchmark"] = totals_benchmark(totals_quotes, games)
    desc = quotes[quotes["split"] == "2025-26"]
    if len(desc):
        f2 = pinnacle_fair(desc)
        p2, c2 = pair_with_fair(desc, f2)
        res["desc_2025"] = {"events": int(desc["event_id"].nunique()), "pair": c2,
                            "edge_share": edge_share(p2) if len(p2) else pd.DataFrame()}
    return res


def _intro(res: dict) -> list[str]:
    status = ", ".join(f"{k}: {v:,}" for k, v in res["clv_status"].items())
    return ["# Experiment 4: player props against Pinnacle (generated report)\n",
            "Generated by `python -m nbatotals backtest-props --legacy`. Rules: "
            "[PREREGISTRATION.md](PREREGISTRATION.md). Interpretation: [RESULTS.md](RESULTS.md). "
            "Test set: 2024-25 regular season. ROI and CLV intervals: bootstrap over events (games), "
            f"{metrics.N_BOOT:,} resamples, seed {metrics.SEED}. Hit-rate intervals are Wilson and treat bets as "
            "independent (too narrow for pooled 'all books' rows, where one prop is bet at several books). "
            "CLV is in probability points (Pinnacle close minus Pinnacle T−3h, same line).\n",
            "## Data counts\n",
            "```\n" + _json(res["counts"]) + "\n```\n",
            "T−3h CLV status of same-line sides: " + status + "\n"]


def _bar_section(res: dict) -> list[str]:
    out = ["\n## Pre-registered cells (markets and sides pooled)\n"]
    bar = res["bar"]
    n_cells = len(bar)
    hit = bar[bar["meets_bar"]] if n_cells else bar
    out.append(f"{n_cells} cells (book or region pooled × window × threshold). Cells meeting the evidence bar "
               f"(n ≥ {MIN_BETS}, ROI lower bound > 0, CLV lower bound > 0): **{len(hit)}**.\n")
    if len(hit):
        out.append(_cell_md(hit) + "\n")
    pos = bar[(bar["n"] >= MIN_BETS) & (bar["roi_lo"] > 0)] if n_cells else bar
    out.append(f"Cells with n ≥ {MIN_BETS} and ROI lower bound > 0 (regardless of CLV): **{len(pos)}**.\n")
    if len(pos):
        out.append(_cell_md(pos) + "\n")
    return out


def _threshold_sections(res: dict) -> list[str]:
    out = []
    for t in (DESCRIPTIVE_THRESHOLD,) + THRESHOLDS:
        strict = t == DESCRIPTIVE_THRESHOLD
        for mkt in ("all",) + tuple(STAT):
            lab = "edge > 0 (descriptive)" if strict else f"edge ≥ {t:.0%}"
            out.append(f"\n### {lab}, {MARKET_LABELS[mkt]}\n")
            out.append(_cell_md(cell_table(res["pairs"], t, mkt, strict=strict)))
    out.append("\n## Overs and unders (markets pooled)\n")
    for t in THRESHOLDS:
        for side in ("over", "under"):
            out.append(f"\n### edge ≥ {t:.0%}, {side}s\n")
            out.append(_cell_md(cell_table(res["pairs"], t, side=side)))
    return out


def _distance_sections(res: dict) -> list[str]:
    shares = tuple(f">= {t:.0%}" for t in THRESHOLDS)
    out = ["\n## How far retail books sit from Pinnacle\n",
           _frame_md(res["distance"],
                     pct_cols=("same_line_share", "hold", "share_edge_2pct_over", "share_edge_2pct_under"),
                     fmt={"mean_abs_line_diff_when_different": "{:.2f}", "mean_p_over_minus_pin": "{:+.4f}",
                          "mean_abs_p_over_minus_pin": "{:.4f}"}),
           "\n## Share of same-line retail sides with paper edge at or above each threshold\n",
           "Props (2024-25 regular season):\n\n",
           _frame_md(res["edge_share"], pct_cols=shares)]
    if "totals_benchmark" in res:
        out.append("\nGame totals, same rule (multi-region totals payloads, 2024-25 regular season; "
                   "`early_evening` ≈ T−3h, `true_close` = T−15 min):\n\n")
        out.append(_frame_md(res["totals_benchmark"], pct_cols=shares))
    return out


def _quality_sections(res: dict) -> list[str]:
    ages = ", ".join(f"{v:.2f}" for v in res["last_update_age_minutes"].values())
    return ["\n## Pinnacle calibration (over side, every Pinnacle player-line settled)\n",
            _frame_md(res["calibration"], pct_cols=("mean p_over", "over hit rate", "lo", "hi")),
            "\n## Stale quotes (market last_update more than 60 min before capture), share of test-set outcomes\n",
            "Age of `last_update` at capture, minutes (quantiles 0.5, 0.99, 1.0): " + ages + "\n\n",
            _frame_md(res["stale"], pct_cols=("stale_share",)),
            "\nDescriptive, added after pre-registration: T−3h bets whose book quotes the same line and side at "
            "the close, and whether its price was unchanged.\n\n",
            _frame_md(res["unchanged"], pct_cols=("same line at close", "price unchanged (of those)",
                                                  "ROI, unchanged", "ROI, changed"))]


def _desc_2025_section(res: dict) -> list[str]:
    if "desc_2025" not in res:
        return []
    d2 = res["desc_2025"]
    return [f"\n## 2025-26 (descriptive, not graded): {d2['events']} events\n",
            "```\n" + _json(d2["pair"]) + "\n```\n",
            _frame_md(d2["edge_share"], pct_cols=tuple(f">= {t:.0%}" for t in THRESHOLDS))]


def _sensitivity_section(sensitivity: dict | None) -> list[str]:
    if sensitivity is None:
        return []
    sb = sensitivity["bar"]
    return ["\n## Sensitivity: stale retail and Pinnacle quotes dropped (pre-registered cells)\n",
            f"Cells meeting the bar: **{int(sb['meets_bar'].sum()) if len(sb) else 0}** of {len(sb)}.\n\n",
            _cell_md(sb[sb["book"] == "all books"])]


def report_markdown(res: dict, sensitivity: dict | None = None) -> str:
    out = (_intro(res) + _bar_section(res) + _threshold_sections(res) + _distance_sections(res)
           + _quality_sections(res) + _desc_2025_section(res) + _sensitivity_section(sensitivity))
    return "\n".join(out)


def _json(d) -> str:
    import json

    def conv(x):
        if isinstance(x, dict):
            return {str(k): conv(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [conv(v) for v in x]
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating, float)):
            return None if np.isnan(x) else round(float(x), 4)
        return x
    return json.dumps(conv(d), indent=2, ensure_ascii=False)
