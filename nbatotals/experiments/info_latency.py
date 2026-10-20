"""Experiment 2, Phase C: the information-latency report.

Every number comes from the harness's own grading functions
(nbatotals/evaluate/backtest.py: `_bets`, `_grade`, `edge_vs_move`,
`blend_regression`, `pinnacle_grading`) applied to walk-forward predictions, so
a cell here equals the same cell in a `backtest --legacy --model ...` report.

Needs the walk-forward fits cached by `python -m nbatotals backtest --legacy
--model <name>` for pace_eff, elo_total, league_avg and lineup_pace_eff
(data/fit_cache*.pkl), and the env vars listed in
nbatotals/evaluate/adapters/legacy_players.py. Run:

    python -m nbatotals.experiments.info_latency [--out docs/experiments/info_latency/report.md]
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nbatotals import params as P
from nbatotals.evaluate import backtest, market, metrics
from nbatotals.evaluate.backtest import TEST_SEASONS, TRUE_CLOSE as SPEC, _table, season_label

ROOT = Path(__file__).resolve().parents[2]
MODELS = ("lineup_pace_eff", "pace_eff", "elo_total", "league_avg")
PLACEBO = "lineup_prev_minutes"
SEASONS = list(TEST_SEASONS) + ["pooled"]


def _cache(name: str) -> Path:
    suffix = "" if name == "pace_eff" else f"_{name}"
    return ROOT / "data" / f"fit_cache{suffix}.pkl"


def load_market(games, base) -> tuple[pd.DataFrame, pd.DataFrame]:
    from nbatotals.evaluate.adapters import legacy_multiregion

    path = ROOT / "data" / "exp2_quotes.pkl"
    if path.exists():
        quotes = pickle.loads(path.read_bytes())
    else:
        quotes, _ = legacy_multiregion.anchor_quotes(legacy_multiregion.read_files(), games)
        path.write_bytes(pickle.dumps(quotes))
    cons = market.consensus(quotes, base)
    cons, _ = market.enforce_anchor_order(cons, SPEC.ref)
    return quotes, market.wide(cons)


# --------------------------------------------------------------------------- cells

def cells(pred: pd.DataFrame, w: pd.DataFrame, anchors=SPEC.anchors, col: str = "proj") -> pd.DataFrame:
    """Threshold-0, every-game cells per anchor and season, exactly as `backtest.grading` builds them."""
    rows = []
    for a in anchors:
        b = backtest._bets(pred, w, a, col, SPEC)
        b = b[b["edge"] != 0]
        for s in SEASONS:
            x = b if s == "pooled" else b[b["season"] == s]
            rows.append({"anchor": a, "season": s, **backtest._grade(x, a, SPEC)})
    return pd.DataFrame(rows)


def clv_by_side(pred, w, anchors=SPEC.clv_from) -> pd.DataFrame:
    rows = []
    for a in anchors:
        b = backtest._bets(pred, w, a, "proj", SPEC)
        b = b[(b["edge"] != 0) & b["clv_pts"].notna()]
        for side, x in (("over", b[b["over"]]), ("under", b[~b["over"]])):
            lo, hi = metrics.bootstrap_mean_ci(x["clv_pts"])
            rows.append({"anchor": a, "side": side, "n": len(x), "clv": float(x["clv_pts"].mean()), "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def paired_clv(pa, pb, w, anchors=SPEC.clv_from) -> pd.DataFrame:
    """Per-game CLV of model a minus model b on the games both bet (threshold 0)."""
    rows = []
    for a in anchors:
        ba = backtest._bets(pa, w, a, "proj", SPEC)
        bb = backtest._bets(pb, w, a, "proj", SPEC)
        m = ba[ba["edge"] != 0][["game_id", "season", "clv_pts"]].merge(
            bb[bb["edge"] != 0][["game_id", "clv_pts"]], on="game_id", suffixes=("_a", "_b")).dropna()
        d = m["clv_pts_a"] - m["clv_pts_b"]
        for s in SEASONS:
            x = d if s == "pooled" else d[m["season"] == s]
            lo, hi = metrics.bootstrap_mean_ci(x)
            rows.append({"anchor": a, "season": s, "n": len(x), "diff": float(x.mean()), "lo": lo, "hi": hi,
                         "same_side_share": float((np.sign(m.loc[x.index, "clv_pts_a"]) ==
                                                   np.sign(m.loc[x.index, "clv_pts_b"])).mean())})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- lineup-change groups and placebo

def player_minutes(games):
    """DnT rows joined to regular-season games with matched actual minutes and previous-game minutes."""
    from nbatotals.evaluate.adapters import legacy_players as LP
    from nbatotals.experiments import info_latency_gate as G

    box = LP.read_player_box()
    d, _ = G.minutes_frame(LP.read_dnt_box(), box, games)
    m = d[d["matched"]].copy()
    m["prev"] = G._prev_game_minutes(m)
    return d, m


def lineup_change_games(m: pd.DataFrame) -> pd.DataFrame:
    """Per game: did either team's DnT lineup differ materially from its previous game's actual minutes?"""
    k = m[m["prev"].notna()]
    flag = ((k["p_mp"] < 5) & (k["prev"] >= 25)) | ((k["p_mp"] >= 25) & (k["prev"] < 5))
    g = k.assign(flag=flag).groupby("game_id")["flag"].any()
    return g.rename("lineup_change").reset_index()


def placebo_inputs(inputs, d: pd.DataFrame, m: pd.DataFrame):
    """DnT minutes replaced by each player's actual minutes in his team's previous game.

    Rows with no known previous game (first game of a season, unmatched players)
    keep DnT's p_mp, so the placebo is slightly conservative."""
    prev = m[["game_id_dnt", "player_id", "prev"]].dropna()
    rep = inputs.dnt[["game_id", "player_id", "p_mp"]].merge(
        prev.rename(columns={"game_id_dnt": "game_id"}), on=["game_id", "player_id"], how="left")
    rep["p_mp"] = rep["prev"].where(rep["prev"].notna(), rep["p_mp"])
    graded = rep["game_id"].isin(set(d["game_id_dnt"]))  # rows of regular-season games 2021-22 to 2024-25
    return inputs.with_minutes(rep[["game_id", "player_id", "p_mp"]]), float(rep.loc[graded, "prev"].notna().mean())


