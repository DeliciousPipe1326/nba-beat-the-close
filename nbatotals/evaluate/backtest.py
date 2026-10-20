"""Walk-forward backtest of the Tier A engine against the market, as pre-registered.

`run(games, box, odds, params)` returns every table; `report_markdown` turns them
into the Markdown that docs/RESULTS.md quotes. Run on the maintainer's legacy
data with `python -m nbatotals backtest --legacy`.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dataclasses import dataclass, field

from nbatotals.evaluate import market, metrics


@dataclass(frozen=True)
class MarketSpec:
    """Which anchors exist, which is the primary comparison and CLV target (`ref`),
    which anchors CLV is measured from, and which one stands in for the
    pre-registration's "pretip" CLV criterion."""
    anchors: tuple
    ref: str
    clv_from: tuple
    pretip: str
    headline_clv: tuple = ()
    labels: dict = field(default_factory=dict)
    clv_sd: float = metrics.TOTAL_SD  # SD of the normal approximation behind CLV in cents


# Pre-registration Amendment 2: multi-region payloads with a true close.
TRUE_CLOSE = MarketSpec(
    anchors=("opening", "noon", "afternoon", "early_evening", "late_evening", "near_close", "true_close"),
    ref="true_close",
    clv_from=("opening", "noon", "afternoon", "early_evening", "late_evening", "near_close"),
    pretip="noon",
    headline_clv=("opening", "noon"),
    labels={"opening": "opening (~24h)", "noon": "noon (~10h)", "afternoon": "afternoon (~5h)",
            "early_evening": "early evening (~3h)", "late_evening": "late evening (~2h)",
            "near_close": "near close (~1h)", "true_close": "true close (T−15 min)"},
)
# Odds you collect yourself with `poll-odds` (live anchor names; T-15 min is the
# reference, matching the true close graded above).
LIVE = MarketSpec(
    anchors=("opening", "t-10h", "t-5h", "t-3h", "t-2h", "t-1h", "t-15m"), ref="t-15m",
    clv_from=("opening", "t-10h", "t-5h", "t-3h", "t-2h", "t-1h"), pretip="t-10h", headline_clv=("opening", "t-10h"),
    labels={"opening": "opening", "t-10h": "T−10h", "t-5h": "T−5h", "t-3h": "T−3h", "t-2h": "T−2h", "t-1h": "T−1h",
            "t-15m": "T−15 min"},
)
# Pre-registration Amendment 1: temporal payloads, no close (cross-check only).
TEMPORAL = MarketSpec(
    anchors=("early", "overnight", "afternoon"), ref="afternoon", clv_from=("early", "overnight"),
    pretip="overnight",
    headline_clv=("early", "overnight"),
    labels={"early": "early (~23h)", "overnight": "overnight (~17h)", "afternoon": "afternoon (~6h)"},
)

TEST_SEASONS = (2022, 2023, 2024)
THRESHOLDS = (0, 1, 2, 3, 4, 6)
BREAKEVEN_110 = 110 / 210


STORE_ORDER = ("opening", "t-10h", "t-5h", "t-3h", "t-2h", "t-1h", "t-15m", "close")


def store_quotes(con) -> pd.DataFrame:
    """Totals quotes the --store backtest uses: matched to a game, legacy-table rows excluded."""
    return pd.read_sql_query("SELECT * FROM odds_snapshots WHERE market = 'totals' AND game_id IS NOT NULL "
                             "AND anchor NOT LIKE 'legacy_%'", con)


