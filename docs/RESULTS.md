# Results: Tier A walk-forward retest

Status: search space declared; nothing has been run yet. This section is
committed before any parameter search, consensus or grading code runs.

## Search space (fixed before running)

Objective: RMSE of `total_proj` vs actual total over the **training seasons'**
regular-season games (`postseason = 0`), all games including opening weeks,
pooled across training seasons. No odds are read during the search.

Grid (full Cartesian product, 34,650 points per test season):

| Parameter | Values |
|---|---|
| `features.blend` (l3, l10, season) | every point of the 0.1-step simplex: each weight in {0.0, 0.1, ..., 1.0}, summing to 1 (66 points) |
| `features.team_shrinkage_games` | 0, 2, 5, 10, 20 |
| `projection.pace_weight` | 0.5, 0.75, 1.0 |
| `projection.home_court_total` | −2, −1, 0, 1, 2 |
| `projection.b2b_total_per_team` | −3, −2, −1, 0, 1, 2, 3 |

Everything else stays at the `config/params.yaml` defaults.

Training seasons per test season:

| Test season | Trained on |
|---|---|
| 2022-23 | 2021-22 |
| 2023-24 | 2021-22, 2022-23 |
| 2024-25 | 2021-22, 2022-23, 2023-24 |

Selection: the lowest training RMSE. Ties within 1e-9 go to the first point in
grid order (blend, shrinkage, pace weight, home court, B2B, each ascending).
Every evaluation is logged to `docs/search/fit_log.tsv.gz` (test season,
parameters, training RMSE, training n). The chosen point is frozen and the
whole test season is scored with it. A second run scores every season with the
untouched defaults.

## Anchor labels

The legacy odds have three anchors, all labels without a verified capture
time: **open** (nominally ~18 h before tip), **noon (~12h)** (the legacy
`noon_local` snapshot, stored as `pretip`; it is not the live ingester's
60-minute pre-tip anchor) and **close** (nominally ~0.5 h before tip). The open
anchor is the primary CLV comparison; noon is secondary.

## Market sanity checks (before any betting metric)

Per season and anchor: games scored, median books per game, consensus line
mean and SD, mean devigged p_over (expected near 0.50), share of consensus lines
on a quarter point, MAE of the consensus line vs the actual total (expected about
14.4 at the close), and, as an anchor-ordering check, the share of games whose
open and close consensus lines differ and the mean absolute open-to-close move.
If any of these is off, grading stops and the problem is reported first.

### Sanity check result (20 Oct 2026): the legacy "open" anchor fails

Grading stopped here. No betting metric has been computed.

Consensus per season and anchor (regular season):

| season | anchor | games | books (median) | line mean | line SD | mean p_over | quarter-point share | MAE vs actual |
|---|---|---|---|---|---|---|---|---|
| 2021-22 | open | 1,055 | 14 | 220.7 | 11.2 | 0.500 | 0.080 | **12.56** |
| 2021-22 | noon (~12h) | 826 | 15 | 221.7 | 8.0 | 0.500 | 0.070 | 14.62 |
| 2021-22 | close | 1,213 | 17 | 220.9 | 8.5 | 0.501 | 0.040 | 14.34 |
| 2022-23 | open | 1,120 | 16 | 228.7 | 10.6 | 0.500 | 0.089 | **12.33** |
| 2022-23 | noon (~12h) | 861 | 17 | 228.1 | 6.8 | 0.500 | 0.031 | 14.24 |
| 2022-23 | close | 1,235 | 19 | 228.5 | 7.7 | 0.500 | 0.022 | 14.09 |
| 2023-24 | open | 1,193 | 12 | 227.9 | 11.9 | 0.500 | 0.127 | **12.68** |
| 2023-24 | noon (~12h) | 1,226 | 13 | 227.9 | 9.8 | 0.500 | 0.074 | 14.29 |
| 2023-24 | close | 1,237 | 14 | 227.9 | 10.2 | 0.500 | 0.070 | 14.16 |
| 2024-25 | open | 1,216 | 9 | 226.9 | 10.0 | 0.500 | 0.129 | **13.41** |
| 2024-25 | noon (~12h) | 1,237 | 10 | 226.9 | 8.2 | 0.500 | 0.084 | 14.37 |
| 2024-25 | close | 1,237 | 10 | 226.8 | 8.7 | 0.500 | 0.069 | 14.18 |

The close and noon rows look as expected: MAE about 14.1 to 14.6, mean devigged
p_over 0.500, quarter-point consensus lines 2% to 8% of games. The open does not.
An opening line cannot be more accurate than the close, yet the legacy open
beats it by 0.8 to 1.8 points of MAE, has a wider spread of lines, and moves a
mean 3.5 to 4.9 points before the close (noon to close: 1.7 to 2.1).

Diagnosis:

- corr(open − close, actual − close) = **0.39** over 4,579 games: the open line
  "knows" which way the game finished relative to the close. The same
  correlation for noon is 0.007.
- Splitting open quotes by the legacy row's own `game_date`: where it equals the
  game date (1,619 games) the open MAE is 14.31, slightly *worse* than the
  close's 14.05, as an open should be. Where it is the day after the game (2,944
  games, 64%), the open MAE is 11.95 against the close's 14.21.

