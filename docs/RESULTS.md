# Results: Tier A walk-forward retest

Run 20 October 2026 with `python -m nbatotals backtest --legacy` (maintainer
only: needs the private legacy DB and raw odds payloads). Every table below is
copied from [backtest_legacy_report.md](backtest_legacy_report.md), which that
command regenerates; re-running it and checking `git diff` shows whether the
numbers reproduce. Pre-registered expectations are from
[PREREGISTRATION.md](PREREGISTRATION.md) (written before any backtest; anchors
changed by Amendment 1 before any betting metric was computed).

## Summary

| Question | Pre-registered expectation | Result |
|---|---|---|
| Does betting the model's side beat the afternoon (~6h) line? (primary: every game, 3 test seasons) | cover 48–52% | **49.7%** (95% Wilson 48.0–51.3%), n = 3,543 |
| Real-price ROI | about −4.5% | **−5.1%** (95% CI −8.2% to −2.0%) |
| Fair (devigged) ROI | about 0% | **−0.6%** (−3.9% to +2.6%) |
| Model MAE vs the line's MAE | model worse by 0.3–1.5 pts | model 14.68 vs line 14.23: **worse by 0.45** (0.16–0.55 across seasons and anchors) |
| Blend regression weight on the model, `c` | −0.10 to +0.15, CI including 0 | **−0.100** (−0.258 to +0.057) |
| CLV of bets struck at early (~23h) and overnight (~17h), measured to afternoon (~6h) | within ±0.2 points | **+0.41** (+0.31 to +0.51) and **+0.21** (+0.13 to +0.28): **outside the expectation** |
| Pre-registered evidence bar for an edge | not met | **not met**: no cell in any table has a cover lower bound above 52.38% (highest 51.2%) |

In plain words: the model does not beat the market. Betting its side wins at
the rate the prices imply and loses the vig. Once the afternoon line is
known, the model adds nothing to it. The one surprise is that the market line
moves towards the model between the day before and about six hours before tip
(positive CLV). That survived every bug check below and is reported as an
exploratory finding, not an edge: it is too small to pay the vig (about 0.9¢
on the dollar from early, 0.45¢ from overnight), it is measured to a line six
hours out rather than the true close, and the seasons were not unseen.

## Search space (fixed before running)

Declared and committed (80341a5) before any search ran. Objective: RMSE of
`total_proj` vs actual total over the **training seasons'** regular-season
games, all games including opening weeks, pooled across training seasons. No
odds were read during the search.

| Parameter | Values |
|---|---|
| `features.blend` (l3, l10, season) | the 0.1-step simplex, summing to 1 (66 points) |
| `features.team_shrinkage_games` | 0, 2, 5, 10, 20 |
| `projection.pace_weight` | 0.5, 0.75, 1.0 |
| `projection.home_court_total` | −2, −1, 0, 1, 2 |
| `projection.b2b_total_per_team` | −3, −2, −1, 0, 1, 2, 3 |

Full grid: 34,650 points per test season. All 103,950 evaluations are in
[search/fit_log.tsv.gz](search/fit_log.tsv.gz). Ties within 1e-9 would go to
the first point in grid order (none occurred at the minimum).

## Walk-forward fit

| test season | trained on | train n | blend l3/l10/season | shrinkage | pace weight | home court | B2B per team | train RMSE chosen | train RMSE default | test RMSE chosen | test RMSE default |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022-23 | 2021-22 | 1,230 | 0.0/0.5/0.5 | 10 | 1.0 | +2 | +1 | 18.651 | 19.116 | 18.776 | 19.349 |
| 2023-24 | 2021-22, 2022-23 | 2,466 | 0.0/0.4/0.6 | 10 | 1.0 | +2 | +1 | 18.705 | 19.233 | 18.401 | 18.776 |
| 2024-25 | 2021-22, 2022-23, 2023-24 | 3,703 | 0.1/0.4/0.5 | 10 | 1.0 | +2 | +0 | 18.582 | 19.082 | 18.276 | 18.758 |

Tuning cut out-of-sample RMSE by about 0.4 to 0.6 points in each test season.
`home_court_total` was chosen at the top of its declared range (+2) every time.
It is the formula's constant term, and the untuned projection runs about 1 point
low (Phase 2), so a wider range would likely pick a larger value. The grid was
not widened after the fact. The blend moves weight from L3 to the season-to-date
window, and stronger shrinkage (10) wins over the default (5).

## Headline (primary cell: tuned model, afternoon (~6h), every game)