# --------------------------------------------------------------------------- report

def _pct(x):
    return backtest._pct(x)


def _ci(v, lo, hi, d=2):
    return f"{v:+.{d}f} ({lo:+.{d}f} to {hi:+.{d}f})"


def clv_compare_table(c: dict, seasons=("pooled",)) -> str:
    rows = []
    for a in SPEC.clv_from:
        for s in seasons:
            row = [SPEC.labels[a], season_label(s)]
            for name in c:
                x = c[name]
                x = x[(x["anchor"] == a) & (x["season"] == s)].iloc[0]
                row.append(f"{_ci(x.clv_pts, x.clv_lo, x.clv_hi)} n={int(x.clv_n):,}")
            rows.append(row)
    return _table(["bet struck at", "season"] + [f"{n}: CLV pts (95% CI)" for n in c], rows)


def edge_move_compare(em: dict) -> str:
    rows = []
    for a in SPEC.clv_from:
        for s in SEASONS:
            row = [SPEC.labels[a], season_label(s)]
            for name in em:
                x = em[name]
                x = x[(x["anchor"] == a) & (x["season"] == s)].iloc[0]
                row.append(f"{x.r:+.3f} ({x.lo:+.3f}, {x.hi:+.3f})")
            rows.append(row)
    return _table(["bet anchor", "season"] + [f"{n}: corr (95% CI)" for n in em], rows)


def headline_compare(c: dict) -> str:
    rows = []
    for name, x in c.items():
        for s in SEASONS:
            r = x[(x["anchor"] == SPEC.ref) & (x["season"] == s)].iloc[0]
            rows.append([name, season_label(s), f"{int(r.n):,}", f"{_pct(r.cover)} ({_pct(r.cover_lo)}–{_pct(r.cover_hi)})",
                         _pct(r.baseline), f"{_pct(r.fair_roi)} ({_pct(r.fair_lo)} to {_pct(r.fair_hi)})",
                         f"{_pct(r.real_roi)} ({_pct(r.real_lo)} to {_pct(r.real_hi)})"])
    return _table(["projector", "season", f"n ({SPEC.labels[SPEC.ref]})", "cover (95% Wilson)", "no-info baseline",
                   "fair ROI (95% CI)", "real ROI (95% CI)"], rows)


