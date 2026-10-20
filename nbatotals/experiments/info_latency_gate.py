"""Experiment 2, Phase A: are the Dunks & Threes inputs point-in-time?

Implements the gate pre-registered in docs/experiments/info_latency/PREREGISTRATION.md
(G1: projected minutes; G2: player ratings). Run with
`python -m nbatotals.experiments.info_latency_gate` (needs NBA_LEGACY_DB,
NBA_LEGACY_DNT, NBA_LEGACY_PLAYER_EPM, NBA_LEGACY_PROPS_DB); it prints the
Markdown that GATE.md quotes.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from nbatotals.evaluate.adapters import legacy_players

SEASONS = (2021, 2022, 2023, 2024)
G1_THRESHOLDS = {"g1a_min": 0.005, "g1b_max": 0.90, "g1c_abs_max": 5.0, "g1d_lo": 225.0, "g1d_hi": 255.0,
                 "match_min": 0.90}
G2_THRESHOLDS = {"g2a_max": 0.50, "g2b_after_min": 0.05, "g2b_gap_min": 0.05}


def _season_of_date(games: pd.DataFrame) -> pd.Series:
    return games.drop_duplicates("game_date").set_index("game_date")["season"]


def regular_games(games: pd.DataFrame) -> pd.DataFrame:
    return games[(games["status"] == "final") & (games["postseason"] == 0) & games["season"].isin(SEASONS)]


def minutes_frame(dnt, box, games) -> tuple[pd.DataFrame, dict]:
    """DnT rows for joined regular-season games with the player's actual minutes (matched players)."""
    reg = regular_games(games)
    gmap = legacy_players.dnt_games(dnt, reg)
    d = dnt.merge(gmap[["dnt_game_id", "game_id"]], left_on="game_id", right_on="dnt_game_id",
                  suffixes=("_dnt", ""))
    seasons = _season_of_date(games)
    match = legacy_players.match_players(d.rename(columns={"game_id_dnt": "x"}), box, seasons)
    d["season"] = d["date"].map(seasons)
    d = d.merge(match, on=["season", "team", "player_id"], how="left")
    act = box[["player_id", "game_id", "minutes"]].rename(columns={"player_id": "bdl_player_id"})
    d = d.merge(act, on=["bdl_player_id", "game_id"], how="left")
    d["matched"] = d["bdl_player_id"] >= 0
    d["actual"] = np.where(d["matched"], d["minutes"].fillna(0.0), np.nan)
    info = {"regular_games": len(reg), "dnt_games_joined": int(gmap["game_id"].nunique()),
            "joined_by_season": reg[reg["id"].isin(gmap["game_id"])].groupby("season").size().to_dict(),
            "regular_by_season": reg.groupby("season").size().to_dict()}
    return d, info


