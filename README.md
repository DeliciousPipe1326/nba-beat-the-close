# nbatotals

A transparent pace × efficiency engine for NBA game totals (over/under), a data
engine that fetches today's fixtures and odds with your own API keys, and a
backtest harness built so that it cannot flatter itself.

**It does not beat the market.** That is the main result, and the reason to use
this repository is to see exactly how it was measured.

## What the backtest found

Walk-forward over three held-out seasons, every parameter fitted on earlier
seasons only, graded against the devigged consensus of 30-plus books 15
minutes before tip. The hypotheses and expected results were committed before
any backtest ran ([docs/PREREGISTRATION.md](docs/PREREGISTRATION.md)). Full
results: [docs/RESULTS.md](docs/RESULTS.md).

| season | bets | cover vs true close (95% Wilson) | no-information baseline | fair ROI (95% CI) | real ROI (95% CI) |
|---|---|---|---|---|---|
| 2022-23 | 1,207 | 48.4% (45.6%–51.2%) | 50.0% | -3.2% (-9.0% to 2.5%) | -7.6% (-13.2% to -2.3%) |
| 2023-24 | 1,225 | 47.9% (45.1%–50.7%) | 50.1% | -4.3% (-9.8% to 1.3%) | -8.5% (-13.8% to -3.2%) |
| 2024-25 | 1,220 | 50.3% (47.5%–53.1%) | 50.2% | 0.2% (-5.3% to 5.7%) | -4.0% (-9.4% to 1.1%) |
| **pooled** | **3,652** | **48.9% (47.3–50.5%)** | 50.1% | **−2.4%** (−5.7% to +0.8%) | **−6.7%** (−9.8% to −3.7%) |

- Against Pinnacle's own closing line and price only: **49.5%** cover, **−3.8%**
  at Pinnacle's price.
- Given the closing line, the model adds nothing: regressing the actual total on
  the close and the model gives the model a weight of **−0.117** (95% CI −0.264
  to +0.031), i.e. about zero.
- **The pre-registered evidence bar for an edge was not met** (a cover-rate lower
  bound above the 52.38% break-even on 1,000+ bets, plus positive CLV): no cell
  in any season, anchor or threshold came close, the best lower bound being 49.2%.

**One exploratory finding, not an edge.** Box-score information is priced in
between about 24 and 10 hours before tip: a bet at the open gains 0.8¢ of CLV
(+0.39 points of line movement towards the model, 95% CI +0.29 to +0.49; exactly
+0.80¢) against roughly 4.5¢ of vig. From noon (about 10 hours out) the CLV is
zero (−0.02 points). Bets at the open still won only 49.6% and lost 5.5% at real
prices. Testing whether an opening-line strategy works needs a live, unseen
season (2025-26 onwards, collected with the ingesters here) and its own
pre-registration.

**How many bets it takes to prove an edge.** Totals are noisy (the closing
line misses the final total by 18 points SD). To show, at 95% confidence, that a
true win rate clears the 52.38% break-even you need roughly
`n = 1.96² · p(1−p) / (p − 0.5238)²` bets:

| true win rate | edge over break-even | bets needed | NBA seasons of betting every game |
|---|---|---|---|
| 53.38% | 1 point | 9,560 | about 8 |
| 54.38% | 2 points | 2,382 | about 2 |
| 55.38% | 3 points | 1,055 | about 1 |
| 57.38% | 5 points | 376 | a third of one |

Three seasons give about 3,650 bets. That can find a large edge or rule one
out; it cannot confirm a small one. An earlier variance study by the same
author reached the same figures (about 9,000 bets for a 1-point edge).

## What it is

**Tier A engine** (the one tested). For each game, using only data dated
before the game:

1. each team's pace and points per 100 possessions (offence and defence) over its
   last 3 games, last 10 and the season so far, blended and shrunk towards the
   league average early in the season;
2. `pace = league + w·(home pace dev + away pace dev)`;
   `home pts/100 = league + (home offence dev) + (away defence dev)`, and the
   same for the away side;
