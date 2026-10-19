# Pre-registration: Experiment 5, spreads and moneyline through the same harness

Written 20 October 2026, before any spreads or moneyline projection, consensus,
sanity number or grading exists in this repository. The commit that adds this
file is the timestamp. Before writing it I looked only at the payload layout
(file names, JSON keys, the list of books in one file); no line, price or
outcome was summarised. Any later change is a new commit with the reason in its
message, and RESULTS.md reports against the version committed here.

The main totals pre-registration ([../../PREREGISTRATION.md](../../PREREGISTRATION.md))
and its graded results are not touched by this experiment. Its rules (Wilson
intervals, bootstrap over games with 10,000 resamples and seed 20261020, pushes
excluded, every bet at its own price, CLV by anchor, blend regression,
Pinnacle-only secondary) apply here unless this file says otherwise.

## What is being tested

The point-in-time team ratings already in the repository project each game's
**home margin** and **home win probability**. These are compared with the
devigged market consensus for spreads and for the moneyline (h2h) at the true
close, 15 minutes before tip. The question is the same as for totals: does the
projection contain information the closing market does not?

- **H0 (expected):** no. Betting the side the model favours wins at the rate the
  devigged price implies, and the market does not move towards it after noon.
- **H1:** the projection beats the close often enough to profit at real prices.

This is a baseline, not a search: the projectors were built for totals and are
reused as they are, with only the two calibration constants below fitted for
the new targets.

## Projections

Both projectors are run walk-forward exactly as in the totals test: for test
season S (2022-23, 2023-24, 2024-25), everything is fitted on seasons before S
only, from games and box scores, never odds.

**(a) `pace_eff`.** The pre-registered totals formula with its walk-forward
parameters (chosen by total RMSE, unchanged). Raw margin =
`home_pts_proj − away_pts_proj` from nbatotals/model/projection.py, i.e.
`pace × (off_home − off_away) / 100`. This has no home-court term: the formula's
`home_court_total` enters the total only. So a home-court constant is added (see
calibration). The raw margin without it (`h = 0`, the literal brief) is
reported as a labelled secondary row.

**(b) `elo_total`, margin version.** The brief asks for "elo_total's Elo ratings,
margin = rating difference plus home court". elo_total's existing ratings are in
points of *total* (both teams' ratings are added), so their difference measures
which team plays in higher-scoring games, not which team wins; it carries no
margin information by construction. So (b) is elo_total's update machinery
applied to the margin residual, as separate ratings in the same projector class:

- expected home margin = `L_m + r_home − r_away`, where `L_m` is the
  point-in-time league mean home margin (games dated before the target, same
  season, weighted against a base as if the base were `league_prior_games` = 100
  games; base = previous season's mean home margin, or `fallback_margin` = 2.0
  when the store has no earlier season, which only affects 2021-22, a training
  season);
- after each game: `r_home += K·err`, `r_away −= K·err`, err = actual margin −
  expected margin; ratings multiplied by `season_carry` = 0.5 at each new season;
- K chosen from the declared grid **{0.02, 0.05, 0.1, 0.2}** by margin RMSE on
  earlier seasons (first minimum in grid order). If K lands on the edge of the
  grid the grid is not widened; that is reported.
- Untuned default (state = None): K = 0.1.

The totals elo_total projection, fit and report are not changed (the margin
ratings use a separate fit method).

**Calibration (both projectors, fitted on earlier seasons only).** For test
season S, the projector's raw margin is computed point-in-time for every scored
game of the training seasons, with that season's fitted state. Then:

1. `h` = mean of (actual margin − raw margin) on those games. Model margin =
   raw + h. (For pace_eff this is the home-court constant; for the margin Elo it
   should be near 0.)
2. Home win probability = `1 / (1 + exp(−(raw + h) / s))`; the scale `s` is fitted
   by maximum likelihood (log loss) on the same training games' home-win
   outcomes, searched on [1, 60]. Expected `s` between 6 and 12 points; not a
   criterion.

`h` and `s` per test season are reported in the fit table.

A "default" run (projector state = None, i.e. params.yaml values, with `h` and
`s` still fitted on earlier seasons) is reported in the full reports only, as in
the totals test.

## Market consensus (fixed in advance)

Source: the same multi-region The Odds API payloads, same seven buckets, same
event-to-game join (commence_time's US Eastern date + team names mapped to
aliases), same timestamp rules as Amendment 2 of the main pre-registration: a
file counts only if polled before `commence_time`; a book is dropped if its
`last_update` is after `commence_time`; consensus rows captured at or after the
same game's true close are dropped. Prices converted from American to decimal
exactly.

**Spreads** (`spreads.json`). A book counts when it has exactly two outcomes
whose names are the event's home and away teams, both with a point and a valid
price, and home point = −(away point). Otherwise it is dropped and counted.

1. Drop a book whose home spread is more than **10 points** from the median home
   spread of all books for that game and bucket.
2. Consensus home spread = median of the remaining books' home spreads.
3. Devig each book multiplicatively, `p_home = (1/h) / (1/h + 1/a)`; consensus
   `p_home_cover` = mean over books.
4. Real price per side = median of the books' decimal prices for that side.
5. At least **3 books** after step 1.

Internally the line is stored as the **home margin the market implies**,
`m = −(home spread)`, so "home" plays the role of "over" in the totals code:
home covers when actual margin > m.

**Moneyline** (`h2h.json`). A book counts when it has exactly two outcomes
named as the event's home and away teams with valid prices (a draw outcome or a
third outcome drops the book). Each book devigged multiplicatively; consensus
`p_home` = mean of the books' devigged home probabilities; real price per side =
median decimal price; at least 3 books. There is no line, so there is no outlier
rule.

