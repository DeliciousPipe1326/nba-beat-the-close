# Experiment 4 results: player props against Pinnacle

Rules: [PREREGISTRATION.md](PREREGISTRATION.md) (committed in `99ff45c` before
any quote was joined to a box score). Every table here comes from the generated
report, [backtest_props_report.md](backtest_props_report.md), which
`python -m nbatotals backtest-props --legacy` regenerates byte for byte. Test
set: the 2024-25 regular season (1,228 games with prop payloads). Points,
rebounds and assists. Flat 1-unit stakes. ROI and CLV intervals are 95%
bootstrap intervals over games (10,000 resamples); hit-rate intervals are 95%
Wilson.

**This measures price inefficiency, not a strategy.** The books where the
gaps show up (Ladbrokes, TAB, Unibet, BetRivers, BetMGM) limit or close
accounts that win. A positive number here says a retail price was out of line
with Pinnacle at the moment of capture. It does not say that anyone could have
kept betting it.

## Answer

- **Retail prop prices sit much further from Pinnacle than game-total prices
  do.** At the same line, 3.0% of retail sides beat Pinnacle's devigged fair
  probability by 2% or more at T−3h, and 4.3% at the close (about T−9 min). For
  game totals, at the same books and rule, the figure is 0.0% to 0.1%.
- **Betting those gaps does not clear the pre-registered bar in any of the 159
  cells.** Eight cells have a realised-ROI lower bound above zero, but every
  one has **negative** CLV: Pinnacle's own close moves away from the bet side.
  Across T−3h cells with n ≥ 100, CLV runs from −0.4 to −3.2 probability
  points, and every interval is below zero.
- **Exploratory, not an edge:** Australian books at T−3h. All Australian
  books pooled, edge ≥ 2%: n 5,890, ROI **+3.8%** (+0.8% to +6.8%). At ≥ 3%:
  n 3,657, ROI **+6.4%** (+2.8% to +10.1%). Most of it is unders. It survives
  the bug checks below, but its CLV is negative, half of its profit comes from
  March 2025, and it is one of 159 overlapping cells. It needs a season nobody
  has looked at.
- **Pinnacle is not a sharp anchor in props.** Its prop hold is **7.0%** (2.9%
  on game totals), the same as the retail books' 5.3% to 7.8%. Its devigged
  over probability runs 0.6 to 0.8 points above the over's actual hit rate
  (T−3h: 49.3% priced, 48.5% hit, 95% Wilson 47.9%–49.2%; close: 49.2% vs
  48.6%). Multiplicative devig spreads the
  margin evenly between the sides, so it leaves this bias in the fair value.
  That flatters unders and penalises overs throughout.

## Expected vs found

| Pre-registered expectation | Found |
|---|---|
| Paper edges at retail more often than in game lines | **Yes.** 3.0% / 4.3% of same-line sides at ≥ 2% (T−3h / close) vs 0.0% / 0.1% for totals |
| Concentrated in overs | **No.** Overs and unders are about equal pooled (T−3h 3.0% vs 3.1%; close 3.9% vs 4.6%). It depends on the book: FanDuel, Novig and Sportsbet lean to overs; TAB (13.3% of its unders at T−3h) and Ladbrokes lean to unders |
| Realised ROI below paper edge | **Mostly.** In 22 of 24 region-pooled cells (n ≥ 100); the exceptions are AU T−3h at 3% and 8% |
| Unders closer to break-even than overs | **Yes.** All same-line sides: overs −8.2% (T−3h), −7.9% (close); unders −4.4%, −4.8%. Above the thresholds, unders beat overs in 17 of 24 region × window × threshold cells (11 of the 12 at T−3h; the exception is AU at 8%) |
| CLV of T−3h bets within ±1 point of 0 | **No.** Negative: −0.4 to −3.2 points across T−3h cells with n ≥ 100, every interval below zero |
| Evidence bar not met | **Not met.** 0 of 159 cells |

## How far retail books sit from Pinnacle

Same-line comparisons only. Lines are never converted. Of 2.20 million retail
sides in the test set: 46,696 had no Pinnacle file for that event, market and
window; 645,841 were for a player Pinnacle did not price; 522,854 were at a
line other than Pinnacle's; **985,486 same-line pairs remain** (44.8%).

