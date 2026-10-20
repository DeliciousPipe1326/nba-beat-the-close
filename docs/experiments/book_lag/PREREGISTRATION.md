# Pre-registration: Experiment 3, book versus book (soft books against Pinnacle)

Written 20 October 2026, before any code for this experiment exists and before
any soft-book price was compared with Pinnacle's. The commit that adds this
file is the timestamp. Any later change is a new commit with its reason, and
RESULTS.md reports against the version committed before the first run.

## Question

At each pre-tip poll, how far does each soft book's price sit from Pinnacle's
devigged probability **at the same poll time**, in cents? And does betting
those discrepancies pay after the soft book's own vig, when settled at the game
result and measured as CLV against Pinnacle's true close?

This is not a projector. It is a market-against-market strategy harness
(`nbatotals/evaluate/market_vs_market.py`, CLI `python -m nbatotals
backtest-books --legacy`) that reuses the devig in `market.py` and the
statistics in `metrics.py`.

## Data

- The maintainer's private multi-region The Odds API payloads
  (`$NBA_LEGACY_MULTIREGION`, read only, never copied or committed):
  `season=*/date=*/nba_game_id=*/bucket=*/{totals,spreads,h2h}.json`, each one
  event polled at a fixed offset before tip, with `metadata.timestamp` (poll
  time), `event.commence_time` and, per book, `last_update` and American prices.
- Games and final scores from `$NBA_LEGACY_DB`. Events are joined to games
  exactly as in Amendment 2 of the main pre-registration: `commence_time`
  converted to a US Eastern date plus home and away team names mapped to
  aliases. Scored games: `status = final` and `postseason = 0` as the source
  flags it (the same set as the main study).
- **Test seasons: 2022-23, 2023-24, 2024-25.** 2021-22 (incomplete in this
  source) is reported descriptively and never counts towards the evidence bar.
  The partial 2025-26 folder is not read: it stays unseen for a later check.
- Final scores include overtime. Totals, spreads and moneylines (h2h) are all
  settled on the final score including overtime.

## Anchors

Bets can be struck at **opening, noon, afternoon, early_evening, late_evening
and near_close**. **true_close** (T−15 min) is used only as the CLV reference,
never as a betting anchor.

## Quote hygiene (book-level sanity checks, fixed in advance)

A file counts only if `metadata.timestamp` is before `event.commence_time`.
Within a counted file, a book's quote (soft book or Pinnacle) is dropped, and
counted by reason, if:

1. **stale:** its `last_update` is more than 30 minutes before the poll time;
2. **after tip:** its `last_update` is at or after `commence_time`;
3. **from the future:** its `last_update` is after the poll time (should never
   happen; counted);
4. **malformed:** a missing price or point; totals whose over and under points
   differ; spreads whose two points are not equal and opposite; outcome names
   that do not match the event's teams (spreads, h2h) or Over/Under (totals);
   an American price that does not convert;
5. **duplicate:** a second row for the same game, bucket, market and book
   (first kept), or an event that matches more than one game.

The counts of dropped quotes by reason, book and market are reported. A soft
book's quote is compared with Pinnacle's only when both survive at the same
game, bucket and market.

## Fair value

`p_fair` = **Pinnacle's devigged probability at the same bucket**, two-way
multiplicative devig as in `market.py`: `p_a = (1/d_a) / (1/d_a + 1/d_b)` for
decimal prices `d_a`, `d_b`.

- **h2h:** no line; `p_fair` for home and away directly.
- **totals and spreads, exact-line (primary):** the soft book's line must equal
  Pinnacle's line (totals: same total; spreads: same home handicap).
- **totals and spreads, converted (secondary, reported beside the primary):**
  if the lines differ by at most 0.5 points, Pinnacle's probability is moved to
  the soft book's line with a normal approximation: the outcome (total, or the
  bet team's margin) is normal with **SD 18 for totals and 13.5 for spreads**,
  centred so that the probability at Pinnacle's line equals Pinnacle's devigged
  probability (`metrics.prob_over_at`). This ignores the extra push mass on
  whole-number lines; that is a stated approximation. Lines further apart than
  0.5 points are not compared.

Two discrepancy measures are reported per book (descriptive, no bets):

- **price gap, cents** = `100 × (p_fair − 1/d)` for each side, where `1/d` is
  the soft book's raw implied probability (vig included). Positive on a side
  means the book pays more than Pinnacle's fair value implies.
- **devigged disagreement, cents** = `100 × (p_book_devig − p_fair)` on the
  home / over side: where the book's own vig-free view sits relative to
  Pinnacle's.

## Bets (fixed in advance)

- For each soft book, game, bucket and market, each side's **edge** =
  `p_fair × d − 1`, with `d` the soft book's decimal price for that side.
- **One bet at most per (book, game, bucket, market):** the side with the larger
  edge, if that edge is at or above the threshold. (Both sides can show a
  positive edge only when the book's own overround is below Pinnacle's fair
  book; the rule keeps it to one.)
- **Thresholds: 1%, 2%, 3%, 5%.** All are reported; none is selected. Tables
  that show one threshold show 2%, chosen here before running.
- Flat 1-unit stakes. A win returns `d − 1`; a loss −1.
- **Settlement** from final scores at the soft book's own line. **Pushes are
  excluded** from cover rate and ROI and counted separately.
- Pinnacle itself is never bet (it is the fair value). Every other book key in
  the payloads is a "soft book" here, whatever its reputation.
