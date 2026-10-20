# Pre-registration: Experiment 1, benchmark a professional public model (Dunks & Threes)

Written 20 October 2026. The commit that adds this file is the timestamp. It
comes before any gate metric (Phase A) and before any odds or betting result
(Phase B) for these projections. Later changes are new commits with the reason
in the message; RESULTS.md reports against this version.

This experiment is **not** part of the main pre-registration
([docs/PREREGISTRATION.md](../../PREREGISTRATION.md)) and changes none of its
results. It uses the same harness, market source (true close, T−15 min) and
grading rules.

## What was looked at before writing this

Only structure, no outcome:

- The files: `<root>/<YYYY-MM-DD>/dunksandthrees_game_predictions_box.json`,
  1,352 date folders from 2021-10-19 to 2026-04-14 (160 without the file, 185
  with an empty list). Each row is one player in one game: `game_id` (NBA Stats
  form, e.g. 22200614), `team_id` (NBA Stats), `player_id`, `player_name`,
  `p_mp`, `p_pts`, `p_pace`, `p_fg2a/m`, `p_fg3a/m`, `p_fta/m`, `p_orb`,
  `p_drb`, `p_tov`, `p_ast`, `p_stl`, `p_blk`, `p_reb`, plus height, weight,
  position. No timestamp of any kind. Every game appears in exactly one date
  folder, with exactly two teams. `p_pace` varies by player within a team.
- File modification times are November 2025 (with some September and
  December 2025): the folders were fetched by date long after the games. The
  fetch code in the old repository calls `/game-predictions-box?date=D`.
- The NBA-Stats-id-to-alias map (`nbatotals/teams.NBA_STATS_ID_TO_ALIAS`)
  agrees with BallDontLie's team for 128,318 of 128,318 player-days matched by
  date and exact name.
- Game join, by Eastern date plus both aliases (the files have no home/away
  flag): regular-season games covered 1,211 of 1,230 (2021-22), 1,233 of 1,236
  (2022-23), 1,237 of 1,237 (2023-24), 1,237 of 1,237 (2024-25). The
  unmatched 2021-22 games are dated differently in the two sources
  (postponed games).

Nothing about minutes, points, totals versus actuals, or odds was computed.

## The question

Is a professional public model's game projection better than the market at
any anchor (opening ~24 h, noon ~10 h, true close)? Before that: are these
historical files genuine pre-game projections, or were they back-filled after
the games when the folders were fetched?

## Phase A: the gate (pre-game or back-filled?)

### Data

- DnT player-games from regular-season games (`postseason = 0` in the legacy
  DB, as in the main test) that join to a legacy game, seasons 2021-22 to
  2024-25. Decided on each test season (2022-23, 2023-24, 2024-25) and pooled;
  2021-22 reported only.
- Actual minutes: BallDontLie `player_game_logs` in the old repository's
  `nba_props.db` (read-only; an independent source, not Dunks & Threes). It
  lists roster players with 0 minutes too. Joined by Eastern date, team alias
  and normalised name (lower case, accents stripped, punctuation removed,
  suffixes Jr/Sr/II/III/IV dropped). A DnT player-game is **matched** if the
  name is in that team's rows for that game. A DnT player whose name matches
  that team in any game of the season but is absent from this game's rows is
  counted at 0 minutes (reported separately). Join precondition: at least 95%
  of DnT player-games with `p_mp ≥ 10` matched; if lower, only the name
  normalisation may be changed, and every change is logged.
- Actual game totals and overtime: the legacy DB (`games.period > 4` is OT).

### Tests and thresholds (fixed now)

| test | statistic | PASS (pre-game) | FAIL (back-filled) | genuine pre-game expectation | back-filled expectation |
|---|---|---|---|---|---|
| (a) minutes | `R² = 1 − Σ(actual − p_mp)² / Σ(actual − mean)²` over matched player-games (`p_mp` as the prediction, not a fitted line); r² also shown | ≤ 0.90 | ≥ 0.95 | 0.55–0.85 | ≥ 0.95 |
| (b) late scratches | share of player-games with `p_mp ≥ 20` whose actual minutes are 0 (absent-but-on-roster counted as 0; the listed-with-0 version also shown) | ≥ 0.5% | < 0.2% | 1–4% | about 0 |
| (c) overtime | `Δ = mean(actual − proj | OT) − mean(actual − proj | regulation)`, game totals, `proj = Σ p_pts` over both teams | ≥ +12 points | ≤ +6 points | +18 to +28 (an OT period is about 24 points) | 0 to +5 |
| (d) minutes budget | per team-game `Σ p_mp`: median, and mean(OT games) − mean(regulation games) | median in [236, 244] and OT difference < 2 min | OT difference ≥ 10 min, or median outside [225, 255] | median ≈ 240, OT difference ≈ 0 | regulation ≈ 240, OT ≈ 265 |

