"""Experiment 5: spreads and moneyline through the same harness.

Pre-registered in docs/experiments/other_markets/PREREGISTRATION.md. The totals
harness (backtest.py) is reused wherever the rules are the same:

- spreads are graded by the totals code unchanged, with home in the role of
  over: the "line" is the home margin the market implies (minus the home
  spread), the projection is the model's home margin, the actual is the home
  margin (market.consensus_spreads builds the columns that way);
- the moneyline has no line, so it has its own bets (edge = model minus market
  home probability), Brier and log loss, and a logistic blend regression.

Margins come from a projector's optional `predict_margin` (model/base.py),
walk-forward. Per test season, on earlier seasons only: `h` = mean(actual −
raw margin) and the logistic scale `s` by maximum likelihood; model margin =
raw + h, home win probability = 1 / (1 + exp(−margin / s)).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from nbatotals.evaluate import backtest, market, metrics
from nbatotals.evaluate.backtest import TEST_SEASONS, _grade, _pct, _table, season_label

SPREADS = dataclasses.replace(backtest.TRUE_CLOSE, clv_sd=metrics.MARGIN_SD)
H2H = backtest.TRUE_CLOSE
H2H_THRESHOLDS = (0, 0.02, 0.04, 0.06)
SEASONS = list(TEST_SEASONS) + ["pooled"]


# --------------------------------------------------------------------------- predictions

def _scored(games: pd.DataFrame) -> pd.DataFrame:
    return games[(games["status"] == "final") & (games["postseason"] == 0)].reset_index(drop=True)


def _margin(projector, targets, games, box, state, params) -> pd.Series:
    from nbatotals.model import base as model_base

    out = model_base.check_margin_output(projector.predict_margin(targets, games, box, state, params), targets)
    return out.set_index("game_id")["margin_proj"].loc[targets["id"]]


def _calibrate(raw: pd.Series, actual: pd.Series) -> tuple[float, float]:
    h = float((actual.to_numpy() - raw.to_numpy()).mean())
    s = metrics.fit_logistic_scale(raw.to_numpy() + h, (actual.to_numpy() > 0).astype(float))
    return h, s


def margin_predictions(games, box, base, projector, test_seasons=TEST_SEASONS, progress=None):
    """Walk-forward margins and win probabilities. Returns (pred, fits)."""
    from nbatotals.features.pointintime import build_features

    if not hasattr(projector, "predict_margin"):
        raise TypeError(f"{projector.name} has no predict_margin (see nbatotals/model/base.py)")
    games = games[games["season"] <= max(test_seasons)]
    targets = _scored(games)
    margin = (targets["home_pts"] - targets["away_pts"]).set_axis(targets["id"])
    played = build_features(targets, games, box, base).set_index("game_id")[["home_n", "away_n"]]
    rows, fits = [], []
    for s in test_seasons:
        train_games = games[games["season"] < s]
        train_box = box[box["game_id"].isin(train_games["id"])]
        state = projector.fit(train_games, train_box, base, progress=progress) or {}
        summary = {}
        if hasattr(projector, "fit_margin"):
            extra = projector.fit_margin(train_games, train_box, base, state) or {}
            summary.update(extra.pop("summary", {}))
            state = {**state, **extra}
        train_t = _scored(train_games)
        tg = targets[targets["season"] == s]
        ids = tg["id"].to_numpy()
        cols, cal = {}, {}
        for run, st in (("tuned", state), ("default", None)):
            raw_train = _margin(projector, train_t, train_games, train_box, st, base)
            h, sc = _calibrate(raw_train, margin.loc[train_t["id"]])
            raw = _margin(projector, tg, games, box, st, base).to_numpy()
            resid = raw_train.to_numpy() + h - margin.loc[train_t["id"]].to_numpy()
            cal[run] = (h, sc, float(np.sqrt((resid ** 2).mean())))
            sfx = "" if run == "tuned" else "_default"
            cols[f"proj{sfx}"] = raw + h
            cols[f"p_model{sfx}"] = 1 / (1 + np.exp(-(raw + h) / sc))
            if run == "tuned":
                cols["proj_raw"] = raw
        df = pd.DataFrame({
            "game_id": ids, "season": s, **cols,
            "actual": margin.loc[ids].to_numpy(dtype=float),
            "both_10": ((played.loc[ids, "home_n"] >= 10) & (played.loc[ids, "away_n"] >= 10)).to_numpy(),
        })
        df["home_win"] = df["actual"] > 0
        rows.append(df)
        e = df["proj"] - df["actual"]
        fits.append({
            "test_season": s,
            "trained_on": ", ".join(season_label(x) for x in range(int(games["season"].min()), s)),
            "train_n": len(train_t), **summary,
            "h": cal["tuned"][0], "s": cal["tuned"][1], "train_rmse": cal["tuned"][2],
            "h_default": cal["default"][0], "s_default": cal["default"][1],
            "test_mae": float(e.abs().mean()), "test_rmse": float(np.sqrt((e ** 2).mean())),
            "test_mae_default": float((df["proj_default"] - df["actual"]).abs().mean()),
            "test_n": len(df),
        })
    return pd.concat(rows, ignore_index=True), pd.DataFrame(fits)


# --------------------------------------------------------------------------- sanity and stop rules

def _paired_rows(w: pd.DataFrame, spec, value) -> list[dict]:
    """Per earlier anchor, the paired difference (earlier − reference) of a per-game loss, on games with both."""
    rows = []
    for a in spec.clv_from:
        both = w[w[f"p_over_{a}"].notna() & w[f"p_over_{spec.ref}"].notna()]
        for s in sorted(both["season"].unique()) + ["all"]:
            x = both if s == "all" else both[both["season"] == s]
            d = value(x, a) - value(x, spec.ref)
            lo, hi = metrics.bootstrap_mean_ci(d)
            rows.append({"anchor": spec.labels[a], "season": s, "games": len(x), "diff": float(d.mean()),
                         "lo": lo, "hi": hi})
    return rows


def sanity(cons_sp: pd.DataFrame, cons_ml: pd.DataFrame, games: pd.DataFrame, spec=SPREADS) -> dict:
    """The pre-registered sanity tables and the four stop rules, computed before any grading."""
    g = _scored(games)[["id", "season", "home_pts", "away_pts"]].rename(columns={"id": "game_id"})
    g["margin"] = g["home_pts"] - g["away_pts"]
    g["home_win"] = (g["margin"] > 0).astype(float)
    order = {a: i for i, a in enumerate(spec.anchors)}

    sp = cons_sp.merge(g, on="game_id")
    sp_rows = []
    for (season, anchor), x in sp.groupby(["season", "anchor"]):
        e = x["margin"] - x["line"]
        sp_rows.append({"season": season, "anchor": anchor, "games": len(x), "books_median": float(x["books"].median()),
                        "home_spread_mean": x["home_spread"].mean(), "p_home_cover_mean": x["p_over"].mean(),
                        "mae": e.abs().mean(), "rmse": float(np.sqrt((e ** 2).mean())), "mean_error": e.mean()})
    def by_season_anchor(rows: list) -> pd.DataFrame:
        return pd.DataFrame(rows).sort_values(["season", "anchor"],
                                              key=lambda c: c.map(order) if c.name == "anchor" else c)

    sp_tab = by_season_anchor(sp_rows)

    ml = cons_ml.merge(g, on="game_id")
    ml_rows = []
    for (season, anchor), x in ml.groupby(["season", "anchor"]):
        ml_rows.append({"season": season, "anchor": anchor, "games": len(x), "books_median": float(x["books"].median()),
                        "p_home_mean": x["p_over"].mean(), "home_win_rate": x["home_win"].mean(),
                        "brier": metrics.brier(x["p_over"], x["home_win"]).mean(),
                        "log_loss": metrics.log_loss(x["p_over"], x["home_win"]).mean()})
    ml_tab = by_season_anchor(ml_rows)

    tc = cons_sp[cons_sp["anchor"] == spec.ref][["game_id", "home_spread"]].merge(
        cons_ml[cons_ml["anchor"] == spec.ref][["game_id", "p_over"]], on="game_id").merge(g, on="game_id")
    tc = tc[tc["home_spread"] != 0]
    agree = ((tc["home_spread"] < 0) == (tc["p_over"] > 0.5))
    fav = pd.DataFrame([{"season": s, "games": int(len(x)), "agreement": float(agree.loc[x.index].mean())}
                        for s, x in list(tc.groupby("season")) + [("all", tc)]])

    wsp = market.wide(cons_sp).merge(g, on="game_id")
    wml = market.wide(cons_ml).merge(g, on="game_id")
    mae_pairs = pd.DataFrame(_paired_rows(wsp, spec, lambda x, a: (x["margin"] - x[f"line_{a}"]).abs().to_numpy()))
    ll_pairs = pd.DataFrame(_paired_rows(wml, spec,
                                         lambda x, a: metrics.log_loss(x[f"p_over_{a}"], x["home_win"])))

    sp_ref = sp[sp["anchor"] == spec.ref]
    ml_ref = ml[ml["anchor"] == spec.ref]
    checks = {
        "1. pooled mean p_home_cover at the true close in 0.48–0.52": (
            f"{sp_ref['p_over'].mean():.4f}", bool(0.48 <= sp_ref["p_over"].mean() <= 0.52)),
        "2. pooled mean p_home within 3 points of the home win rate": (
            f"{ml_ref['p_over'].mean():.4f} vs {ml_ref['home_win'].mean():.4f}",
            bool(abs(ml_ref["p_over"].mean() - ml_ref["home_win"].mean()) <= 0.03)),
        "3. spread favourite = moneyline favourite in ≥ 98% of games": (
            f"{agree.mean():.4f} (n = {len(tc):,})", bool(agree.mean() >= 0.98)),
        "4a. no earlier bucket beats the true close on spread MAE (pooled paired CI below 0)": (
            "", bool(not ((mae_pairs["season"] == "all") & (mae_pairs["hi"] < 0)).any())),
        "4b. no earlier bucket beats the true close on moneyline log loss (pooled paired CI below 0)": (
            "", bool(not ((ll_pairs["season"] == "all") & (ll_pairs["hi"] < 0)).any())),
    }
    return {"spreads": sp_tab, "h2h": ml_tab, "favourite": fav, "mae_pairs": mae_pairs, "ll_pairs": ll_pairs,
            "checks": checks, "passed": all(ok for _, ok in checks.values())}


# --------------------------------------------------------------------------- spreads

def pinnacle_spreads(pred, odds, base, spec=SPREADS) -> pd.DataFrame:
    from nbatotals import params as params_io

    pin = odds[(odds["book"] == "pinnacle") & (odds["anchor"] == spec.ref)]
    cons = market.consensus_spreads(pin, params_io.with_overrides(base, {"market.min_books": 1}))
    bets = backtest._bets(pred, market.wide(cons), spec.ref, "proj", spec)
    rows = []
    for t in backtest.THRESHOLDS:
        bt = bets[bets["edge"] != 0] if t == 0 else bets[bets["edge"].abs() >= t]
        for s in SEASONS:
            x = bt if s == "pooled" else bt[bt["season"] == s]
            rows.append({"threshold": t, "season": s, **_grade(x, spec.ref, spec)})
    return pd.DataFrame(rows)


def run_spreads(pred, fits, odds, games, base, sane: dict, spec=SPREADS) -> dict:
    cons = market.consensus_spreads(odds, base)
    cons, dropped = market.enforce_anchor_order(cons, spec.ref)
    w = market.wide(cons)
    g = backtest.grading(pred, w, spec)
    raw = backtest._bets(pred, w, spec.ref, "proj_raw", spec)
    raw_rows = [{"season": s, **_grade((raw if s == "pooled" else raw[raw["season"] == s]).query("edge != 0"),
                                       spec.ref, spec)}
                for s in SEASONS]
    d = pred.merge(w, on="game_id")
    d = d[d[f"line_{spec.ref}"].notna()]
    corr = metrics.corr_ci(d["proj"], d[f"line_{spec.ref}"])
    res = {"market": "spreads", "spec": spec, "labels": spec.labels, "fits": fits, "pred": pred, "grading": g,
           "order_dropped": dropped, "sanity": sane, "raw": pd.DataFrame(raw_rows),
           "accuracy": backtest.accuracy(pred, w, spec), "regression": backtest.blend_regression(pred, w, spec),
           "edge_move": backtest.edge_vs_move(pred, w, spec), "evidence": backtest.evidence(g, spec),
           "model_line_corr": corr}
    if (odds["book"] == "pinnacle").any():
        res["pinnacle"] = pinnacle_spreads(pred, odds, base, spec)
    return res


# --------------------------------------------------------------------------- moneyline

def _bets_h2h(pred: pd.DataFrame, w: pd.DataFrame, anchor: str, p_col: str, spec=H2H) -> pd.DataFrame:
    """One bet per game: home if the model's home probability is above the market's, away if below."""
    d = pred.merge(w, on="game_id", how="inner")
    d = d[d[f"p_over_{anchor}"].notna()].copy()
    p_home = d[f"p_over_{anchor}"]
    d["edge"] = d[p_col] - p_home
    d["over"] = d["edge"] > 0  # home
    d["push"] = False
    d["win"] = np.where(d["over"], d["home_win"], ~d["home_win"].astype(bool))
    d["p_side"] = np.where(d["over"], p_home, 1 - p_home)
    d["price"] = np.where(d["over"], d[f"over_price_{anchor}"], d[f"under_price_{anchor}"])
    d["fair_ret"] = np.where(d["win"], 1 / d["p_side"] - 1, -1.0)
    d["real_ret"] = np.where(d["win"], d["price"] - 1, -1.0)
    if anchor != spec.ref:
        p_ref = d[f"p_over_{spec.ref}"]
        d["clv_pts"] = np.nan
        d["clv_cents"] = 100 * (np.where(d["over"], p_ref, 1 - p_ref) - d["p_side"])  # NaN where no close
    return d


def _h2h_select(b: pd.DataFrame, t: float) -> pd.DataFrame:
    return b[b["edge"] != 0] if t == 0 else b[b["edge"].abs() > t]


def grading_h2h(pred, w, spec=H2H) -> pd.DataFrame:
    rows = []
    for run, col in (("tuned", "p_model"), ("default", "p_model_default")):
        for anchor in spec.anchors:
            bets = _bets_h2h(pred, w, anchor, col, spec)
            for cut in ("all", "both_10"):
                b = bets if cut == "all" else bets[bets["both_10"]]
                for t in H2H_THRESHOLDS:
                    bt = _h2h_select(b, t)
                    for s in SEASONS:
                        x = bt if s == "pooled" else bt[bt["season"] == s]
                        rows.append({"run": run, "anchor": anchor, "cut": cut, "threshold": t, "season": s,
                                     **_grade(x, anchor, spec)})
    return pd.DataFrame(rows)


def scores(pred, w, p_market_col: str, model_cols=("p_model", "p_model_default")) -> pd.DataFrame:
    """Brier and log loss of each model column and of the market, with paired bootstrap CIs (model − market)."""
    d = pred.merge(w, on="game_id")
    d = d[d[p_market_col].notna()]
    rows = []
    for col in model_cols:
        for s in SEASONS:
            x = d if s == "pooled" else d[d["season"] == s]
            y = x["home_win"].astype(float)
            row = {"model": col, "season": s, "n": len(x)}
            for name, fn in (("brier", metrics.brier), ("log_loss", metrics.log_loss)):
                m, k = fn(x[col], y), fn(x[p_market_col], y)
                row[f"{name}_model"], row[f"{name}_market"] = float(m.mean()), float(k.mean())
                row[f"{name}_diff"] = float((m - k).mean())
                row[f"{name}_lo"], row[f"{name}_hi"] = metrics.bootstrap_mean_ci(m - k)
            row["mae_margin"] = float((x["proj"] - x["actual"]).abs().mean()) if col == "p_model" else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def blend_logistic(pred, w, p_market_col: str) -> pd.DataFrame:
    d = pred.merge(w, on="game_id")
    d = d[d[p_market_col].notna()]
    rows = []
    for run, col in (("tuned", "p_model"), ("default", "p_model_default")):
        for s in SEASONS:
            x = d if s == "pooled" else d[d["season"] == s]
            r = metrics.logistic_regression(x["home_win"].astype(float),
                                            {"market": metrics.logit(x[p_market_col]), "model": metrics.logit(x[col])})
            rows.append({"run": run, "season": s, "n": r["n"],
                         **{f"{k}_{m}": r[k][m] for k in ("const", "market", "model") for m in ("coef", "lo", "hi")}})
    return pd.DataFrame(rows)


def evidence_h2h(g: pd.DataFrame, sc: pd.DataFrame, spec=H2H) -> dict:
    prim = g[(g["run"] == "tuned") & (g["anchor"] == spec.ref) & (g["cut"] == "all") & (g["threshold"] == 0)]
    pooled = prim[prim["season"] == "pooled"].iloc[0]
    per = prim[prim["season"] != "pooled"]
    noon = g[(g["run"] == "tuned") & (g["anchor"] == spec.pretip) & (g["cut"] == "all") & (g["threshold"] == 0)
             & (g["season"] == "pooled")].iloc[0]
    ll = sc[(sc["model"] == "p_model") & (sc["season"] == "pooled")].iloc[0]
    out = {
        "pooled_n": int(pooled["n"]), "pooled_real_roi": pooled["real_roi"], "pooled_real_roi_lo": pooled["real_lo"],
        "c1_real_roi_ci_above_0_on_1000_plus": bool(pooled["real_lo"] > 0 and pooled["n"] >= 1000),
        "c1_win_rate_above_baseline_each_season": bool((per["cover"] > per["baseline"]).all()),
        f"c2_clv_cents_{spec.pretip}_ci_above_0": bool(noon["clv_cents_lo"] > 0),
        "c3_log_loss_below_market_ci": bool(ll["log_loss_hi"] < 0),
    }
    out["edge"] = all(v for k, v in out.items() if k.startswith("c"))
    flags = g[(g["n"] >= 1) & ((g["real_lo"] > 0) | (g.get("clv_cents_lo", pd.Series(dtype=float)) > 0))]
    out["cells_clearing_a_bar"] = flags[["run", "anchor", "cut", "threshold", "season", "n", "cover", "real_roi",
                                         "real_lo", "clv_cents", "clv_cents_lo"]]
    return out


def pinnacle_h2h(pred, odds, base, spec=H2H) -> dict:
    from nbatotals import params as params_io

    pin = odds[(odds["book"] == "pinnacle") & (odds["anchor"] == spec.ref)]
    w = market.wide(market.consensus_h2h(pin, params_io.with_overrides(base, {"market.min_books": 1})))
    bets = _bets_h2h(pred, w, spec.ref, "p_model", spec)
    rows = []
    for t in H2H_THRESHOLDS:
        bt = _h2h_select(bets, t)
        for s in SEASONS:
            x = bt if s == "pooled" else bt[bt["season"] == s]
            rows.append({"threshold": t, "season": s, **_grade(x, spec.ref, spec)})
    return {"bets": pd.DataFrame(rows), "scores": scores(pred, w, f"p_over_{spec.ref}", ("p_model",)),
            "regression": blend_logistic(pred, w, f"p_over_{spec.ref}")}


def run_h2h(pred, fits, odds, games, base, sane: dict, spec=H2H) -> dict:
    cons = market.consensus_h2h(odds, base)
    cons, dropped = market.enforce_anchor_order(cons, spec.ref)
    w = market.wide(cons)
    g = grading_h2h(pred, w, spec)
    sc = scores(pred, w, f"p_over_{spec.ref}")
    by_anchor = []
    for a in spec.anchors:
        x = scores(pred, w, f"p_over_{a}", ("p_model",))
        by_anchor.append(x[x["season"] == "pooled"].assign(anchor=a))
    res = {"market": "h2h", "spec": spec, "labels": spec.labels, "fits": fits, "pred": pred, "grading": g,
           "order_dropped": dropped, "sanity": sane, "scores": sc, "scores_by_anchor": pd.concat(by_anchor),
           "regression": blend_logistic(pred, w, f"p_over_{spec.ref}"), "evidence": evidence_h2h(g, sc, spec)}
    if (odds["book"] == "pinnacle").any():
        res["pinnacle"] = pinnacle_h2h(pred, odds, base, spec)
    return res


# --------------------------------------------------------------------------- markdown

def sanity_markdown(sane: dict, labels: dict) -> str:
    sp = _table(["season", "anchor", "games", "books (median)", "mean home spread", "mean p_home_cover",
                 "MAE vs actual margin", "RMSE", "mean error (actual − implied)"],
                [[season_label(r.season), labels[r.anchor], f"{r.games:,}", f"{r.books_median:.0f}",
                  f"{r.home_spread_mean:+.2f}", f"{r.p_home_cover_mean:.3f}", f"{r.mae:.2f}", f"{r.rmse:.2f}",
                  f"{r.mean_error:+.2f}"] for r in sane["spreads"].itertuples()])
    ml = _table(["season", "anchor", "games", "books (median)", "mean p_home", "home win rate", "Brier", "log loss"],
                [[season_label(r.season), labels[r.anchor], f"{r.games:,}", f"{r.books_median:.0f}",
                  f"{r.p_home_mean:.3f}", f"{r.home_win_rate:.3f}", f"{r.brier:.4f}", f"{r.log_loss:.4f}"]
                 for r in sane["h2h"].itertuples()])
    fav = _table(["season", "games (spread ≠ 0)", "spread favourite = moneyline favourite"],
                 [[r.season if r.season == "all" else season_label(r.season), f"{r.games:,}", f"{r.agreement:.4f}"]
                  for r in sane["favourite"].itertuples()])

    def pair(df, d):
        return _table(["earlier bucket", "season", "games with both", "earlier − true close (95% CI)"],
                      [[r.anchor, r.season if r.season == "all" else season_label(r.season), f"{r.games:,}",
                        f"{r.diff:+.{d}f} ({r.lo:+.{d}f} to {r.hi:+.{d}f})"] for r in df.itertuples()])

    checks = _table(["stop rule (grading proceeds only if every row passes)", "value", "passes"],
                    [[k, v, "yes" if ok else "**NO**"] for k, (v, ok) in sane["checks"].items()])
    return "\n\n".join([
        "### Stop rules", checks,
        "### Spreads consensus by bucket (scored games, 2021-22 to 2024-25)", sp,
        "### Moneyline consensus by bucket", ml,
        "### Cross-market: favourite agreement at the true close", fav,
        "### Spread MAE vs actual margin, paired: earlier bucket minus true close (same games)",
        pair(sane["mae_pairs"], 3),
        "### Moneyline log loss, paired: earlier bucket minus true close (same games)", pair(sane["ll_pairs"], 4),
    ])


def fit_markdown(fits: pd.DataFrame) -> str:
    extra = [c for c in ("margin_k", "train_rmse_margin") if c in fits]
    rows = [[season_label(r["test_season"]), r["trained_on"], f"{int(r['train_n']):,}"]
            + [f"{r[c]:.3f}" for c in extra]
            + [f"{r['h']:+.2f}", f"{r['s']:.2f}", f"{r['train_rmse']:.2f}", f"{r['h_default']:+.2f}",
               f"{r['s_default']:.2f}", f"{r['test_mae']:.2f}", f"{r['test_rmse']:.2f}", f"{r['test_mae_default']:.2f}",
               f"{int(r['test_n']):,}"] for _, r in fits.iterrows()]
    return _table(["test season", "trained on", "train n"] + [c.replace("_", " ") for c in extra]
                  + ["h (tuned)", "logistic scale s (tuned)", "train margin RMSE", "h (default)", "s (default)",
                     "test margin MAE (tuned)", "test margin RMSE (tuned)", "test margin MAE (default)", "test n"],
                  rows)


def _counts(res: dict) -> str:
    counts = dict(res.get("anchor_counts") or {})
    counts["consensus_rows_captured_at_or_after_the_reference"] = res.get("order_dropped", 0)
    return _table(["count", "value"], [[k, f"{v:,}"] for k, v in counts.items()])


def _bars(ev: dict) -> str:
    return _table(["criterion", "met"], [[k, v] for k, v in ev.items() if k != "cells_clearing_a_bar"])


def spreads_report(res: dict) -> str:
    spec = res["spec"]
    ev = res["evidence"]
    flagged = ev["cells_clearing_a_bar"]
    flagged_rows = [[x.run, spec.labels[x.anchor], x.cut, x.threshold, season_label(x.season), f"{int(x.n):,}",
                     f"{_pct(x.cover)} (lo {_pct(x.cover_lo)})",
                     "n/a" if pd.isna(x.clv_pts) else f"{x.clv_pts:+.2f} (lo {x.clv_lo:+.2f})"]
                    for x in flagged.itertuples()]
    raw = _table(["season", "n", "cover (95% Wilson)", "fair ROI (95% CI)", "real ROI (95% CI)"],
                 [[season_label(x.season), f"{int(x.n):,}", f"{_pct(x.cover)} ({_pct(x.cover_lo)}–{_pct(x.cover_hi)})",
                   f"{_pct(x.fair_roi)} ({_pct(x.fair_lo)} to {_pct(x.fair_hi)})",
                   f"{_pct(x.real_roi)} ({_pct(x.real_lo)} to {_pct(x.real_hi)})"] for x in res["raw"].itertuples()])
    r, lo, hi, n = res["model_line_corr"]
    parts = [
        f"Spreads, projector `{res['projector']}`. Pre-registered in "
        "[PREREGISTRATION.md](PREREGISTRATION.md). \"Line\" below is the home margin the market implies "
        "(minus the home spread); \"over\"/cover means the home side covers.",
        "## Anchor construction counts", _counts(res),
        "## Market sanity (before grading)", sanity_markdown(res["sanity"], spec.labels),
        "## Walk-forward fit (margin calibration on earlier seasons only)", fit_markdown(res["fits"]),
        f"Correlation of the model margin with the true-close implied margin: {r:+.3f} ({lo:+.3f}, {hi:+.3f}), "
        f"n = {n:,}.",
        f"## Headline (primary cell: tuned model, {spec.labels[spec.ref]}, every game)", backtest.headline_table(res),
        "### Secondary: raw margin without the fitted home-court constant (h = 0)", raw,
        f"## CLV by anchor (tuned model, every game, all bets), measured to {spec.labels[spec.ref]}",
        backtest.clv_table(res),
        *([f"## Pinnacle only: tuned model against Pinnacle's own {spec.labels[spec.ref]} spread and price",
           backtest.pinnacle_table(res)] if "pinnacle" in res else []),
        "## Projection accuracy (model margin and implied margin vs actual margin)", backtest.accuracy_table(res),
        f"## Market + model blend regression: actual margin = a + b·{spec.ref} implied margin + c·model margin",
        backtest.regression_table(res),
        "## Does the model's edge predict the line move?", backtest.edge_move_table(res),
        "## Pre-registered evidence bar", _bars(ev),
        "## Cells clearing a bar (cover lower bound above 52.38% or CLV lower bound above 0)",
        _table(["run", "anchor", "cut", "edge ≥", "season", "n", "cover", "CLV pts"], flagged_rows)
        if flagged_rows else "None.",
        "## All cells, tuned model, every game", backtest.grading_table(res, "tuned", "all"),
        "## All cells, tuned model, both teams 10+ games", backtest.grading_table(res, "tuned", "both_10"),
        "## All cells, default parameters, every game", backtest.grading_table(res, "default", "all"),
    ]
    return "\n\n".join(parts) + "\n"


def _scores_table(sc: pd.DataFrame) -> str:
    return _table(["model", "season", "n", "Brier model", "Brier market", "Brier model − market (95% CI)",
                   "log loss model", "log loss market", "log loss model − market (95% CI)"],
                  [[x.model, season_label(x.season), f"{x.n:,}", f"{x.brier_model:.4f}", f"{x.brier_market:.4f}",
                    f"{x.brier_diff:+.4f} ({x.brier_lo:+.4f} to {x.brier_hi:+.4f})", f"{x.log_loss_model:.4f}",
                    f"{x.log_loss_market:.4f}",
                    f"{x.log_loss_diff:+.4f} ({x.log_loss_lo:+.4f} to {x.log_loss_hi:+.4f})"]
                   for x in sc.itertuples()])


def _logit_table(r: pd.DataFrame, ref_label: str) -> str:
    return _table(["model run", "season", "n", "intercept (95% CI)", f"market logit, {ref_label} (95% CI)",
                   "model logit (95% CI)"],
                  [[x.run, season_label(x.season), f"{x.n:,}",
                    f"{x.const_coef:+.3f} ({x.const_lo:+.3f}, {x.const_hi:+.3f})",
                    f"{x.market_coef:.3f} ({x.market_lo:.3f}, {x.market_hi:.3f})",
                    f"{x.model_coef:+.3f} ({x.model_lo:+.3f}, {x.model_hi:+.3f})"] for x in r.itertuples()])


def _bets_rows(g: pd.DataFrame, labels: dict, ref: str, with_anchor=True) -> list:
    rows = []
    for c in g.itertuples():
        clv = "n/a" if getattr(c, "anchor", ref) == ref or pd.isna(getattr(c, "clv_cents", np.nan)) else (
            f"{c.clv_cents:+.2f}¢ ({c.clv_cents_lo:+.2f}, {c.clv_cents_hi:+.2f})")
        rows.append(([labels[c.anchor]] if with_anchor else []) + [
            f"{100 * c.threshold:.0f}%", season_label(c.season), f"{int(c.n):,}",
            f"{_pct(c.cover)} ({_pct(c.cover_lo)}–{_pct(c.cover_hi)})", _pct(c.baseline),
            f"{_pct(c.fair_roi)} ({_pct(c.fair_lo)}, {_pct(c.fair_hi)})",
            f"{_pct(c.real_roi)} ({_pct(c.real_lo)}, {_pct(c.real_hi)})"] + ([clv] if with_anchor else []))
    return rows


def h2h_headline(res: dict) -> str:
    spec = res["spec"]
    g = res["grading"]
    sc = res["scores"]
    rows = []
    for s in SEASONS:
        primary = (g.run == "tuned") & (g.cut == "all") & (g.threshold == 0) & (g.season == s)
        c = g[primary & (g.anchor == spec.ref)].iloc[0]
        x = sc[(sc.model == "p_model") & (sc.season == s)].iloc[0]
        row = [season_label(s), f"{int(c.n):,}", f"{x.log_loss_model:.4f} vs {x.log_loss_market:.4f}",
               f"{x.log_loss_diff:+.4f} ({x.log_loss_lo:+.4f} to {x.log_loss_hi:+.4f})",
               f"{_pct(c.cover)} ({_pct(c.cover_lo)}–{_pct(c.cover_hi)})", _pct(c.baseline),
               f"{_pct(c.fair_roi)} ({_pct(c.fair_lo)} to {_pct(c.fair_hi)})",
               f"{_pct(c.real_roi)} ({_pct(c.real_lo)} to {_pct(c.real_hi)})"]
        for a in spec.headline_clv:
            o = g[primary & (g.anchor == a)].iloc[0]
            row += [f"{o.clv_cents:+.2f}¢ ({o.clv_cents_lo:+.2f} to {o.clv_cents_hi:+.2f})"]
        rows.append(row)
    head = ["season", "bets", "log loss model vs market", "difference (95% CI)", "win rate (95% Wilson)",
            "no-info baseline", "fair ROI (95% CI)", "real ROI (95% CI)"]
    head += [f"CLV {a} → {spec.ref}, cents (95% CI)" for a in spec.headline_clv]
    return _table(head, rows)


def h2h_report(res: dict) -> str:
    spec = res["spec"]
    labels = spec.labels
    g = res["grading"]
    ev = res["evidence"]
    bet_head = ["anchor", "edge >", "season", "n", "win rate (95% Wilson)", "baseline", "fair ROI (CI)",
                "real ROI (CI)", "CLV to true close, cents (CI)"]
    clv = g[(g.run == "tuned") & (g.cut == "all") & (g.threshold == 0) & (g.anchor != spec.ref)]
    thr = g[(g.run == "tuned") & (g.cut == "all") & (g.anchor == spec.ref)]
    sba = res["scores_by_anchor"]
    by_anchor = _table(["market at", "n", "log loss model", "log loss market", "model − market (95% CI)",
                        "Brier market"],
                       [[labels[x.anchor], f"{x.n:,}", f"{x.log_loss_model:.4f}", f"{x.log_loss_market:.4f}",
                         f"{x.log_loss_diff:+.4f} ({x.log_loss_lo:+.4f} to {x.log_loss_hi:+.4f})",
                         f"{x.brier_market:.4f}"]
                        for x in sba.itertuples()])
    flagged = ev["cells_clearing_a_bar"]
    flagged_rows = [[x.run, labels[x.anchor], x.cut, f"{100 * x.threshold:.0f}%", season_label(x.season),
                     f"{int(x.n):,}",
                     f"{_pct(x.real_roi)} (lo {_pct(x.real_lo)})",
                     "n/a" if pd.isna(x.clv_cents) else f"{x.clv_cents:+.2f}¢ (lo {x.clv_cents_lo:+.2f})"]
                    for x in flagged.itertuples()]
    parts = [
        f"Moneyline, projector `{res['projector']}`. Pre-registered in [PREREGISTRATION.md](PREREGISTRATION.md). "
        "Probabilities are the home team's; a bet is on home if the model's probability is above the market's "
        "devigged probability, away if below.",
        "## Anchor construction counts", _counts(res),
        "## Market sanity (before grading)", sanity_markdown(res["sanity"], labels),
        "## Walk-forward fit (margin calibration on earlier seasons only)", fit_markdown(res["fits"]),
        f"## Headline (primary cell: tuned model, {labels[spec.ref]}, every game with a non-zero edge)",
        h2h_headline(res),
        f"## Probability scores against the {labels[spec.ref]} consensus", _scores_table(res["scores"]),
        "### Model vs the market at each bucket (pooled, tuned)", by_anchor,
        "## Market + model blend: logistic regression of home win on logit(market) and logit(model)",
        _logit_table(res["regression"], labels[spec.ref]),
        f"## Betting the side the model favours at {labels[spec.ref]}, by threshold (tuned, every game)",
        _table(bet_head, _bets_rows(thr, labels, spec.ref)),
        f"## CLV by anchor (tuned, every game, threshold 0), measured to {labels[spec.ref]}",
        _table(bet_head, _bets_rows(clv, labels, spec.ref)),
    ]
    if "pinnacle" in res:
        p = res["pinnacle"]
        parts += [f"## Pinnacle only: tuned model against Pinnacle's own {labels[spec.ref]} devigged probability "
                  "and price",
                  _scores_table(p["scores"]), _logit_table(p["regression"], "Pinnacle " + labels[spec.ref]),
                  _table(bet_head[1:-1], _bets_rows(p["bets"], labels, spec.ref, with_anchor=False))]
    parts += [
        "## Pre-registered evidence bar", _bars(ev),
        "## Cells clearing a bar (real ROI lower bound above 0 or CLV lower bound above 0)",
        _table(["run", "anchor", "cut", "edge >", "season", "n", "real ROI", "CLV cents"], flagged_rows)
        if flagged_rows else "None.",
        "## All cells, tuned model, every game",
        _table(bet_head, _bets_rows(g[(g.run == "tuned") & (g.cut == "all")], labels, spec.ref)),
        "## All cells, tuned model, both teams 10+ games",
        _table(bet_head, _bets_rows(g[(g.run == "tuned") & (g.cut == "both_10")], labels, spec.ref)),
        "## All cells, default parameters, every game",
        _table(bet_head, _bets_rows(g[(g.run == "default") & (g.cut == "all")], labels, spec.ref)),
    ]
    return "\n\n".join(parts) + "\n"


def stopped_report(market_type: str, projector: str, sane: dict, labels: dict) -> str:
    return (f"{market_type}, projector `{projector}`.\n\n**Grading stopped: a pre-registered sanity stop rule "
            "failed.** Nothing was graded.\n\n" + sanity_markdown(sane, labels) + "\n")
