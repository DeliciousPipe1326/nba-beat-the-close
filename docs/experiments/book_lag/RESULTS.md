# Results: Experiment 3, soft books against Pinnacle at the same poll

Run 20 October 2026 with `python -m nbatotals backtest-books --legacy`
(maintainer only: needs the private multi-region payloads and the legacy DB).
Every table below is copied from [report.md](report.md), which that command
regenerates in full; re-running it and checking `git diff` shows whether the
numbers reproduce (two runs from the same parsed payloads gave identical
reports). Rules: [PREREGISTRATION.md](PREREGISTRATION.md), committed in
2a129e7 before any harness code existed. Harness: 7317825.

Test seasons 2022-23, 2023-24 and 2024-25, regular season (the main study's
game set). Fair value is Pinnacle's two-way multiplicatively devigged
probability **from the same poll file**. Bets: one per (book, game, bucket,
market), the side with the larger edge `p_fair × price − 1`, flat stakes,
settled at the soft book's own line, pushes excluded. Intervals: 95% bootstrap
over games (10,000 resamples, fixed seed) for ROI and CLV; 95% Wilson for
cover. CLV = Pinnacle's devigged true-close probability of the bet side at the
bet's line minus `p_fair`, in cents.

## Summary

| Question | Pre-registered expectation | Result |
|---|---|---|
| Does any (book, market) clear the evidence bar? (2%, buckets pooled: ≥ 500 bets, ROI lower bound > 0, CLV lower bound > 0) | (bar, not an expectation) | **No.** 0 of 124 cells with exact lines, 0 of 178 with converted lines. No cell reaches 500 bets with a positive ROI lower bound; none has a CLV lower bound above zero together with positive ROI |
| Where does the paper edge sit? | a few books, recreational / offshore, plus exchanges | **Totals and spreads: almost entirely at onexbet** (342 of 440 totals bets, 411 of 557 spreads bets at 2%). **Moneylines: the exchanges** (matchbook, betfair_ex_uk/eu/au, and `betfair`, see below) **and suprabets, marathonbet, williamhill, superbook**. The big US books (draftkings, fanduel, betmgm) have 0–4 totals and spreads bets between them; in moneylines they have 570–870 bets each and lose (−3.3%, −1.7%, −14.5%) |
| How far off Pinnacle are soft books? | (descriptive) | Totals and spreads: 0.6–0.85¢ mean absolute disagreement in devigged probability; only **0.1–0.4%** of quotes on Pinnacle's line are 2% or more better than Pinnacle's fair price. Moneylines: 0.7–0.8¢, **4–7%** of quotes, mostly on long-priced underdogs |
| Paper edge rises towards tip | more 2% bets per game and higher mean edge late than at opening | **Moneylines yes** (2.0 bets per game at opening → 3.4 at near close; share of quotes 4.4% → 7.2%). **Totals and spreads no**: 0.02–0.04 bets per game at every bucket |
| Realised ROI below paper edge | yes | **Mixed and noisy.** Moneylines −0.9% against +5.7% paper (CI −12.8% to +11.7%); totals +2.9% against +3.1% (−8.3% to +14.2%); spreads **+10.5% against +3.3% (+0.4% to +20.9%)**, see the bug-first checks |
| CLV near zero or slightly positive | yes | **Negative almost everywhere**: −0.31¢ totals, −0.65¢ spreads, −0.40¢ moneylines at 2%, pooled. When a soft book is 2% better than Pinnacle's fair price, Pinnacle on average then moves *towards the soft book*, not away. Edge at the close is still positive (+2.0% to +4.2%) because that move is smaller than the paper edge |
| Soft books lag Pinnacle | positive next-period correlation for slow books | **Every book with enough data in moneylines, and most in totals and spreads**, follows Pinnacle's previous move by more than Pinnacle follows itself, but weakly: median correlation +0.08 (totals), +0.07 (spreads), +0.09 (moneylines) against Pinnacle's own +0.04, +0.02, +0.03 |

**Where the paper edge sits, plainly.** In totals and spreads it sits at one
offshore book, onexbet (1xBet). In moneylines it sits at the betting exchanges
(whose prices exclude commission, so their paper edge overstates what a bettor
keeps) and a handful of recreational and offshore sportsbooks (suprabets,
marathonbet, williamhill, superbook, williamhill_us). Sportsbooks of this kind
are widely reported to limit or close accounts that win; this data cannot show
whether a bet of any size was available at the snapshot price. **So this is a
measurement of inefficiency, not a strategy**, and even as a measurement it
does not clear the pre-registered bar.