| season | n (afternoon (~6h)) | cover (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | early (~23h) bets | CLV early → afternoon, points (95% CI) | overnight (~17h) bets | CLV overnight → afternoon, points (95% CI) |
|---|---|---|---|---|---|---|---|---|---|
| 2022-23 | 1,181 | 49.7% (46.9%–52.6%) | 50.0% | -0.6% (-6.3% to 5.0%) | -5.1% (-10.6% to 0.3%) | 603 | +0.37 (+0.19 to +0.56) | 838 | +0.38 (+0.22 to +0.53) |
| 2023-24 | 1,181 | 48.8% (45.9%–51.6%) | 50.0% | -2.4% (-8.1% to 3.3%) | -6.8% (-12.2% to -1.3%) | 973 | +0.37 (+0.22 to +0.52) | 1,184 | +0.25 (+0.13 to +0.36) |
| 2024-25 | 1,181 | 50.6% (47.7%–53.4%) | 50.0% | 1.1% (-4.5% to 6.7%) | -3.4% (-8.8% to 1.9%) | 1,054 | +0.47 (+0.31 to +0.64) | 1,193 | +0.05 (-0.07 to +0.16) |
| pooled | 3,543 | 49.7% (48.0%–51.3%) | 50.0% | -0.6% (-3.9% to 2.6%) | -5.1% (-8.2% to -2.0%) | 2,630 | +0.41 (+0.31 to +0.51) | 3,215 | +0.21 (+0.13 to +0.28) |

n is graded bets (pushes excluded: 8, 14 and 12). That n comes out as 1,181 in
all three seasons is a coincidence: 1,189 − 8, 1,195 − 14 and 1,193 − 12 scored
games minus pushes. CLV is in points of total; in cents it is +0.90¢ (early)
and +0.45¢ (overnight) pooled. The "no-info baseline" is the mean devigged
probability of the sides bet.

Pre-registered expectations against the headline: cover 48–52% in every
season (met: 48.8%, 49.7%, 50.6%), real ROI about −4.5% (−5.1%), fair ROI about
0 (−0.6%), CLV within ±0.2 (not met for early in any season, nor for overnight
in 2022-23 and 2023-24).

## Projection accuracy

| season | anchor | n | MAE model (tuned) | MAE model (default) | MAE line | RMSE model (tuned) | RMSE model (default) | RMSE line |
|---|---|---|---|---|---|---|---|---|
| 2022-23 | afternoon (~6h) | 1,189 | 14.67 | 15.20 | 14.24 | 18.77 | 19.34 | 18.32 |
| 2022-23 | early (~23h) | 619 | 14.37 | 14.84 | 14.01 | 17.99 | 18.58 | 17.56 |
| 2022-23 | overnight (~17h) | 860 | 14.59 | 15.17 | 14.26 | 18.59 | 19.26 | 18.24 |
| 2023-24 | afternoon (~6h) | 1,195 | 14.84 | 15.06 | 14.29 | 18.45 | 18.80 | 17.82 |
| 2023-24 | early (~23h) | 1,013 | 14.78 | 15.06 | 14.33 | 18.47 | 18.96 | 18.04 |
| 2023-24 | overnight (~17h) | 1,226 | 14.76 | 14.96 | 14.29 | 18.38 | 18.78 | 17.91 |
| 2024-25 | afternoon (~6h) | 1,193 | 14.54 | 14.97 | 14.16 | 18.18 | 18.67 | 17.65 |
| 2024-25 | early (~23h) | 1,098 | 14.33 | 14.74 | 14.17 | 17.97 | 18.44 | 17.74 |
| 2024-25 | overnight (~17h) | 1,237 | 14.64 | 15.06 | 14.37 | 18.28 | 18.76 | 17.89 |
| pooled | afternoon (~6h) | 3,577 | 14.68 | 15.07 | 14.23 | 18.47 | 18.94 | 17.93 |
| pooled | early (~23h) | 2,730 | 14.51 | 14.88 | 14.20 | 18.16 | 18.67 | 17.81 |
| pooled | overnight (~17h) | 3,323 | 14.67 | 15.05 | 14.31 | 18.40 | 18.90 | 17.99 |

Each row compares the model and the line on the games that have that anchor.
Expectation: model worse than the line by 0.3 to 1.5 points of MAE. Result: worse
in every season and anchor, by 0.16 to 0.55 (tuned; pooled afternoon 0.45). Two
cells are closer than expected: 2024-25 early (0.16) and overnight (0.27). Every
line here is a pre-tip line; the true close would be at least as accurate.

## Market + model blend regression: actual = a + b·afternoon line + c·model

| model run | season | n | intercept (95% CI) | b: afternoon (~6h) line (95% CI) | c: model (95% CI) |
|---|---|---|---|---|---|
| tuned | 2022-23 | 1,189 | +23.3 (-12.1, +58.6) | 1.011 (0.744, 1.278) | -0.109 (-0.388, +0.171) |
| tuned | 2023-24 | 1,195 | +13.9 (-13.4, +41.2) | 1.122 (0.878, 1.367) | -0.181 (-0.464, +0.102) |
| tuned | 2024-25 | 1,193 | -6.8 (-36.4, +22.8) | 1.037 (0.803, 1.272) | -0.003 (-0.264, +0.258) |
| tuned | pooled | 3,577 | +9.2 (-8.1, +26.4) | 1.064 (0.923, 1.205) | -0.100 (-0.258, +0.057) |
| default | 2022-23 | 1,189 | +17.7 (-15.3, +50.7) | 1.012 (0.774, 1.250) | -0.086 (-0.270, +0.098) |
| default | 2023-24 | 1,195 | +5.2 (-18.1, +28.5) | 0.940 (0.734, 1.146) | +0.039 (-0.132, +0.209) |
| default | 2024-25 | 1,193 | -6.7 (-33.1, +19.7) | 1.058 (0.860, 1.257) | -0.025 (-0.194, +0.144) |
| default | pooled | 3,577 | +4.1 (-11.3, +19.5) | 1.005 (0.884, 1.126) | -0.020 (-0.120, +0.080) |

This is the cleanest test of whether the model knows something the market does
not. Expectation: `b` near 1; `c` between −0.10 and +0.15 with a CI including 0.
Result: `b` 0.94 to 1.12; `c` −0.18 to +0.04, every interval including 0. Given the
afternoon line, the model's best weight is zero.

## Does the model's edge predict the line move?

| bet anchor | season | n | corr(model − anchor line, afternoon line − anchor line) (95% CI) |
|---|---|---|---|
| early (~23h) | 2022-23 | 603 | +0.237 (+0.160, +0.311) |
| early (~23h) | 2023-24 | 973 | +0.239 (+0.179, +0.298) |
| early (~23h) | 2024-25 | 1,054 | +0.244 (+0.186, +0.300) |
| early (~23h) | pooled | 2,630 | +0.236 (+0.199, +0.271) |
| overnight (~17h) | 2022-23 | 838 | +0.217 (+0.151, +0.280) |
| overnight (~17h) | 2023-24 | 1,184 | +0.190 (+0.135, +0.244) |
| overnight (~17h) | 2024-25 | 1,193 | +0.083 (+0.027, +0.139) |
| overnight (~17h) | pooled | 3,215 | +0.157 (+0.124, +0.191) |

Yes, modestly: where the model disagrees with the early or overnight line, the
line tends to move its way by the afternoon. Together with the regression above,
the picture is that the model holds public box-score information the market has
not fully priced a day out, and has priced by six hours out. The 2024-25
overnight figure is much smaller than the earlier seasons'.

## Bug-first checks on the positive CLV

The pre-registration says to treat any number that looks like an edge as a bug
first. The CLV lower bounds above zero triggered that. Each check and its
outcome:

1. **Anchor timestamps.** Every early and overnight consensus was captured before
   the same game's afternoon consensus (3,488 early–afternoon pairs, and every
   overnight–afternoon pair). All three come from the provider's own snapshot
   times in the raw files, with in-play quotes removed. Outcome: ordering correct.
