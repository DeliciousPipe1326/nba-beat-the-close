# Results: Experiment 1, Dunks & Threes benchmark

Run 20 October 2026. Pre-registration: [PREREGISTRATION.md](PREREGISTRATION.md),
committed (91157d2) before any gate metric was computed. Every number below is
from [gate_report.md](gate_report.md), which
`python -m nbatotals.evaluate.dnt_gate` regenerates byte for byte (maintainer
only: needs `NBA_LEGACY_DB`, `NBA_LEGACY_PROPS_DB` and `NBA_DNT_BOX`).

## Finding

**The pre-registered gate fails, so Phase B did not run.** No odds were read
and no betting metric was computed for these projections. The `dnt_box` and
`dnt_pace_eff` projectors were not built.

The gate fails on ambiguity, not because the files look back-filled. Three
of the four tests say the per-player projections were made before the games.
The fourth (the minutes budget) shows that the files are **not a coherent game
projection**: team minutes do not sum to 240, so summing `p_pts` does not give
Dunks & Threes' projected total. Its accuracy (game MAE 18.4 to 24.3 points
against about 14.2 for the closing line) says the same.

## The gate (regular season; decided on each test season and pooled)

| season | (a) R² of p_mp vs actual minutes | (b) p_mp ≥ 20 who played 0 min | (c) OT − regulation error of Σ p_pts (95% CI) | (d) Σ p_mp per team: median; OT − regulation | verdicts a / b / c / d | season verdict |
|---|---|---|---|---|---|---|
| 2021-22 (not gating) | 0.668 | 2.09% of 15,125 | +26.4 (+17.7 to +35.1) | 240.4; −3.38 | PASS / PASS / PASS / PASS | pre-game |
| 2022-23 | 0.783 | 1.87% of 15,242 | +16.0 (+9.6 to +22.4) | 242.2; **+3.02** | PASS / PASS / PASS / ambiguous | **fails (ambiguous)** |
| 2023-24 | 0.799 | 2.12% of 15,217 | +21.9 (+15.8 to +28.1) | 241.6; −0.71 | PASS / PASS / PASS / PASS | pre-game |
| 2024-25 | 0.809 | **0.45%** of 14,745 | +27.0 (+18.6 to +35.4) | **232.8**; −4.27 | PASS / ambiguous / PASS / ambiguous | **fails (ambiguous)** |
| pooled 2022-23 to 2024-25 | 0.797 (RMSE 6.3 min, n = 126,791) | 1.49% (673 of 45,204) | +21.0 (+16.7 to +25.2; 200 OT / 3,507 regulation games) | 239.5; −0.05 | PASS / PASS / PASS / PASS | pre-game |

Pre-registered thresholds: (a) PASS ≤ 0.90, FAIL ≥ 0.95; (b) PASS ≥ 0.5%,
FAIL < 0.2%; (c) PASS ≥ +12, FAIL ≤ +6; (d) PASS when the median is in
[236, 244] and the OT difference is under 2 minutes, FAIL when the OT difference
is 10 minutes or more or the median is outside [225, 255]. The decision rule
needs every test season to pass. 2022-23 and 2024-25 are ambiguous, so the gate
fails. No test FAILed anywhere.

Join: DnT player-games with `p_mp ≥ 10` matched to a BallDontLie log row in
99.0–99.2% of cases in every season (pre-registered floor 95%). DnT rows cover
1,233 of 1,236, 1,237 of 1,237 and 1,237 of 1,237 regular-season games in the
three test seasons.

## What the tests say

- **Not back-filled from the box score.** The projections do not know about
  overtime: on OT games the actual total beats Σ `p_pts` by about 21 more
  points than on regulation games (CI +16.7 to +25.2), close to one OT
  period's scoring. The team minutes budget is the same in OT and regulation
  games (pooled difference −0.05 ± 1.29 min). About 1.5% of players projected
  for 20+ minutes did not play (late scratches). Minutes R² is 0.78 to 0.81,
  the range of a forecast, not a record.
- **Not a coherent game projection.** Per team-game, Σ `p_mp` has an SD of 19
  to 27 minutes, and only 39–49% of team-games fall between 230 and 250 (5th to
  95th percentile: 195 to 268). Players set to 0 minutes (about 4 to 5 per team
  per game) do not have their minutes given to anyone else. Example: a Dallas
  game in 2022-23 with four rotation players at 0 sums to 176.5 minutes and
  81.5 points, against 119 actual points. Σ `p_pts` per team predicts actual
  team points worse than a constant (R² −0.44 to −1.37). Game-total MAE is
  20.30, 18.42 and 24.29 in the three test seasons.