## Evidence bar

| lines | (book, market) cells at 2% | clear the bar | clear the Bonferroni bound |
|---|---|---|---|
| exact (primary) | 124 | 0 | 0 |
| converted (±0.5 points) | 178 | 0 | 0 |

The closest cell is spreads at onexbet: 411 bets, ROI +11.0% (−1.2% to
+22.6%), CLV −0.16¢ (−0.55¢ to +0.22¢). It fails on all three conditions
(fewer than 500 bets, ROI lower bound below zero, CLV not positive).

## All soft books and buckets pooled

Exact lines at every threshold, and converted lines at 2%.

| lines | edge ≥ | market | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI | edge at close |
|---|---|---|---|---|---|---|---|---|---|---|---|
| exact | 1% | totals | 1,295 | +2.0% | +1.3% | -5.7% to +8.3% | 50.6% (47.9%–53.3%) | 50.9% | -0.52¢ | -0.74¢ to -0.31¢ | +1.0% |
| exact | 1% | spreads | 1,396 | +2.2% | +2.9% | -3.9% to +9.6% | 51.0% (48.4%–53.6%) | 50.7% | -0.57¢ | -0.79¢ to -0.36¢ | +1.0% |
| exact | 1% | h2h | 78,417 | +4.3% | -0.3% | -10.0% to +10.1% | 25.6% (25.3%–25.9%) | 26.2% | -0.36¢ | -0.45¢ to -0.26¢ | +3.0% |
| exact | 2% | totals | 440 | +3.1% | +2.9% | -8.3% to +14.2% | 50.9% (46.3%–55.6%) | 50.8% | -0.31¢ | -0.64¢ to +0.01¢ | +2.4% |
| exact | 2% | spreads | 557 | +3.3% | +10.5% | +0.4% to +20.9% | 54.0% (49.9%–58.1%) | 50.4% | -0.65¢ | -1.07¢ to -0.25¢ | +2.0% |
| exact | 2% | h2h | 52,674 | +5.7% | -0.9% | -12.8% to +11.7% | 22.4% (22.0%–22.7%) | 23.4% | -0.40¢ | -0.51¢ to -0.29¢ | +4.2% |
| exact | 3% | totals | 146 | +4.3% | +8.6% | -10.4% to +27.1% | 53.4% (45.3%–61.3%) | 50.9% | -0.27¢ | -0.83¢ to +0.27¢ | +3.7% |
| exact | 3% | spreads | 195 | +4.9% | +23.1% | +6.9% to +39.3% | 59.5% (52.5%–66.1%) | 50.4% | -1.01¢ | -1.74¢ to -0.32¢ | +2.8% |
| exact | 3% | h2h | 37,342 | +7.0% | -1.7% | -16.2% to +13.7% | 19.8% (19.4%–20.2%) | 21.3% | -0.42¢ | -0.55¢ to -0.30¢ | +5.3% |
| exact | 5% | totals | 13 | +10.2% | -21.2% |  | 38.5% (17.7%–64.5%) | 50.8% | -1.53¢ |  | +6.9% |
| exact | 5% | spreads | 25 | +13.0% | -20.0% |  | 36.0% (20.2%–55.5%) | 50.3% | -1.99¢ |  | +8.5% |
| exact | 5% | h2h | 21,143 | +9.4% | -3.7% | -23.4% to +18.7% | 16.3% (15.8%–16.8%) | 18.6% | -0.51¢ | -0.67¢ to -0.35¢ | +7.1% |
| converted | 2% | totals | 1,578 | +3.0% | +0.5% | -5.8% to +7.0% | 50.2% (47.7%–52.7%) | 51.4% | -0.47¢ | -0.71¢ to -0.24¢ | +2.1% |
| converted | 2% | spreads | 1,296 | +3.4% | +5.8% | -2.1% to +13.6% | 52.2% (49.4%–54.9%) | 50.8% | -0.75¢ | -1.05¢ to -0.47¢ | +1.9% |
| converted | 2% | h2h | 52,674 | +5.7% | -0.9% | -12.8% to +11.7% | 22.4% (22.0%–22.7%) | 23.4% | -0.40¢ | -0.51¢ to -0.29¢ | +4.2% |