def store_spec(anchors, leads: dict | None = None) -> MarketSpec:
    """The market spec for odds in a local store (live polling, backfill-odds or a replay).

    Live and backfill anchors keep their fixed order; any other names (a replay keeps recorded bucket names)
    are ordered by `leads` (median minutes before tip, largest first). The reference is T−15 min if present,
    else the live `close`, else the anchor nearest tip; CLV is measured from every earlier one."""
    names = list(dict.fromkeys(anchors))
    if all(a in STORE_ORDER for a in names):
        present = [a for a in STORE_ORDER if a in names]
        ref = "t-15m" if "t-15m" in present else ("close" if "close" in present else present[-1])
    else:
        if leads is None:
            raise ValueError(f"anchors {sorted(names)} need their leads to be ordered")
        present = sorted(names, key=lambda a: -leads[a])
        ref = present[-1]
    if not present:
        raise ValueError("no anchors")
    clv_from = tuple(a for a in present[:present.index(ref)] if a != "close")
    pretip = "t-10h" if "t-10h" in clv_from else (clv_from[0] if clv_from else ref)
    return MarketSpec(anchors=clv_from + (ref,), ref=ref, clv_from=clv_from, pretip=pretip,
                      headline_clv=clv_from[:2], labels={a: market.ANCHOR_LABELS.get(a, a) for a in present})


def _seasons(pred: pd.DataFrame) -> list:
    """The test seasons present in the predictions, ascending, then "pooled"."""
    return sorted(pd.unique(pred["season"]).tolist()) + ["pooled"]


def season_label(s) -> str:
    return "pooled" if s == "pooled" else f"{s}-{str(s + 1)[-2:]}"


# --------------------------------------------------------------------------- predictions