3. `total = pace × (home pts/100 + away pts/100) / 100 + home-court constant +
   back-to-back adjustment`.

No machine learning: a formula whose every coefficient is in
[config/params.yaml](config/params.yaml), seven of them re-fitted per season by
the backtest. Details and the leakage self-test:
[docs/features.md](docs/features.md).

**Tier B** (optional, not built): player-level EPM from Dunks & Threes behind
your own key. `nbatotals/ingest/dunksandthrees.py` is a documented stub. Nothing
in the results says anything about it.

**The harness.** Walk-forward fitting, devigged consensus, pushes excluded,
every bet graded at its own price, CLV in points and cents, Wilson and bootstrap
intervals, edge thresholds fixed in advance and all reported, and a
market-plus-model regression. Any number that looks like an edge is treated as
a bug until checks rule that out (see RESULTS.md for the eight it went through).

## Quick start

Python 3.10+.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # then put your own keys in .env
pytest                  # runs offline: no keys, no data needed
```

Keys (in `.env` only; it is git-ignored):

- `BALLDONTLIE_API_KEY`: fixtures, results and box scores (balldontlie.io).
- `THEODDS_API_KEY`: odds (the-odds-api.com). Each odds call costs
  `markets × regions` credits; listing events is free.
- `DUNKSANDTHREES_API_KEY`: optional, Tier B only.

Build your history, then poll odds on a schedule:

```bash
python -m nbatotals init
python -m nbatotals ingest-games --season 2025
python -m nbatotals ingest-box --season 2025
```

```bash
python -m nbatotals poll-odds
```

Run `poll-odds` every 5 to 10 minutes on game days (cron, launchd, Task
Scheduler). It only spends credits when an anchor is due. Then:

```bash
python -m nbatotals today
```

That writes `out/today_<date>.csv`, with each fixture's projected total and
pace, the stored consensus line and when it was captured, the devigged over
probability and `edge` (projection minus line). The first line of the file
repeats what the backtest found. It is research output, not betting advice.

To refresh results and box scores each morning, run `ingest-games --date
<yesterday>` and `ingest-box --date <yesterday>`. The local store is
`data/nbatotals.db`; its schema is in [docs/schema.md](docs/schema.md).

## Every knob in `config/params.yaml`

Fitted means the backtest re-chose it per season from earlier seasons only.
Fixed means it never did.

| Key | Default | What it does |
|---|---|---|
| `features.blend.l3 / l10 / season` | 0.3 / 0.5 / 0.2 | Weights on a team's last 3 games, last 10 and season-to-date. Must sum to 1. Fitted (chose 0.0–0.1 / 0.4–0.5 / 0.5–0.6). |
| `features.team_shrinkage_games` | 5 | The league-average prior counts as this many games: `(n·blend + k·prior)/(n + k)`. Fitted (chose 10 every season). |
| `features.team_carryover_weight` | 0 | Share of a team's previous-season rating in its early-season prior. 0 = every team starts at league average. Fixed. |
| `features.home_away_split` | false | Use only home games for the home team and away games for the away team. Fixed. |
| `league.shrinkage_team_games` | 30 | How strongly the season-to-date league average is pulled towards its base early in the season. Fixed. |
| `league.prior_source` | previous_season | Base for the league average: last season's, or the constants below. Fixed. |
| `league.fallback_pace / fallback_ortg` | 99.0 / 112.0 | Used only when no earlier season is in the store. Fixed. |
| `projection.pace_weight` | 1.0 | 1.0 adds both teams' pace deviations; 0.5 averages them. Fitted (chose 1.0). |
| `projection.off_weight / def_weight` | 1.0 / 1.0 | Weight on offence and opponent-defence deviations. Fixed. |
| `projection.home_court_total` | 0.0 | Points added to every total; acts as the constant term. Fitted (chose +2, the top of the range: see limitations). |
| `projection.b2b_total_per_team` | 0.0 | Points added per team on the second night of a back-to-back. Fitted (chose +1, +1, 0). |
| `market.outlier_points` | 10 | Drop a book more than this far from the median line. Pre-registered. |
| `market.min_books` | 3 | Books needed for a consensus. Pre-registered. |
| `ingest.theodds.regions / markets` | us / totals,spreads,h2h | What to request; each multiplies the credit cost. |
| `ingest.theodds.anchors_minutes_before_tip` | 600, 300, 180, 120, 60, 15 | The T−10h … T−15m anchors (the buckets the backtest graded). `opening` and `close` are always kept. |
| `ingest.theodds.opening_recheck_minutes` | 60 | Stops an event no book has priced yet from costing credits on every poll. |
| `ingest.theodds.min_requests_remaining` | 20 | Refuse to spend credits below this remaining quota. |
| `ingest.balldontlie.min_seconds_between_requests` | 12 | Spacing to respect your plan's rate limit. |
| `today.market_anchor` | close | Which stored anchor supplies the line in the `today` CSV (`close` = latest pre-tip poll). |

If you change a fitted or fixed value and want to know whether it helps, re-run
a backtest on data you collect yourself, pre-register what you expect first,
and report every variant you tried, not just the best one.

## Known limitations

- **`home_court_total` hit the top of its declared range (+2) in every season.**
  It is the formula's constant term, and the untuned projection runs about a
  point low. The grid was deliberately not widened after the results were seen.
  You can widen it in params.yaml and re-run; that is a new, post-hoc
  experiment, so label it as one.
- **2021-22 odds coverage is incomplete** in the multi-region source (1,051 of
  1,230 regular-season games). It was a training season only, and the parameter
  search used no odds, so no test number depends on it.
- **The legacy data is private.** The backtest ran on the author's own
  BallDontLie and The Odds API history, which cannot be redistributed, so
  `python -m nbatotals backtest --legacy` is maintainer-only. Everyone else
  rebuilds history with their own keys through the ingesters; past odds need The
  Odds API's paid historical endpoint.
- **Live box scores are summed from player rows.** BallDontLie's `/stats` has
  no team-turnover line, so live possessions can sit slightly below those from
  the official team totals the backtest used. The size of that difference has
  not been measured.
- **The seasons were not unseen.** The same author tested related ideas on these
  seasons before. A clean confirmation needs data collected from now on.

## Lessons for anyone using The Odds API historical data

Read [RESULTS.md, Appendix B](docs/RESULTS.md#appendix-b-data-defect-in-the-legacy-odds-table-historical-note)
before you build on historical snapshots. Snapshots taken at fixed clock times
contain the previous evening's games **in play**. In the author's old data, an
"open" fetched at 8:25 pm Eastern was attached to games already under way, and it
"beat" the later lines because it could see the score. **Always keep the poll
timestamp and the event's `commence_time` with every quote, and drop anything
polled at or after tip.** The ingester here does both, and the backtest rebuilt
every anchor from the raw payloads' own timestamps rather than trusting labels.

## Repository map

| Path | What |
|---|---|
| `nbatotals/features/pointintime.py` | Point-in-time team features (cut-off: rows dated before the game) |
| `nbatotals/model/projection.py` | The projection formula |
| `nbatotals/evaluate/` | Consensus and devig, walk-forward fit, grading, leakage checks, legacy adapters |
| `nbatotals/ingest/` | BallDontLie, The Odds API, Dunks & Threes stub |
| `nbatotals/today.py`, `nbatotals/cli.py` | The `today` CSV and the command line |
| `config/params.yaml` | Every number the engine uses |
| `docs/` | Pre-registration, results, full backtest reports, schema, features |
| `tests/` | Offline tests on synthetic data, including the leakage self-test |

## Licence and data

Code: MIT ([LICENSE](LICENSE)). Data: none is included, and none should be
committed. BallDontLie, The Odds API and Dunks & Threes data is licensed to
whoever fetched it, so fetch it with your own keys into the git-ignored `data/`
folder. `.gitignore` excludes `.env*`, `data/`, databases, parquet, CSV, logs and
model binaries; keep it that way.