At thresholds of 3% and 5%, moneyline cover falls further below the
no-information baseline (19.8% vs 21.3%; 16.3% vs 18.6%): the bigger the
apparent edge on a moneyline, the more often it is a long-priced underdog whose
Pinnacle fair probability was too high, not too low. Spreads at 2% and 3% have
ROI lower bounds above zero; they are almost all onexbet bets and are taken
apart in the bug-first checks below.

## Per book and anchor (2%, exact lines), sorted by bets

Top 10 rows per market; every row is in [report.md](report.md).

**totals**

| book | anchor | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| onexbet | near close | 83 | +3.0% | +19.8% | -2.2% to +41.6% | 59.0% (48.3%–69.0%) | 50.8% | -0.18¢ | -0.48¢ to +0.11¢ |
| onexbet | afternoon | 67 | +3.0% | +2.7% | -21.5% to +26.9% | 50.7% (39.1%–62.3%) | 50.8% | -0.06¢ | -0.77¢ to +0.60¢ |
| onexbet | late evening | 63 | +2.9% | +15.6% | -10.1% to +41.1% | 57.1% (44.9%–68.6%) | 50.9% | -0.07¢ | -0.69¢ to +0.53¢ |
| onexbet | early evening | 55 | +2.9% | +6.5% | -19.3% to +32.4% | 52.7% (39.8%–65.3%) | 50.9% | -0.09¢ | -0.74¢ to +0.56¢ |
| onexbet | noon | 54 | +2.8% | -10.5% | -36.7% to +15.6% | 44.4% (32.0%–57.6%) | 50.9% | +0.53¢ | -0.50¢ to +1.58¢ |
| onexbet | opening | 20 | +2.9% | -19.6% |  | 40.0% (21.9%–61.3%) | 51.0% | +0.23¢ |  |
| betopenly | opening | 17 | +2.7% | -52.8% |  | 23.5% (9.6%–47.3%) | 51.3% | -1.49¢ |  |
| lowvig | opening | 9 | +2.6% | -11.2% |  | 44.4% (18.9%–73.3%) | 51.2% | -5.48¢ |  |
| matchbook (exchange, gross) | near close | 9 | +3.0% | -54.9% |  | 22.2% (6.3%–54.7%) | 50.0% | -0.99¢ |  |
| lowvig | early evening | 5 | +2.5% | +59.6% |  | 80.0% (37.6%–96.4%) | 51.4% | -1.22¢ |  |

**spreads**

| book | anchor | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| onexbet | noon | 87 | +3.1% | -22.4% | -43.4% to -1.2% | 37.9% (28.5%–48.4%) | 50.4% | +0.14¢ | -0.68¢ to +1.02¢ |
| onexbet | early evening | 80 | +2.8% | +25.4% | +4.6% to +46.6% | 61.3% (50.3%–71.2%) | 50.2% | -0.72¢ | -1.51¢ to +0.01¢ |
| onexbet | near close | 80 | +3.1% | +12.7% | -10.2% to +35.6% | 55.0% (44.1%–65.4%) | 50.3% | +0.00¢ | -0.38¢ to +0.42¢ |
| onexbet | afternoon | 79 | +2.9% | +21.9% | -1.3% to +43.2% | 59.5% (48.5%–69.6%) | 50.2% | -0.03¢ | -0.73¢ to +0.69¢ |
| onexbet | late evening | 54 | +2.7% | +17.5% | -9.2% to +44.1% | 57.4% (44.2%–69.7%) | 50.4% | -0.20¢ | -1.13¢ to +0.70¢ |
| onexbet | opening | 31 | +2.8% | +24.0% | -9.2% to +57.2% | 61.3% (43.8%–76.3%) | 50.7% | -0.19¢ | -1.31¢ to +1.00¢ |
| matchbook (exchange, gross) | near close | 16 | +3.3% | +3.0% |  | 50.0% (28.0%–72.0%) | 50.1% | -2.23¢ |  |
| matchbook (exchange, gross) | noon | 14 | +6.9% | +3.9% |  | 50.0% (26.8%–73.2%) | 50.1% | -0.29¢ |  |
| betopenly | opening | 13 | +2.9% | -7.4% |  | 46.2% (23.2%–70.9%) | 51.4% | -0.95¢ |  |
| matchbook (exchange, gross) | early evening | 7 | +6.1% | +25.4% |  | 57.1% (25.0%–84.2%) | 50.2% | -3.49¢ |  |

**h2h**