def cover_at_anchor_table(c: dict, anchors=("opening", "noon")) -> str:
    rows = []
    for name, x in c.items():
        for a in anchors:
            for s in SEASONS:
                r = x[(x["anchor"] == a) & (x["season"] == s)].iloc[0]
                rows.append([name, SPEC.labels[a], season_label(s), f"{int(r.n):,}",
                             f"{_pct(r.cover)} ({_pct(r.cover_lo)}–{_pct(r.cover_hi)})",
                             f"{_pct(r.real_roi)} ({_pct(r.real_lo)} to {_pct(r.real_hi)})"])
    return _table(["projector", "bet struck at", "season", "n", "cover vs that anchor's consensus (95% Wilson)",
                   "real ROI at that anchor (95% CI)"], rows)


def pinnacle_anchor_table(pins: dict) -> str:
    rows = []
    for (name, a), p in pins.items():
        for x in p[p["threshold"] == 0].itertuples():
            rows.append([name, SPEC.labels[a], season_label(x.season), f"{int(x.n):,}", int(x.pushes),
                         f"{_pct(x.cover)} ({_pct(x.cover_lo)}–{_pct(x.cover_hi)})", _pct(x.baseline),
                         f"{_pct(x.fair_roi)} ({_pct(x.fair_lo)} to {_pct(x.fair_hi)})",
                         f"{_pct(x.real_roi)} ({_pct(x.real_lo)} to {_pct(x.real_hi)})"])
    return _table(["projector", "Pinnacle anchor", "season", "n", "pushes", "cover vs Pinnacle's line (95% Wilson)",
                   "baseline", "fair ROI at Pinnacle's devigged price", "ROI at Pinnacle's own price"], rows)


def group_table(gc: dict) -> str:
    rows = []
    for (name, grp), x in gc.items():
        for a in ("opening", "noon", "afternoon", "near_close"):
            for s in SEASONS:
                r = x[(x["anchor"] == a) & (x["season"] == s)].iloc[0]
                rows.append([name, grp, SPEC.labels[a], season_label(s), f"{int(r.clv_n):,}",
                             _ci(r.clv_pts, r.clv_lo, r.clv_hi), f"{_pct(r.cover)}", _pct(r.real_roi)])
    return _table(["projector", "games", "bet struck at", "season", "bets", "CLV to true close, pts (95% CI)",
                   "cover at that anchor", "real ROI at that anchor"], rows)


def side_table(sides: dict) -> str:
    rows = [[name, SPEC.labels[x.anchor], x.side, f"{x.n:,}", _ci(x.clv, x.lo, x.hi)]
            for name, t in sides.items() for x in t.itertuples() if x.anchor in ("opening", "noon")]
    return _table(["projector", "bet struck at", "side", "bets", "CLV pts (95% CI)"], rows)


def paired_table(p: pd.DataFrame) -> str:
    rows = [[SPEC.labels[x.anchor], season_label(x.season), f"{x.n:,}", _ci(x.diff, x.lo, x.hi),
             f"{x.same_side_share:.3f}"] for x in p.itertuples()]
    return _table(["bet struck at", "season", "games both bet", "CLV lineup − pace_eff, pts (95% CI)",
                   "share of games on the same side"], rows)


def bias_table(preds: dict) -> str:
    rows = []
    for name, p in preds.items():
        row = [name]
        for s in SEASONS:
            x = p if s == "pooled" else p[p["season"] == s]
            e = x["proj"] - x["actual"]
            row.append(f"{e.mean():+.2f} / {np.sqrt((e ** 2).mean()):.2f}")
        rows.append(row)
    return _table(["projector"] + [f"{season_label(s)}: mean error / RMSE" for s in SEASONS], rows)