2. **Join.** Every quote is matched to its game by Eastern commence date and both
   team names. 36 of 5,351 provider events match no played game (rescheduled
   games) and are ignored. 804 games carry more than one `commence_time` across
   their files (tip times revised); each file's lead uses its own. Outcome: no
   cross-game mixing found.
3. **Sign convention.** Unit-tested (`tests/test_harness.py::test_clv_sign`):
   an over gains when the line rises. Outcome: correct.
4. **Market drift.** The mean move from early to afternoon is −0.14 points and the
   model bets overs 59% of the time, so drift works against its CLV, not for it.
   CLV is positive for both sides: overs +0.23, unders +0.67 (early); overs
   +0.10, unders +0.37 (overnight). Outcome: not drift.
5. **Book composition.** Early has a median 8 books and afternoon 16, so the
   consensus could move just because different books are in it. Measured only
   on the same book's own line at both times, CLV is +0.37 (+0.28 to +0.47) from
   early and +0.19 (+0.12 to +0.26) from overnight. Outcome: not composition.
6. **Placebos.** Random sides (seeded): early +0.05 (−0.04 to +0.15), overnight
   +0.02 (−0.06 to +0.09). A predictor with no team information (the
   point-in-time league-average total): −0.07 and −0.06, both intervals
   including 0. Outcome: the CLV needs the model's team information.