| book | anchor | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| matchbook (exchange, gross) | near close | 1,425 | +6.5% | +0.9% | -9.8% to +11.6% | 24.4% (22.3%–26.7%) | 25.7% | -0.41¢ | -0.50¢ to -0.32¢ |
| matchbook (exchange, gross) | late evening | 1,378 | +6.4% | +2.8% | -7.9% to +13.8% | 23.9% (21.7%–26.2%) | 24.2% | -0.20¢ | -0.33¢ to -0.08¢ |
| matchbook (exchange, gross) | early evening | 1,298 | +6.2% | +2.9% | -8.6% to +14.4% | 23.3% (21.0%–25.6%) | 23.5% | -0.12¢ | -0.25¢ to +0.01¢ |
| matchbook (exchange, gross) | afternoon | 1,150 | +6.1% | +8.3% | -3.9% to +20.7% | 23.7% (21.3%–26.2%) | 22.5% | -0.08¢ | -0.23¢ to +0.07¢ |
| betfair_ex_uk (exchange, gross) | near close | 987 | +6.5% | -3.2% | -15.9% to +9.9% | 23.0% (20.5%–25.7%) | 24.5% | -0.41¢ | -0.52¢ to -0.31¢ |
| betfair_ex_eu (exchange, gross) | near close | 983 | +6.5% | -6.4% | -18.8% to +6.7% | 22.2% (19.7%–24.9%) | 24.6% | -0.41¢ | -0.52¢ to -0.31¢ |
| betfair_ex_au (exchange, gross) | near close | 969 | +6.5% | -4.6% | -17.2% to +8.5% | 22.5% (20.0%–25.2%) | 24.3% | -0.43¢ | -0.54¢ to -0.32¢ |
| betfair_ex_uk (exchange, gross) | late evening | 929 | +6.4% | +0.9% | -12.4% to +14.3% | 22.6% (20.0%–25.4%) | 22.8% | -0.08¢ | -0.22¢ to +0.06¢ |
| betfair_ex_eu (exchange, gross) | late evening | 917 | +6.5% | +2.0% | -11.3% to +15.9% | 22.6% (20.0%–25.4%) | 22.5% | -0.12¢ | -0.25¢ to +0.02¢ |
| betfair_ex_au (exchange, gross) | late evening | 904 | +6.5% | +1.3% | -12.3% to +15.6% | 22.5% (19.9%–25.3%) | 22.4% | -0.10¢ | -0.24¢ to +0.05¢ |

## Per book, six buckets pooled (2%, exact lines)

Top 8 rows per market by bets. "Bonferroni" is mean − 3.54 × bootstrap SE
(0.05 over 120 cells, two-sided).

**totals**

| book | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI | Bonferroni ROI lower bound | clears bar |
|---|---|---|---|---|---|---|---|---|---|---|
| onexbet | 342 | +2.9% | +6.4% | -6.9% to +19.6% | 52.6% (47.3%–57.9%) | 50.9% | +0.01¢ | -0.32¢ to +0.35¢ | -17.8% | no |
| lowvig | 24 | +2.5% | +32.9% |  | 66.7% (46.7%–82.0%) | 51.3% | -2.53¢ |  |  | no |
| matchbook (exchange, gross) | 22 | +6.1% | -44.5% |  | 27.3% (13.2%–48.2%) | 50.2% | -1.77¢ |  |  | no |
| betopenly | 17 | +2.7% | -52.8% |  | 23.5% (9.6%–47.3%) | 51.3% | -1.49¢ |  |  | no |
| topsport | 12 | +2.8% | +2.0% |  | 50.0% (25.4%–74.6%) | 50.1% | -1.05¢ |  |  | no |
| williamhill_us | 11 | +2.6% | +10.5% |  | 54.5% (28.0%–78.7%) | 50.6% | -0.47¢ |  |  | no |
| bovada | 3 | +3.1% | -33.3% |  | 33.3% (6.1%–79.2%) | 50.7% | -2.40¢ |  |  | no |
| betr_au | 2 | +2.0% | +2.5% |  | 50.0% (9.5%–90.5%) | 49.9% | -1.43¢ |  |  | no |

**spreads**

