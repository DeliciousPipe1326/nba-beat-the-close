# Pre-registration: Experiment 4, player props against Pinnacle

Written 20 October 2026, before any prop quote has been joined to a box score or
any bet has been graded. The commit that adds this file is the timestamp. Later
changes are new commits with the reason in the message; RESULTS.md reports
against the version committed before the first graded run.

What was looked at before writing this (structure only, no outcomes): the file
layout, the JSON fields, which books appear in which region, capture timestamps
against `commence_time`, how many lines each book quotes per player, and which
2024-25 players have a name in `balldontlie_players`. Facts found, used below:

- 37,125 prop files in five region folders (`us`, `us_ex`, `uk`, `eu`, `au`),
  1,245 events on 167 dates with files (199 date folders; some are empty).
  Dates with files run 22 Oct 2024 to 16 Apr 2025, plus one date, 28 Nov 2025.
  A stray date folder `player_props/2024-11-18/` with no region is ignored.
- `uk` files contain no bookmakers. `eu` holds only Pinnacle and BetOnline.
  BetOnline (`betonlineag`) appears in both `us` and `eu`.
- Each event and market has two captures. Measured from the payload's own
  `timestamp` against `commence_time`: the early capture is about **T−3h05m**
  and the late one about **T−9 min** (the file names are about 4 minutes later
  than the payload timestamps, because the provider returns the snapshot at or
  before the requested time). This report calls them **T−3h** and **close (about
  T−9 min)**, not T−5 min. 75 files are captured at or after tip; a few events
  were rescheduled and have extra files.
- Prices are American integers. Most books quote one line per player; BetRivers
  and Unibet also quote alternate lines; the exchanges (Novig, ProphetX,
  BetOpenly) often quote one side only. Pinnacle quotes one two-sided line per
  player.
- All 587 BallDontLie player ids with a 2024-25 row in `player_game_logs` have a
  name in `nba.db.balldontlie_players`.

## Question

In player points, rebounds and assists props, how far do retail books' prices
sit from Pinnacle's at T−3h and at the close, and does betting the side where a
retail price beats Pinnacle's devigged fair probability pay after the vig,
settled on the actual box score?

## What we already know

The maintainer's earlier private work tested player-prop rules (trailing
hit-rate streaks) on overlapping data and found overs losing 12–14% and unders
losing about the vig. These seasons are therefore not unseen for props.

## Scope and test set

- Markets: `player_points`, `player_rebounds`, `player_assists`.
- **Test set:** events whose game is a 2024-25 regular-season game: matched in
  `nba.db.games` with season 2024, `postseason = 0`, and US Eastern tip date on
  or before **13 April 2025** (the last regular-season day; the 15–16 April
  play-in games carry `postseason = 0` in the source and are excluded).
- Descriptive only: the 2025-26 date (28 Nov 2025). The settlement table ends
  with 2024-25, so those quotes are reported as discrepancies only, not graded.
- Books: every bookmaker key except Pinnacle is a "retail" book, exchanges
  included (reported by name, so exchanges can be read separately).

## Data rules (fixed in advance)

1. **Capture windows.** A file's lead = `commence_time − timestamp` from the
   file itself. **T−3h** = lead between 120 and 240 minutes; **close** = lead
   above 0 and at most 30 minutes. Other files are dropped and counted. If a
   region has more than one file for the same event, market and window, the one
   with the latest `timestamp` is kept and the others counted.
2. **In-play and stale quotes.** A book's market is dropped if its
   `last_update` is after `commence_time` (counted). A quote is **stale** if its
   market `last_update` is more than 60 minutes before the file timestamp.
   Stale quotes stay in the primary run; their share is reported per book and a
   sensitivity run drops stale retail and stale Pinnacle quotes.
3. **Duplicate lines.** Within one file and book, if the same player, line and
   side has more than one price, that player-line is dropped for that book
   (counted). Different lines for the same player (alternates) are separate
   quotes.
4. **Double counting across regions.** The same book can appear in several
   region files. Quotes are deduplicated on (book, event, market, player, line,
   side, window), keeping the first region in the order `us`, `us_ex`, `au`,
   `eu`. This is stricter than deduplicating on the book's `last_update` too;
   both counts are reported, as is how many duplicates disagreed on price.
5. **Fair value.** Pinnacle's two-sided quote for the same event, market,
   player (exact `description` string), line and window, devigged
   multiplicatively with the repository's rule:
   `p_over = (1/o) / (1/o + 1/u)` (as in `nbatotals/evaluate/market.py`).
   The Pinnacle file and the retail file must be timestamped within 10 minutes
   of each other (else the pair is dropped and counted).
6. **Same line only.** Where the retail line differs from Pinnacle's, there is
   no comparison: prop distributions are discrete and skewed, so no line
   conversion is attempted. The number of retail quotes with a Pinnacle quote
   for the player but a different line, and the number of same-line pairs that
   remain, are reported.
7. **Edge.** For a retail quote on side s at decimal price d:
   `edge = p_fair(s) × d − 1`. A bet is placed on every side whose edge is at
   or above the threshold. **Thresholds: 2%, 3%, 5%, 8%**, all reported, none
   selected. A 0% row (every same-line side with edge > 0) is reported as
   descriptive. Flat 1-unit stakes.