7. **Look-ahead against the early snapshot.** The early file is captured about
   8:25 pm Eastern the evening before the game, while that evening's games are
   still being played. The model uses every game dated before the game day, so
   for a team that played the previous evening it can know a box score the
   early line could not. Split by whether either team played the previous
   day: CLV +0.41 (+0.31 to +0.52) when neither did (2,008 games) and +0.40
   (+0.18 to +0.62) when one did (622 games). Outcome: not explained by this
   route. The edge-to-move correlation is higher in the previous-day group
   (0.35 vs 0.21), so part of that group's signal may be timing; the
   neither-played group alone clears zero. The overnight snapshot (2:25 am
   Eastern) comes after the previous evening's games finish.
8. **Devig and push handling.** CLV in points uses no prices, and pushes do not
   enter it. The fair and real ROI arithmetic is unit-tested on hand-built
   bets. Outcome: not applicable to the CLV; correct for ROI.

Conclusion: the positive CLV looks real for this data, but it is **not an
edge**. Bets struck at early or overnight win at the rates their prices imply
(49.9% and 49.5% pooled at threshold 0) and lose about 5% at real prices. CLV
of 0.4 points is roughly 0.9¢, against a vig of about 4.5¢. It is also
measured to a line six hours out, not to the close. Confirming or refuting it
needs a true close and an unseen season: the live ingester from 2025-26 on.

## Cells clearing a bar

No cell in any run, anchor, cut, threshold or season has a cover-rate lower
bound above 52.38%. The highest is 51.2% (overnight, edge ≥ 6, pooled: 55.7%,
n = 461, real ROI +6.5% with a CI from −2.2% to +14.8%). Of the 288 cells (2 runs
× 2 cuts × 3 anchors × 6 thresholds × 4 season columns), the 96 afternoon cells
have no CLV. Of the 192 early and overnight cells, 178 have a CLV lower bound
above zero; the 14 that do not are all overnight cells in 2024-25, the season
where the overnight signal fades. That is the CLV pattern
above, not separate findings. Full list in the report.

## Secondary cut and default parameters

Restricted to games where both teams have played at least 10 games (tuned,
pooled, threshold 0): afternoon 50.0% (48.2–51.7%), n = 3,085, real ROI −4.6%.
Early 50.6%, CLV +0.41; overnight 49.9%, CLV +0.17.

With the untouched defaults (pooled, threshold 0): afternoon 49.4% (47.7–51.0%),
real ROI −5.7%. Early 50.1%, CLV +0.61 (+0.51 to +0.70); overnight 49.3%, CLV
+0.38 (+0.30 to +0.45). Tuning made the projection more accurate but not more
profitable, and the CLV does not depend on tuning.

Every cell (3 anchors × 6 thresholds × 3 seasons plus pooled) is tabulated in
[backtest_legacy_report.md](backtest_legacy_report.md): for the tuned model on
both cuts, and for the defaults on every game.

## Market anchors (pre-registration Amendment 1)

For a game on Eastern date D the provider was polled three times in UTC
partition D. Anchors are built from those raw files, keeping only quotes
captured before `commence_time`:

| anchor | file | measured lead before tip, regular season (5th–50th–95th percentile) |
|---|---|---|
| early (~23h) | 01:25 UTC (legacy folder "open") | 18.7–23.1–25.7 h |
| overnight (~17h) | 07:25 UTC (legacy "noon_local") | 13.1–17.2–19.7 h |
| afternoon (~6h) | 18:55 UTC (legacy "close") | 3.2–5.7–8.2 h |

Construction counts: 5,351 provider events, 5,315 matched to a game; 188,265
quote rows in the game's own partition; 1,110 in-play rows dropped (afternoon
tips); 0 books with `last_update` after tip; 20,462 rows with no totals quote
(the book posted only spreads or moneyline); 112 games whose afternoon snapshot
was under 1 hour before tip, dropped from the primary comparison.

Sanity table on the rebuilt anchors (regular season, before grading):

