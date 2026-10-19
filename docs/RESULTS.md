# Results: Tier A walk-forward retest

Run 20 October 2026 with `python -m nbatotals backtest --legacy` (maintainer
only: needs the private legacy DB and raw odds payloads). Every table below is
copied from [backtest_legacy_report.md](backtest_legacy_report.md), which that
command regenerates; re-running it and checking `git diff` shows whether the
numbers reproduce. Pre-registered expectations are from
[PREREGISTRATION.md](PREREGISTRATION.md), written before any backtest. The market
anchors were changed twice before any betting metric on the final source was
computed (Amendments 1 and 2; the reasons are in that file and in Appendix B).

## Summary

| Question | Pre-registered expectation | Result |
|---|---|---|
| Does betting the model's side beat the **true close (T−15 min)**? (primary: every game, 3 test seasons) | cover 48–52% | **48.9%** (95% Wilson 47.3–50.5%), n = 3,652; 2023-24 alone is 47.9%, just under the expected range |
| Real-price ROI (median book price) | about −4.5% | **−6.7%** (95% CI −9.8% to −3.7%) |
| Fair (devigged) ROI | about 0% | **−2.4%** (−5.7% to +0.8%) |
| Model MAE vs the true close's MAE | model worse by 0.3–1.5 pts | 14.70 vs 14.16: **worse by 0.54** |
| Blend regression weight on the model, `c` | −0.10 to +0.15, CI including 0 | **−0.117** (−0.264 to +0.031) |
| CLV from noon (~10h) to the true close (the pre-registered pretip criterion) | within ±0.2 points | **−0.02** (−0.08 to +0.05) |
| CLV from opening (~24h) to the true close | within ±0.2 points | **+0.39** (+0.29 to +0.49) = +0.80¢: **outside the expectation** |
| Pinnacle only: cover against Pinnacle's own true close | (secondary) | **49.5%** (47.9–51.2%), ROI at Pinnacle's price −3.8% |
| Pre-registered evidence bar for an edge | not met | **not met**: no cell has a cover lower bound above 52.38% (highest 49.2%) |

In plain words: the model does not beat the closing market, at consensus or at
Pinnacle. Betting its side loses the vig, a little more than a no-information
bettor would. Once the closing line is known, the model adds nothing to it.
What it does carry is box-score information that the market has not fully
priced 18 to 36 hours before tip, and has priced by about 10 hours before tip.
Bets struck at the opening move the right way by the close (+0.39 points), but
win only 49.6% and lose 5.5% at real prices: 0.8¢ of CLV against roughly 4.5¢
of vig. That is reported as an exploratory finding, not an edge. The CLV from
noon onwards is zero.

## Search space (fixed before running)

Declared and committed (80341a5) before any search ran. Objective: RMSE of
`total_proj` vs actual total over the **training seasons'** regular-season
games, all games including opening weeks, pooled across training seasons. No
odds were read during the search, so the market changes in Amendments 1 and 2
did not touch it.

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

## Headline (primary cell: tuned model, true close (T−15 min), every game)