**Pinnacle-only** versions use Pinnacle's own quote at the true close (1 book
allowed), on games where Pinnacle quotes that market.

## Sanity table and stop rules (before any grading)

Per season and bucket, printed in the report before any grading table:

- spreads: games, median books, mean home spread, mean devigged `p_home_cover`,
  MAE and RMSE of the implied margin `m` against the actual margin, mean error;
- moneyline: games, median books, mean devigged `p_home`, the observed home win
  rate, Brier score and log loss of `p_home`;
- cross-market: share of games at the true close where the spread favourite
  (home spread < 0) is the moneyline favourite (`p_home > 0.5`), among games
  where the spread is not 0.

Expected: mean `p_home_cover` 0.48 to 0.52 at every bucket; mean `p_home` within
about 3 points of the season's home win rate; spread MAE vs actual margin around
9 to 10 points at the true close; favourite agreement at least 98%.

Grading stops, and the problem is reported instead, if any of these hold:

1. pooled mean devigged `p_home_cover` at the true close outside 0.48–0.52;
2. pooled mean devigged `p_home` at the true close more than 3 points from the
   pooled observed home win rate;
3. favourite agreement below 98% (a sign of a home/away mapping bug);
4. an earlier bucket beats the true close on the same games: paired difference
   (earlier − true close) in spread MAE, or in moneyline log loss, with a 95%
   bootstrap interval entirely below zero. A point estimate below zero whose
   interval includes zero is reported as noise and grading proceeds. (This is a
   tolerance on the main pre-registration's literal "must not be lower" rule,
   declared now because the near-close bucket is 45 minutes from the true close
   and a tie broken by noise should not stop the experiment; the literal
   comparison is printed too.)

## Grading rules (fixed in advance)

### Spreads

As the totals rules, with home = over:

- edge = model margin − market implied margin `m` (= model margin + home
  spread). Bet home if edge > 0, away if edge < 0, no bet at exactly 0.
- Thresholds 0 (every game), 1, 2, 3, 4, 6 points of |edge|. All reported.
- **Push:** actual margin = `m`. Excluded from cover rate and ROI, counted.
- Cover rate beside 50% and the mean devigged probability of the sides bet.
- Fair ROI pays `1/p_side − 1`; real ROI pays the median decimal price − 1;
  flat 1-unit stakes; bootstrap 95% intervals.
- **CLV in points** from each earlier bucket to the true close: home bets
  `m_close − m_A`, away bets `m_A − m_close` (positive = the market moved towards
  the bet). **CLV in cents**: the devigged close probability of the bet side at
  the bucket's line minus the bucket's devigged probability, with the line
  difference adjusted by a normal approximation with **SD 12 points** (declared
  now; the measured RMSE of the close against the actual margin is reported
  beside it).
- **Blend regression** `actual margin = a + b·m_close + c·model margin`, OLS,
  95% intervals.
- Projection accuracy: MAE and RMSE of the model margin and of `m` at each
  bucket against the actual margin.