| book | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI | Bonferroni ROI lower bound | clears bar |
|---|---|---|---|---|---|---|---|---|---|---|
| onexbet | 411 | +2.9% | +11.0% | -1.2% to +22.6% | 54.3% (49.4%–59.0%) | 50.3% | -0.16¢ | -0.55¢ to +0.22¢ | -10.6% | no |
| matchbook (exchange, gross) | 49 | +7.2% | +7.8% | -23.0% to +37.9% | 51.0% (37.5%–64.4%) | 50.0% | -1.54¢ | -2.41¢ to -0.74¢ | -46.7% | no |
| lowvig | 17 | +2.4% | +17.2% |  | 58.8% (36.0%–78.4%) | 51.4% | -2.62¢ |  |  | no |
| betopenly | 13 | +2.9% | -7.4% |  | 46.2% (23.2%–70.9%) | 51.4% | -0.95¢ |  |  | no |
| boylesports | 7 | +2.8% | +71.4% |  | 85.7% (48.7%–97.4%) | 51.4% | +0.72¢ |  |  | no |
| topsport | 6 | +2.5% | +37.7% |  | 66.7% (30.0%–90.3%) | 50.0% | -0.26¢ |  |  | no |
| prophetx | 6 | +3.6% | -31.3% |  | 33.3% (9.7%–70.0%) | 50.1% | -2.59¢ |  |  | no |
| novig | 5 | +3.3% | -16.2% |  | 40.0% (11.8%–76.9%) | 49.7% | -6.01¢ |  |  | no |

**h2h**

| book | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI | Bonferroni ROI lower bound | clears bar |
|---|---|---|---|---|---|---|---|---|---|---|
| matchbook (exchange, gross) | 6,273 | +6.2% | +1.7% | -8.7% to +12.1% | 23.2% (22.1%–24.2%) | 23.6% | -0.21¢ | -0.30¢ to -0.12¢ | -17.1% | no |
| suprabets | 4,370 | +5.9% | -0.5% | -14.4% to +14.5% | 19.0% (17.9%–20.2%) | 20.0% | +0.02¢ | -0.09¢ to +0.13¢ | -26.4% | no |
| betfair_ex_uk (exchange, gross) | 4,299 | +6.3% | -3.7% | -15.5% to +9.1% | 21.4% (20.2%–22.7%) | 22.4% | -0.19¢ | -0.30¢ to -0.09¢ | -25.9% | no |
| betfair_ex_eu (exchange, gross) | 4,277 | +6.3% | -4.5% | -16.3% to +8.4% | 21.1% (19.9%–22.4%) | 22.3% | -0.21¢ | -0.30¢ to -0.10¢ | -26.8% | no |
| betfair_ex_au (exchange, gross) | 4,204 | +6.3% | -4.0% | -16.2% to +8.8% | 21.2% (20.0%–22.5%) | 22.2% | -0.20¢ | -0.30¢ to -0.10¢ | -26.5% | no |
| betfair | 1,926 | +5.9% | +12.8% | -5.4% to +32.0% | 26.9% (25.0%–28.9%) | 25.9% | -0.28¢ | -0.46¢ to -0.09¢ | -21.0% | no |
| marathonbet | 1,389 | +4.7% | -10.8% | -26.4% to +6.4% | 24.8% (22.6%–27.1%) | 28.9% | -0.55¢ | -0.74¢ to -0.35¢ | -40.3% | no |
| williamhill | 1,243 | +5.2% | +13.1% | -3.4% to +31.3% | 29.2% (26.7%–31.8%) | 27.5% | -0.01¢ | -0.20¢ to +0.19¢ | -18.1% | no |

## Overall picture by anchor (all soft books pooled, exact lines)

