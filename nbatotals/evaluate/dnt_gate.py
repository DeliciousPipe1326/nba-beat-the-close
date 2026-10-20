"""Experiment 1, Phase A: are the historical Dunks & Threes projections pre-game?

Tests and thresholds are fixed in docs/experiments/dnt_benchmark/PREREGISTRATION.md
(committed before this ran). Run, maintainer only:

    NBA_LEGACY_DB=... NBA_LEGACY_PROPS_DB=... NBA_DNT_BOX=... python -m nbatotals.evaluate.dnt_gate

It writes docs/experiments/dnt_benchmark/gate_report.md (deterministic).
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from nbatotals.evaluate.adapters import dnt_box, legacy_lake, legacy_nba_db
from nbatotals.teams import BDL_ID_TO_ALIAS

PROPS_ENV_VAR = "NBA_LEGACY_PROPS_DB"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "experiments" / "dnt_benchmark" / "gate_report.md"
SEASONS = (2021, 2022, 2023, 2024)
TEST_SEASONS = (2022, 2023, 2024)

# Pre-registered thresholds (PREREGISTRATION.md, Phase A).
A_PASS, A_FAIL = 0.90, 0.95
B_PASS, B_FAIL = 0.005, 0.002
C_PASS, C_FAIL = 12.0, 6.0
D_MEDIAN_PASS, D_MEDIAN_FAIL = (236.0, 244.0), (225.0, 255.0)
D_OT_PASS, D_OT_FAIL = 2.0, 10.0
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", "", s.replace("-", " "))
    return " ".join(w for w in s.split() if w not in SUFFIXES)


def parse_minutes(v) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
        return 0.0
    s = str(v).strip()
    if ":" in s:
        m, sec = s.split(":", 1)
        return float(m) + float(sec) / 60.0
    return float(s)


def read_bdl_logs(path: str | os.PathLike | None = None) -> pd.DataFrame:
    """BallDontLie player logs (nba_props.db) with names from nba.db's balldontlie_players.

    nba_props.db's own `players` table holds only 569 current players, so it
    loses the names of most 2021-22 to 2023-24 logs; balldontlie_players covers
    every logged player id.
    """
    path = path or os.environ.get(PROPS_ENV_VAR)
    if not path:
        raise RuntimeError(f"set {PROPS_ENV_VAR} to the legacy nba_props.db (BallDontLie player logs)")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        con.execute("ATTACH DATABASE ? AS n", (f"file:{legacy_nba_db.legacy_path()}?mode=ro",))
        df = pd.read_sql_query(
            """SELECT l.game_id, l.game_date, l.season, l.team_id, l.minutes_played,
                      p.first_name || ' ' || p.last_name AS name
               FROM player_game_logs l LEFT JOIN n.balldontlie_players p USING (player_id)""", con)
    finally:
        con.close()
    if df["name"].isna().any():
        raise ValueError("BallDontLie log rows without a player name")
    df["team"] = df["team_id"].map(BDL_ID_TO_ALIAS)
    df["minutes"] = df["minutes_played"].map(parse_minutes)
    df["key"] = df["name"].map(norm_name)
    return df[["game_id", "game_date", "season", "team", "key", "minutes"]]


def build(games: pd.DataFrame, dnt: pd.DataFrame, bdl: pd.DataFrame) -> dict:
    reg = games[(games["status"] == "final") & (games["postseason"] == 0) & games["season"].isin(SEASONS)]
    m = dnt_box.match_games(dnt, reg)
    rows = dnt.merge(m[["date", "game_id", "id"]], on=["date", "game_id"], how="inner")
    rows = rows.merge(reg[["id", "season", "home", "away", "home_pts", "away_pts", "periods"]], on="id")
    rows["key"] = rows["player_name"].map(norm_name)
    rows[["p_mp", "p_pts"]] = rows[["p_mp", "p_pts"]].astype(float)
    no_mp = rows["p_mp"].isna()  # a handful of rows carry no projection at all: kept out of the player tests
    rows = rows.assign(no_mp=no_mp)
    b = bdl[bdl["game_id"].isin(reg["id"])].rename(columns={"game_id": "id"})
    dup_bdl = int(b.duplicated(["id", "team", "key"]).sum())
    b = b.drop_duplicates(["id", "team", "key"])
    p = rows.merge(b[["id", "team", "key", "minutes"]], on=["id", "team", "key"], how="left")
    p["matched"] = p["minutes"].notna()
    on_roster = set(zip(b["season"], b["team"], b["key"]))
    p["matchable"] = [(s, t, k) in on_roster for s, t, k in zip(p["season"], p["team"], p["key"])]
    p["absent"] = ~p["matched"] & p["matchable"]
    p["actual_min"] = np.where(p["matched"], p["minutes"], np.where(p["absent"], 0.0, np.nan))
    # team-game and game level
    team = p.groupby(["id", "season", "team", "home", "home_pts", "away_pts", "periods"], as_index=False).agg(
        p_mp=("p_mp", "sum"), p_pts=("p_pts", "sum"))
    team["actual_pts"] = np.where(team["team"] == team["home"], team["home_pts"], team["away_pts"])
    team["ot"] = team["periods"] > 4
    game = team.groupby(["id", "season"], as_index=False).agg(proj=("p_pts", "sum"), actual=("actual_pts", "sum"),
                                                              ot=("ot", "first"))
    game["err"] = game["actual"] - game["proj"]
    # descriptive: BDL players with >= 20 actual minutes absent from the DnT game rows
    dkeys = set(zip(p["id"], p["team"], p["key"]))
    big = b[(b["minutes"] >= 20) & b["id"].isin(m["id"])]
    big = big.assign(in_dnt=[(i, t, k) in dkeys for i, t, k in zip(big["id"], big["team"], big["key"])])
    return {"players": p, "team": team, "game": game, "big": big, "dup_bdl": dup_bdl,
            "games_joined": m.merge(reg[["id", "season"]], on="id").groupby("season").size(),
            "games_reg": reg.groupby("season").size()}


def _r2(y, x) -> float:
    y, x = np.asarray(y, float), np.asarray(x, float)
    return float(1 - ((y - x) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def stats(d: dict, seasons) -> dict:
    p_all = d["players"][d["players"]["season"].isin(seasons)]
    p = p_all[~p_all["no_mp"]]
    t = d["team"][d["team"]["season"].isin(seasons)]
    g = d["game"][d["game"]["season"].isin(seasons)]
    big = d["big"][d["big"]["season"].isin(seasons)]
    mt = p[p["matched"]]
    p10 = p[p["p_mp"] >= 10]
    hi = p[(p["p_mp"] >= 20) & (p["matched"] | p["absent"])]
    hi_strict = p[(p["p_mp"] >= 20) & p["matched"]]
    ot, rg = g[g["ot"]], g[~g["ot"]]
    d_ot = ot["err"].mean() - rg["err"].mean()
    se = np.sqrt(ot["err"].var() / len(ot) + rg["err"].var() / len(rg))
    return {
        "player_games": len(p), "no_mp": int(p_all["no_mp"].sum()), "matched_share": p["matched"].mean(), "match10_share": p10["matched"].mean(),
        "absent": int(p["absent"].sum()), "unmatched_not_on_roster": int((~p["matched"] & ~p["matchable"]).sum()),
        "a_r2": _r2(mt["minutes"], mt["p_mp"]), "a_corr2": float(np.corrcoef(mt["minutes"].to_numpy(float), mt["p_mp"].to_numpy(float))[0, 1] ** 2),
        "a_n": len(mt), "a_rmse": float(np.sqrt(((mt["minutes"] - mt["p_mp"]) ** 2).mean())),
        "b_share": float((hi["actual_min"] == 0).mean()), "b_n": len(hi), "b_zero": int((hi["actual_min"] == 0).sum()),
        "b_strict": float((hi_strict["minutes"] == 0).mean()), "b_strict_n": len(hi_strict),
        "c_delta": float(d_ot), "c_lo": float(d_ot - 1.96 * se), "c_hi": float(d_ot + 1.96 * se),
        "c_ot_n": len(ot), "c_reg_n": len(rg), "c_ot_err": float(ot["err"].mean()), "c_reg_err": float(rg["err"].mean()),
        "d_median": float(t["p_mp"].median()), "d_p05": float(t["p_mp"].quantile(0.05)),
        "d_p95": float(t["p_mp"].quantile(0.95)),
        "d_reg_mean": float(t.loc[~t["ot"], "p_mp"].mean()), "d_ot_mean": float(t.loc[t["ot"], "p_mp"].mean()),
        "d_ot_diff": float(t.loc[t["ot"], "p_mp"].mean() - t.loc[~t["ot"], "p_mp"].mean()),
        "e_absent_share": float((~big["in_dnt"]).mean()), "e_n": len(big),
        "d_ot_se": float(np.sqrt(t.loc[t["ot"], "p_mp"].var() / t["ot"].sum()
                                 + t.loc[~t["ot"], "p_mp"].var() / (~t["ot"]).sum())),
        "d_sd": float(t["p_mp"].std()), "d_in_230_250": float(t["p_mp"].between(230, 250).mean()),
        "z_n": int(((p["p_mp"] == 0) & (p["matched"] | p["absent"])).sum()),
        "z_played": int(((p["p_mp"] == 0) & (p["actual_min"] > 0)).sum()),
        "f_team_r2": _r2(t["actual_pts"], t["p_pts"]), "game_mae": float(g["err"].abs().mean()),
        "game_bias": float(g["err"].mean()), "games": len(g),
    }


def verdicts(s: dict) -> dict:
    def band(x, ok, bad):
        return "PASS" if ok(x) else ("FAIL" if bad(x) else "ambiguous")

    a = band(s["a_r2"], lambda x: x <= A_PASS, lambda x: x >= A_FAIL)
    b = band(s["b_share"], lambda x: x >= B_PASS, lambda x: x < B_FAIL)
    c = band(s["c_delta"], lambda x: x >= C_PASS, lambda x: x <= C_FAIL)
    med, diff = s["d_median"], s["d_ot_diff"]
    if D_MEDIAN_PASS[0] <= med <= D_MEDIAN_PASS[1] and diff < D_OT_PASS:
        dv = "PASS"
    elif diff >= D_OT_FAIL or not (D_MEDIAN_FAIL[0] <= med <= D_MEDIAN_FAIL[1]):
        dv = "FAIL"
    else:
        dv = "ambiguous"
    v = {"a": a, "b": b, "c": c, "d": dv}
    if all(x == "PASS" for x in v.values()):
        v["season"] = "pre-game"
    elif b == "ambiguous" and a == c == dv == "PASS":
        v["season"] = "pre-game (near tip / active list known)"
    elif "FAIL" in v.values():
        v["season"] = "gate fails"
    else:
        v["season"] = "gate fails (ambiguous)"
    return v


def _lab(s) -> str:
    return s if isinstance(s, str) else f"{s}-{str(s + 1)[-2:]}"


def report(d: dict) -> str:
    cells = [(_lab(s), (s,)) for s in SEASONS] + [("pooled 2022-23 to 2024-25", TEST_SEASONS),
                                                  ("pooled all four", SEASONS)]
    res = [(lab, stats(d, ss)) for lab, ss in cells]
    ver = {lab: verdicts(s) for lab, s in res}
    L = ["# Experiment 1, Phase A: gate report", "",
         "Generated by `python -m nbatotals.evaluate.dnt_gate` (maintainer only). Thresholds are from",
         "[PREREGISTRATION.md](PREREGISTRATION.md), committed before this ran. Regular-season games",
         "(`postseason = 0`), DnT player-games joined to BallDontLie player logs by game, team and",
         "normalised name.", "", "## Join", "",
         "| season | regular-season games | games with DnT rows | DnT player-games (rows without p_mp, excluded) | matched to a BDL row | matched, `p_mp ≥ 10` | on roster but absent (counted as 0 min) | unmatched, not on roster |",
         "|---|---|---|---|---|---|---|---|"]
    for lab, s in res:
        if lab.startswith("pooled"):
            continue
        season = int(lab[:4])
        L.append(f"| {lab} | {d['games_reg'].get(season, 0):,} | {d['games_joined'].get(season, 0):,} | "
                 f"{s['player_games']:,} ({s['no_mp']}) | {s['matched_share']:.1%} | {s['match10_share']:.1%} | {s['absent']:,} | "
                 f"{s['unmatched_not_on_roster']:,} |")
    L += ["", f"Duplicate (game, team, name) rows in the BDL logs, dropped: {d['dup_bdl']}.", "",
          "## The four tests", "",
          "| cell | (a) R² p_mp vs actual min (r²; RMSE; n) | (b) p_mp ≥ 20 with 0 actual min (strict: listed with 0) | (c) OT − regulation error, game total (95% CI; n OT / reg) | (d) Σ p_mp per team: median (5–95%); OT − regulation mean | verdicts a / b / c / d | season verdict |",
          "|---|---|---|---|---|---|---|"]
    for lab, s in res:
        v = ver[lab]
        L.append(
            f"| {lab} | {s['a_r2']:.3f} ({s['a_corr2']:.3f}; {s['a_rmse']:.1f} min; {s['a_n']:,}) | "
            f"{s['b_share']:.2%} = {s['b_zero']:,}/{s['b_n']:,} ({s['b_strict']:.2%} of {s['b_strict_n']:,}) | "
            f"{s['c_delta']:+.1f} ({s['c_lo']:+.1f} to {s['c_hi']:+.1f}; {s['c_ot_n']:,} / {s['c_reg_n']:,}) | "
            f"{s['d_median']:.1f} ({s['d_p05']:.1f}–{s['d_p95']:.1f}); {s['d_ot_diff']:+.2f} | "
            f"{v['a']} / {v['b']} / {v['c']} / {v['d']} | {v['season']} |")
    L += ["", "Thresholds: (a) PASS ≤ 0.90, FAIL ≥ 0.95; (b) PASS ≥ 0.5%, FAIL < 0.2%; (c) PASS ≥ +12, FAIL ≤ +6;",
          "(d) PASS median in [236, 244] and OT difference < 2 min, FAIL OT difference ≥ 10 min or median outside",
          "[225, 255].", "", "## Descriptive (not gating)", "",
          "| cell | mean error (actual − Σ p_pts), OT games | regulation games | game MAE | game bias | team Σ p_pts vs actual team points, R² | BDL players with ≥ 20 actual min absent from the DnT game | Σ p_mp mean, regulation / OT |",
          "|---|---|---|---|---|---|---|---|"]
    for lab, s in res:
        L.append(f"| {lab} | {s['c_ot_err']:+.1f} | {s['c_reg_err']:+.1f} | {s['game_mae']:.2f} | {s['game_bias']:+.2f} | "
                 f"{s['f_team_r2']:.3f} | {s['e_absent_share']:.2%} of {s['e_n']:,} | "
                 f"{s['d_reg_mean']:.1f} / {s['d_ot_mean']:.1f} |")
    L += ["", "## Diagnostics (computed after the decision; not gating)", "",
          "| cell | Σ p_mp per team: SD | share of team-games with Σ p_mp in 230–250 | (d) OT − regulation Σ p_mp (± 1 SE) | players with p_mp = 0 who played |",
          "|---|---|---|---|---|"]
    for lab, s in res:
        L.append(f"| {lab} | {s['d_sd']:.1f} | {s['d_in_230_250']:.1%} | {s['d_ot_diff']:+.2f} ± {s['d_ot_se']:.2f} | "
                 f"{s['z_played']:,} of {s['z_n']:,} ({s['z_played'] / s['z_n']:.2%}) |")
    cells_t = [_lab(s) for s in TEST_SEASONS] + ["pooled 2022-23 to 2024-25"]
    passed = all(ver[c]["season"].startswith("pre-game") for c in cells_t)
    said = "; ".join(f"{c}: {ver[c]['season']} ({', '.join(k for k in 'abcd' if ver[c][k] != 'PASS') or 'all PASS'})"
                     for c in cells_t)
    L += ["", "## Decision", "", f"{said} (in brackets: the tests that did not PASS).", "",
          f"**Gate {'passes' if passed else 'fails'}** under the pre-registered rule.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    old = os.environ.pop(legacy_lake.ENV_VAR, None)
    try:
        games = legacy_nba_db.load()["games"]
    finally:
        if old is not None:
            os.environ[legacy_lake.ENV_VAR] = old
    d = build(games, dnt_box.read_all(), read_bdl_logs())
    md = report(d)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