- Pinnacle-only: cover, fair ROI and ROI at Pinnacle's own price against
  Pinnacle's true-close spread.

### Moneyline

- Model probability `p_model` (above) vs the market's devigged consensus
  `p_market` at the true close.
- **Brier score and log loss** of `p_model` and of `p_market` against the home-win
  outcome, per season and pooled, with a bootstrap 95% interval on the paired
  difference (model − market).
- **Blend regression**: logistic regression of the home-win outcome on an
  intercept, `logit(p_market)` and `logit(p_model)`, maximum likelihood with Wald
  95% intervals.
- **Flat-stake betting**: edge = `p_model − p_market` (home). Bet home if edge > t,
  away if edge < −t, at thresholds t = **2%, 4%, 6%** of probability (as briefed)
  and also **0** (every game with a non-zero edge), declared here as the primary
  cell by analogy with totals. All four reported, at every bucket. Win rate
  beside the no-information baseline (mean devigged probability of the sides
  bet); fair ROI pays `1/p_side − 1`; real ROI pays the median decimal price − 1;
  bootstrap intervals.
- **CLV in cents** from each earlier bucket to the true close: devigged close
  probability of the bet side minus the bucket's devigged probability of that
  side. (No line, so no points.)
- Pinnacle-only: Brier, log loss and betting at Pinnacle's devigged probability
  and own price at the true close.

## Expected results (written down before testing)

For both projectors unless stated.

| Metric | Expectation |
|---|---|
| ATS cover vs the true-close consensus spread, every game | 48% to 52% in each test season and pooled |
| ATS cover at thresholds 1, 2, 3, 4, 6 points | 47% to 53%, no monotone rise with threshold |
| ATS real ROI (median price) | about −4.5%, interval including that; fair ROI about 0%, interval including 0 |
| Model margin MAE vs the close's MAE against the actual margin | model worse, roughly 9.6 vs 9.0 points as briefed (the brief's figures; my own expectation is a close MAE nearer 9.5–10); model worse by 0.3 to 1.5 points |
| Spread blend regression | `b` near 1; `c` near 0 with a 95% interval including 0 |
| Spread CLV, opening → true close | possibly positive and small (0 to +0.4 points), as in totals |
| Spread CLV, noon and later → true close | within ±0.2 points of zero |
| Moneyline log loss and Brier | model worse than the market in every season (difference > 0), interval on the pooled difference above 0 |
| Moneyline blend regression | market coefficient near 1; model coefficient near 0 with a 95% interval including 0 |
| Moneyline betting at 0, 2, 4, 6% | win rate near the no-information baseline; fair ROI about 0 (interval including 0); real ROI negative, about −2% to −8% |
| Moneyline CLV in cents | opening possibly small positive; within ±0.5¢ of zero from noon on |
| Pinnacle-only | the same conclusions; ROI at Pinnacle's price negative, smaller in size than at the median price |
| `h` (fitted home-court constant) | pace_eff about +2 to +3.5 points; margin Elo within ±1 |

## What would count as evidence of an edge

**Spreads**, as in the main pre-registration, on the primary cell (tuned model,
true close, threshold 0): (1) Wilson 95% lower bound on cover above **52.38%** on
at least **1,000** graded bets pooled over at least two test seasons, with cover
above 50% in each; (2) noon → true close CLV in points with a bootstrap interval
above 0; (3) real-price ROI interval above 0.

**Moneyline**, adapted because prices vary bet to bet, on the primary cell (tuned
model, true close, threshold 0): (1) real-price ROI with a bootstrap interval
above 0 on at least 1,000 bets pooled over at least two test seasons, and win
rate above the no-information baseline in each season; (2) noon → true close CLV
in cents with an interval above 0; (3) model log loss below the market's, with
the pooled paired interval entirely below 0.

Everything else (other thresholds, buckets, projectors, the `h = 0` row, the
default run, Pinnacle-only) is descriptive. A non-primary cell clearing a bar is
an exploratory finding needing a fresh season, not an edge.

## Before believing any positive number

Bug first. Checked and written down in RESULTS.md: the home/away mapping of
outcomes (favourite agreement, mean `p_home` vs home win rate, and a hand check
of one game's file against the consensus row); the sign of the model margin
(its correlation with `m_close` must be strongly positive); the push and ROI
arithmetic and the devig (synthetic tests); the CLV sign; the anchor timestamps;
and the truncation leakage test extended to `predict_margin` for both projectors.
