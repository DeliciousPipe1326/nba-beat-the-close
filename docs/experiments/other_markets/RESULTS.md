# Results: Experiment 5, spreads and moneyline through the same harness

Run 20 October 2026 with

```bash
python -m nbatotals backtest --legacy --market-type spreads [--model elo_total]
python -m nbatotals backtest --legacy --market-type h2h --reuse-fit [--model elo_total]
```

(maintainer only: needs the private legacy DB and the multi-region payloads).
Every number below is copied from the four full reports in this folder, which
those commands regenerate:
[spreads, pace_eff](backtest_legacy_spreads_report_pace_eff.md),
[spreads, elo_total](backtest_legacy_spreads_report_elo_total.md),
[moneyline, pace_eff](backtest_legacy_h2h_report_pace_eff.md),
[moneyline, elo_total](backtest_legacy_h2h_report_elo_total.md).
The rules and expectations were committed before anything was computed
([PREREGISTRATION.md](PREREGISTRATION.md), commit 6ed9336). The totals
pre-registration, its results and its reports are unchanged. Re-running the
totals backtests for both projectors with this code rewrote
`docs/backtest_legacy_report.md`, `docs/backtest_legacy_report_elo_total.md` and
both fit logs with an empty `git diff`.

Test seasons 2022-23, 2023-24 and 2024-25. Everything was fitted on earlier
seasons only. Graded against the devigged consensus 15 minutes before tip.
"elo_total" here means the margin version of its Elo machinery. The pre-registration
explains why its totals ratings cannot be used for a margin.

## Summary

| Question | Pre-registered expectation | pace_eff | elo_total (margin Elo) |
|---|---|---|---|
| **ATS cover vs the true-close consensus spread**, every game, pooled | 48–52% in each season and pooled | **50.3%** (48.7–51.9%), n = 3,629; seasons 51.4, 48.2, 51.3% | **49.4%** (47.8–51.1%), n = 3,629; seasons 49.2, 48.5, 50.7% |
| ATS real-price ROI | about −4.5%, CI including it | −4.0% (−7.0 to −1.0%) | −5.6% (−8.7 to −2.6%) |
| ATS fair ROI | about 0, CI including 0 | +0.6% (−2.5 to +3.8%) | −1.1% (−4.4 to +2.1%) |
| ATS cover at thresholds 1–6 points (pooled) | 47–53%, no monotone rise | 49.0–50.9%, no rise | 46.6–50.4%; **6 points: 46.6%** (n = 399), just under 47% |
| Margin MAE, model vs the close | model worse by 0.3–1.5; close about 9.0 (brief) or 9.5–10 (mine) | **10.91 vs 10.29** (+0.62) | **10.79 vs 10.29** (+0.50). The close's MAE is above both expectations |
| Spread blend `actual = a + b·close + c·model` | `b` ≈ 1, `c` ≈ 0 with CI including 0 | b 0.973, **c +0.052 (−0.066, +0.170)** | b 1.015, **c −0.009 (−0.132, +0.114)** |
| Spread CLV, opening → true close | 0 to +0.4 points | +0.06 (+0.01 to +0.12) | +0.10 (+0.04 to +0.16) |
| Spread CLV, noon → true close (the pre-registered criterion) | within ±0.2 | +0.04 (−0.01 to +0.09) | +0.04 (−0.00 to +0.09) |
| **Moneyline log loss, model − market** (pooled) | > 0 every season, CI above 0 | **+0.0346** (+0.0268 to +0.0423); every season > 0 | **+0.0282** (+0.0213 to +0.0350); every season > 0 |
| Moneyline logistic blend, model coefficient | ≈ 0, CI including 0; market ≈ 1 | −0.030 (−0.209, +0.149); market 1.047 | −0.090 (−0.274, +0.094); market 1.092 |
| Moneyline betting at 0 / 2 / 4 / 6%, real ROI | −2% to −8%; fair about 0 | −5.8 / −5.1 / −5.6 / −4.8% | −5.7 / −6.7 / −6.7 / −4.9% |
| Moneyline CLV, noon → true close | within ±0.5¢ | +0.07¢ (−0.06 to +0.20) | +0.11¢ (−0.02 to +0.24) |
| Pinnacle only | same conclusions; smaller loss at Pinnacle's price | ATS 50.2%, −1.8% at Pinnacle's price; ML log loss +0.034, −4.7% | ATS 49.6%, −3.1%; ML +0.028, −4.2% |
| `h`, fitted home-court constant | pace_eff +2 to +3.5; Elo within ±1 | +1.62, +2.15, +2.23 (**2022-23 below the range**) | −0.34, −0.27, −0.26 |
| Logistic scale `s` | 6–12 (not a criterion) | 9.21, 8.65, 8.86 | 8.51, 8.78, 8.56 |
| **Pre-registered evidence bar** (both markets) | not met | **not met** | **not met** |