| season | n (true close (T−15 min)) | cover (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | opening (~24h) bets | CLV opening → true_close, points (95% CI) | noon (~10h) bets | CLV noon → true_close, points (95% CI) |
|---|---|---|---|---|---|---|---|---|---|
| 2022-23 | 1,207 | 48.4% (45.6%–51.2%) | 50.0% | -3.2% (-9.0% to 2.5%) | -7.6% (-13.2% to -2.3%) | 858 | +0.43 (+0.25 to +0.62) | 1,188 | +0.03 (-0.09 to +0.15) |
| 2023-24 | 1,225 | 47.9% (45.1%–50.7%) | 50.1% | -4.3% (-9.8% to 1.3%) | -8.5% (-13.8% to -3.2%) | 1,213 | +0.46 (+0.31 to +0.61) | 1,236 | +0.15 (+0.04 to +0.26) |
| 2024-25 | 1,220 | 50.3% (47.5%–53.1%) | 50.2% | 0.2% (-5.3% to 5.7%) | -4.0% (-9.4% to 1.1%) | 1,149 | +0.28 (+0.11 to +0.45) | 1,231 | -0.23 (-0.35 to -0.11) |
| pooled | 3,652 | 48.9% (47.3%–50.5%) | 50.1% | -2.4% (-5.7% to 0.8%) | -6.7% (-9.8% to -3.7%) | 3,220 | +0.39 (+0.29 to +0.49) | 3,655 | -0.02 (-0.08 to +0.05) |

n is graded bets: pushes are excluded (35 pooled), as are games with no
true-close consensus. The "no-info baseline" is the mean devigged probability
of the sides bet: what a bettor with no information would expect to win.

Against the pre-registration: cover 48–52% in every season (2022-23 48.4% and
2024-25 50.3% are inside; 2023-24 47.9% is 0.1 points under); real ROI about
−4.5% (−6.7%, worse by roughly the margin the cover falls below 50%); fair ROI
about 0 (−2.4%, CI including 0).

## CLV by anchor

Tuned model, every game, threshold 0. Bets struck at each anchor's consensus,
measured to the true close.

| bet struck at | season | bets | CLV to true close (T−15 min), points (95% CI) | CLV, cents (95% CI) | cover at that anchor (95% Wilson) | real ROI at that anchor |
|---|---|---|---|---|---|---|
| opening (~24h) | 2022-23 | 858 | +0.43 (+0.25 to +0.62) | +0.94¢ (+0.53 to +1.35) | 51.1% (47.7%–54.4%) | -2.5% |
| opening (~24h) | 2023-24 | 1,213 | +0.46 (+0.31 to +0.61) | +0.91¢ (+0.59 to +1.23) | 47.9% (45.1%–50.7%) | -8.6% |
| opening (~24h) | 2024-25 | 1,149 | +0.28 (+0.11 to +0.45) | +0.58¢ (+0.22 to +0.94) | 50.2% (47.3%–53.1%) | -4.3% |
| opening (~24h) | pooled | 3,220 | +0.39 (+0.29 to +0.49) | +0.80¢ (+0.60 to +1.01) | 49.6% (47.8%–51.3%) | -5.5% |
| noon (~10h) | 2022-23 | 1,188 | +0.03 (-0.09 to +0.15) | +0.07¢ (-0.19 to +0.33) | 49.5% (46.6%–52.3%) | -5.5% |
| noon (~10h) | 2023-24 | 1,236 | +0.15 (+0.04 to +0.26) | +0.25¢ (+0.02 to +0.46) | 47.6% (44.8%–50.4%) | -9.2% |
| noon (~10h) | 2024-25 | 1,231 | -0.23 (-0.35 to -0.11) | -0.48¢ (-0.72 to -0.23) | 50.0% (47.2%–52.8%) | -4.7% |
| noon (~10h) | pooled | 3,655 | -0.02 (-0.08 to +0.05) | -0.06¢ (-0.20 to +0.08) | 49.0% (47.4%–50.6%) | -6.5% |
| afternoon (~5h) | pooled | 3,686 | +0.02 (-0.03 to +0.06) | +0.01¢ (-0.09 to +0.10) | 49.8% (48.2%–51.4%) | -5.0% |
| early evening (~3h) | pooled | 3,670 | +0.04 (-0.00 to +0.08) | +0.05¢ (-0.04 to +0.13) | 49.4% (47.8%–51.0%) | -5.7% |
| late evening (~2h) | pooled | 3,637 | +0.04 (+0.01 to +0.08) | +0.05¢ (-0.03 to +0.13) | 49.6% (47.9%–51.2%) | -5.4% |
| near close (~1h) | pooled | 3,687 | +0.01 (-0.01 to +0.04) | +0.01¢ (-0.05 to +0.06) | 49.2% (47.6%–50.8%) | -6.1% |

Per-season rows for afternoon to near close are in the report. They lie between
−0.05 and +0.11 points. The late-evening pooled lower bound of +0.01 points
(0.05¢) is too small to matter.

## Pinnacle only (secondary)

Tuned model against Pinnacle's own true-close total and its devigged price, for
games where Pinnacle quoted one: 1,206 (2022-23), 1,220 and 1,209 regular-season
games. "ROI at Pinnacle's price" is what flat bets at Pinnacle's actual close
would have returned.

| edge ≥ | season | n | pushes | cover (95% Wilson) | baseline | fair ROI at Pinnacle's devigged price (CI) | ROI at Pinnacle's own price (CI) |
|---|---|---|---|---|---|---|---|
| 0 | 2022-23 | 1,187 | 19 | 49.5% (46.6%–52.3%) | 50.0% | -1.0% (-6.7% to 4.6%) | -3.8% (-9.3% to 1.7%) |
| 0 | 2023-24 | 1,209 | 11 | 48.4% (45.6%–51.2%) | 50.0% | -3.3% (-8.9% to 2.3%) | -6.0% (-11.5% to -0.6%) |
| 0 | 2024-25 | 1,198 | 11 | 50.8% (47.9%–53.6%) | 50.0% | 1.4% (-4.3% to 6.9%) | -1.5% (-7.0% to 3.9%) |
| 0 | pooled | 3,594 | 41 | 49.5% (47.9%–51.2%) | 50.0% | -1.0% (-4.3% to 2.2%) | -3.8% (-7.0% to -0.7%) |
| 1 | pooled | 2,951 | 37 | 48.5% (46.7%–50.3%) | 50.0% | -3.2% (-6.7% to 0.4%) | -5.9% (-9.4% to -2.5%) |
| 2 | pooled | 2,348 | 28 | 48.5% (46.5%–50.5%) | 50.0% | -3.1% (-7.1% to 1.0%) | -5.8% (-9.7% to -1.9%) |
| 3 | pooled | 1,821 | 23 | 49.8% (47.5%–52.0%) | 50.0% | -0.6% (-5.1% to 4.0%) | -3.4% (-7.8% to 1.1%) |
| 4 | pooled | 1,332 | 16 | 50.8% (48.1%–53.4%) | 50.0% | 1.5% (-3.9% to 6.8%) | -1.4% (-6.6% to 3.8%) |
| 6 | pooled | 671 | 9 | 49.8% (46.0%–53.6%) | 50.0% | -0.5% (-7.9% to 7.2%) | -3.3% (-10.5% to 4.2%) |

Per-season rows for every threshold are in the report.

## Projection accuracy (selected rows)

| season | anchor | n | MAE model (tuned) | MAE model (default) | MAE line | RMSE model (tuned) | RMSE model (default) | RMSE line |
|---|---|---|---|---|---|---|---|---|
| 2022-23 | true close (T−15 min) | 1,220 | 14.63 | 15.17 | 14.12 | 18.70 | 19.29 | 18.18 |
| 2023-24 | true close (T−15 min) | 1,236 | 14.79 | 14.98 | 14.21 | 18.40 | 18.78 | 17.69 |
| 2024-25 | true close (T−15 min) | 1,231 | 14.68 | 15.10 | 14.15 | 18.31 | 18.80 | 17.66 |
| pooled | true close (T−15 min) | 3,687 | 14.70 | 15.09 | 14.16 | 18.47 | 18.96 | 17.84 |
| pooled | opening (~24h) | 3,226 | 14.69 | 15.05 | 14.34 | 18.39 | 18.87 | 18.01 |
| pooled | noon (~10h) | 3,664 | 14.68 | 15.06 | 14.26 | 18.45 | 18.93 | 17.97 |

Expectation: the model worse than the line by 0.3 to 1.5 points of MAE. Result:
0.51 to 0.58 behind the true close in each season, and 0.35 behind even the
opening line. Every anchor's rows are in the report.

## Market + model blend regression: actual = a + b·true close + c·model

| model run | season | n | intercept (95% CI) | b: true close (T−15 min) line (95% CI) | c: model (95% CI) |
|---|---|---|---|---|---|
| tuned | 2022-23 | 1,220 | +18.9 (-15.8, +53.5) | 1.027 (0.783, 1.271) | -0.105 (-0.364, +0.154) |
| tuned | 2023-24 | 1,236 | +16.1 (-10.5, +42.7) | 1.149 (0.920, 1.377) | -0.217 (-0.485, +0.051) |
| tuned | 2024-25 | 1,231 | -5.6 (-34.7, +23.6) | 1.058 (0.844, 1.272) | -0.030 (-0.272, +0.212) |
| tuned | pooled | 3,687 | +9.1 (-7.8, +26.1) | 1.080 (0.950, 1.210) | -0.117 (-0.264, +0.031) |
| default | 2022-23 | 1,220 | +13.5 (-18.3, +45.3) | 1.040 (0.819, 1.261) | -0.095 (-0.268, +0.078) |
| default | 2023-24 | 1,236 | +4.4 (-18.0, +26.7) | 0.979 (0.784, 1.174) | +0.003 (-0.161, +0.167) |
| default | 2024-25 | 1,231 | -6.6 (-32.4, +19.1) | 1.065 (0.881, 1.250) | -0.033 (-0.192, +0.127) |
| default | pooled | 3,687 | +2.9 (-12.0, +17.7) | 1.027 (0.914, 1.140) | -0.037 (-0.131, +0.058) |

This is the cleanest test of whether the model knows something the market does
not. Expectation: `b` near 1; `c` between −0.10 and +0.15 with a CI including 0.
Result: `b` 0.98 to 1.15; `c` −0.22 to +0.003, every interval including 0. The
pooled tuned value (−0.117) is just under the expected range. Given the true
close, the model's best weight is zero.

## Does the model's edge predict the line move?

Correlation between the model's edge at an anchor and the line's move from that
anchor to the true close.

| bet anchor | season | n | corr (95% CI) |
|---|---|---|---|
| opening (~24h) | 2022-23 | 858 | +0.209 (+0.144, +0.272) |
| opening (~24h) | 2023-24 | 1,213 | +0.230 (+0.176, +0.283) |
| opening (~24h) | 2024-25 | 1,149 | +0.144 (+0.087, +0.201) |
| opening (~24h) | pooled | 3,220 | +0.197 (+0.164, +0.230) |
| noon (~10h) | 2022-23 | 1,188 | +0.037 (-0.020, +0.093) |
| noon (~10h) | 2023-24 | 1,236 | +0.064 (+0.009, +0.120) |
| noon (~10h) | 2024-25 | 1,231 | -0.056 (-0.111, +0.000) |
| noon (~10h) | pooled | 3,655 | +0.020 (-0.012, +0.053) |
| afternoon (~5h) | pooled | 3,686 | -0.005 (-0.037, +0.028) |
| early evening (~3h) | pooled | 3,684 | +0.001 (-0.031, +0.033) |
| late evening (~2h) | pooled | 3,640 | +0.006 (-0.027, +0.038) |
| near close (~1h) | pooled | 3,687 | -0.008 (-0.040, +0.024) |

From the opening, the line moves towards the model; from noon on, it does not.
The information the model carries is priced into the market between about 24
and 10 hours before tip.

## Bug-first checks on the positive opening CLV

The pre-registration says to treat any number that looks like an edge as a bug
first. The opening CLV's lower bound above zero triggered that. Each check and
its outcome:

1. **Anchor timestamps.** Every opening consensus was captured before the same
   game's true-close consensus (4,368 games checked), using the provider's own
   poll times. Outcome: ordering correct. (Separately, 17 early- or late-evening
   snapshots in early 2024-25 were polled at or after the true close and were
   dropped by the ordering rule; none is an opening.)
2. **Join.** Every event is matched by Eastern commence date and both team
   names: 5,419 of 5,419 events matched a game. Outcome: no unmatched or mixed
   games.
3. **Sign convention.** Unit-tested (`tests/test_harness.py::test_clv_sign`).
   Outcome: correct.
4. **Market drift.** The mean move from opening to true close is −0.01 points.
   CLV is positive for both sides: overs +0.31, unders +0.52. Outcome: not drift.
5. **Book composition.** The median is 32 books at opening and 33 at the close,
   so composition barely changes. Measured only on each book's own line at both
   times, CLV is +0.38 (+0.28 to +0.49). Outcome: not composition.
6. **Placebos.** Random sides (seeded): −0.06 (−0.16 to +0.04). A predictor with
   no team information (the point-in-time league-average total): −0.02 (−0.12 to
   +0.08). Outcome: the CLV needs the model's team information.
7. **Look-ahead.** Opening snapshots were polled between 1:10 and 4:10 am
   Eastern, after the previous evening's games had finished, so every box score
   the model uses existed before the opening line was taken. Split by whether
   either team played the previous day: +0.38 (2,313 games) vs +0.40 (907 games).
   Outcome: no look-ahead route found.
8. **Devig and push handling.** CLV in points uses no prices, and pushes do not
   enter it. CLV in cents uses the normal approximation pre-registered (SD 18
   points). The ROI arithmetic is unit-tested. Outcome: not applicable; correct.

Conclusion: the opening CLV looks real for this data, and **it is not an
edge**. Bets at the opening win 49.6% (47.8–51.3%) and lose 5.5% at real
prices. The noon CLV, which is the pre-registered criterion, is zero. A real
test of an opening-line strategy would need opening prices with limits, an
unseen season (2025-26 onward, collected live) and a pre-registered rule; this
backtest does not provide that.

## Cells clearing a bar

No cell in any run, anchor, cut, threshold or season has a cover-rate lower
bound above 52.38%. The highest is 49.2% (opening, edge ≥ 6, pooled: 53.8%,
n = 448, real ROI +2.6% with a CI from −6.3% to +11.5%). 164 cells have a CLV
lower bound above zero. All 96 opening cells do. Of the other 68, 25 are noon
cells in single seasons (12 in 2022-23, 13 in 2023-24, mostly at higher edge
thresholds); 40 are afternoon-to-near-close cells in 2023-24, the one season
where the late buckets show small positive CLV (+0.06 to +0.11 points); and 3 are
pooled evening cells whose lower bounds are 0.00 to 0.01 points.

## Secondary cut and default parameters

Both teams with at least 10 games played (tuned, pooled, threshold 0): true
close 49.0% (47.3–50.7%), n = 3,189, real ROI −6.5%. Opening CLV +0.38; noon
−0.01.

Untouched defaults (pooled, threshold 0): true close 48.8% (47.2–50.5%), real ROI
−6.8%. Opening CLV +0.53 (+0.43 to +0.63); noon +0.06 (−0.01 to +0.12). Tuning
made the projection more accurate but not more profitable, and the CLV does
not depend on it.

## Market anchors (pre-registration Amendment 2)

Source: the maintainer's multi-region The Odds API payloads, one file per game,
bucket and market, each recording when it was polled and the event's
`commence_time`. Read through `nbatotals/evaluate/adapters/legacy_multiregion.py`.

Construction counts: 37,212 totals files; 5,419 provider events, all matched
to a game (5,418 games); 51 files polled at or after tip dropped; 0 books with
`last_update` after tip; 4 book rows without a clean quote; 17 evening
consensus rows captured at or after the same game's true close dropped. No team
name was missing from the alias map.

Games that joined, regular season (all phases in brackets): 2021-22 1,051 of
1,230 (1,144), 2022-23 1,222 of 1,236 (1,306), 2023-24 1,237 of 1,237 (1,319),
2024-25 1,237 of 1,237 (1,321). **2021-22 is incomplete** in this source. It is
a training season only, and the parameter search used no odds, so no test
number depends on it.

Measured leads match the bucket names: true close 0.25 h median (all between
0.08 and 0.42 h), near close 1 h, late evening 2 h, early evening 3 h, afternoon
5 h, noon 10 h, opening 18 h (2022-23 onwards) to 24 h (2021-22; range 16 to
36 h). In 2024-25, 259 game-bucket snapshots sit outside their bucket's usual
lead band (opening 58, noon 56, afternoon 64, early evening 57, late evening
24); 2 more fall in 2025-26. Only those polled at or after the true close were
dropped. The true-close leads are all inside 0.08–0.42 h.

Sanity table (regular season, before grading):

| season | anchor | games | books (median) | line mean | line SD | mean p_over | quarter-point share | MAE vs actual |
|---|---|---|---|---|---|---|---|---|
| 2021-22 | opening (~24h) | 497 | 15 | 222.2 | 7.9 | 0.506 | 0.050 | 15.38 |
| 2021-22 | noon (~10h) | 1,045 | 26 | 221.4 | 8.0 | 0.503 | 0.035 | 14.63 |
| 2021-22 | afternoon (~5h) | 1,051 | 26 | 221.3 | 8.4 | 0.503 | 0.030 | 14.49 |
| 2021-22 | early evening (~3h) | 1,051 | 26 | 221.3 | 8.4 | 0.503 | 0.023 | 14.51 |
| 2021-22 | late evening (~2h) | 1,051 | 26 | 221.3 | 8.5 | 0.503 | 0.035 | 14.52 |
| 2021-22 | near close (~1h) | 1,051 | 26 | 221.3 | 8.5 | 0.503 | 0.028 | 14.51 |
| 2021-22 | true close (T−15 min) | 1,049 | 26 | 221.3 | 8.5 | 0.503 | 0.039 | 14.47 |
| 2022-23 | opening (~24h) | 859 | 26 | 228.2 | 6.8 | 0.501 | 0.023 | 14.28 |
| 2022-23 | noon (~10h) | 1,190 | 31 | 228.6 | 7.0 | 0.502 | 0.029 | 14.21 |
| 2022-23 | afternoon (~5h) | 1,221 | 31 | 228.3 | 7.2 | 0.502 | 0.028 | 14.20 |
| 2022-23 | early evening (~3h) | 1,221 | 31 | 228.3 | 7.2 | 0.502 | 0.019 | 14.20 |
| 2022-23 | late evening (~2h) | 1,221 | 31 | 228.3 | 7.2 | 0.502 | 0.016 | 14.20 |
| 2022-23 | near close (~1h) | 1,221 | 31 | 228.3 | 7.2 | 0.502 | 0.025 | 14.18 |
| 2022-23 | true close (T−15 min) | 1,220 | 31 | 228.3 | 7.3 | 0.502 | 0.020 | 14.12 |
| 2023-24 | opening (~24h) | 1,214 | 35 | 228.0 | 9.8 | 0.500 | 0.028 | 14.35 |
| 2023-24 | noon (~10h) | 1,237 | 41 | 228.0 | 9.8 | 0.501 | 0.017 | 14.26 |
| 2023-24 | afternoon (~5h) | 1,237 | 41 | 227.9 | 10.0 | 0.501 | 0.016 | 14.26 |
| 2023-24 | early evening (~3h) | 1,237 | 41 | 227.9 | 10.0 | 0.501 | 0.010 | 14.27 |
| 2023-24 | late evening (~2h) | 1,237 | 41 | 227.9 | 10.0 | 0.501 | 0.014 | 14.26 |
| 2023-24 | near close (~1h) | 1,236 | 41 | 228.0 | 10.1 | 0.500 | 0.015 | 14.25 |
| 2023-24 | true close (T−15 min) | 1,236 | 41 | 228.1 | 10.1 | 0.500 | 0.020 | 14.21 |
| 2024-25 | opening (~24h) | 1,153 | 39 | 226.8 | 8.1 | 0.500 | 0.018 | 14.37 |
| 2024-25 | noon (~10h) | 1,237 | 34 | 226.9 | 8.3 | 0.500 | 0.016 | 14.31 |
| 2024-25 | afternoon (~5h) | 1,236 | 34 | 226.8 | 8.6 | 0.500 | 0.016 | 14.25 |
| 2024-25 | early evening (~3h) | 1,220 | 34 | 226.8 | 8.6 | 0.500 | 0.017 | 14.26 |
| 2024-25 | late evening (~2h) | 1,187 | 34 | 226.8 | 8.7 | 0.501 | 0.019 | 14.21 |
| 2024-25 | near close (~1h) | 1,234 | 34 | 226.8 | 8.7 | 0.501 | 0.016 | 14.19 |
| 2024-25 | true close (T−15 min) | 1,231 | 34 | 226.8 | 8.8 | 0.500 | 0.013 | 14.15 |

Stop rule (no earlier bucket may have a lower MAE than the true close on the
same games). On the same games, every earlier bucket's MAE is at or above the
true close's in every season; pooled: opening 14.49 vs 14.28, noon 14.35 vs
14.21, afternoon 14.30 vs 14.23, early evening 14.31 vs 14.23, late evening
14.30 vs 14.22, near close 14.27 vs 14.23. The fall is not strictly monotonic
between the middle buckets (for example 2021-22 afternoon 14.51, early evening
14.53, late evening 14.54 on the same games). Those steps are 0.01 to 0.03
points, well inside noise. True-close MAE is 14.12 to 14.47, against an expected
~14.4; mean devigged p_over is 0.500 to 0.506 at every bucket. The look-ahead
signature corr(bucket − close, actual − close) is −0.10 to 0.00. Passed.

---

## Appendix A: cross-check against the temporal payloads (Amendment 1)

Before the multi-region source was found, Phase 3 was run against the legacy
temporal payloads. Those are polled three times a day and have no close: early
(~23h), overnight (~17h) and the last pre-tip snapshot, afternoon (~6h). That
run is kept as a cross-check. Its full report is
[backtest_legacy_temporal_report.md](backtest_legacy_temporal_report.md),
regenerated with `backtest --legacy --market temporal`.

| season | n (afternoon (~6h)) | cover (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | early (~23h) bets | CLV early → afternoon, points (95% CI) | overnight (~17h) bets | CLV overnight → afternoon, points (95% CI) |
|---|---|---|---|---|---|---|---|---|---|
| 2022-23 | 1,181 | 49.7% (46.9%–52.6%) | 50.0% | -0.6% (-6.3% to 5.0%) | -5.1% (-10.6% to 0.3%) | 603 | +0.37 (+0.19 to +0.56) | 838 | +0.38 (+0.22 to +0.53) |
| 2023-24 | 1,181 | 48.8% (45.9%–51.6%) | 50.0% | -2.4% (-8.1% to 3.3%) | -6.8% (-12.2% to -1.3%) | 973 | +0.37 (+0.22 to +0.52) | 1,184 | +0.25 (+0.13 to +0.36) |
| 2024-25 | 1,181 | 50.6% (47.7%–53.4%) | 50.0% | 1.1% (-4.5% to 6.7%) | -3.4% (-8.8% to 1.9%) | 1,054 | +0.47 (+0.31 to +0.64) | 1,193 | +0.05 (-0.07 to +0.16) |
| pooled | 3,543 | 49.7% (48.0%–51.3%) | 50.0% | -0.6% (-3.9% to 2.6%) | -5.1% (-8.2% to -2.0%) | 2,630 | +0.41 (+0.31 to +0.51) | 3,215 | +0.21 (+0.13 to +0.28) |

Blend regression against the afternoon (~6h) line, pooled: `c` = −0.100
(−0.258 to +0.057). No cell had a cover lower bound above 52.38%.

How the two runs fit together: both show no edge against the reference line
and the same CLV from about a day out (+0.41 vs +0.39). The temporal run's
positive overnight (~17h) CLV and the multi-region run's zero noon (~10h) CLV
point the same way: the model's information is priced in between roughly 17
and 10 hours before tip. Its anchors were built by the same rules (pre-tip
quotes only, timestamp ordering); they are described in its report and in
Amendment 1.

## Appendix B: data defect in the legacy odds table (historical note)

This records what the legacy `odds_truth` table's three anchors actually are,
measured from the raw temporal payloads they were parsed from. Nothing in the
results above uses that table. All 197,757 legacy totals rows were found in
their source files, with 0 line or price mismatches, once the provider's decimal
prices were used: the legacy American columns were rounded from them (1.91
became −109).

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
