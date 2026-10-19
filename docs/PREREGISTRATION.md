# Pre-registration: Tier A totals engine

Written 20 October 2026, before any projection code or backtest exists in this
repository. The git commit that adds this file is the timestamp. Any later change
to this file is a new commit with the reason in the message, and RESULTS.md
reports against the version committed before the first backtest ran.

## What is being tested

A box-score pace × efficiency formula (Tier A, no player data, no machine
learning) projects each NBA game's total points from data dated strictly before
the game. Each projection is compared with the betting market's consensus total.
The question is whether the projection contains information the closing market
does not.

## What we already know (so this is not a pristine hold-out)

The same maintainer spent 2025-26 testing related ideas on these same four
seasons in an older private repository. That work found closing totals well
calibrated (mean error +0.37 points, SD 18.0 points across 2021-22 to 2024-25),
found the market prices pace-driven totals variance in every cell of a
pace-variance kill-test, and found no out-of-sample edge in any totals strategy.
So these seasons are not unseen, and a positive result here would still need
confirming on a season nobody has looked at: 2025-26 onward, collected live with
`nbatotals.ingest`.

## Hypotheses

- **H0 (expected):** the projection adds no information beyond the devigged
  closing consensus. Betting the side it favours wins at about the rate the
  devigged price implies, and the line does not move towards it.
- **H1:** the projection beats the close often enough to profit at real prices.

## Expected results (written down before testing)

| Metric | Expectation |
|---|---|
| Cover rate vs devigged consensus close, all games (edge threshold 0) | 48% to 52% in each test season and pooled |
| Cover rate at edge thresholds 1, 2, 3, 4, 6 points | 47% to 53%, wider at higher thresholds because n is smaller; no monotone rise with threshold |
| CLV of bets struck at the open and pretip anchors | Mean within ±0.2 points of zero |
| ROI at real (vigged) median prices | About −4.5% (the vig), interval including that |
| ROI at devigged (fair) prices | About 0%, interval including 0 |
| MAE of projection vs actual total | Higher than the closing line's MAE (about 14.4 points; SD 18) by 0.3 to 1.5 points |
| Blend regression `actual = a + b·close + c·model` | `b` near 1, `c` between −0.10 and +0.15 with a 95% interval that includes 0 |

## What would count as evidence of an edge

All of these, on the primary comparison (devigged consensus close, edge threshold 0):

1. The lower bound of the 95% Wilson interval on cover rate is above **52.38%**
   (the −110 breakeven) on at least **1,000 graded bets** pooled across **at least
   two held-out seasons**, and the cover rate is above 50% in each of those seasons.
2. **Positive CLV:** for the same bets struck at the pretip anchor, the 95%
   bootstrap interval on mean CLV in points is above zero.
3. ROI at the real median price has a 95% bootstrap interval above zero.

Results at the other thresholds and anchors are descriptive. If a non-primary
cell clears the bar while the primary does not, it is reported as an exploratory
finding that needs a fresh season, not as an edge: there are 6 thresholds × 3
anchors × 3 seasons of cells, and some will look good by chance.

For scale: with a total SD of 18 points, the earlier variance study put the
sample needed to show a 1-point-of-win-rate edge (53.4% vs 52.4%) at about 9,000
bets at 95% confidence; three seasons give about 3,700. **This test can detect
a large edge or rule one out; it cannot confirm a small one.**

## Data

- Games, box scores and odds from the maintainer's private legacy DB, read
  through `nbatotals/evaluate/adapters/legacy_nba_db.py` (counts in
  [schema.md](schema.md)). The legacy odds rows have no capture timestamps;
  anchors are labels (open ≈ 18 h, pretip/noon_local ≈ 12 h, close ≈ 0.5 h
  before tip).
- Seasons 2021-22 to 2024-25. Scored games: final games with `postseason = 0`
  as the source flags it (this includes the play-in from 2022-23 on, and the
  NBA Cup final from 2023-24 on; about 6 to 7 games a season).
- Every scored game is projected, including opening week (where the projection
  leans on priors). A secondary cut reports games where both teams have played at
  least 10 games that season.

## Market consensus (fixed in advance)

For each game and anchor, using totals quotes with both prices:

1. Drop any book whose line is more than **10 points** from the median line of all
   books for that game and anchor (removes half and quarter totals filed as full
   game, and `0.0` lines).
2. **Consensus line** = median of the remaining books' lines. It may land on a
   quarter point; it is a reference line, graded as is.
3. **Devig** each book multiplicatively: `p_over = (1/o) / (1/o + 1/u)`.
   Consensus `p_over` = mean of the books' `p_over`. `p_under = 1 − p_over`.
4. **Real price** for a side = median of the books' decimal prices for that side.
5. A game needs at least **3 books** after step 1 to be scored at that anchor.

## Bet and grading rules (fixed in advance)

- Edge = projected total − consensus line. Bet over if edge > 0, under if edge < 0,
  no bet if edge = 0 exactly.
- Thresholds: 0 (every game), 1, 2, 3, 4 and 6 points of |edge|. All are reported;
  none is selected.
- **Push:** the actual total equals the consensus line. Pushes are excluded from
  cover rate and ROI and counted separately.
- Cover rate is reported beside two baselines: 50%, and the mean devigged
  probability of the sides bet (the rate a no-information bettor would expect).
  Breakeven at −110 is 52.38%, but every bet's ROI is computed at its own prices:
  - **fair ROI:** win pays `1/p_side − 1`, where `p_side` is the devigged
    consensus probability;
  - **real ROI:** win pays the real (median vigged) price minus 1.
  Flat 1-unit stakes. 95% intervals by bootstrap over games, 10,000 resamples,
  fixed seed.
- **CLV** for a bet struck at anchor A (open or pretip): in points, the close
  line minus the A line for overs, and the A line minus the close line for unders
  (positive means the market moved towards the bet); in cents, the devigged close
  probability of the bet side at the A line minus the devigged A probability.
  Bets struck at the close have CLV 0 by construction and are reported as n/a.
  The close-in-cents measure needs a close probability at the open's line; we use
  the close consensus probability, adjusted for the line difference with a
  normal approximation (SD 18 points), and say so beside the number.

## Walk-forward protocol (fixed in advance)

- Test seasons: **2022-23, 2023-24, 2024-25**. 2021-22 is training only.
- For test season S, every tunable parameter (L3/L10/season blend weights, the
  early-season shrinkage count, the pace-combination weight, home-court and
  back-to-back adjustments) is chosen using **only seasons before S**, by
  minimising the RMSE of projected vs actual total on those seasons' scored
  games. The objective is never the betting result, and never involves odds.
- The search (grid or simple coordinate descent) is logged: every candidate and
  its training RMSE are written next to the results.
- The chosen parameters are **frozen** and the whole of season S is scored with
  them. Features for S still use S's own games played before each game date;
  that is data, not fitting.
- A second run uses the untouched defaults from `config/params.yaml` for every
  season, as a check that the tuning is not what produces any result.

## Before believing any positive number

Treat it as a bug first. Check, and write down in RESULTS.md that we checked:
the game join (dates, home/away), the anchor timestamps (is "open" earlier than
"close"?), the devig arithmetic, push handling, and the point-in-time feature
cut-off (the leakage self-test in `tests/`).