- **Exchanges** (`betfair_ex_uk`, `betfair_ex_eu`, `betfair_ex_au`,
  `matchbook`) quote prices before commission. They are reported in the same
  tables, marked, with realised ROI shown gross. Their commission is not
  measured in this data; an exchange edge smaller than its commission (a few
  percent of net winnings) is not an edge.

## CLV (fixed in advance)

For a bet struck at bucket A on side s at the soft book's line L:

- **CLV, cents** = `100 × (p_close(s, L) − p_fair(s, L))`, where `p_close` is
  Pinnacle's devigged true-close probability of side s. When Pinnacle's
  true-close line differs from L, `p_close` is moved to L with the same normal
  approximation (SD 18 totals, 13.5 spreads), whatever the distance. Positive
  means Pinnacle's fair price moved towards the bet after it was struck.
- **Line movement, points** (totals and spreads): Pinnacle's true-close line
  relative to L, signed so that positive favours the bet: over `close − L`,
  under `L − close`; spreads, for the bet team's handicap h (e.g. +5.5),
  `h − h_close`.
- **Edge at the close** = `p_close(s, L) × d − 1`: the conventional "beat the
  closing line" measure. This is positive more or less by construction for any
  bet with a positive paper edge if Pinnacle moves little, so it is reported
  but is not the test.
- Bets on games where Pinnacle has no surviving true-close quote are kept for
  ROI and excluded from CLV; their count is reported.

## Statistics

- Cover rate with a 95% Wilson interval, beside the baseline of the mean
  `p_fair` of the sides bet.
- Realised ROI and mean CLV with 95% bootstrap intervals (10,000 resamples,
  seed 20261020, `metrics.SEED`). Within one (book, bucket, market) cell there
  is at most one bet per game, so resampling bets is resampling games. When
  buckets are pooled, the bootstrap resamples **games** (a cluster bootstrap),
  because the same game's outcome settles several bets.
- Mean paper edge per cell.

## Expected results (written down before running)

1. **Paper edge** at or above 2% exists, but is **concentrated at a few books**,
   most likely recreational, offshore and slow-moving books (for example
   mybookieag, betus, bovada, everygame, fliff, some AU and EU books) and the
   exchanges; the large US books (draftkings, fanduel, betmgm) show little.
2. Paper edge **rises towards tip**: the number of 2% bets per game and the
   mean paper edge are higher at late_evening and near_close than at opening,
   because Pinnacle moves on late information (injuries, line-ups) and slower
   books follow with a delay. (The book names in 1 are a guess from the books'
   reputations, not from this data.)
3. **Realised ROI below the mean paper edge**, because some of the gap is the
   soft book being right or Pinnacle's price being noisy, and because of
   variance; ROI intervals at the per-book level will be wide (±10% or more on
   a few hundred bets).
4. **CLV, cents** (the Pinnacle move after the bet) near zero or slightly
   positive: Pinnacle is the reference and moves little after near_close.
   **Edge at the close** positive for most cells, mechanically.
5. **Lag correlation** (below) positive for slow books and near zero for books
   that copy Pinnacle within the same poll.

## Evidence bar (fixed in advance)

A book is reported as showing a **measured inefficiency that paid** in a market
only if, at the **2% threshold, pooling the six betting buckets** over the three
test seasons:

1. at least **500 settled bets** at that book in that market;
2. the 95% cluster-bootstrap interval on **realised ROI** has a lower bound
   **above zero**;
3. the 95% interval on mean **CLV in cents** has a lower bound **above zero**.

There are about 40 books × 3 markets = about 120 primary cells, and many more
descriptive cells (6 buckets × 4 thresholds). With 120 independent cells at a
one-sided 2.5% level, about 3 would clear condition 2 by chance. So every
primary cell also gets a **Bonferroni lower bound** (mean − 3.54 × bootstrap
SE, for 0.05/120 two-sided), and a book that clears the bar only without the
Bonferroni correction is reported as exploratory.

Even a book that clears the bar is **a measurement of inefficiency, not a
strategy**: books with soft prices restrict or close accounts that win, and the
API's snapshot price is not proof that a bet of any size could have been
placed at it.

## Lag measured directly

For each soft book and market, over consecutive betting buckets
(opening → noon → afternoon → early_evening → late_evening → near_close →
true_close): the correlation between **Pinnacle's move over the previous bucket
pair (b−1 → b)** and **the soft book's move over the next pair (b → b+1)**.
Moves are line points for totals and spreads (each book's own main line) and
devigged home probability (cents) for h2h. Reported with a 95% Fisher interval
(`metrics.corr_ci`), pooled over the test seasons. Two reference rows: Pinnacle's
own correlation between consecutive moves (momentum), and the same-period
correlation between Pinnacle's and the book's move over b → b+1. A book
lags if its next-period correlation clearly exceeds Pinnacle's own momentum
row.

## Before believing any positive number

Treat it as a bug first. For any book with positive realised ROI in a primary
cell, check and write down in RESULTS.md:

1. **stale quotes:** distribution of `poll − last_update` for its bets; re-run
   with a 10-minute staleness rule;
2. **line mismatch:** exact-line versus converted results; that the bet's line
   equals Pinnacle's line in the exact-line run;
3. **sign of the devig:** that `p_fair` is attached to the right side (over vs
   under, home vs away) on hand-checked rows, and that the mean `p_fair` of the
   sides bet matches their cover rate when edges are zero;
4. **duplicate events:** no event joined to two games, no game with two events,
   no repeated (book, game, bucket, market);
5. **in-play contamination:** every bet's poll time and `last_update` before
   `commence_time`; minimum lead per bucket.