def run(out: Path) -> dict:
    from nbatotals.evaluate.adapters import legacy_nba_db
    from nbatotals.features.players import PlayerInputs
    from nbatotals.model.lineup_pace_eff import LineupPaceEff

    base = P.load()
    frames = legacy_nba_db.load()
    games, box = frames["games"], frames["team_box"].drop(columns=["legacy_pace"])
    quotes, w = load_market(games, base)
    fitted = {}
    for name in MODELS:
        if not _cache(name).exists():
            raise FileNotFoundError(f"{_cache(name)}: run `python -m nbatotals backtest --legacy --model {name}` first")
        fitted[name] = pickle.loads(_cache(name).read_bytes())
    preds = {n: f[0] for n, f in fitted.items()}

    # placebo: same projector, DnT minutes replaced by previous-game actual minutes
    d, m = player_minutes(games)
    pcache = ROOT / "data" / f"fit_cache_{PLACEBO}.pkl"
    inputs = PlayerInputs.from_env()
    pin_inputs, replaced = placebo_inputs(inputs, d, m)
    if pcache.exists():
        fitted[PLACEBO] = pickle.loads(pcache.read_bytes())
    else:
        fitted[PLACEBO] = backtest.predictions(games, box, base, projector=LineupPaceEff(pin_inputs))
        pcache.write_bytes(pickle.dumps(fitted[PLACEBO]))
    preds[PLACEBO] = fitted[PLACEBO][0]

    c = {n: cells(p, w) for n, p in preds.items()}
    em = {n: backtest.edge_vs_move(p, w, SPEC) for n, p in preds.items()}
    pins = {(n, a): backtest.pinnacle_grading(preds[n], quotes, base, SPEC, anchor=a)
            for n in ("lineup_pace_eff", "pace_eff") for a in ("opening", "noon", "true_close")}
    reg = backtest.blend_regression(preds["lineup_pace_eff"], w, SPEC)
    both = preds["lineup_pace_eff"].merge(preds["pace_eff"][["game_id", "proj"]], on="game_id", suffixes=("", "_pe"))
    both = both.merge(w[["game_id", f"line_{SPEC.ref}"]], on="game_id").dropna(subset=[f"line_{SPEC.ref}"])
    reg3 = metrics.ols(both["actual"], {"close": both[f"line_{SPEC.ref}"], "pace_eff": both["proj_pe"],
                                        "lineup": both["proj"]})
    groups = lineup_change_games(m)
    gc = {}
    for name in ("lineup_pace_eff", "pace_eff", PLACEBO):
        p = preds[name].merge(groups, on="game_id", how="left")
        for label, sel in (("lineup change", p["lineup_change"] == True),  # noqa: E712
                           ("no change", p["lineup_change"] == False)):  # noqa: E712
            gc[(name, label)] = cells(p[sel].drop(columns="lineup_change"), w)
    sides = {n: clv_by_side(preds[n], w) for n in ("lineup_pace_eff", "pace_eff")}
    paired = paired_clv(preds["lineup_pace_eff"], preds["pace_eff"], w)
    lp = c["lineup_pace_eff"]
    lb = lambda a: lp[(lp["anchor"] == a) & (lp["season"] == "pooled")].iloc[0]["clv_lo"]
    info = {"I1 opening CLV lower bound > +0.39": bool(lb("opening") > 0.39),
            "I2 noon CLV lower bound > 0": bool(lb("noon") > 0)}
    edge_res = backtest.evidence(_grading_for_evidence(preds["lineup_pace_eff"], w), SPEC)
    res = dict(c=c, em=em, pins=pins, reg=reg, reg3=reg3, gc=gc, sides=sides, paired=paired, info=info,
               edge=edge_res, preds=preds, fits=fitted["lineup_pace_eff"][1], replaced=replaced,
               groups=groups.merge(preds["lineup_pace_eff"][["game_id", "season"]], on="game_id"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(res))
    return res


def _grading_for_evidence(pred, w) -> pd.DataFrame:
    """The rows `backtest.evidence` reads (tuned, every game; threshold 0), from the harness grading."""
    rows = []
    for a in SPEC.anchors:
        b = backtest._bets(pred, w, a, "proj", SPEC)
        for t in backtest.THRESHOLDS:
            bt = b[b["edge"] != 0] if t == 0 else b[b["edge"].abs() >= t]
            for s in SEASONS:
                x = bt if s == "pooled" else bt[bt["season"] == s]
                rows.append({"run": "tuned", "anchor": a, "cut": "all", "threshold": t, "season": s,
                             **backtest._grade(x, a, SPEC)})
    return pd.DataFrame(rows)


def markdown(res: dict) -> str:
    c = res["c"]
    four = {n: c[n] for n in MODELS}
    g = res["groups"]
    gcount = g.groupby("season")["lineup_change"].agg(["size", "sum"])
    ev = res["edge"]
    r3 = res["reg3"]
    parts = [
        "# Experiment 2 report (generated)",
        "Generated by `python -m nbatotals.experiments.info_latency`. Tuned models, every game, threshold 0, "
        f"graded against {SPEC.labels[SPEC.ref]} unless a table says otherwise. Interpretation: RESULTS.md.",
        "## lineup_pace_eff walk-forward fit", backtest.fit_table({"fits": res["fits"]}),
        "## Information bar (pre-registered)", _table(["criterion", "met"], [[k, v] for k, v in res["info"].items()]),
        "## Edge bar (main pre-registration), lineup_pace_eff",
        _table(["criterion", "met"], [[k, v] for k, v in ev.items() if k != "cells_clearing_a_bar"]),
        "## 1. CLV by anchor to the true close, pooled", clv_compare_table({**four, PLACEBO: c[PLACEBO]}),
        "## 1b. CLV by anchor to the true close, by season", clv_compare_table(four, seasons=list(TEST_SEASONS)),
        "## 1c. Paired: lineup_pace_eff minus pace_eff, same games", paired_table(res["paired"]),
        "## 2. Edge vs subsequent line move: corr(model − anchor line, true close − anchor line)",
        edge_move_compare({**{n: res["em"][n] for n in MODELS}, PLACEBO: res["em"][PLACEBO]}),
        "## 3. Headline at the true close", headline_compare({**four, PLACEBO: c[PLACEBO]}),
        "## 3b. Cover and ROI against each anchor's own consensus", cover_at_anchor_table(
            {n: c[n] for n in ("lineup_pace_eff", "pace_eff")}),
        "## 3c. Pinnacle only, at the opening, noon and true-close anchors (Pinnacle's own line and price there)",
        pinnacle_anchor_table(res["pins"]),
        "## 4. Blend regression: actual = a + b·true close + c·lineup_pace_eff",
        backtest.regression_table({"spec": SPEC, "regression": res["reg"]}),
        "Three-way, pooled tuned: actual = a + b·close + c1·pace_eff + c2·lineup_pace_eff: " + ", ".join(
            f"{k} {r3[k]['coef']:+.3f} ({r3[k]['lo']:+.3f}, {r3[k]['hi']:+.3f})" for k in ("close", "pace_eff", "lineup"))
        + f"; n = {r3['n']:,}.",
        "## 5. Decomposition: games whose DnT lineup differs materially from the previous game",
        "A game is a lineup change if either team has a player with p_mp < 5 who played 25+ minutes in the team's "
        "previous game, or p_mp ≥ 25 who played under 5 (including absent). Games per season (all / lineup change): "
        + ", ".join(f"{season_label(s)} {int(r['size']):,} / {int(r['sum']):,}" for s, r in gcount.iterrows()) + ".",
        group_table(res["gc"]),
        "## 6. Drift check: CLV by side", side_table(res["sides"]),
        "## 7. Mean error and RMSE of the projection vs the actual total", bias_table(res["preds"]),
        f"Placebo `{PLACEBO}`: DnT minutes replaced by each player's previous-game actual minutes on "
        f"{res['replaced']:.1%} of DnT rows in regular-season games 2021-22 to 2024-25 (the rest, each team's first "
        "game of a season and unmatched players, keep DnT's projection).",
    ]
    return "\n\n".join(parts) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "experiments" / "info_latency" / "report.md"))
    args = ap.parse_args(argv)
    res = run(Path(args.out))
    print(clv_compare_table({**{n: res["c"][n] for n in MODELS}, PLACEBO: res["c"][PLACEBO]}))
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
