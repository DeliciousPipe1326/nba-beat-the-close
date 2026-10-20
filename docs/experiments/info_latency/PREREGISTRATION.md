# Pre-registration: Experiment 2, information latency

Written 20 October 2026, before any gate number, projection or odds for this
experiment was computed. The commit that adds this file is the timestamp. Any
later change is a new commit with the reason in its message, and RESULTS.md (same
folder) reports against this version.

## Question

The main backtest ([docs/RESULTS.md](../../RESULTS.md)) found that the box-score
formula `pace_eff` has +0.39 points of CLV (95% CI +0.29 to +0.49) when bet at
the opening anchor (~24 h before tip) and none from noon (~10 h) on (−0.02,
CI −0.08 to +0.05). The correlation between its edge and the later line move is
0.20 from the opening and 0.02 from noon. So box-score information is priced in
between about 24 and 10 hours before tip.

What else does the market price in that window, and after it? The hypothesis is
lineup and availability news (injuries, rest, rotation changes). A projection
that uses each game's projected minutes and player ratings should then show more
CLV than `pace_eff` from the opening and, unlike `pace_eff`, CLV from noon.

## What was looked at before writing this

Only data structure, not any quantity this file sets a threshold on:

- File layout and coverage: Dunks & Threes (DnT) per-player per-game files exist
  for every regular-season game date from 2021-22 to 2024-25 (165, 167, 164, 167
  dates); the lake `player_epm` parquet covers the same dates.
- On 21 randomly chosen dates the raw `dunksandthrees_epm.json` and the lake
  `player_epm` (game_optimized = 0) hold identical rows and values. The lake
  `season` column is the season's end year; its partition is the start year.
- One date (2023-01-10) was printed while learning the format: its 14 per-team
  sums of `p_mp` ranged from 204 to 280 (mean about 242). No other date's sums,
  no actual minutes and no rating-timing statistic were computed.
- The files' download dates are 2025 (an archive fetched after the fact), so
  whether DnT served the as-of-pre-game version is exactly what Phase A tests.
- No odds were read for this experiment.

Note on the brief: `player_epm` has no actual-minutes column (`p_mp_48` is a
projection of minutes per 48). Actual player minutes come from the legacy
BallDontLie player box (`nba_props.db › player_game_logs`), matched to DnT
players by Eastern date, team and normalised name (rules below).

## Phase A: are the inputs point-in-time? (gate, computed before Phase B)