- **2024-25 is different.** The minutes budget is lower (median 232.8, mean 229),
  the summed total is biased 14.1 points low, and 221 of 12,225 players set to
  0 minutes played (1.81%; mean 19.6 minutes when they did). In 2022-23 and
  2023-24 that happened once in 9,366 and once in 10,861. The files look like a
  different vintage or a different pipeline from that season on. This was not
  investigated further.
- **One thing the gate cannot settle.** In 2022-23 and 2023-24 a player with
  `p_mp = 0` almost never played (2 of 20,227). That fits zeros taken from
  the official "Out" designations before the game (Out is rarely reversed).
  It also fits zeros taken from the actual inactive list after the fact.
  Test (b) separates the two only for players projected to play. Those
  players sat 1.9–2.1% of the time, which a pure back-fill would not show.

## Why the gate failed, plainly

Test (d) was written on the assumption that a pre-game box projection
allocates 240 minutes per team, with the OT difference as the back-fill
signal. The OT signal is clean: the projections do not know game length.
The 240-minute assumption is false for this data in every season. Two of the
pre-registered thresholds were also tighter than their own noise. The
2022-23 OT difference, +3.02, has a standard error of 1.84 minutes against a
2-minute PASS line. The 2024-25 median, 232.8, misses a PASS band that is only
±4 minutes wide. Those are design errors in the pre-registration. The verdict
stands as pre-registered, and the thresholds were not changed after the fact.

Even if the gate had passed, Phase B as registered (`total_proj = Σ p_pts`)
would have benchmarked an aggregation artefact, not Dunks & Threes' model.

## Deviations from the pre-registration (all before the decision; none changes a threshold)

1. **Name source for the BallDontLie logs.** The first run took player names
   from `nba_props.db.players`, which holds only 569 current players, so most
   2021-22 to 2023-24 log rows had no name. Only 70–91% of `p_mp ≥ 10` rows
   matched in those seasons, under the 95% precondition. Names now come from
   `nba.db.balldontlie_players` (5,434 players, every logged id covered). This
   is a lookup fix, not a change to the name normalisation. The first run's
   verdicts were the same for (c) and (d), which do not use the logs:
   2022-23 ambiguous on (d), 2023-24 pre-game, 2024-25 ambiguous on (b) and (d)
   (its (a) was undefined because of the missing rows below). Those verdicts
   are superseded.
2. **Rows without a projection.** 98 DnT rows in 2024-25 have no `p_mp` or
   `p_pts` (null). They are left out of the player tests and count as 0 in the
   team sums.
3. **2021-22 BallDontLie logs** appear to omit 0-minute players for much of
   the season (9,859 DnT players were on the team's roster that season but
   absent from that game's logs, counted as 0 minutes as pre-registered).
   2021-22 is not a gating season.

## Bug-first checks on the gate numbers

- Team-id map: 128,318 of 128,318 player-days agree with BallDontLie's team
  (checked before the pre-registration).
- Every DnT game appears in exactly one date folder, with exactly two teams,
  and no player appears twice in one game. No duplicate (game, team, name)
  rows exist in the BallDontLie logs.
- The low Σ `p_mp` sums are not a parsing error: the rows per team-game are
  12 to 21 (median 17), every row is read, and the low sums come from players
  set to 0 minutes whose time was not reallocated (example above).
- The gate code is unit-tested offline on a hand-built league
  (`tests/test_dnt_gate.py`), including every branch of the decision rule.

## Answer to the experiment's question

Not answered. Does a professional public model beat the open, noon or the
close? These files cannot say, because they hold per-player projections that
do not add up to a game projection. Nothing in this repository says anything
about Dunks & Threes' own game-total forecasts.

## Possible next steps (each would need its own pre-registration; not done)

- Rescale each team's rows to 240 minutes (`p_pts × 240 / Σ p_mp`) and benchmark
  that. It would be a new model ("Dunks & Threes players with this project's
  minutes constraint"), not Dunks & Threes' projection, and 2024-25's
  zero-minute players who played would still be a problem.
- The old repository's `data/lake/game_predictions` parquet (5,622 rows,
  2021–2025, per its data catalogue) may hold Dunks & Threes' team-level
  `/game-predictions` output. It was not opened here (no parquet engine in
  this environment), and it would need its own pre-game gate.
- A clean test needs projections captured live, with a timestamp, on an unseen
  season.