In plain words: neither rating beats the closing spread or the closing
moneyline, at the consensus or at Pinnacle. Betting the model's side against the
spread wins about half the time and loses roughly the vig. Given the close, the
model's margin adds nothing (blend weight about 0). The model's win
probabilities are clearly worse than the market's (log loss 0.03 higher in
every season), and given the market they add nothing either. As in totals,
the spread line moves slightly towards the ratings after the opening (+0.06 and
+0.10 points). It also moves a little after noon (+0.04, interval touching zero),
but that never becomes covers or profit. Every pre-registered expectation held
except three small misses: the close's own MAE (10.3, not about 9), pace_eff's
`h` in 2022-23 (+1.6, not +2 or more), and elo_total's 6-point cell (46.6%, n = 399).

## Headline: spreads

Primary cell: tuned model, true close (T−15 min), every game, pushes excluded.

**pace_eff** (expectation: cover 48–52% each season; real ROI about −4.5%; fair about 0)

| season | n | cover (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | CLV opening → close, points | CLV noon → close, points |
|---|---|---|---|---|---|---|---|
| 2022-23 | 1,194 | 51.4% (48.6%–54.2%) | 50.0% | 2.8% (-2.8% to 8.6%) | -1.8% (-7.2% to 3.8%) | +0.02 (-0.08 to +0.13) | +0.02 (-0.07 to +0.11) |
| 2023-24 | 1,221 | 48.2% (45.4%–51.0%) | 50.0% | -3.6% (-9.2% to 2.0%) | -8.1% (-13.4% to -2.6%) | +0.06 (-0.03 to +0.15) | +0.03 (-0.05 to +0.11) |
| 2024-25 | 1,214 | 51.3% (48.5%–54.1%) | 50.0% | 2.8% (-2.9% to 8.5%) | -2.1% (-7.4% to 3.4%) | +0.10 (+0.00 to +0.21) | +0.06 (-0.02 to +0.15) |
| **pooled** | **3,629** | **50.3% (48.7%–51.9%)** | 50.0% | 0.6% (-2.5% to 3.8%) | -4.0% (-7.0% to -1.0%) | +0.06 (+0.01 to +0.12) | +0.04 (-0.01 to +0.09) |

Without the fitted home-court constant (`h = 0`, the brief's literal margin):
pooled 50.3% (48.6–51.9%), real ROI −4.1% (−7.2 to −1.0%).

**elo_total, margin Elo** (same expectations)

| season | n | cover (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | CLV opening → close, points | CLV noon → close, points |
|---|---|---|---|---|---|---|---|
| 2022-23 | 1,194 | 49.2% (46.3%–52.0%) | 50.0% | -1.8% (-7.4% to 3.9%) | -6.1% (-11.5% to -0.7%) | +0.05 (-0.05 to +0.16) | +0.01 (-0.08 to +0.11) |
| 2023-24 | 1,221 | 48.5% (45.7%–51.3%) | 50.0% | -3.0% (-8.7% to 2.7%) | -7.5% (-12.9% to -2.0%) | +0.16 (+0.07 to +0.25) | +0.09 (+0.01 to +0.17) |
| 2024-25 | 1,214 | 50.7% (47.8%–53.5%) | 50.0% | 1.4% (-4.3% to 7.0%) | -3.4% (-8.7% to 2.0%) | +0.08 (-0.02 to +0.18) | +0.03 (-0.05 to +0.11) |
| **pooled** | **3,629** | **49.4% (47.8%–51.1%)** | 50.0% | -1.1% (-4.4% to 2.1%) | -5.6% (-8.7% to -2.6%) | +0.10 (+0.04 to +0.16) | +0.04 (-0.00 to +0.09) |

`h = 0`: pooled 49.7% (48.1–51.4%), real ROI −5.1%.

Fit: elo_total's margin K was 0.05 in every season, inside the declared grid
{0.02, 0.05, 0.1, 0.2}. Full fit tables are in the reports.

## Headline: moneyline

Primary cell: tuned model, true close, every game with a non-zero edge (one bet
per game: home if the model's home probability is above the market's devigged
one, away if below).

**pace_eff** (expectation: log loss worse than the market's; win rate near the baseline; real ROI −2% to −8%)

| season | bets | log loss model vs market | difference (95% CI) | win rate (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | CLV opening → close, cents | CLV noon → close, cents |
|---|---|---|---|---|---|---|---|---|---|
| 2022-23 | 1,220 | 0.6571 vs 0.6250 | +0.0322 (+0.0178 to +0.0467) | 37.7% (35.0%–40.5%) | 37.4% | 3.5% (-5.2% to 12.2%) | -0.7% (-9.0% to 7.8%) | -0.03¢ (-0.33 to +0.26) | +0.09¢ (-0.16 to +0.34) |
| 2023-24 | 1,236 | 0.6216 vs 0.5806 | +0.0410 (+0.0288 to +0.0535) | 34.6% (32.0%–37.3%) | 37.3% | -8.2% (-16.7% to 0.2%) | -12.0% (-20.1% to -4.0%) | -0.03¢ (-0.27 to +0.21) | +0.03¢ (-0.17 to +0.24) |
| 2024-25 | 1,231 | 0.6124 vs 0.5818 | +0.0306 (+0.0169 to +0.0448) | 38.6% (35.9%–41.3%) | 37.7% | -0.7% (-9.1% to 7.9%) | -4.7% (-12.8% to 3.5%) | +0.19¢ (-0.07 to +0.45) | +0.09¢ (-0.13 to +0.30) |
| **pooled** | **3,687** | **0.6303 vs 0.5957** | **+0.0346 (+0.0268 to +0.0423)** | 37.0% (35.4%–38.5%) | 37.5% | -1.8% (-6.7% to 3.1%) | -5.8% (-10.5% to -1.1%) | +0.04¢ (-0.11 to +0.19) | +0.07¢ (-0.06 to +0.20) |

**elo_total, margin Elo**

| season | bets | log loss model vs market | difference (95% CI) | win rate (95% Wilson) | no-info baseline | fair ROI (95% CI) | real ROI (95% CI) | CLV opening → close, cents | CLV noon → close, cents |
|---|---|---|---|---|---|---|---|---|---|
| 2022-23 | 1,220 | 0.6500 vs 0.6250 | +0.0251 (+0.0125 to +0.0379) | 40.5% (37.8%–43.3%) | 40.3% | 3.3% (-5.2% to 11.8%) | -0.9% (-9.1% to 7.4%) | -0.02¢ (-0.32 to +0.27) | +0.06¢ (-0.19 to +0.31) |
| 2023-24 | 1,236 | 0.6144 vs 0.5806 | +0.0338 (+0.0229 to +0.0449) | 38.9% (36.2%–41.7%) | 39.7% | -3.7% (-11.9% to 4.4%) | -7.7% (-15.6% to 0.0%) | +0.20¢ (-0.04 to +0.44) | +0.14¢ (-0.07 to +0.35) |
| 2024-25 | 1,231 | 0.6074 vs 0.5818 | +0.0256 (+0.0135 to +0.0379) | 38.7% (36.0%–41.4%) | 39.4% | -4.5% (-12.4% to 3.9%) | -8.3% (-15.9% to -0.3%) | +0.29¢ (+0.03 to +0.55) | +0.12¢ (-0.09 to +0.34) |
| **pooled** | **3,687** | **0.6239 vs 0.5957** | **+0.0282 (+0.0213 to +0.0350)** | 39.4% (37.8%–40.9%) | 39.8% | -1.6% (-6.4% to 3.1%) | -5.7% (-10.2% to -1.1%) | +0.15¢ (-0.00 to +0.30) | +0.11¢ (-0.02 to +0.24) |

Brier scores tell the same story: pooled model − market +0.0155 (pace_eff) and
+0.0126 (elo_total), intervals above zero.

By threshold at the true close (pooled; expectation: win rate near the baseline,
fair ROI about 0, real ROI −2% to −8%):

| projector | edge > | bets | win rate (95% Wilson) | baseline | fair ROI (95% CI) | real ROI (95% CI) |
|---|---|---|---|---|---|---|
| pace_eff | 0% | 3,687 | 37.0% (35.4%–38.5%) | 37.5% | -1.8% (-6.7%, 3.1%) | -5.8% (-10.5%, -1.1%) |
| pace_eff | 2% | 3,224 | 36.0% (34.3%–37.7%) | 36.2% | -1.1% (-6.3%, 4.3%) | -5.1% (-10.1%, 0.1%) |
| pace_eff | 4% | 2,726 | 34.3% (32.5%–36.1%) | 34.9% | -1.6% (-7.5%, 4.4%) | -5.6% (-11.3%, 0.2%) |
| pace_eff | 6% | 2,291 | 33.0% (31.1%–35.0%) | 33.7% | -0.9% (-7.4%, 5.9%) | -4.8% (-11.1%, 1.6%) |
| elo_total | 0% | 3,687 | 39.4% (37.8%–40.9%) | 39.8% | -1.6% (-6.4%, 3.1%) | -5.7% (-10.2%, -1.1%) |
| elo_total | 2% | 3,087 | 37.2% (35.5%–38.9%) | 38.1% | -2.8% (-8.1%, 2.6%) | -6.7% (-11.8%, -1.6%) |
| elo_total | 4% | 2,518 | 35.7% (33.8%–37.6%) | 36.8% | -2.8% (-8.9%, 3.3%) | -6.7% (-12.7%, -0.9%) |
| elo_total | 6% | 1,997 | 35.0% (32.9%–37.1%) | 35.7% | -0.9% (-7.9%, 6.1%) | -4.9% (-11.6%, 1.9%) |

The win rates are below 50% because most of these bets are on underdogs (see
the bug-first checks): 72% (elo_total) and 78% (pace_eff) of the bets at the close.

## CLV by anchor

Threshold-0 bets struck at each earlier bucket, measured to the true close,
pooled over the three test seasons. Expectation: spreads 0 to +0.4 points from
opening and within ±0.2 from noon on; moneyline within ±0.5¢ from noon on.
Spread cents use the declared normal approximation with SD 12 points (the
measured RMSE of the close against the actual margin is 13.24).

**Spreads (points; cents in brackets)**

| bet struck at | pace_eff CLV, points (95% CI) | pace_eff cents | elo_total CLV, points (95% CI) | elo_total cents |
|---|---|---|---|---|
| opening (~24h) | +0.06 (+0.01 to +0.12) | +0.17¢ | +0.10 (+0.04 to +0.16) | +0.30¢ |
| noon (~10h) | +0.04 (-0.01 to +0.09) | +0.09¢ | +0.04 (-0.00 to +0.09) | +0.12¢ |
| afternoon (~5h) | +0.04 (+0.00 to +0.08) | +0.09¢ | +0.04 (+0.01 to +0.08) | +0.11¢ |
| early evening (~3h) | +0.03 (+0.00 to +0.07) | +0.09¢ | +0.04 (+0.01 to +0.07) | +0.11¢ |
| late evening (~2h) | +0.02 (-0.01 to +0.05) | +0.04¢ | +0.04 (+0.00 to +0.07) | +0.09¢ |
| near close (~1h) | -0.00 (-0.02 to +0.01) | -0.03¢ | +0.00 (-0.02 to +0.02) | -0.01¢ |

Covers at those anchors (pooled, threshold 0): pace_eff 50.2–50.7%, elo_total
49.1–50.1%. Real ROI −3.3% to −4.3% and −4.4% to −6.3%.

**Moneyline (cents of devigged probability)**

| bet struck at | pace_eff CLV (95% CI) | pace_eff real ROI | elo_total CLV (95% CI) | elo_total real ROI |
|---|---|---|---|---|
| opening (~24h) | +0.04¢ (-0.11, +0.19) | -5.0% | +0.15¢ (-0.00, +0.30) | -5.7% |
| noon (~10h) | +0.07¢ (-0.06, +0.20) | -5.0% | +0.11¢ (-0.02, +0.24) | -5.1% |
| afternoon (~5h) | +0.08¢ (-0.01, +0.18) | -6.5% | +0.10¢ (+0.00, +0.19) | -5.2% |
| early evening (~3h) | +0.05¢ (-0.04, +0.14) | -6.5% | +0.08¢ (-0.01, +0.16) | -4.8% |
| late evening (~2h) | +0.03¢ (-0.05, +0.11) | -5.1% | +0.06¢ (-0.02, +0.14) | -5.1% |
| near close (~1h) | -0.02¢ (-0.07, +0.02) | -5.8% | -0.01¢ (-0.06, +0.03) | -5.9% |

Every CLV figure is within its pre-registered band. Several spread intervals
(afternoon, early evening, and late evening for elo_total) sit just above zero.
Their size is 0.03 to 0.04 points, about a tenth of a cent, against roughly
4.5¢ of vig. They are listed in the reports under "Cells clearing a bar" and
count as exploratory observations, not as edges.

## Pinnacle only (secondary)

Against Pinnacle's own true-close quote, on games where Pinnacle quotes that
market. Expectation: the same conclusions, with a smaller loss at Pinnacle's
price than at the median price.

| market | projector | n | cover / win rate (95% Wilson) | baseline | fair ROI (95% CI) | ROI at Pinnacle's price (95% CI) | log loss model − Pinnacle (95% CI) | logistic model coefficient (95% CI) |
|---|---|---|---|---|---|---|---|---|
| spreads | pace_eff | 3,568 | 50.2% (48.6%–51.9%) | 50.0% | 0.6% (-2.6% to 3.9%) | -1.8% (-5.0% to 1.4%) | – | – |
| spreads | elo_total | 3,568 | 49.6% (47.9%–51.2%) | 50.0% | -0.8% (-4.0% to 2.6%) | -3.1% (-6.3% to 0.1%) | – | – |
| moneyline | pace_eff | 3,635 | 36.8% (35.2%–38.3%) | 37.4% | -2.0% (-7.0%, 3.1%) | -4.7% (-9.5%, 0.3%) | +0.0343 (+0.0263 to +0.0421) | -0.020 (-0.201, +0.162) |
| moneyline | elo_total | 3,635 | 39.1% (37.6%–40.7%) | 39.7% | -1.6% (-6.5%, 3.4%) | -4.2% (-9.0%, 0.6%) | +0.0283 (+0.0211 to +0.0353) | -0.093 (-0.279, +0.093) |

Spreads at thresholds 1–6 points against Pinnacle: pace_eff 49.1–51.2%,
elo_total 46.7–50.8%. No lower bound is above 52.38%.

## Blend regressions

Expectation: the market's coefficient near 1; the model's near 0, with an
interval including 0.

**Spreads**, OLS: `actual margin = a + b·true-close implied margin + c·model margin`

| projector | season | n | b: close (95% CI) | c: model (95% CI) |
|---|---|---|---|---|
| pace_eff | 2022-23 | 1,220 | 0.872 (0.710, 1.034) | +0.021 (-0.194, +0.237) |
| pace_eff | 2023-24 | 1,236 | 1.113 (0.922, 1.303) | -0.088 (-0.309, +0.133) |
| pace_eff | 2024-25 | 1,231 | 0.945 (0.774, 1.116) | +0.145 (-0.048, +0.337) |
| pace_eff | **pooled** | 3,687 | 0.973 (0.873, 1.072) | **+0.052 (-0.066, +0.170)** |
| elo_total | 2022-23 | 1,220 | 0.935 (0.754, 1.116) | -0.079 (-0.298, +0.141) |
| elo_total | 2023-24 | 1,236 | 1.146 (0.934, 1.358) | -0.116 (-0.338, +0.105) |
| elo_total | 2024-25 | 1,231 | 0.998 (0.801, 1.196) | +0.064 (-0.145, +0.273) |
| elo_total | **pooled** | 3,687 | 1.015 (0.902, 1.128) | **-0.009 (-0.132, +0.114)** |

**Moneyline**, logistic regression of home win on an intercept, `logit(market)` and `logit(model)`

| projector | season | n | market logit (95% CI) | model logit (95% CI) |
|---|---|---|---|---|
| pace_eff | 2022-23 | 1,220 | 0.942 (0.714, 1.171) | -0.103 (-0.452, +0.246) |
| pace_eff | 2023-24 | 1,236 | 1.285 (1.024, 1.545) | -0.260 (-0.586, +0.066) |
| pace_eff | 2024-25 | 1,231 | 0.946 (0.720, 1.171) | +0.166 (-0.121, +0.453) |
| pace_eff | **pooled** | 3,687 | 1.047 (0.911, 1.183) | **-0.030 (-0.209, +0.149)** |
| elo_total | 2022-23 | 1,220 | 0.986 (0.729, 1.244) | -0.153 (-0.484, +0.178) |
| elo_total | 2023-24 | 1,236 | 1.328 (1.035, 1.620) | -0.285 (-0.621, +0.051) |
| elo_total | 2024-25 | 1,231 | 1.021 (0.759, 1.283) | +0.037 (-0.266, +0.339) |
| elo_total | **pooled** | 3,687 | 1.092 (0.937, 1.248) | **-0.090 (-0.274, +0.094)** |

Margin accuracy against the actual margin, pooled at the true close
(n = 3,687): close 10.29 MAE / 13.24 RMSE; pace_eff 10.91 / 13.88; elo_total
10.79 / 13.78. With default (untuned) settings: 11.29 and 11.00. Per season, the
close's MAE is 9.78, 10.53 and 10.56. The brief expected about 9.0, and the
pre-registration said 9.5 to 10.

## Market sanity and stop rules (computed before grading)

All five stop rules passed, so grading went ahead. The full tables are in each
report under "Market sanity".

| stop rule | value | passes |
|---|---|---|
| pooled mean devigged p_home_cover at the true close in 0.48–0.52 | 0.5000 | yes |
| pooled mean devigged p_home within 3 points of the home win rate | 0.5588 vs 0.5541 | yes |
| spread favourite = moneyline favourite in ≥ 98% of games | 0.9979 (n = 4,729) | yes |
| no earlier bucket beats the true close on spread MAE (pooled paired 95% CI below 0) | none | yes |
| no earlier bucket beats the true close on moneyline log loss (same) | none | yes |

Under the main pre-registration's literal rule ("must not be lower"), the
point estimates show a few earlier buckets slightly ahead of the true close. On
spread MAE, near close pooled is −0.002 (−0.018 to +0.015). By season, the
negative differences are 2021-22 early evening and near close, 2022-23 afternoon
to near close, and 2023-24 near close, all between −0.025 and −0.000. On
moneyline log loss, near close is −0.0003 in 2021-22 and −0.0001 in 2022-23.
Every one of these intervals includes zero. As the pre-registration declared,
they count as noise. Opening and noon are worse than the close in every
pooled comparison (spread MAE +0.110 and +0.076; log loss +0.0082 and +0.0055).

Source counts: 37,397 spreads files and 37,407 h2h files; 5,420 events, all
matched to a game (this includes 2025-26 files, which are not scored). 51 files
were polled at or after tip and dropped. Book rows without a clean quote: 0
spreads, 1 h2h. Consensus rows captured at or after the same game's true close
(dropped): 17 in each market, as in totals.

## Bug-first checks

No number met the evidence bar. Even so, the small positive spread CLVs and the
underdog-heavy moneyline bets were checked before being reported:

1. **Home/away mapping.** Outcomes are matched to the event's teams by name,
   never by position; a synthetic test lists the away team first
   (`tests/test_sides.py`). Cross-market favourite agreement is 99.8%. Mean
   devigged p_home is 0.559 against an observed home win rate of 0.554.
2. **Hand check.** Game 1038147 (Houston at Philadelphia, 15 January 2024, true
   close): recomputing from the raw spreads.json gives 41 books, home spread
   −8.5 and p_home_cover 0.49067. From h2h.json: 54 books, p_home 0.74340. Both
   are identical to the consensus rows.
3. **Sign of the model margin.** Its correlation with the true-close implied
   margin is +0.805 (pace_eff) and +0.853 (elo_total).
4. **Push, ROI, devig and CLV-sign arithmetic.** Synthetic tests cover a home
   cover, a push, an away cover and a loss with exact fair and real returns. The
   CLV tests cover points and cents with SD 12, the h2h devig (a fair price devigs
   to itself), moneyline returns, CLV in cents and the strict thresholds.
5. **Drift and placebo.** The spread CLV is not a drift artefact. Home bets are
   47–50% of the total, and the mean line drift towards home is −0.05 to +0.00
   points, which explains at most 0.004 points of CLV. A random-side placebo
   (seed 20261020) gives spread CLV of −0.013 (opening), −0.037 (noon), +0.006
   (afternoon) and −0.004 (near close), every interval including zero. On the
   moneyline the placebo gives −0.20¢ from the opening (−0.35 to −0.05), +0.08¢,
   −0.06¢ and +0.01¢. One of the eight placebo cells excludes zero, slightly
   more often than the expected one in twenty.
6. **Anchor timestamps.** Every earlier bucket's consensus was captured before
   the same game's true close. True-close files are 5 to 30 minutes before tip;
   near close 0.8 to 1.5 hours; noon 2.7 to 10.2 hours. A few early-evening and
   late-evening files were polled far off their band (up to 21 hours before tip),
   as in totals; they are kept because they precede the close.
7. **Leakage.** The truncation test passes for `predict_margin` of both
   projectors: each projection is bit-identical when every row dated on or after
   the game is deleted. A second test swaps the home and away scores of every
   test-season game and checks that the calibration constants (`h`, `s`) and K
   do not change, so they were fitted on earlier seasons only.
8. **Why the moneyline bets are mostly underdogs.** The model's probabilities are
   compressed: their SD is 0.153 (pace_eff) and 0.168 (elo_total), against 0.201
   for the market. Where the market prices the home side at 0.85, the models say
   0.75 to 0.78, and home wins 85.5%. So "bet the side the model rates higher" is
   mostly "bet the underdog". The market is well calibrated in every probability
   bin. This is why the model's log loss is worse; the win rate below 50% does
   not indicate a bug.

## Interpretation

Spreads and moneylines give the same answer as totals: the existing
point-in-time ratings carry nothing the closing market lacks. Against the
spread, both projectors cover within noise of 50% in every season (pooled
50.3% and 49.4%). Neither has a cell with a cover lower bound above 52.38%.
Each loses roughly the vig at real prices, and less at Pinnacle's. Given the
closing spread, the model's weight is −0.01 to +0.05 with intervals around zero.
The model margins are 0.5 to 0.6 points of MAE worse than the close. On the
moneyline, the model's probabilities are measurably worse than the market's in
every season (log loss +0.028 to +0.035, Brier +0.013 to +0.016). The logistic
blend gives them no weight. Betting where they disagree with the market (mostly
on underdogs, because the model is less confident) loses 4.8–6.7% at real
prices at every threshold. The one consistent signal is the one totals showed: a small
movement of the spread towards the ratings, mostly between the opening and the
afternoon (+0.06 to +0.10 points from the opening, +0.04 from noon). It is a
tenth of a cent against several cents of vig, it does not turn into covers or
profit, and it passed the drift and placebo checks without becoming an edge.
The pre-registered evidence bar was not met for either market or either
projector, so the clean baseline is "no edge" for all three markets. Any claim
otherwise would need a new pre-registration tested on an unseen season (2025-26
onwards).