Population: regular-season games 2021-22 to 2024-25 in the legacy DB, joined to
DnT by Eastern date plus both team aliases (an NBA Stats team id map is added to
`nbatotals/teams.py` and checked against DnT's own game file aliases).

Player matching (for actual minutes): DnT `player_name` and BallDontLie
`first_name last_name` are normalised (accents stripped, lower case, punctuation
removed, suffixes Jr/Sr/II/III/IV dropped) and matched within (season, team).
A DnT player counts as matched if exactly one BallDontLie player of that name
appears for that team that season. Unmatched players are excluded from G1 and
counted. A matched player with no row, a DNP row or 0:00 in the game's box
"played 0 minutes".

### G1: DnT projected minutes (`p_mp`)

| check | pass if | expected if pre-game | expected if back-filled from the box |
|---|---|---|---|
| G1a: share of matched players with `p_mp` ≥ 20 who played 0 minutes | ≥ 0.5% | 1–6% (late scratches) | ~0% |
| G1b: R² of `p_mp` vs actual minutes (matched players, all rows) | ≤ 0.90 | 0.55–0.85 | ≥ 0.95 |
| G1c: mean per-team sum of `p_mp`, overtime games minus regulation games | within ±5 minutes | ~0 | about +25 per OT period |
| G1d: mean per-team sum of `p_mp` (regulation games) | 225 to 255 | ~240 | 240 |

G1 passes only if all four pass. Matching must reach 90% of DnT rows with
`p_mp` ≥ 10; if not, G1 is reported as not testable and fails.

Descriptive (no threshold): the reverse surprise (`p_mp` < 5, played 25+), the
R² of actual minutes on the player's previous game's actual minutes (the naive
alternative), and the G1 numbers by season.

Caveat fixed in advance: G1 can show the file was made before the game. It
cannot show when on the game day it was made. If DnT's archive keeps its last
pre-tip version, it can hold news that arrived after noon. Phase C's CLV from
noon is then an upper bound on what a bettor at noon could have had. The
near-close (~1 h) CLV is the check: a projection carrying news from the last
hour shows CLV from the near-close anchor too.

### G2: player ratings (`player_epm`, game_optimized = 0)

A third party's ratings cannot be recomputed with later games deleted, so the
literal truncation test is replaced by three tests of the same property, that
the rating on date D is a trailing rating that has not seen game D or later:

| check | pass if |
|---|---|
| G2a, not a broadcast: among player-seasons with ≥ 20 games, the share whose `epm` range over the season is below 0.05 | < 50% |
| G2b, timing: for a player's consecutive games g1 < g2 < g3, perf(g2) = Hollinger game score per 36 minutes (players with ≥ 10 minutes in g2). c_in = corr(r(g2) − r(g1), perf(g2)); c_after = corr(r(g3) − r(g2), perf(g2)) | c_after > 0.05, c_after − c_in > 0.05 and c_in < c_after / 2 (c_in can be slightly positive from form persisting between games) |
| G2c, trailing at season start: corr(rating at a player's first game of season S, his last game of S−1) vs corr(first game of S, his last game of S) | the first exceeds the second |

If the rating at D included game D, c_in would be positive and at least as large
as c_after; a season-final rating would fail G2a and G2c.

The game-adjusted twin (`player_epm_optimized`) is not used.

### What happens on failure

- G1 fails, G2 passes: minutes come from the trailing fallback (below), not DnT.
- G2 fails: no lineup projector can be built (minutes without ratings carry no
  offence or defence). The gate is written up and the experiment stops.
- Both fail: written up, stop.

Gate numbers are committed before any Phase B code reads odds.

## Phase B: projector `lineup_pace_eff`

For game G on Eastern date D, each team's players are the DnT rows for G (or,
under the fallback, the team's players over its last 10 games before D). Minutes
`m_i` = `p_mp` (fallback: mean actual minutes over the team's last 10 games,
0 where absent, same season). Ratings `o_i`, `d_i`, `t_i` = `oepm`, `depm`,
`p_t_poss_48` from the `player_epm` row for (player, G); if missing, the
player's latest earlier row; if none, 0 for `oepm`/`depm` and the team mean for
pace. Lake duplicates (the first dates of 2024-25 appear in two partitions) are
removed by (player, game).

Team values, minutes-weighted: `O = 5·Σ m o / Σ m`, `Dv = 5·Σ m d / Σ m`,
`P = Σ m t / Σ m`. Each is centred on its point-in-time league reference: the
mean over every team-game dated before D in the same season, shrunk towards the
previous season's mean as if that were worth `league.shrinkage_team_games`
team-games (in the first season with no earlier one: towards the mean of the
earliest date's team-games, which affects 2021-22 only, a training season).

In the `pace_eff` formula shape, with `L_pace`, `L_ortg` and back-to-back flags
from the same point-in-time features as `pace_eff`, and `λ = n/(n+k)` with n the
team's games before D this season:

    pace     = L_pace + λ_h(P_h − ref_P) + λ_a(P_a − ref_P)
    off_home = L_ortg + s·λ_h(O_h − ref_O) − s·λ_a(Dv_a − ref_D)
    off_away = L_ortg + s·λ_a(O_a − ref_O) − s·λ_h(Dv_h − ref_D)
    total    = pace·(off_home + off_away)/100 + home_court_total + b2b·(home_b2b + away_b2b)

Every coefficient is in `config/params.yaml` under `models.lineup_pace_eff`.
`fit` chooses only `s` (rating-to-points scale) from {0.5, 0.75, 1.0, 1.25, 1.5}
and `k` (shrinkage, team-games) from {0, 5, 10, 20}, by RMSE on earlier seasons'
regular-season games (no odds). Fixed: `home_court_total` = +2 and `b2b` = +1,
the values `pace_eff`'s fit chose for 2022-23 from 2021-22 alone, so they come
from before any test season. A team with no DnT rows for G gets zero deviations;
the count is reported.

Leakage: the projector joins the registry and the truncation test in
`tests/test_leakage.py`. An added test writes synthetic DnT and rating files to a
folder, and for each sampled game deletes every file dated after D, every other
game's rows dated D, and every games and box row dated on or after D; the
projection must be bit-identical. Files dated D for game G itself are the
pre-game inputs whose timing Phase A tests; truncation cannot test them.

## Phase C: what is reported (all through the harness)

`python -m nbatotals backtest --legacy --model lineup_pace_eff` (standard report),
plus an experiment report built from the same harness functions:

1. CLV by anchor to the true close (T−15 min), pooled and per season, for
   `lineup_pace_eff`, `pace_eff`, `elo_total`, `league_avg`.
2. Edge vs subsequent line move correlation by anchor, same four.
3. Cover and ROI at the opening and noon anchors against Pinnacle's own line and
   price at that anchor (the harness's Pinnacle table extended to any anchor;
   the existing report stays byte-identical).
4. Blend regression `actual = a + b·close + c·model`.
5. Decomposition: games where either team's DnT lineup differs materially from
   its previous game (a player with `p_mp` < 5 who played 25+ minutes in the
   team's previous game, or `p_mp` ≥ 25 who played under 5, including absent),
   against the rest. CLV from opening and noon in each group, for
   `lineup_pace_eff` and `pace_eff`. Uses actual minutes of the previous game
   only (dated before D).

## Expected results (written before computing them)

| metric | expectation |
|---|---|
| Gate | G1 and G2 pass |
| CLV opening → true close, pooled | +0.5 to +1.0 points (pace_eff +0.39) |
| CLV noon → true close, pooled | +0.1 to +0.4 points (pace_eff −0.02) |
| CLV afternoon and later | +0.0 to +0.2 points |
| Edge-move correlation, opening / noon | 0.25–0.40 / 0.05–0.20 |
| Cover vs the true close, every game | 48–52% in each season and pooled |
| Real ROI at the true close | about −4.5%, CI including that |
| Pinnacle, opening and noon anchors | cover 48–53%, ROI at Pinnacle's price −1% to −5% |
| Blend weight `c` | −0.10 to +0.25 |
| MAE vs actual | between the close's (14.16) and pace_eff's (14.70) |
| Decomposition | noon CLV larger in the lineup-change group than in the rest |

## Evidence bars (two, separate)

**Information** (the hypothesis of this experiment), on the tuned model, every
game, threshold 0, pooled over 2022-23 to 2024-25:

- I1: the 95% bootstrap lower bound of opening CLV (points) is above **+0.39**
  (pace_eff's estimate);
- I2: the 95% lower bound of noon CLV is above **0** (pace_eff's estimate is −0.02);
- both survive the bug-first checks below.

I1 and I2 both: supported. One of them: partly supported. Neither: not supported.
Information is not an edge: CLV of a few tenths of a point is smaller than the vig.

**Edge**: the main pre-registration's bar, unchanged
([docs/PREREGISTRATION.md](../../PREREGISTRATION.md)): at the true close,
every game, a cover lower bound above 52.38% on ≥ 1,000 pooled bets with cover
above 50% in each season, noon CLV lower bound above 0, and real-ROI CI above 0.
Other cells (thresholds, anchors, Pinnacle) are descriptive.

## Bug-first checks (any information or edge result goes through all)

1. Gate passed (Phase A) and truncation tests pass, including the external-file test.
2. Join counts: DnT games matched to legacy games per season; teams with no DnT rows.
3. Placebo: the same projector with each team's DnT minutes replaced by its
   previous game's actual minutes (no same-day news). Its CLV from noon should
   fall towards pace_eff's if the hypothesis is right.
4. Late-news signature: CLV from near close (~1 h) and late evening (~2 h). If
   these are clearly positive, DnT's snapshot carries news from the last hours,
   and noon CLV is not something a noon bettor could have had.
5. Drift: CLV split by over and under bets.
6. Season stability: sign of the CLV difference vs pace_eff in each season.

Any number that clears a bar is treated as a bug until these are written up in
RESULTS.md.

## Rules

- No change to the main pre-registered results: `docs/backtest_legacy_report.md`
  must regenerate byte for byte.
- No data files, legacy contents or keys are committed. Legacy data is read in
  place, read-only.
- Not pushed.