| market | anchor | share of quotes with edge ≥ 2% | 2% bets per game | bets | mean paper edge | realised ROI | ROI 95% CI | cover (95% Wilson) | baseline (mean p_fair) | CLV | CLV 95% CI |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h2h | opening | 3,538 | +5.2% | -9.0% | -27.9% to +11.1% | 22.3% (21.0%–23.7%) | 23.3% | -0.35¢ | -0.71¢ to +0.02¢ |  | +3.7% |
| h2h | noon | 8,319 | +5.5% | +0.8% | -15.3% to +18.3% | 21.9% (21.0%–22.8%) | 22.0% | -0.27¢ | -0.52¢ to -0.00¢ |  | +4.4% |
| h2h | afternoon | 9,252 | +5.7% | +4.6% | -10.3% to +20.3% | 22.7% (21.8%–23.5%) | 22.2% | -0.29¢ | -0.49¢ to -0.11¢ |  | +4.1% |
| h2h | early evening | 9,524 | +5.6% | -2.7% | -17.1% to +13.7% | 21.0% (20.2%–21.8%) | 22.5% | -0.32¢ | -0.47¢ to -0.17¢ |  | +4.2% |
| h2h | late evening | 9,793 | +5.7% | -0.3% | -13.8% to +14.7% | 22.5% (21.7%–23.4%) | 23.5% | -0.36¢ | -0.52¢ to -0.20¢ |  | +4.5% |
| h2h | near close | 12,248 | +5.9% | -2.9% | -15.3% to +10.2% | 23.5% (22.8%–24.3%) | 25.7% | -0.68¢ | -0.87¢ to -0.51¢ |  | +3.9% |
| spreads | opening | 74 | +4.0% | +12.1% | -14.7% to +37.7% | 55.4% (44.1%–66.2%) | 51.0% | -1.73¢ | -3.43¢ to -0.20¢ | -0.27 | +0.6% |
| spreads | noon | 107 | +3.5% | -19.5% | -38.7% to -0.2% | 39.3% (30.5%–48.7%) | 50.4% | +0.02¢ | -0.72¢ to +0.80¢ | +0.14 | +3.6% |
| spreads | afternoon | 96 | +3.0% | +15.2% | -5.4% to +35.6% | 56.2% (46.3%–65.7%) | 50.2% | -0.31¢ | -1.10¢ to +0.41¢ | -0.01 | +2.3% |
| spreads | early evening | 94 | +3.0% | +26.9% | +6.0% to +46.7% | 61.7% (51.6%–70.9%) | 50.3% | -0.93¢ | -1.66¢ to -0.24¢ | -0.20 | +1.1% |
| spreads | late evening | 72 | +3.1% | +27.5% | +4.7% to +49.9% | 62.5% (51.0%–72.8%) | 50.5% | -0.62¢ | -1.65¢ to +0.32¢ | -0.09 | +1.9% |
| spreads | near close | 114 | +3.1% | +9.5% | -10.1% to +28.9% | 53.5% (44.4%–62.4%) | 50.4% | -0.65¢ | -1.07¢ to -0.23¢ | -0.15 | +1.7% |
| totals | opening | 49 | +3.3% | -30.2% | -55.1% to -2.0% | 34.7% (22.9%–48.7%) | 51.1% | -1.49¢ | -2.94¢ to +0.01¢ | -0.21 | +0.4% |
| totals | noon | 64 | +2.9% | -11.8% | -37.0% to +13.3% | 43.8% (32.3%–55.9%) | 50.9% | -0.02¢ | -1.01¢ to +0.95¢ | +0.41 | +2.8% |
| totals | afternoon | 74 | +3.0% | -1.5% | -23.6% to +20.6% | 48.6% (37.6%–59.8%) | 50.8% | -0.06¢ | -0.77¢ to +0.66¢ | +0.29 | +2.9% |
| totals | early evening | 70 | +3.3% | +12.5% | -10.7% to +35.6% | 55.7% (44.1%–66.8%) | 50.8% | -0.01¢ | -0.62¢ to +0.62¢ | +0.25 | +3.3% |
| totals | late evening | 74 | +2.9% | +14.8% | -8.5% to +36.9% | 56.8% (45.4%–67.4%) | 50.9% | -0.27¢ | -0.98¢ to +0.36¢ | +0.05 | +2.4% |
| totals | near close | 109 | +3.0% | +15.2% | -3.6% to +33.9% | 56.9% (47.5%–65.8%) | 50.8% | -0.35¢ | -0.68¢ to -0.05¢ | +0.03 | +2.2% |

- **Moneylines**: the share of quotes 2% better than Pinnacle rises from 4.4%
  at opening to 7.2% at near close, and CLV is most negative at near close
  (−0.68¢): late discrepancies are mostly Pinnacle's price moving first and
  then partly back, or soft books holding a price Pinnacle later comes to.
- **Totals and spreads**: on Pinnacle's own line, soft books almost never sit
  2% off its fair price at any bucket (0.1–0.2% of quotes). Converting within
  half a point roughly triples the number of bets but leaves the picture the
  same (report.md, converted table).
- Pooled ROI intervals at single anchors that exclude zero: spreads early
  evening (+26.9%, +6.0% to +46.7%, 94 bets) and late evening (+27.5%, +4.7% to
  +49.9%, 72 bets) above; spreads noon (−19.5%, −38.7% to −0.2%, 107 bets) and
  totals opening (−30.2%, −55.1% to −2.0%, 49 bets) below. With 18 market × anchor cells per
  line mode, one or two such cells either way are expected by chance; every
  positive one has negative CLV.

## Lag measured directly

For each book: the correlation between Pinnacle's line move over the previous
bucket pair and the book's move over the next pair, pooled over five bucket
triples and test-season games. The reference is Pinnacle's own correlation
between consecutive moves (momentum). Books with at least 1,000 pairs.