Conclusion: most legacy "open" snapshots were captured after tip-off (in-game
lines), not ~18 h before. Any CLV or cover rate measured from the legacy open
would be look-ahead. The close and noon anchors show no such signature, but
neither has a verified capture time.

## Anchor timing, measured (fixed before grading)

The legacy `odds_truth` rows carry no capture time, but each names the raw The
Odds API payload it was parsed from (`raw_json_file`) and the provider's event
id. Joining every one of the 197,757 totals rows to its file and event
(`nbatotals/evaluate/adapters/legacy_lake.py`, path from `NBA_LEGACY_ODDS_LAKE`)
gives the snapshot time and the event's `commence_time`. All 197,757 rows were
found, and every parsed line and price equals the file's (0 mismatches, after
switching the adapter to the provider's decimal prices: the legacy American
columns were rounded from them, e.g. 1.91 became −109). One event appears twice
in one file (2025-03-20 close); the first listing is used.

What the three legacy labels really are: fixed wall-clock snapshots, not lead
times.

| legacy label | captured at (US Eastern) | measured lead before tip, regular season, pre-tip quotes |
|---|---|---|
| `close` | 13:55 or 14:55 on game day | median 5.7 h; 5th–95th percentile 1.7–8.7 h |
| `noon_local` | 02:25 or 03:25 on game day | median 17.2 h; 13.1–19.7 h |
| `open` | 20:25 or 21:25, on the evening before **or of** the game | median 0.2–1.7 h; −1.7 to 25.1 h |

So the legacy "close" is not a closing line (it is about six hours before tip),
"noon_local" is an overnight snapshot, and "open" is the day before for some
games and during or just before the game for others. Below, the anchors are
labelled **open (~23h)**, **noon_local (~17h)** and **close (~6h)**. No true
closing line exists in this data, which matters for reading the results: a
line six hours out is, if anything, easier to beat than the real close.

Rules applied, decided from capture times only, before any grading:

1. A quote captured at or after its event's `commence_time` is in-play and is
   dropped. That removes 3,461 to 8,301 "open" rows a season (634 to 730 games
   affected) and 141 to 291 "close" rows (19 to 22 games a season, afternoon
   tip-offs). No noon_local row is in-play.
2. A quote whose event commences on a different US Eastern date than the game
   (a rescheduled game) is dropped: 1 to 75 rows per season and anchor.
3. An open consensus captured at or after the same game's close capture is not
   an open and is dropped (1,279 game-seasons in total). What remains of the
   open is the evening-before snapshot: median lead 22.7 h (5th–95th
   percentile 18–25 h).

Sanity table after these rules (regular season):

| season | anchor | games | books (median) | line mean | line SD | mean p_over | quarter-point share | MAE vs actual |
|---|---|---|---|---|---|---|---|---|
| 2021-22 | open (~23h) | 379 | 9 | 221.8 | 8.4 | 0.500 | 0.061 | 14.20 |
| 2021-22 | noon_local (~17h) | 826 | 15 | 221.7 | 8.0 | 0.500 | 0.070 | 14.62 |
| 2021-22 | close (~6h) | 1,193 | 17 | 220.9 | 8.4 | 0.501 | 0.040 | 14.40 |
| 2022-23 | open (~23h) | 423 | 8 | 227.7 | 6.8 | 0.500 | 0.059 | 13.79 |
| 2022-23 | noon_local (~17h) | 860 | 17 | 228.1 | 6.8 | 0.500 | 0.031 | 14.26 |
| 2022-23 | close (~6h) | 1,211 | 19 | 228.5 | 7.2 | 0.500 | 0.023 | 14.21 |
| 2023-24 | open (~23h) | 621 | 6 | 227.3 | 10.4 | 0.500 | 0.106 | 14.31 |
| 2023-24 | noon_local (~17h) | 1,226 | 13 | 227.9 | 9.8 | 0.500 | 0.074 | 14.29 |
| 2023-24 | close (~6h) | 1,220 | 14 | 227.9 | 9.9 | 0.500 | 0.068 | 14.28 |
| 2024-25 | open (~23h) | 622 | 6 | 226.5 | 8.3 | 0.500 | 0.137 | 14.63 |
| 2024-25 | noon_local (~17h) | 1,237 | 10 | 226.9 | 8.2 | 0.500 | 0.084 | 14.37 |
| 2024-25 | close (~6h) | 1,218 | 10 | 226.8 | 8.6 | 0.500 | 0.068 | 14.24 |

The look-ahead signature is gone: corr(anchor − close, actual − close) is
−0.010 for the open (1,989 games) and −0.001 for noon_local (4,086 games),
against 0.39 before the in-play rows were removed. Mean absolute move to the
close: open 1.8 to 2.1 points, noon_local 1.6 to 2.0. The open covers only 379
to 622 games a season, so open-anchor CLV rests on about 1,650 test-season
games.

## Amendment: anchors rebuilt from the raw payloads (fixed before grading)

The "Anchor timing, measured" rules above are superseded before any grading by
Amendment 1 in [PREREGISTRATION.md](PREREGISTRATION.md): early (~23h),
overnight (~17h) and afternoon (~6h) anchors rebuilt per game from UTC
partition D's three files, pre-tip snapshots only, primary comparison
afternoon (~6h), CLV early → afternoon and overnight → afternoon.