def g1(d: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """G1 per season and pooled."""
    periods = games.set_index("id")["periods"]
    rows = []
    for s in list(SEASONS) + ["pooled"]:
        x = d if s == "pooled" else d[d["season"] == s]
        m = x[x["matched"]]
        big = m[m["p_mp"] >= 20]
        small = m[m["p_mp"] < 5]
        r = np.corrcoef(m["p_mp"], m["actual"])[0, 1]
        team = x.groupby(["game_id", "team"])["p_mp"].sum().reset_index()
        team["ot"] = team["game_id"].map(periods) > 4
        # naive alternative: the player's actual minutes in his team's previous game (0 if absent)
        prev = _prev_game_minutes(m)
        ok = prev.notna()
        r_naive = np.corrcoef(prev[ok], m.loc[ok, "actual"])[0, 1]
        rows.append({
            "season": s, "dnt_rows": len(x), "rows_pmp_ge_10": int((x["p_mp"] >= 10).sum()),
            "match_share_pmp_ge_10": float(x.loc[x["p_mp"] >= 10, "matched"].mean()),
            "g1a_n": len(big), "g1a_share_played_0": float((big["actual"] == 0).mean()),
            "g1b_r2": float(r * r), "g1b_n": len(m),
            "g1c_ot_minus_reg": float(team.loc[team["ot"], "p_mp"].mean() - team.loc[~team["ot"], "p_mp"].mean()),
            "g1c_ot_team_games": int(team["ot"].sum()),
            "g1d_mean_team_sum_reg": float(team.loc[~team["ot"], "p_mp"].mean()),
            "team_sum_sd_reg": float(team.loc[~team["ot"], "p_mp"].std()),
            "reverse_share_pmp_lt5_played_25": float((small["actual"] >= 25).mean()), "reverse_n": len(small),
            "naive_prev_game_r2": float(r_naive * r_naive), "naive_n": int(ok.sum()),
            "naive_same_rows_pmp_r2": float(np.corrcoef(m.loc[ok, "p_mp"], m.loc[ok, "actual"])[0, 1] ** 2),
        })
    return pd.DataFrame(rows)


def _prev_game_minutes(m: pd.DataFrame) -> pd.Series:
    """Actual minutes of the player in his team's previous game this season (0 if he did not play)."""
    team_games = m[["season", "team", "date", "game_id"]].drop_duplicates().sort_values(["season", "team", "date"])
    team_games["prev_game"] = team_games.groupby(["season", "team"])["game_id"].shift(1)
    x = m[["season", "team", "game_id", "bdl_player_id"]].merge(
        team_games[["season", "team", "game_id", "prev_game"]], on=["season", "team", "game_id"], how="left")
    played = m[["game_id", "bdl_player_id", "actual"]].rename(columns={"game_id": "prev_game", "actual": "prev"})
    x = x.merge(played, on=["prev_game", "bdl_player_id"], how="left")
    prev = np.where(x["prev_game"].isna(), np.nan, x["prev"].fillna(0.0))
    return pd.Series(prev, index=m.index)


def absence_anticipation(d: pd.DataFrame) -> pd.DataFrame:
    """Descriptive: how much availability news the file holds, by season.

    Players who played 25+ minutes in their team's previous game: of those who
    then played 0, the share DnT projected under 5 minutes (anticipated); of those
    DnT projected under 5, the share who indeed played 0. Plus the share of
    team-games whose projected minutes sum below 220 or above 260.
    """
    m = d[d["matched"]].copy()
    m["prev"] = _prev_game_minutes(m)
    rows = []
    for s in list(SEASONS) + ["pooled"]:
        x = d if s == "pooled" else d[d["season"] == s]
        y = m if s == "pooled" else m[m["season"] == s]
        regular = y[y["prev"] >= 25]
        out = regular[regular["actual"] == 0]
        zeroed = regular[regular["p_mp"] < 5]
        ts = x.groupby(["game_id", "team"])["p_mp"].sum()
        big = y[y["p_mp"] >= 20]
        rows.append({"season": s, "absences_after_25min_game": len(out),
                     "share_anticipated_p_mp_lt5": float((out["p_mp"] < 5).mean()),
                     "projected_out_n": len(zeroed),
                     "projected_out_share_played_0": float((zeroed["actual"] == 0).mean()),
                     "team_sum_lt_220": float((ts < 220).mean()), "team_sum_gt_260": float((ts > 260).mean()),
                     "p_mp_missing_rows": int(x["p_mp_missing"].sum()) if "p_mp_missing" in x else 0,
                     "g1a_share_played_0": float((big["actual"] == 0).mean())})
    return pd.DataFrame(rows)


def g1_pass(t: pd.DataFrame) -> dict:
    p = t[t["season"] == "pooled"].iloc[0]
    th = G1_THRESHOLDS
    out = {
        "matching >= 90% of p_mp >= 10 rows": bool(p["match_share_pmp_ge_10"] >= th["match_min"]),
        "G1a share >= 0.5%": bool(p["g1a_share_played_0"] >= th["g1a_min"]),
        "G1b R2 <= 0.90": bool(p["g1b_r2"] <= th["g1b_max"]),
        "G1c |OT - regulation| <= 5": bool(abs(p["g1c_ot_minus_reg"]) <= th["g1c_abs_max"]),
        "G1d mean team sum in 225-255": bool(th["g1d_lo"] <= p["g1d_mean_team_sum_reg"] <= th["g1d_hi"]),
    }
    out["G1 passes"] = all(out.values())
    return out


def ratings_frame(epm, box, games) -> pd.DataFrame:
    reg = regular_games(games)
    gmap = legacy_players.dnt_games(epm, reg)
    r = epm.merge(gmap[["dnt_game_id", "game_id"]], left_on="game_id", right_on="dnt_game_id",
                  suffixes=("_dnt", ""))
    seasons = _season_of_date(games)
    r["season"] = r["date"].map(seasons)
    match = legacy_players.match_players(r, box, seasons)
    r = r.merge(match, on=["season", "team", "player_id"], how="left")
    b = box.assign(perf=legacy_players.game_score_per36(box))[["player_id", "game_id", "perf"]]
    r = r.merge(b.rename(columns={"player_id": "bdl_player_id"}), on=["bdl_player_id", "game_id"], how="left")
    return r.sort_values(["player_id", "season", "date", "game_id"]).reset_index(drop=True)


def g2(r: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows = []
    grp = r.groupby(["player_id", "season"])["epm"]
    rng = grp.agg(lambda s: s.max() - s.min())
    cnt = grp.size()
    r = r.copy()
    r["r_prev"] = grp.shift(1)
    r["r_next"] = grp.shift(-1)
    for s in list(SEASONS) + ["pooled"]:
        x = r if s == "pooled" else r[r["season"] == s]
        sel = cnt.index.get_level_values(1).isin(SEASONS if s == "pooled" else [s]) & (cnt >= 20).to_numpy()
        y = x[x["perf"].notna() & x["r_prev"].notna() & x["r_next"].notna()]
        c_in = np.corrcoef(y["epm"] - y["r_prev"], y["perf"])[0, 1]
        c_after = np.corrcoef(y["r_next"] - y["epm"], y["perf"])[0, 1]
        rows.append({"season": s, "player_seasons_20plus": int(sel.sum()),
                     "g2a_share_range_lt_0.05": float((rng[sel] < 0.05).mean()),
                     "median_season_range": float(rng[sel].median()),
                     "g2b_n": len(y), "g2b_c_in": float(c_in), "g2b_c_after": float(c_after)})
    t = pd.DataFrame(rows)
    # G2c: first game of S vs last game of S-1 and of S
    first = r.groupby(["player_id", "season"])["epm"].first()
    last = r.groupby(["player_id", "season"])["epm"].last()
    f = first.reset_index().rename(columns={"epm": "first"})
    f["last_same"] = last.reindex(list(zip(f["player_id"], f["season"], strict=True))).to_numpy()
    f["last_prev"] = last.reindex(list(zip(f["player_id"], f["season"] - 1, strict=True))).to_numpy()
    f = f.dropna()
    c = {"g2c_n": len(f), "g2c_corr_first_vs_prev_last": float(np.corrcoef(f["first"], f["last_prev"])[0, 1]),
         "g2c_corr_first_vs_same_last": float(np.corrcoef(f["first"], f["last_same"])[0, 1]),
         "g2c_mean_abs_first_minus_prev_last": float((f["first"] - f["last_prev"]).abs().mean()),
         "g2c_mean_abs_first_minus_same_last": float((f["first"] - f["last_same"]).abs().mean())}
    return t, c


def g2_pass(t: pd.DataFrame, c: dict) -> dict:
    p = t[t["season"] == "pooled"].iloc[0]
    th = G2_THRESHOLDS
    out = {
        "G2a broadcast share < 50%": bool(p["g2a_share_range_lt_0.05"] < th["g2a_max"]),
        "G2b c_after > 0.05": bool(p["g2b_c_after"] > th["g2b_after_min"]),
        "G2b c_after - c_in > 0.05": bool(p["g2b_c_after"] - p["g2b_c_in"] > th["g2b_gap_min"]),
        "G2b c_in < c_after / 2": bool(p["g2b_c_in"] < p["g2b_c_after"] / 2),
        "G2c corr(first, previous last) > corr(first, same last)":
            bool(c["g2c_corr_first_vs_prev_last"] > c["g2c_corr_first_vs_same_last"]),
    }
    out["G2 passes"] = all(out.values())
    return out


def _md(df: pd.DataFrame) -> str:
    from nbatotals.evaluate.backtest import season_label

    if "season" in df:
        df = df.assign(season=df["season"].map(season_label))

    def fmt(v):
        if isinstance(v, (float, np.floating)):
            return f"{v:.4f}"
        if isinstance(v, (int, np.integer)):
            return f"{v:,}"
        return str(v)
    head = "| " + " | ".join(df.columns) + " |\n|" + "|".join("---" for _ in df.columns) + "|\n"
    return head + "\n".join("| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False))


def run() -> dict:
    from nbatotals.evaluate.adapters import legacy_nba_db

    games = legacy_nba_db.load()["games"]
    box = legacy_players.read_player_box()
    dnt = legacy_players.read_dnt_box()
    epm = legacy_players.read_player_epm()
    d, info = minutes_frame(dnt, box, games)
    t1 = g1(d, games)
    t1d = absence_anticipation(d)
    r = ratings_frame(epm, box, games)
    t2, c2 = g2(r)
    return {"info": info, "g1": t1, "g1_desc": t1d, "g1_pass": g1_pass(t1),
            "g2": t2, "g2c": c2, "g2_pass": g2_pass(t2, c2),
            "ratings_matched_share": float((r["bdl_player_id"] >= 0).mean())}


def markdown(res: dict) -> str:
    parts = ["### Join", _md(pd.DataFrame([{k: v for k, v in res["info"].items() if not isinstance(v, dict)}])),
             "Regular-season games joined to DnT by season: " + ", ".join(
                 f"{s}: {res['info']['joined_by_season'].get(s, 0):,} of {n:,}"
                 for s, n in res["info"]["regular_by_season"].items()),
             "### G1: projected minutes", _md(res["g1"]),
             _md(pd.DataFrame([{"criterion": k, "passes": v} for k, v in res["g1_pass"].items()])),
             "Descriptive: availability news in the file", _md(res["g1_desc"]),
             "### G2: player ratings", _md(res["g2"]),
             _md(pd.DataFrame([res["g2c"]])),
             f"Rating rows matched to a BallDontLie player: {res['ratings_matched_share']:.4f}",
             _md(pd.DataFrame([{"criterion": k, "passes": v} for k, v in res["g2_pass"].items()]))]
    return "\n\n".join(parts) + "\n"


def main() -> int:
    pd.set_option("display.width", 200)
    print(markdown(run()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