| market | Pinnacle momentum (95% CI) | books | soft books' corr_next: min / median / max | books whose lower bound does not clear Pinnacle's momentum | highest |
|---|---|---|---|---|---|
| totals | +0.040 (+0.024 to +0.055) | 56 | −0.008 / +0.083 / +0.151 | 16, incl. betmgm, betus, circasports, matchbook, coral, ladbrokes_uk | tipico_de +0.151, mybookieag +0.149, foxbet +0.148, onexbet +0.139 |
| spreads | +0.019 (+0.004 to +0.035) | 56 | −0.004 / +0.071 / +0.168 | 7, incl. matchbook, coral, betsson, topsport | tipico_de +0.168, ballybet +0.148, sisportsbook +0.117, foxbet +0.113 |
| moneylines | +0.031 (+0.016 to +0.047) | 76 | +0.058 / +0.094 / +0.281 | none | williamhill +0.281, ballybet +0.173, mybookieag +0.147, winamax_de +0.143 |

The large US books sit in the middle: totals draftkings +0.071, fanduel
+0.072, betmgm +0.047; moneylines draftkings +0.093, betmgm +0.085, fanduel
+0.074. Same-period correlations with Pinnacle are +0.7 to +0.9 for most books,
so most of a soft book's movement happens in the same bucket as Pinnacle's and
the lagged part is small. A lag that shows in the correlations but produces no
pre-registered cell with positive realised ROI and positive CLV is, at these
polling intervals (one to fourteen hours apart), not a bettable lag.
onexbet, where the totals and spreads paper edge sits, is among the more
lagged books in totals (+0.139).

## Bug-first checks

The pre-registered checks ran on every (book, market) with positive realised
ROI at 2% (full table in report.md). Those with at least 100 bets:

| market | book | bets | ROI | quote age at poll, median / p90 | 10-minute staleness rule | converted lines | cover vs mean p_fair | 2021-22 (descriptive) |
|---|---|---|---|---|---|---|---|---|
| spreads | onexbet | 411 | +11.0% | 5.5 / 8.6 min | 383 bets, +14.9% (+2.5% to +26.9%) | 855 bets, +4.5% | 54.3% vs 50.3% | 143 bets, −17.9% (−36.4% to +1.2%) |
| totals | onexbet | 342 | +6.4% | 5.3 / 7.7 min | 316 bets, +3.7% (−10.3% to +17.1%) | 1,093 bets, +4.1% | 52.6% vs 50.9% | 104 bets, +6.4% |
| h2h | matchbook (exchange, gross) | 6,273 | +1.7% | 5.0 / 6.4 min | 5,901 bets, +1.2% (−9.0% to +11.8%) | (no line) | 23.2% vs 23.6% | 1,291 bets, +10.8% |
| h2h | betfair | 1,926 | +12.8% | 5.0 / 6.0 min | 1,835 bets, +11.3% (−6.7% to +30.1%) | (no line) | 26.9% vs 25.9% | 1,228 bets, +9.5% |
| h2h | williamhill | 1,243 | +13.1% | 5.6 / 9.4 min | 1,111 bets, +16.0% (−1.0% to +34.0%) | (no line) | 29.2% vs 27.5% | 358 bets, −0.1% |
| h2h | williamhill_us | 1,063 | +0.6% | 5.7 / 8.5 min | 940 bets, −1.3% (−20.8% to +19.3%) | (no line) | 21.7% vs 22.7% | |
| h2h | superbook | 1,022 | +14.2% | 5.2 / 7.4 min | 964 bets, +14.3% (−8.8% to +38.6%) | (no line) | 25.7% vs 24.4% | |

Another 22 moneyline books have positive realised ROI on 100 to 1,000 bets
(report.md); every one has a 95% interval including zero, and pooled over all
books the moneyline ROI is −0.9%. With exact lines, no (book, market) cell at
2% has an ROI lower bound above zero. With converted lines, one does: totals at
lowvig, 110 bets, +20.1% (+1.3% to +38.1%), with CLV −1.91¢ (−2.59¢ to
−1.24¢), i.e. Pinnacle moved firmly against those bets.

Outcomes of the five pre-registered checks:

1. **Stale quotes.** Quote ages at the poll are about 5 minutes (median) and
   under 10 minutes at the 90th percentile for every positive book. Tightening
   the staleness rule from 30 to 10 minutes drops 3–13% of bets; it changes
   the sign of ROI only for unibet and williamhill_us moneylines, both near
   zero. Only 861 quote rows of 3.86 million were dropped as stale
   under the 30-minute rule. **Not the cause.**