| season | anchor | games | books (median) | line mean | line SD | mean p_over | quarter-point share | MAE vs actual |
|---|---|---|---|---|---|---|---|---|
| 2021-22 | early (~23h) | 582 | 10 | 222.2 | 7.9 | 0.500 | 0.053 | 14.26 |
| 2021-22 | overnight (~17h) | 826 | 15 | 221.7 | 8.0 | 0.500 | 0.070 | 14.62 |
| 2021-22 | afternoon (~6h) | 1,179 | 17 | 220.8 | 8.3 | 0.501 | 0.042 | 14.41 |
| 2022-23 | early (~23h) | 619 | 10 | 228.5 | 7.0 | 0.500 | 0.058 | 14.01 |
| 2022-23 | overnight (~17h) | 860 | 17 | 228.1 | 6.8 | 0.500 | 0.031 | 14.26 |
| 2022-23 | afternoon (~6h) | 1,189 | 19 | 228.5 | 7.2 | 0.500 | 0.023 | 14.24 |
| 2023-24 | early (~23h) | 1,013 | 8 | 228.1 | 9.9 | 0.500 | 0.104 | 14.33 |
| 2023-24 | overnight (~17h) | 1,226 | 13 | 227.9 | 9.8 | 0.500 | 0.074 | 14.29 |
| 2023-24 | afternoon (~6h) | 1,195 | 14 | 228.0 | 10.0 | 0.500 | 0.066 | 14.29 |
| 2024-25 | early (~23h) | 1,098 | 6 | 227.0 | 8.1 | 0.500 | 0.148 | 14.17 |
| 2024-25 | overnight (~17h) | 1,237 | 10 | 226.9 | 8.3 | 0.500 | 0.078 | 14.37 |
| 2024-25 | afternoon (~6h) | 1,193 | 10 | 226.8 | 8.6 | 0.500 | 0.067 | 14.16 |

Games per season with a valid afternoon anchor: 1,179 of 1,230 (2021-22),
1,189 of 1,236, 1,195 of 1,237, 1,193 of 1,237.

Stop-rule check (early must not be more accurate than afternoon). The table
compares different game sets: early covers only 582 to 1,098 games a season. On
the same games, early is worse than afternoon in every season: 14.29 vs 13.99,
14.07 vs 14.00, 14.35 vs 14.23, 14.03 vs 13.90 (pooled 14.18 vs 14.03, n =
3,192). The look-ahead signature corr(anchor − afternoon, actual − afternoon) is
−0.06 to +0.02 for early and −0.04 to +0.02 for overnight. Passed.

## Data defect: the legacy anchors are mislabelled

This section records what the legacy `odds_truth` table's three anchors
actually are, measured from the raw The Odds API payloads they were parsed
from. All 197,757 legacy totals rows were found in their source files, with 0
line or price mismatches, once the provider's decimal prices were used: the
legacy American columns were rounded from them (1.91 became −109).

**Legacy "open": contaminated with in-play prices (quarantined, used for
nothing).** The partition for date D+1 was fetched at 01:25 UTC on D+1, about
8:25 pm Eastern on D, while day-D games were in play. The legacy parser
attached those in-play quotes to the day-D games as their "open". Evidence,
before anything was removed:

- the legacy open's MAE vs the actual total was 12.3–13.4 per season, below its
  own close's 14.1–14.3. An opening line cannot be more accurate than a later one;
- corr(open − close, actual − close) = **0.39** over 4,579 games (noon_local:
  0.007). The "open" knew how the game was going;
- 64% of open games (2,944) had a legacy `game_date` one day after the game.
  Their open MAE was 11.95, against 14.21 for the close; the open games dated on
  the game day had 14.31, slightly worse than the close's 14.05, as an open should;
- measured lead of legacy open rows: median 0.2–1.7 h by season, 5th percentile
  −1.7 h. 3,461 to 8,301 rows a season, touching 634 to 730 games, were captured
  after tip.

**Legacy "close": about six hours before tip, not a close.** Fetched at 18:55
UTC (1:55 or 2:55 pm Eastern). Measured lead: median 5.7 h, 5th–95th
percentile 1.7–8.7 h. For afternoon tip-offs it is captured during play: 141 to
291 rows a season, 19 to 22 games. Any "CLV vs close" from the old repository is
CLV against a line six hours out, with in-play contamination on matinees.

**Legacy "noon_local": an overnight line.** Fetched at 07:25 UTC (2:25 or 3:25
am Eastern). Measured lead: median 17.2 h, 5th–95th percentile 13.1–19.7 h. No
row is in-play.

**Consequence for the old repository:** any result built on open-to-noon or
open-to-close movement there read in-play prices and is void. That includes the
FADE@Noon 65%, the Stage 3 conditioning, RMTS reverse-movement, and the
rolling-reset Elo note that "market_open" beat the close.