Values between PASS and FAIL are **ambiguous**.

**Decision rule**, applied to each of the three test seasons and to the
pooled three:

- All four PASS: pre-game. Phase B runs.
- (b) ambiguous and (a), (c), (d) PASS: pre-game but made near tip or with
  the active list known. Phase B runs with that flag, and CLV from anchors
  earlier than the projection's unknown time is read as an upper bound, not a
  bettable result.
- Any FAIL in any test season, or any other ambiguity: the gate fails. Phase B
  does not run. RESULTS.md reports the gate as the finding.

Descriptive, not gating: share of BallDontLie players with ≥ 20 actual minutes
who are absent from the DnT file for that game (a pre-game projection misses
some; a back-fill from the box score misses about none); R² of team `Σ p_pts`
against actual team points.

## Phase B (only if the gate passes)

### Projectors

- **`dnt_box`**: `total_proj = Σ p_pts` over both teams' rows in the file
  **dated the game's Eastern date**, joined by that date and both aliases.
  Nothing dated later is read. `fit` is a no-op (no parameters, nothing tuned,
  so the "tuned" and "default" rows are the same projection). Folder from the
  environment variable `NBA_DNT_BOX`; no DnT data is copied into the repo.
- **`dnt_pace_eff`** (variant, same file and cut-off), the pace_eff shape with
  DnT's inputs: per team, projected possessions
  `poss = Σ(p_fg2a + p_fg3a) − Σ p_orb + Σ p_tov + 0.44·Σ p_fta`, offensive
  rating `ortg = 100·Σ p_pts / poss`, pace = the `p_mp`-weighted mean of the
  team's `p_pace`; game pace = mean of the two teams' paces;
  `total_proj = pace · (ortg_home + ortg_away) / 100`. No home-court or
  back-to-back constant, nothing fitted.
- **Missing games**: a target game with no DnT rows (expected 3 in 2022-23,
  0 in the other test seasons) gets the point-in-time league-average total
  (the `league_avg` projector), and the count is reported. If more than 1% of
  any test season were missing, the run would stop instead.
- **Leakage test**: the harness's truncation test (delete every games and box
  row dated on or after the game, blank its score) plus deleting every DnT file
  dated **after** the game's date; the projection must be bit-identical. The
  file dated on the game's date is the projection under test and is kept:
  deleting it would remove the projection by construction, and whether its
  contents are pre-game is what Phase A decides.

### Runs

`python -m nbatotals backtest --legacy --model dnt_box` and
`--model dnt_pace_eff`, each producing the standard report
(`docs/backtest_legacy_report_<model>.md`), unchanged harness: true close
(T−15 min) primary, thresholds 0/1/2/3/4/6, CLV from every bucket, Pinnacle
only, blend regression, test seasons 2022-23 to 2024-25.

### Expected results (dnt_box; dnt_pace_eff expected within noise of it)

| metric | expectation |
|---|---|
| Cover vs true close, every game, pooled | 48–52%; each season 47–53% |
| Real ROI | about −4.5%, CI including it |
| Fair ROI | about 0%, CI including 0 |
| MAE vs actual total | 14.2–15.0 (true close 14.16; pace_eff 14.70) |
| Blend regression weight `c` on the model | −0.10 to +0.30 |
| CLV opening (~24 h) → true close | positive, +0.3 to +1.2 points |
| CLV noon (~10 h) → true close | 0 to +0.4 points |
| CLV near close (~1 h) → true close | within ±0.1 points |
| Pinnacle-only cover | 48–52% |

### Evidence bar for an edge

Identical to the main pre-registration, on the primary cell (true close, edge
threshold 0): cover-rate Wilson lower bound above 52.38% on at least 1,000
pooled bets with cover above 50% in each test season; noon CLV interval above
zero; real-price ROI interval above zero. All three are required. Even then,
because the projection's creation time is unknown, a claim would need DnT
projections captured live with timestamps on an unseen season.

### Interpretation rule (fixed now)

The DnT file carries no time. "Beats the open" or "beats noon" can only mean
the line moved towards a projection whose creation time is unknown and may be
later than that anchor. Positive CLV from an anchor is evidence of
information the market had not priced at that anchor, not a bet anyone could
have placed then.

### Bug-first checks (run and written down whatever the result)

1. Truncation test above passes on synthetic data (offline pytest).
2. Look-ahead signature: `corr(proj − close, actual − close)` on the test
   seasons, beside pace_eff's. Above +0.10 is treated as a leak and stops the
   interpretation.
3. Overtime premium (Phase A test (c)) repeated on the graded games.
4. Placebo: DnT projections shuffled among games on the same date; CLV from
   the opening must be about zero.
5. Join: every graded game's DnT teams equal the harness game's teams; counts
   of games with DnT rows per season.
6. CLV by side (overs and unders) and mean line drift, as in the main checks.