2. **Line mismatch.** Every exact-line bet has the soft book's line equal to
   Pinnacle's (0 mismatches in every book). Converting within half a point
   shrinks the spreads onexbet ROI from +11.0% to +4.5% and totals from +6.4%
   to +4.1%, both with intervals including zero. **Not the cause; the
   exact-line ROI is not robust to adding the near-line bets.**
3. **Sign of the devig.** Over all exact-line Pinnacle quotes (one per game and
   bucket), side a won 55.7% of moneylines against a mean `p_fair` of 55.8%,
   50.2% of spreads against 50.0%, 51.2% of totals against 50.1%; split at
   one half, the favoured side wins at its predicted rate (moneylines 68.7% vs
   68.8%, underdogs 34.2% vs 34.3%). Unit tests fix the side for over/under,
   home/away and the spread handicap. **The sign is right.**
4. **Duplicate events.** No event matched two games; 2 games were matched by
   two events and were dropped; no (book, game, bucket, market) appears twice
   among bets. **Clean.**
5. **In-play contamination.** No bet's poll or `last_update` is at or after
   tip (among the positive books' bets, the latest `last_update` and the
   latest poll are both 14 minutes before tip). 3,912 quote rows from files
   polled at or after tip were dropped before pairing. Pinnacle's quote comes
   from the same poll file in every bet. **Clean.**

**What the spreads number is.** The onexbet spreads bets cover 54.3% against a
Pinnacle fair probability of 50.3%, while Pinnacle's price then moves against
them (CLV −0.16¢, line move +0.05 points). If onexbet's line carried real
information that Pinnacle lacked, Pinnacle would move towards the bet. A cover
rate 4 points above the fair probability with no closing-line movement is what
noise looks like on 411 bets (the Wilson interval, 49.4%–59.0%, includes the
baseline). It also falls by season (2022-23 +14.2%, 2023-24 +8.8%, 2024-25
−1.0% for all books pooled), it reverses in 2021-22 (−17.9% on 143 bets),
and it halves when the half-point-off bets are added. It is reported as noise
consistent with chance across about 120 primary cells, not as a finding.

## Deviations from the pre-registration (all in the code and the report)

1. **Event join, fixed after the first run.** The first run dropped every
   event whose metadata differed between files (it counted 896 conflicting
   rows; 879 events have a `commence_time` that is revised between polls, by up
   to 235 minutes). The join now runs per file
   row, exactly as the main study's adapter does, and 5,088 of 5,092 events
   match. The first run's tables were seen; the fix restores coverage and
   changes no rule.
2. **Conservative tip time.** For the in-play checks, a row's tip is the
   earlier of its own file's `commence_time` and the one in the event's
   last-polled file (52,131 rows moved earlier). This can only drop more
   quotes.
3. **CLV needs a close polled after the bet.** In 2024-25, 1,231 compared
   quotes at early- and late-evening buckets were polled at or after the same
   game's true-close poll (the off-schedule snapshots the main study also
   found). They keep their ROI but get no CLV.
4. **Exchange list.** The pre-registration lists `betfair_ex_uk/eu/au` and
   `matchbook` as exchanges. The key `betfair` (title "Betfair") appears in the
   same payloads as `betfair_sb_uk` ("Betfair Sportsbook"), so it is very
   likely the exchange under an older key; it was not on the list, so the
   tables show it as a sportsbook. Its moneyline ROI (+12.8%, −5.4% to +32.0%)
   is gross of commission either way. Exchange commission is not deducted
   anywhere.
5. **Added after the first run, descriptive only:** the price-band table
   (report.md, "By price taken") and the all-books pooled table above.

## Limitations

- Pinnacle is the fair value by assumption. Its moneyline devig is
  multiplicative, which is known to put too much probability on long shots;
  most moneyline "edges" are on long-priced underdogs (decimal 3 or more: 45,528
  of 52,674 bets).
- The Odds API polls a book's feed; the snapshot is not proof a bet could be
  placed at that price, for any stake, before the next update.
- Polls are hours apart (18 h, 10 h, 5 h, 3 h, 2 h, 1 h, 15 min before tip).
  Lags shorter than the gap between polls cannot be seen.
- These seasons were already used by the main study. A clean test of any
  lagged-book idea needs 2025-26 or later, collected live, with its own
  pre-registration.