Top of the table (each book's T−3h row; the close rows are in the full report):

| book | region | same line as Pinnacle | hold | book p_over − Pinnacle (mean) | mean abs. gap | over sides ≥ 2% | under sides ≥ 2% |
|---|---|---|---|---|---|---|---|
| BetMGM | us | 97.9% | 7.1% | +0.23 pt | 1.40 pt | 1.7% | 2.4% |
| Bovada | us | 95.2% | 6.7% | +0.03 pt | 0.67 pt | 1.0% | 1.1% |
| William Hill | us | 92.2% | 7.8% | +0.25 pt | 1.40 pt | 0.5% | 0.8% |
| BetRivers | us | 91.2% | 7.2% | +0.10 pt | 2.06 pt | 4.2% | 4.6% |
| Unibet | au | 91.2% | 7.2% | +0.10 pt | 2.06 pt | 4.2% | 4.6% |
| Novig | us_ex | 89.7% | 5.5% | −0.30 pt | 1.50 pt | 6.5% | 3.4% |
| BetOnline | us | 84.2% | 6.4% | +0.11 pt | 1.16 pt | 0.7% | 1.2% |
| Ladbrokes | au | 75.6% | 7.0% | +0.15 pt | 2.11 pt | 4.5% | 4.9% |
| PointsBet | au | 75.5% | 6.7% | +0.16 pt | 1.67 pt | 1.8% | 2.7% |
| DraftKings | us | 74.6% | 6.6% | +0.12 pt | 1.72 pt | 2.4% | 2.5% |
| FanDuel | us | 72.9% | 5.3% | −0.38 pt | 1.73 pt | 7.2% | 3.2% |
| Sportsbet | au | 72.9% | 6.6% | −0.36 pt | 1.74 pt | 3.7% | 1.7% |
| ProphetX | us_ex | 72.7% | 6.3% | +0.04 pt | 1.61 pt | 8.4% | 7.4% |
| TAB | au | 62.2% | 6.9% | +1.93 pt | 2.54 pt | 1.0% | 13.3% |

BetRivers and Unibet price identically (both are Kambi). TAB prices overs
about 2 points more likely than Pinnacle does, so its unders look generous.
When a book's line differs from Pinnacle's, it differs by about one point.

## Per-book results (edge ≥ 2%, all three markets, sorted by n)

| region | book | window | n | mean paper edge | realised ROI (95% CI) | hit rate (95% Wilson) | mean p_fair | CLV, prob. points (95% CI) |
|---|---|---|---|---|---|---|---|---|
| us | all books | close | 9,361 | 4.4% | −0.2% (−3.0 to +2.6) | 49.9% (48.9–50.9) | 52.2% | n/a |
| au | all books | close | 8,787 | 4.6% | +1.1% (−1.6 to +3.8) | 51.7% (50.7–52.7) | 53.5% | n/a |
| us | all books | T−3h | 6,093 | 3.9% | +0.9% (−2.3 to +4.2) | 50.8% (49.5–52.0) | 52.2% | −1.57 (−1.70 to −1.44) |
| au | all books | T−3h | 5,890 | 4.1% | **+3.8% (+0.8 to +6.8)** | 53.3% (52.0–54.6) | 53.5% | −1.40 (−1.51 to −1.28) |
| us_ex | all books | close | 2,854 | 4.8% | −3.3% (−7.6 to +1.0) | 45.7% (43.9–47.6) | 49.3% | n/a |
| au | ladbrokes_au | close | 2,405 | 4.8% | **+4.3% (+0.3 to +8.2)** | 55.0% (53.0–56.9) | 55.2% | n/a |
| au | unibet | close | 2,234 | 5.1% | +1.3% (−3.1 to +5.8) | 48.8% (46.7–50.9) | 50.7% | n/a |
| us | betrivers | close | 2,222 | 5.0% | +1.2% (−3.2 to +5.7) | 48.8% (46.8–50.9) | 50.7% | n/a |
| us_ex | novig | close | 2,067 | 4.7% | −3.0% (−8.0 to +1.9) | 45.9% (43.7–48.0) | 49.4% | n/a |
| us | fanduel | close | 2,059 | 4.0% | −0.9% (−5.3 to +3.4) | 49.5% (47.4–51.7) | 52.0% | n/a |
| us_ex | all books | T−3h | 2,022 | 4.6% | −5.9% (−11.0 to −0.8) | 44.1% (42.0–46.3) | 49.1% | −1.54 (−1.71 to −1.37) |
| au | tab | close | 1,801 | 4.6% | +0.4% (−4.1 to +4.8) | 52.6% (50.3–54.9) | 54.8% | n/a |
| us | betmgm | close | 1,644 | 4.2% | +3.8% (−1.0 to +8.8) | 53.5% (51.1–55.9) | 53.7% | n/a |
| us | fanduel | T−3h | 1,630 | 3.6% | −1.9% (−6.8 to +3.0) | 49.3% (46.8–51.7) | 52.1% | −1.75 (−1.91 to −1.59) |
| us | betrivers | T−3h | 1,538 | 4.2% | +4.5% (−0.6 to +9.7) | 51.3% (48.8–53.8) | 51.0% | −1.24 (−1.40 to −1.08) |
| au | unibet | T−3h | 1,505 | 4.2% | +4.4% (−0.9 to +9.7) | 51.2% (48.6–53.7) | 51.0% | −1.22 (−1.38 to −1.05) |
| au | ladbrokes_au | T−3h | 1,498 | 4.1% | +4.2% (−0.6 to +8.9) | 55.0% (52.5–57.5) | 55.1% | −1.41 (−1.58 to −1.25) |
| us_ex | novig | T−3h | 1,354 | 4.5% | −9.3% (−15.0 to −3.6) | 42.5% (39.9–45.1) | 48.9% | −1.63 (−1.83 to −1.42) |
| us | draftkings | close | 1,352 | 4.0% | −2.3% (−7.5 to +2.9) | 49.7% (47.0–52.4) | 52.9% | n/a |
| au | tab | T−3h | 1,254 | 4.7% | +4.9% (−0.3 to +10.1) | 54.6% (51.9–57.4) | 54.4% | −0.86 (−1.06 to −0.68) |

The remaining books, all other thresholds, and the per-market tables (points,
rebounds, assists) are in the full report. The Wilson intervals on "all books"
rows treat bets as independent, but the same prop is often bet at several
books, so those intervals are too narrow. The ROI and CLV bootstraps resample
whole games and are not affected.

**CLV caveat.** CLV in probability exists only when Pinnacle's close is at
the same line (342,113 of 486,396 T−3h same-line sides). When Pinnacle's line
moved (94,777), the share that moved towards the bet is in the last column of
the full report: 55% (us) and 67% (au) at ≥ 2%, which is mildly favourable.
The pre-registered CLV measure is the same-line one, and it is negative. Its
likely cause is selection: picking sides where Pinnacle's T−3h price is most
generous relative to a retail book picks Pinnacle prices that revert by the
close.

### Every cell with an ROI lower bound above zero and n ≥ 500

| edge ≥ | region | book | window | n | ROI (95% CI) | CLV (95% CI) |
|---|---|---|---|---|---|---|
| 2% | au | all books | T−3h | 5,890 | +3.8% (+0.8 to +6.8) | −1.40 (−1.51 to −1.28) |
| 2% | au | ladbrokes_au | close | 2,405 | +4.3% (+0.3 to +8.2) | n/a |
| 3% | au | all books | T−3h | 3,657 | +6.4% (+2.8 to +10.1) | −1.46 (−1.59 to −1.33) |
| 3% | au | ladbrokes_au | close | 1,690 | +5.7% (+1.2 to +10.3) | n/a |
| 5% | us | betmgm | close | 1,104 | +6.6% (+0.9 to +12.3) | n/a |
| 5% | us | betrivers | T−3h | 1,011 | +8.1% (+1.7 to +14.5) | −1.31 (−1.51 to −1.12) |
| 5% | au | unibet | T−3h | 987 | +7.8% (+1.4 to +14.5) | −1.29 (−1.49 to −1.09) |
| 5% | au | tab | T−3h | 887 | +6.3% (+0.0 to +12.5) | −0.95 (−1.17 to −0.72) |

Close-window cells cannot meet the bar, because CLV is not defined for them.
Every T−3h cell fails on CLV. Two caveats. The cells overlap: a 5% bet is also
a 2% bet, and BetRivers and Unibet are the same Kambi prices. And with 159
cells, a handful of lower bounds above zero are expected by chance.

## Overs vs unders (edge ≥ 2%, region pooled)

| region | window | overs: n, ROI (95% CI) | unders: n, ROI (95% CI) |
|---|---|---|---|
| us | close | 4,402, +0.0% (−4.0 to +4.1) | 4,959, −0.3% (−4.3 to +3.8) |
| au | close | 3,424, −0.4% (−4.6 to +3.8) | 5,363, +2.1% (−1.3 to +5.5) |
| us | T−3h | 3,125, −1.3% (−6.1 to +3.4) | 2,968, +3.3% (−1.6 to +8.3) |
| au | T−3h | 2,428, +1.1% (−3.9 to +6.0) | 3,462, **+5.7% (+1.6 to +9.7)** |
| us_ex | T−3h | 1,240, −9.4% (−15.9 to −2.7) | 782, −0.4% (−8.3 to +7.5) |

Without any threshold (every same-line side), overs lose 8.2% / 7.9% (T−3h /
close) and unders 4.4% / 4.8%. The old private repo's finding that overs lose
much more than unders shows up here at retail prices too.

## Bug-first checks on the positive cells

Each check below was run on the AU T−3h ≥ 2% cell, and where noted on the whole
T−3h ≥ 2% set:

| check | result |
|---|---|
| Name mismatches | 98.4% of test-set event-player names matched (19,925 of 20,249), 0 ambiguous. The 26 names that matched only after normalisation were all checked by hand (Jr./Jr, II, III, IV, C.J./CJ, KyShawn/Kyshawn, da/Da). **Exact-name bets only: +4.5% (+1.3 to +7.6)** |
| Line mismatches | Re-joining every settled bet to Pinnacle's quote by line: 0 mismatches in 956,110. All lines are half-points, so there are no pushes |
| Devig sign | Pinnacle's favoured side wins 53.8% of 49,990 settled Pinnacle player-lines; the calibration table is monotone; over and under p_fair come out as 1 − each other (synthetic test) |
| Double counting across regions | BetOnline appears in both `us` and `eu`: 159,555 duplicate outcomes dropped, all with identical price and `last_update`. 0 duplicate (book, event, market, player, line, side, window) keys remain. **One bet per prop at the best Australian price: +4.0% (+1.2 to +6.9), n 4,575** |
| Capture before tip | Every file used was captured 4.35 min or more before `commence_time`; 54 in-play files dropped; 0 outcomes updated after tip |
| Concentration | Without TAB: +3.5% (+0.2 to +6.9). Without the 5 most profitable players: +2.5%. By month: −3.2%, +5.9%, +0.5%, +1.6%, +2.5%, **+14.7%** (Mar), −11.0% (Apr). First half of the season +2.1%, second half +5.4% |
| Settlement | 15 random settled bets checked against the box score: all correct. DNP: `is_dnp` and 0 minutes agree on all but 1 of 46,150 rows. 21,486 bets voided (2.2% of matched same-line sides) |

None of these checks found a bug. Combined with the negative CLV, the
concentration in one month and the number of cells tested, the result is an
exploratory pattern for a fresh season. It is not evidence of an edge.

## Data quality

- **Capture times** (measured, not taken from the marker or file names): T−3h
  median lead 184 min (124–239); close median **9.4 min** (4.4–19.4), not the
  T−5 min the `complete.json` marker implies. File-name stamps run about 4
  minutes after the payload timestamps.
- **Files:** 37,125 read; 9,609 had no bookmakers, including every `uk` file;
  54 captured at or after tip; 156 outside both windows (rescheduled games); 32
  superseded within a window.
- **Duplicate lines:** 19,559 player-lines dropped because one book showed two
  prices for the same player, line and side in one file: ProphetX 64,537
  outcomes (its exchange ladder), William Hill 1,752, BetOpenly 679, others
  under 120.
- **Player matching:** listed above. Unmatched names, never guessed, are mostly
  nicknames: Alex Sarr (78 events), Ron Holland (52), B.J. Boston
  Jr, K.J. Martin, Moe Wagner, Herb Jones, Cam Reddish, James Huff, Bones
  Hyland, plus single events where a regular's box-score row is missing.
- **Stale quotes: the pre-registered rule cannot detect staleness in this
  data.** The provider's `last_update` is never more than 14.4 minutes before
  the capture (median 0.2 min), so the 60-minute rule flagged nothing, and the
  stale-dropped sensitivity run is identical to the primary run. A proxy, added
  after pre-registration and descriptive only: of T−3h bets at ≥ 2% whose book
  quotes the same line at the close, 23% have an unchanged price. Unchanged
  prices returned −1.0%, changed prices +0.8%.
- **Games:** all 1,237 events matched a game (1,228 test, 3 play-in, 6 in
  2025-26).
- **2025-26:** only 6 events (28 Nov 2025) exist, so the season is descriptive
  only and has no settlement data. 1,889 same-line sides; 3.3% at ≥ 2% (T−3h),
  in line with 2024-25.

## What would test the exploratory pattern

A season of prop captures nobody has graded (2025-26 onwards, collected live),
with the cell fixed in advance (Australian books, T−3h, unders, edge ≥ 2%).
Fair value should get a better anchor than Pinnacle's multiplicatively
devigged price, for example a devig that allows for the over bias, or a
consensus of sharper prop books. The test should report CLV against the
market's close rather than against Pinnacle alone.