8. **Player matching.** Events are joined to `nba.db.games` by `commence_time`
   converted to the US Eastern date plus home and away full team names (the
   repository's `FULL_NAME_TO_ALIAS`). Player names are matched to the box
   score of that game only (rows in `player_game_logs` for that `game_id`), by
   exact equality after this normalisation and nothing else: Unicode accents
   stripped, lower case, periods and apostrophes removed, hyphens to spaces,
   trailing suffixes `jr`, `sr`, `ii`, `iii`, `iv` removed, whitespace
   collapsed. A name with zero or more than one match in that game is
   **unmatched and excluded, never guessed**. The match rate (distinct
   event-player names, and quotes) is reported, with the unmatched names listed
   by frequency.
9. **Settlement** from `player_game_logs` (points, rebounds, assists):
   - **DNP:** `minutes_decimal = 0` or `is_dnp` → the bet is **void**, as the
     books settle it; voids are counted, not losses.
   - **Push:** stat equal to the line (integer lines only) → excluded from hit
     rate and ROI, counted.
   - Otherwise win pays `d − 1`, loss `−1`.
10. **CLV** for T−3h bets: Pinnacle's close devigged probability of the bet side
    at the same line minus the bet's T−3h `p_fair`. If Pinnacle's close line
    differs from the T−3h line, CLV in probability is not computed (no line
    conversion); those bets are counted, and the share whose Pinnacle line moved
    towards the bet (higher for overs, lower for unders) is reported. Close bets
    have no CLV (n/a).

## What is reported

Per market (and all three pooled) and per region and per book, for each window
and threshold: n settled bets, mean paper edge, realised ROI with a 95%
bootstrap interval, hit rate with a 95% Wilson interval beside the mean `p_fair`
of the bets (the no-information expectation), CLV with a 95% bootstrap interval
and its n. Tables sorted by n. Overs and unders separately. Bootstrap: 10,000
resamples over events (games), seed 20261020, because bets on the same game,
and the same prop at several books, are correlated. The Wilson intervals treat
bets as independent and are too narrow for pooled region cells; this is said
beside them.

Also: how far books sit from Pinnacle: per book and window, the share of
Pinnacle player-lines the book quotes at the same line, the mean absolute line
difference where it differs, the book's hold, and the mean of the book's own
devigged `p_over` minus Pinnacle's at the same line (two-sided quotes only).

Benchmark for "more often than in game lines": the same share of same-line
retail sides with edge ≥ 2% against Pinnacle, computed from the 2024-25
regular-season game totals in the multi-region totals payloads at the
`early_evening` (~3h) and `true_close` (T−15 min) buckets, through the existing
`legacy_multiregion` reader.

## Expected results (written down before testing)

| Metric | Expectation |
|---|---|
| Share of same-line retail sides with paper edge ≥ 2% | Higher in props than in game totals at both windows |
| Where the paper edges are | Concentrated in overs |
| Realised ROI vs mean paper edge | Realised ROI below the mean paper edge in most cells; most cell intervals include or sit below 0 |
| Overs vs unders | Unders closer to break-even than overs |
| CLV of T−3h bets | Mean within ±1 probability point of 0: a retail price above Pinnacle's fair value says the retail book is generous, not that Pinnacle will move |
| Evidence bar | Not met in any cell |

## What would count as evidence of an inefficiency

In a single cell, (book or region) × window × threshold, with all three markets
and both sides pooled:

1. at least **500 settled bets**;
2. the 95% bootstrap interval on realised ROI is above zero;
3. the bets have **positive CLV**: the 95% bootstrap interval on mean CLV is
   above zero (so only T−3h cells can meet the bar).

There are roughly 20 books plus 3 regions × 2 windows × 4 thresholds of cells,
so some will look good by chance. A cell that clears the bar is first treated
as a bug and checked (below); if it survives, it is an exploratory finding that
needs a fresh season, and it measures a price inefficiency, not a strategy:
books like these limit accounts that win.

## Checks on any positive cell (bug first)

Written into RESULTS.md with the outcome of each:

- name mismatches: the matched box-score name for a sample of the cell's bets;
  the cell's result with only names that match without normalisation;
- line mismatches: every bet's retail line equals the Pinnacle line it was
  priced against; integer vs half lines;
- devig sign: over/under not swapped (mean Pinnacle `p_over` on bets placed on
  overs, hit rate of Pinnacle's favoured side across all pairs);
- double counting across regions: no (book, event, market, player, line, side,
  window) appears twice;
- capture time before `commence_time` for every file used; stale-quote
  sensitivity;
- settlement: a sample of settled bets checked against the box score; voids
  counted.

## Sanity checks reported regardless of results

- every file used captured before `commence_time` (count of dropped files);
- the player name match rate between the prop payloads and the box-score table;
- duplicate lines per player per book;
- stale `last_update` shares per book;
- Pinnacle's own calibration: over all same-window Pinnacle quotes, the
  devigged probability of the over against the over's actual hit rate.