def predictions(games, box, base, test_seasons=TEST_SEASONS, progress=None, log_path=None, projector=None):
    """Walk-forward: for each test season, fit on earlier seasons only, then project that season.

    `projector` is any object implementing nbatotals/model/base.py (default: the
    pre-registered pace_eff formula). Returns (pred, fits, log_rows).
    """
    from nbatotals.features.pointintime import build_features
    from nbatotals.model import base as model_base
    from nbatotals.model import registry

    projector = projector or registry.get()
    games = games[games["season"] <= max(test_seasons)]
    targets = games[(games["status"] == "final") & (games["postseason"] == 0)].reset_index(drop=True)
    actual = targets.set_index("id")[["home_pts", "away_pts"]].sum(axis=1)
    # games played before each target (for the "both teams 10+ games" cut), independent of the model
    played = build_features(targets, games, box, base).set_index("game_id")[["home_n", "away_n"]]
    default_proj = model_base.check_output(projector.predict(targets, games, box, None, base), targets)
    default_proj = default_proj.set_index("game_id")["total_proj"]
    rows, fit_rows, logs = [], [], []
    for s in test_seasons:
        train_games = games[games["season"] < s]
        train_box = box[box["game_id"].isin(train_games["id"])]
        state = projector.fit(train_games, train_box, base, progress=progress) or {}
        tg = targets[targets["season"] == s]
        proj = model_base.check_output(projector.predict(tg, games, box, state, base), tg)
        proj = proj.set_index("game_id")["total_proj"]
        ids = tg["id"].to_numpy()
        df = pd.DataFrame({
            "game_id": ids, "season": s,
            "proj": proj.loc[ids].to_numpy(),
            "proj_default": default_proj.loc[ids].to_numpy(),
            "actual": actual.loc[ids].to_numpy(),
            "both_10": ((played.loc[ids, "home_n"] >= 10) & (played.loc[ids, "away_n"] >= 10)).to_numpy(),
        })
        rows.append(df)
        if state.get("log") is not None:
            logs.append(state["log"])
        fit_rows.append({
            "test_season": s, "trained_on": ", ".join(season_label(x) for x in range(min(games["season"]), s)),
            **state.get("summary", {}),
            "test_rmse_chosen": float(np.sqrt(((df["proj"] - df["actual"]) ** 2).mean())),
            "test_rmse_default": float(np.sqrt(((df["proj_default"] - df["actual"]) ** 2).mean())),
            "test_n": len(df),
        })
    log = (projector.combine_logs(logs) if hasattr(projector, "combine_logs") else pd.concat(logs, ignore_index=True)
           ) if logs else pd.DataFrame()
    if log_path and len(log):
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the file byte-identical across re-runs, so git diff shows real changes only
        text = log.to_csv(sep="\t", index=False, float_format="%.6f")
        with open(log_path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as fh:
            fh.write(text.encode())
    return pd.concat(rows, ignore_index=True), pd.DataFrame(fit_rows), len(log)


# --------------------------------------------------------------------------- grading

def _bets(pred: pd.DataFrame, w: pd.DataFrame, anchor: str, proj_col: str,
          spec: MarketSpec = TRUE_CLOSE) -> pd.DataFrame:
    d = pred.merge(w, on="game_id", how="inner")
    d = d[d[f"line_{anchor}"].notna()].copy()
    line = d[f"line_{anchor}"]
    d["line"] = line
    d["edge"] = d[proj_col] - line
    d["over"] = d["edge"] > 0
    d["push"] = d["actual"] == line
    d["win"] = np.where(d["over"], d["actual"] > line, d["actual"] < line)
    d["p_side"] = np.where(d["over"], d[f"p_over_{anchor}"], d[f"p_under_{anchor}"])
    d["price"] = np.where(d["over"], d[f"over_price_{anchor}"], d[f"under_price_{anchor}"])
    d["fair_ret"] = np.where(d["win"], 1 / d["p_side"] - 1, -1.0)
    d["real_ret"] = np.where(d["win"], d["price"] - 1, -1.0)
    if anchor != spec.ref:
        ref_line = d[f"line_{spec.ref}"]
        has_close = ref_line.notna()
        d["clv_pts"] = np.where(d["over"], ref_line - line, line - ref_line).astype(float)
        d.loc[~has_close, "clv_pts"] = np.nan
        p_over_close_at = np.full(len(d), np.nan)
        if has_close.any():
            p_over_close_at[has_close.to_numpy()] = metrics.prob_over_at(
                line[has_close].to_numpy(), ref_line[has_close].to_numpy(),
                d.loc[has_close, f"p_over_{spec.ref}"].to_numpy(dtype=float), sd=spec.clv_sd)
        p_close_side = np.where(d["over"], p_over_close_at, 1 - p_over_close_at)
        d["clv_cents"] = 100 * (p_close_side - d["p_side"])
    return d


def _grade(d: pd.DataFrame, anchor: str, spec: MarketSpec = TRUE_CLOSE) -> dict:
    graded = d[~d["push"]]
    n = len(graded)
    wins = int(graded["win"].sum())
    lo, hi = metrics.wilson(wins, n)
    out = {
        "bets": len(d), "pushes": int(d["push"].sum()), "n": n, "wins": wins,
        "cover": wins / n if n else np.nan, "cover_lo": lo, "cover_hi": hi,
        "baseline": float(graded["p_side"].mean()) if n else np.nan,
        "fair_roi": float(graded["fair_ret"].mean()) if n else np.nan,
        "real_roi": float(graded["real_ret"].mean()) if n else np.nan,
    }
    out["fair_lo"], out["fair_hi"] = metrics.bootstrap_mean_ci(graded["fair_ret"])
    out["real_lo"], out["real_hi"] = metrics.bootstrap_mean_ci(graded["real_ret"])
    if anchor != spec.ref:
        c = d["clv_pts"].dropna()
        out["clv_n"] = len(c)
        out["clv_pts"] = float(c.mean()) if len(c) else np.nan
        out["clv_lo"], out["clv_hi"] = metrics.bootstrap_mean_ci(c)
        cc = d["clv_cents"].dropna()
        out["clv_cents"] = float(cc.mean()) if len(cc) else np.nan
        out["clv_cents_lo"], out["clv_cents_hi"] = metrics.bootstrap_mean_ci(cc)
    return out


def grading(pred: pd.DataFrame, w: pd.DataFrame, spec: MarketSpec = TRUE_CLOSE) -> pd.DataFrame:
    rows = []
    for run, col in (("tuned", "proj"), ("default", "proj_default")):
        for anchor in spec.anchors:
            bets = _bets(pred, w, anchor, col, spec)
            for cut in ("all", "both_10"):
                b = bets if cut == "all" else bets[bets["both_10"]]
                for t in THRESHOLDS:
                    bt = b[b["edge"] != 0] if t == 0 else b[b["edge"].abs() >= t]
                    for s in _seasons(pred):
                        x = bt if s == "pooled" else bt[bt["season"] == s]
                        rows.append({"run": run, "anchor": anchor, "cut": cut, "threshold": t, "season": s,
                                     **_grade(x, anchor, spec)})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- information tests

def accuracy(pred: pd.DataFrame, w: pd.DataFrame, spec: MarketSpec = TRUE_CLOSE) -> pd.DataFrame:
    d = pred.merge(w, on="game_id", how="left")
    rows = []
    for s in _seasons(pred):
        x = d if s == "pooled" else d[d["season"] == s]
        row: dict[str, Any] = {"season": s}
        for anchor in spec.anchors:
            y = x[x[f"line_{anchor}"].notna()]
            row[f"n_{anchor}"] = len(y)
            for name, col in (("proj", "proj"), ("default", "proj_default"), ("line", f"line_{anchor}")):
                e = y[col] - y["actual"]
                row[f"mae_{name}_{anchor}"] = float(e.abs().mean())
                row[f"rmse_{name}_{anchor}"] = float(np.sqrt((e ** 2).mean()))
        rows.append(row)
    return pd.DataFrame(rows)


def blend_regression(pred: pd.DataFrame, w: pd.DataFrame, spec: MarketSpec = TRUE_CLOSE) -> pd.DataFrame:
    d = pred.merge(w, on="game_id")
    d = d[d[f"line_{spec.ref}"].notna()]
    rows = []
    for run, col in (("tuned", "proj"), ("default", "proj_default")):
        for s in _seasons(pred):
            x = d if s == "pooled" else d[d["season"] == s]
            r = metrics.ols(x["actual"], {"market": x[f"line_{spec.ref}"], "model": x[col]})
            rows.append({"run": run, "season": s, "n": r["n"],
                         **{f"{k}_{m}": r[k][m] for k in ("const", "market", "model") for m in ("coef", "lo", "hi")}})
    return pd.DataFrame(rows)


def edge_vs_move(pred: pd.DataFrame, w: pd.DataFrame, spec: MarketSpec = TRUE_CLOSE) -> pd.DataFrame:
    d = pred.merge(w, on="game_id")
    rows = []
    for anchor in spec.clv_from:
        y = d[d[f"line_{anchor}"].notna() & d[f"line_{spec.ref}"].notna()]
        for s in _seasons(pred):
            x = y if s == "pooled" else y[y["season"] == s]
            r, lo, hi, n = metrics.corr_ci(x["proj"] - x[f"line_{anchor}"], x[f"line_{spec.ref}"] - x[f"line_{anchor}"])
            rows.append({"anchor": anchor, "season": s, "n": n, "r": r, "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def evidence(g: pd.DataFrame, spec: MarketSpec = TRUE_CLOSE) -> dict:
    """The pre-registered evidence bar, evaluated on the primary cell."""
    prim = g[(g["run"] == "tuned") & (g["anchor"] == spec.ref) & (g["cut"] == "all") & (g["threshold"] == 0)]
    pooled = prim[prim["season"] == "pooled"].iloc[0]
    per = prim[prim["season"] != "pooled"]
    out = {
        "pooled_n": int(pooled["n"]), "pooled_cover": pooled["cover"], "pooled_cover_lo": pooled["cover_lo"],
        "c1_lower_bound_above_52.38": bool(pooled["cover_lo"] > BREAKEVEN_110 and pooled["n"] >= 1000),
        "c1_each_season_above_50": bool((per["cover"] > 0.5).all()),
        "c3_real_roi_ci_above_0": bool(pooled["real_lo"] > 0),
    }
    for anchor in spec.clv_from:
        c = g[(g["run"] == "tuned") & (g["anchor"] == anchor) & (g["cut"] == "all") & (g["threshold"] == 0)
              & (g["season"] == "pooled")].iloc[0]
        out[f"c2_clv_{anchor}_ci_above_0"] = bool(c["clv_lo"] > 0)
    # The pre-registered CLV criterion names the pretip anchor; spec.pretip says which anchor stands in for it.
    out["edge"] = (out["c1_lower_bound_above_52.38"] and out["c1_each_season_above_50"]
                   and out.get(f"c2_clv_{spec.pretip}_ci_above_0", False) and out["c3_real_roi_ci_above_0"])
    flags = g[(g["n"] >= 1) & ((g["cover_lo"] > BREAKEVEN_110) | (g.get("clv_lo", pd.Series(dtype=float)) > 0))]
    out["cells_clearing_a_bar"] = flags[["run", "anchor", "cut", "threshold", "season", "n", "cover", "cover_lo",
                                         "clv_pts", "clv_lo"]]
    return out


def pinnacle_grading(pred: pd.DataFrame, odds: pd.DataFrame, base: dict, spec: MarketSpec,
                     anchor: str | None = None) -> pd.DataFrame:
    """Secondary: grade against Pinnacle's own line and devigged price at `anchor` (default: the reference)."""
    import dataclasses

    from nbatotals import params as params_io

    anchor = anchor or spec.ref
    at = dataclasses.replace(spec, ref=anchor)  # graded at that anchor's own line and price; no CLV
    pin = odds[(odds["book"] == "pinnacle") & (odds["anchor"] == anchor)]
    cons = market.consensus(pin, params_io.with_overrides(base, {"market.min_books": 1}))
    bets = _bets(pred, market.wide(cons), anchor, "proj", at)
    rows = []
    for t in THRESHOLDS:
        bt = bets[bets["edge"] != 0] if t == 0 else bets[bets["edge"].abs() >= t]
        for s in _seasons(pred):
            x = bt if s == "pooled" else bt[bt["season"] == s]
            rows.append({"threshold": t, "season": s, **_grade(x, anchor, at)})
    return pd.DataFrame(rows)


def run(games, box, odds, base, spec: MarketSpec = TRUE_CLOSE, progress=None, log_path=None, fitted=None,
        projector=None, test_seasons=TEST_SEASONS) -> dict:
    """`fitted` = (pred, fits, log_rows) from an earlier `predictions` call, to skip the odds-free grid."""
    cons = market.consensus(odds, base)
    cons, order_dropped = market.enforce_anchor_order(cons, spec.ref)
    w = market.wide(cons)
    if fitted is None:
        fitted = predictions(games, box, base, test_seasons=test_seasons, progress=progress, log_path=log_path,
                             projector=projector)
    pred, fits, log_rows = fitted
    g = grading(pred, w, spec)
    sanity = market.sanity_table(cons, games[games["season"] <= max(pred["season"])], spec.labels)
    order = {v: i for i, v in enumerate(spec.labels[a] for a in spec.anchors)}
    sanity = sanity.sort_values(["season", "anchor"], key=lambda c: c.map(order) if c.name == "anchor" else c)
    out = {
        "spec": spec, "labels": spec.labels, "fitted": fitted, "sanity": sanity, "order_dropped": order_dropped,
        "fits": fits, "log_rows": log_rows, "pred": pred, "grading": g,
        "accuracy": accuracy(pred, w, spec), "regression": blend_regression(pred, w, spec),
        "edge_move": edge_vs_move(pred, w, spec), "evidence": evidence(g, spec),
    }
    if (odds["book"] == "pinnacle").any():
        out["pinnacle"] = pinnacle_grading(pred, odds, base, spec)
    return out


# --------------------------------------------------------------------------- markdown

def _pct(x, d=1):
    return "–" if pd.isna(x) else f"{100 * x:.{d}f}%"


def _num(x, d=2):
    return "–" if pd.isna(x) else f"{x:+.{d}f}" if d and x != 0 else f"{x:.{d}f}"


def _table(header, rows) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def headline_table(res: dict) -> str:
    spec = res["spec"]
    g = res["grading"]
    rows = []
    for s in _seasons(res["pred"]):
        primary = (g.run == "tuned") & (g.cut == "all") & (g.threshold == 0) & (g.season == s)
        c = g[primary & (g.anchor == spec.ref)].iloc[0]
        row = [season_label(s), f"{int(c.n):,}", f"{_pct(c.cover)} ({_pct(c.cover_lo)}–{_pct(c.cover_hi)})",
               _pct(c.baseline), f"{_pct(c.fair_roi)} ({_pct(c.fair_lo)} to {_pct(c.fair_hi)})",
               f"{_pct(c.real_roi)} ({_pct(c.real_lo)} to {_pct(c.real_hi)})"]
        for a in spec.headline_clv:
            o = g[primary & (g.anchor == a)].iloc[0]
            row += [f"{int(o.clv_n):,}", f"{o.clv_pts:+.2f} ({o.clv_lo:+.2f} to {o.clv_hi:+.2f})"]
        rows.append(row)
    head = ["season", f"n ({spec.labels[spec.ref]})", "cover (95% Wilson)", "no-info baseline", "fair ROI (95% CI)",
            "real ROI (95% CI)"]
    for a in spec.headline_clv:
        head += [f"{spec.labels[a]} bets", f"CLV {a} → {spec.ref}, points (95% CI)"]
    return _table(head, rows)


def clv_table(res: dict) -> str:
    """CLV of threshold-0 bets struck at each earlier anchor, measured to the reference anchor."""
    spec = res["spec"]
    g = res["grading"]
    g = g[(g.run == "tuned") & (g.cut == "all") & (g.threshold == 0)]
    rows = []
    for a in spec.clv_from:
        for s in _seasons(res["pred"]):
            c = g[(g.anchor == a) & (g.season == s)].iloc[0]
            rows.append([spec.labels[a], season_label(s), f"{int(c.clv_n):,}",
                         f"{c.clv_pts:+.2f} ({c.clv_lo:+.2f} to {c.clv_hi:+.2f})",
                         f"{c.clv_cents:+.2f}¢ ({c.clv_cents_lo:+.2f} to {c.clv_cents_hi:+.2f})",
                         f"{_pct(c.cover)} ({_pct(c.cover_lo)}–{_pct(c.cover_hi)})", _pct(c.real_roi)])
    return _table(["bet struck at", "season", "bets", f"CLV to {spec.labels[spec.ref]}, points (95% CI)",
                   "CLV, cents (95% CI)", "cover at that anchor (95% Wilson)", "real ROI at that anchor"], rows)


def pinnacle_table(res: dict) -> str:
    p = res["pinnacle"]
    rows = [[x.threshold, season_label(x.season), f"{int(x.n):,}", int(x.pushes),
             f"{_pct(x.cover)} ({_pct(x.cover_lo)}–{_pct(x.cover_hi)})", _pct(x.baseline),
             f"{_pct(x.fair_roi)} ({_pct(x.fair_lo)} to {_pct(x.fair_hi)})",
             f"{_pct(x.real_roi)} ({_pct(x.real_lo)} to {_pct(x.real_hi)})"] for x in p.itertuples()]
    return _table(["edge ≥", "season", "n", "pushes", "cover (95% Wilson)", "baseline",
                   "fair ROI at Pinnacle's devigged price (CI)",
                   "ROI at Pinnacle's own price (CI)"], rows)


def grading_table(res: dict, run="tuned", cut="all") -> str:
    spec = res["spec"]
    g = res["grading"]
    g = g[(g.run == run) & (g.cut == cut)]
    rows = []
    for anchor in spec.anchors:
        for t in THRESHOLDS:
            for s in _seasons(res["pred"]):
                c = g[(g.anchor == anchor) & (g.threshold == t) & (g.season == s)].iloc[0]
                clv = "n/a" if anchor == spec.ref else (
                    f"{c.clv_pts:+.2f} ({c.clv_lo:+.2f}, {c.clv_hi:+.2f}); {c.clv_cents:+.2f}¢" if c.clv_n else "–")
                rows.append([res["labels"][anchor], t, season_label(s), f"{int(c.n):,}", int(c.pushes),
                             f"{_pct(c.cover)} ({_pct(c.cover_lo)}–{_pct(c.cover_hi)})", _pct(c.baseline),
                             f"{_pct(c.fair_roi)} ({_pct(c.fair_lo)}, {_pct(c.fair_hi)})",
                             f"{_pct(c.real_roi)} ({_pct(c.real_lo)}, {_pct(c.real_hi)})", clv])
    return _table(["anchor", "edge ≥", "season", "n", "pushes", "cover (95% Wilson)", "baseline", "fair ROI (CI)",
                   "real ROI (CI)", "CLV pts (CI); cents"], rows)


def fit_table(res: dict) -> str:
    f = res["fits"]
    if "l3" in f:  # the pace_eff formula's table, as pre-registered
        rows = [[season_label(r.test_season), r.trained_on, f"{r.train_n:,}",
                 f"{r.l3:.1f}/{r.l10:.1f}/{r.season_w:.1f}", r.shrinkage, r.pace_weight, f"{r.home_court_total:+.0f}",
                 f"{r.b2b_total_per_team:+.0f}", f"{r.train_rmse_chosen:.3f}", f"{r.train_rmse_default:.3f}",
                 f"{r.test_rmse_chosen:.3f}", f"{r.test_rmse_default:.3f}"] for r in f.itertuples()]
        return _table(["test season", "trained on", "train n", "blend l3/l10/season", "shrinkage", "pace weight",
                       "home court", "B2B per team", "train RMSE chosen", "train RMSE default", "test RMSE chosen",
                       "test RMSE default"], rows)
    cols = [c for c in f.columns if c not in ("test_season",)]

    def fmt(v):
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    rows = [[season_label(r["test_season"])] + [fmt(r[c]) for c in cols] for _, r in f.iterrows()]
    return _table(["test season"] + [c.replace("_", " ") for c in cols], rows)


def accuracy_table(res: dict) -> str:
    spec = res["spec"]
    a = res["accuracy"]
    labels = res["labels"]
    rows = []
    for r in a.to_dict("records"):  # records, not itertuples: anchor names like "t-15m" are not identifiers
        for anchor in (spec.ref,) + spec.clv_from:
            rows.append([season_label(r["season"]), labels[anchor], f"{r[f'n_{anchor}']:,}",
                         f"{r[f'mae_proj_{anchor}']:.2f}", f"{r[f'mae_default_{anchor}']:.2f}",
                         f"{r[f'mae_line_{anchor}']:.2f}", f"{r[f'rmse_proj_{anchor}']:.2f}",
                         f"{r[f'rmse_default_{anchor}']:.2f}", f"{r[f'rmse_line_{anchor}']:.2f}"])
    return _table(["season", "games with this anchor", "n", "MAE model (tuned)", "MAE model (default)", "MAE line",
                   "RMSE model (tuned)", "RMSE model (default)", "RMSE line"], rows)


def regression_table(res: dict) -> str:
    spec = res["spec"]
    r = res["regression"]
    rows = [[x.run, season_label(x.season), f"{x.n:,}", f"{x.const_coef:+.1f} ({x.const_lo:+.1f}, {x.const_hi:+.1f})",
             f"{x.market_coef:.3f} ({x.market_lo:.3f}, {x.market_hi:.3f})",
             f"{x.model_coef:+.3f} ({x.model_lo:+.3f}, {x.model_hi:+.3f})"] for x in r.itertuples()]
    return _table(["model run", "season", "n", "intercept (95% CI)", f"b: {spec.labels[spec.ref]} line (95% CI)",
                   "c: model (95% CI)"], rows)


def edge_move_table(res: dict) -> str:
    spec = res["spec"]
    e = res["edge_move"]
    rows = [[res["labels"][x.anchor], season_label(x.season), f"{x.n:,}", f"{x.r:+.3f} ({x.lo:+.3f}, {x.hi:+.3f})"]
            for x in e.itertuples()]
    head = f"corr(model − anchor line, {spec.ref} line − anchor line) (95% CI)"
    return _table(["bet anchor", "season", "n", head], rows)


def sanity_markdown(res: dict) -> str:
    s = res["sanity"]
    rows = [[season_label(r.season), r.anchor, f"{r.games:,}", f"{r.books_median:.0f}", f"{r.line_mean:.1f}",
             f"{r.line_sd:.1f}", f"{r.p_over_mean:.3f}", f"{r.quarter_share:.3f}", f"{r.mae_vs_actual:.2f}"]
            for r in s.itertuples()]
    return _table(["season", "anchor", "games", "books (median)", "line mean", "line SD", "mean p_over",
                   "quarter-point share", "MAE vs actual"], rows)


def report_markdown(res: dict) -> str:
    spec = res["spec"]
    ev = res["evidence"]
    flagged = ev["cells_clearing_a_bar"]
    flagged_rows = [[x.run, spec.labels[x.anchor], x.cut, x.threshold, season_label(x.season), f"{int(x.n):,}",
                     f"{_pct(x.cover)} (lo {_pct(x.cover_lo)})",
                     "n/a" if pd.isna(x.clv_pts) else f"{x.clv_pts:+.2f} (lo {x.clv_lo:+.2f})"]
                    for x in flagged.itertuples()]
    counts = dict(res.get("anchor_counts") or {})
    counts["consensus_rows_captured_at_or_after_the_reference"] = res.get("order_dropped", 0)
    parts = [
        "## Anchor construction counts",
        _table(["count", "value"], [[k, f"{v:,}"] for k, v in counts.items()]) if counts else "(not available)",
        "## Market sanity", sanity_markdown(res),
        "## Walk-forward fit", fit_table(res),
        f"Grid evaluations logged: {res['log_rows']:,}.",
        f"## Headline (primary cell: tuned model, {spec.labels[spec.ref]}, every game)", headline_table(res),
        f"## CLV by anchor (tuned model, every game, all bets), measured to {spec.labels[spec.ref]}", clv_table(res),
        *([f"## Pinnacle only: tuned model against Pinnacle's own {spec.labels[spec.ref]} line and price "
           "(games where Pinnacle quotes a total)", pinnacle_table(res)] if "pinnacle" in res else []),
        "## Projection accuracy", accuracy_table(res),
        f"## Market + model blend regression: actual = a + b·{spec.ref} line + c·model", regression_table(res),
        "## Does the model's edge predict the line move?", edge_move_table(res),
        "## Pre-registered evidence bar",
        _table(["criterion", "met"], [[k, v] for k, v in ev.items() if k != "cells_clearing_a_bar"]),
        "## Cells clearing a bar (cover lower bound above 52.38% or CLV lower bound above 0)",
        _table(["run", "anchor", "cut", "edge ≥", "season", "n", "cover", "CLV pts"], flagged_rows)
        if flagged_rows else "None.",
        "## All cells, tuned model, every game", grading_table(res, "tuned", "all"),
        "## All cells, tuned model, both teams 10+ games", grading_table(res, "tuned", "both_10"),
        "## All cells, default parameters, every game", grading_table(res, "default", "all"),
    ]
    return "\n\n".join(parts) + "\n"
