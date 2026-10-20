# nbatotals

## What this is

A toolkit for testing NBA betting models honestly. You bring your own API keys and your own model idea. It gives you the data, a baseline model, and a referee.

**Who this is for.** This is not an app. There is no website, no screen, no button, and nothing to install beyond Python. You use it from a terminal, you write a short Python class to add a model, and you read tables. You should be comfortable with Python and pandas, with running commands and a scheduled job, and with getting your own API keys. If that is not you, the useful part of this repository is the result and the method, which you can read without running anything.

**What it does**

1. **Collects data** into a local database: games, box scores, and bookmaker odds for totals, spreads and moneyline, each odds quote stamped with when it was captured. Live from today onward, or backfilled for past seasons if you pay for history.
2. **Projects games** with a simple, fully visible model: pace times scoring efficiency gives a total, and the same numbers give a margin and a win probability. Every setting is in one file.
3. **Grades any model** against the real closing line, season by season, with confidence intervals and a fixed pass bar that was written down before the test ran. Plug in your own model with one small class and you get the identical report.

**What it found**

The included model, run on four seasons, does not beat the market in any of the three bet types. Nor did a professional public model, nor did price gaps between bookmakers, nor did player props. This repository publishes that result and the full method, so the next person starts from the truth instead of rediscovering it. Plug in your own model and find out whether yours does.

**Your own model** is one Python class with a `name`, a `fit` and a `predict`, plus one line in the registry; then `python -m nbatotals backtest --store --model my_model` produces the same report the included model got. It may only use data dated before each game, and a test checks that for every registered model. See ["Building on this"](#building-on-this).

**What it is not**

Not a picks service, not a dashboard, not a bot. It will not make money. It will tell you quickly and reliably whether your idea does.

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

**Spreads and moneyline: the same answer.** The same ratings were run through the
same harness on the other two markets, under their own pre-registration
([docs/experiments/other_markets/](docs/experiments/other_markets/RESULTS.md)).
Against the true-close spread, pace_eff covers 50.3% (95% Wilson 48.7–51.9%) and a
margin Elo 49.4% (47.8–51.1%), both losing about the vig. On the moneyline both
models' probabilities have a worse log loss than the market's in every season,
and they get no weight once the market is known. The evidence bar was not met in
either market. Run them with `python -m nbatotals backtest --legacy
--market-type spreads` (or `h2h`).

**How many bets it takes to prove an edge.** Totals are noisy: the true close
misses the final total by 17.8 points RMSE in this data. To show, at 95% confidence, that a
true win rate clears the 52.38% break-even you need roughly
`n = 1.96² · p(1−p) / (p − 0.5238)²` bets:

| true win rate | edge over break-even | bets needed | NBA seasons of betting every game |
|---|---|---|---|
| 53.38% | 1 point | 9,560 | about 8 |
| 54.38% | 2 points | 2,382 | about 2 |
| 55.38% | 3 points | 1,055 | about 1 |
| 57.38% | 5 points | 376 | a third of one |

Three seasons give about 3,650 bets. That can find a large edge or rule one
out; it cannot confirm a small one.

## Three ways to use this

The second is the point of the repository.

1. **Look at it** (one minute, no keys): install, run the offline demo, open
   `out/demo_report.html`. See ["Try it in one minute"](#try-it-in-one-minute).

   ```bash
   pip install -e . && python -m nbatotals demo
   ```

2. **Test your own model on past seasons:** keys in `.env`, build the store,
   check the cost with a dry run, then backfill; write and register a projector
   ([docs/YOUR_FIRST_MODEL.md](docs/YOUR_FIRST_MODEL.md), a ten-minute
   walkthrough, and ["Building on this"](#building-on-this)) and grade it. See
   ["Backfilling history"](#backfilling-history).

   ```bash
   python -m nbatotals init && python -m nbatotals ingest-games --season 2023 --season 2024 && python -m nbatotals ingest-box --season 2023 --season 2024
   ```

   ```bash
   python -m nbatotals backfill-odds --season 2024 --dry-run
   ```

   ```bash
   python -m nbatotals backfill-odds --season 2024 && python -m nbatotals backtest --store --model my_model
   ```

3. **Run it on today's games:** `poll-odds` on a schedule, then the day's CSV
   and its HTML page. See ["Quick start"](#quick-start).

   ```bash
   python -m nbatotals poll-odds && python -m nbatotals today && python -m nbatotals report
   ```

## Background

The author previously tried many approaches privately: team rating systems,
boosted models on box-score features, player-level projections, rules built on
line movement, and player props. None of them survived an audit for leakage,
pricing and selection. This repository keeps only the one engine that was
rebuilt under pre-registered rules, together with the data engine and harness
needed to test anything else the same way.

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

**Example projectors** (in [nbatotals/model/](nbatotals/model/), added after the
pre-registered run and not part of it). They went through the same harness and
the same leakage test; full results are in
[RESULTS.md, "Other projectors"](docs/RESULTS.md#other-projectors-through-the-same-harness).

- `league_avg`: every game is projected at the point-in-time league-average
  total (league pace × league points per 100 for both teams). It has no team
  information and no settings of its own. Measured: 49.7% cover against the
  true close (95% Wilson 48.1–51.3%), −5.1% at real prices, CLV from the
  opening −0.02 points.
- `elo_total`: each team has a rating in points of total. The expected total is
  the point-in-time league-average total plus both teams' ratings; after each
  game both ratings move by K × (actual − expected), and ratings are multiplied
  by `season_carry` at each new season. Settings are under `models.elo_total` in
  params.yaml; `fit` picks K from the declared `k_grid` on earlier seasons (it
  chose 0.05 every season). Measured: 49.2% cover (47.6–50.9%), −6.1% at real
  prices, CLV +0.59 points from the opening and +0.14 from noon, test RMSE 18.2
  to 18.7.

**Tier B** (experimental): `lineup_pace_eff`, the same formula with each team's
pace, offence and defence taken from that game's Dunks & Threes projected
minutes and player EPM. It was tested in its own pre-registered experiment
([docs/experiments/info_latency/](docs/experiments/info_latency/RESULTS.md)) on
the maintainer's archived DnT files. Measured: 49.8% cover against the true close,
−5.0% at real prices, CLV +0.85 points from the opening and +0.43 from noon. But
it also predicts line moves in the last two hours before tip, so the archived
files hold late same-day news and the noon CLV is not something a noon bettor
could have had. No edge. Live DnT ingestion is still a stub
(`nbatotals/ingest/dunksandthrees.py`).

**The harness.** Walk-forward fitting, devigged consensus, pushes excluded,
every bet graded at its own price, CLV in points and cents, Wilson and bootstrap
intervals, edge thresholds fixed in advance and all reported, and a
market-plus-model regression. Any number that looks like an edge is treated as
a bug until checks rule that out (see RESULTS.md for the eight it went through).

## Building on this

The harness grades any projection the same way, so you can test your own model
without touching it. New to this? Start with
[docs/YOUR_FIRST_MODEL.md](docs/YOUR_FIRST_MODEL.md), a ten-minute walkthrough;
`python -m nbatotals new-model my_model` writes and registers the template it
uses. A projector is a class with a `name`, a `fit` and a
`predict` (the interface is in [nbatotals/model/base.py](nbatotals/model/base.py)).
The harness hands it `games` (one row per game: date, season, teams, scores
when final) and `box` (one row per team per game: possessions, points, pace and
ratings), both from the local store, plus `params` from `config/params.yaml`;
`targets` are the games to project.

```python
import pandas as pd
from nbatotals.features.pointintime import build_features


class TeamPaceOnly:
    """Team pace, league-average efficiency."""
    name = "team_pace_only"

    def fit(self, train_games, train_box, params, progress=None):
        return {}  # called once per test season with earlier seasons only; tune here if you like

    def predict(self, targets, games, box, state, params):
        f = build_features(targets, games, box, params)  # point-in-time: rows dated before each game
        pace = f.league_pace + (f.home_pace - f.league_pace) + (f.away_pace - f.league_pace)
        return pd.DataFrame({"game_id": f.game_id, "total_proj": pace * 2 * f.league_ortg / 100})
```

Put the class in its own file under `nbatotals/model/`, for example
`nbatotals/model/my_model.py`, next to `pace_eff.py`, `league_avg.py` and
`elo_total.py`.

1. **Register it:** import it in
   [nbatotals/model/registry.py](nbatotals/model/registry.py)
   (`from nbatotals.model.my_model import MyModel`) and add
   `MyModel.name: MyModel` to `PROJECTORS`; for the example above, that is
   `TeamPaceOnly.name: TeamPaceOnly`.
2. **Leakage test:** run `pytest tests/test_leakage.py`. It runs the truncation
   test on every registered projector: each game's projection must be identical
   when every row dated on or after that game is deleted.
3. **The rule:** `fit()` sees only seasons before the one being tested and never
   odds; `predict()` may use only rows dated before each game. `state=None` means
   untuned (the values in params.yaml).
4. **Backtest it:** after backfilling (see "Backfilling history"),
   `python -m nbatotals backtest --store --model team_pace_only` grades it on
   your store and writes the report to `out/`, in the format of the
   pre-registered report. With odds you have collected live, call
   `nbatotals.evaluate.backtest.run(games, box, odds, params, spec=backtest.LIVE, projector=...)`.
   The author's private path, `python -m nbatotals backtest --legacy` (the
   default model, `pace_eff`), needs the maintainer's data and regenerates
   [docs/backtest_legacy_report.md](docs/backtest_legacy_report.md) byte for
   byte.
5. **Use it live:** `python -m nbatotals today --model team_pace_only`.

The two example projectors described under "What it is" (`league_avg`,
`elo_total`) are written exactly this way; read their source as templates.

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

## Try it in one minute

No keys, no downloads:

```bash
pip install -e .
```

```bash
python -m nbatotals demo
```

Then open `out/demo_report.html`. The demo builds a small store under
`data/demo/` from a **made-up league with made-up odds** (`nbatotals/synthetic.py`)
and runs the same `today` and `report` code the real pipeline uses. It shows
what the output looks like, nothing more: its teams, scores and lines are not
real. Real projections need your own API keys and the steps in Quick start;
`python -m nbatotals report` then renders the day's CSV in the same layout.

## Backfilling history

To test your own model on past seasons you need past odds. `backfill-odds` fills
your local store from The Odds API's historical endpoint with your own
`THEODDS_API_KEY`; `backtest --store` then runs the same walk-forward harness
on it:

```bash
python -m nbatotals ingest-games --season 2023 --season 2024
```

```bash
python -m nbatotals ingest-box --season 2023 --season 2024
```

```bash
python -m nbatotals backfill-odds --season 2024 --dry-run
```

```bash
python -m nbatotals backfill-odds --season 2024 --max-credits 100000
```

```bash
python -m nbatotals backtest --store --model elo_total
```

The backtest needs odds for the season you test and box scores for at least
one earlier season, because every parameter is fitted on earlier seasons only.
Its report goes to `out/` (git-ignored).

**Cost.** Historical odds cost 10 credits per market per region per call, at
the provider's published rate; the default is the provider's `us` region, or
pass `--books` with a list of bookmaker keys (10 credits per 10 books). Run on
the real 2024-25 schedule (1,321 games), the dry run plans **4,520 calls** at
the default anchors (opening, T−10h, T−5h, T−1h, T−15 min), totals only: **about
45,000 credits** (up to about 63,000 if openings need later snapshots); all
three markets triple that. Games in the same 5-minute snapshot window share a
call, and nothing already stored is fetched again. The worst case is checked
against the credits remaining and `--max-credits` once, before the first paid
call; re-pricing from each response's `x-requests-last` and
`x-requests-remaining` headers is a TODO in
[`theodds_history.py`](nbatotals/ingest/theodds_history.py).

**Checked on recorded responses, not live.** Replaying the author's 7,851
recorded 2024-25 per-event responses through the same parse, join and store
code (a maintainer-only test, `tests/test_replay_legacy.py`) dropped 31 events
already in play and none beyond the 36-hour maximum lead, stored 222,297 rows,
and put the `strict_close` bucket within 0.5 points of the multi-region true close on
84.1% of 1,287 games, with a mean devigged P(over) of 0.500. The recorded
snapshots are 10 minutes apart in 2021-22 and 5 minutes apart from 2022-23 on,
so the snapshot returned can be up to that long before the requested time.

**What it refuses to do**, each a defect found in the author's earlier data
(see "Lessons" below):

- request snapshots at fixed clock times: every anchor is a lead before that
  game's own tip, and the snapshot's real timestamp is stored next to the lead
  that was asked for;
- join a quote to a game by the request date: events are matched by their own
  commence time and team names;
- keep anything polled at or after tip, or any book updated at or after tip
  (dropped and counted);
- spend credits before printing the plan and its cost and getting a yes
  (`--yes` skips only the prompt), or past the credits remaining or
  `--max-credits`. `--dry-run` makes no request at all.

**Licence.** The Odds API's terms do not allow redistributing the data you
fetch. It stays in your git-ignored `data/` store; commit nothing fetched.

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
| `models.elo_total.k` | 0.05 | `elo_total` only: rating points moved per point of total error, when untuned (`today`, `state=None`). |
| `models.elo_total.k_grid` | 0.01, 0.02, 0.05, 0.1 | `elo_total` only: the declared grid `fit` searches on earlier seasons by RMSE. |
| `models.elo_total.season_carry` | 0.5 | `elo_total` only: ratings are multiplied by this at each new season. |
| `models.elo_total.league_prior_games` | 100 | `elo_total` only: weight, in games, of the base league total early in a season. |
| `models.elo_total.fallback_total` | 222.0 | `elo_total` only: base league total when no earlier season is in the store. |
| `models.lineup_pace_eff.scale / scale_grid` | 1.0 / 0.5–1.5 | `lineup_pace_eff` only: points per 100 possessions per point of minutes-weighted team EPM. Fitted from the grid (chose 1.25, 1.0, 1.0). |
| `models.lineup_pace_eff.shrinkage / shrinkage_grid` | 0 / 0, 5, 10, 20 | `lineup_pace_eff` only: team deviations scaled by n/(n+k), n = team games so far. Fitted (chose 5, 5, 0). |
| `models.lineup_pace_eff.home_court_total / b2b_total_per_team` | 2.0 / 1.0 | `lineup_pace_eff` only: fixed at pace_eff's 2022-23 fit (from 2021-22 alone). |

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
  rebuilds history with their own keys through the ingesters and
  `backfill-odds` (see "Backfilling history"), then runs `backtest --store`.
- **Live box scores are summed from player rows.** BallDontLie's `/stats` has
  no team-turnover line, so live possessions can sit slightly below those from
  the official team totals the backtest used. The size of that difference has
  not been measured.
- **The seasons were not unseen.** The author had tested other approaches on these
  seasons before (see Background). A clean confirmation needs data collected
  from now on.

## The one open question

Nothing in this repository beats the closing line, and the market has priced
the box-score information these models use by about ten hours before tip.
What the market adds between the opening line and the close is mostly who
plays. A projection built from lineup-adjusted player ratings and each game's
projected minutes showed more than twice the formula's closing-line value from
the opening anchor, but every such input available to this study was a
pre-game file of unknown capture time that evidently contained news from late
in the game day, so the result is an upper bound, not a measurement
([docs/experiments/info_latency/RESULTS.md](docs/experiments/info_latency/RESULTS.md)).

Whether a morning lineup projection carries information the noon line has not
priced can only be answered with projections and odds captured live at fixed,
recorded times over an unseen season. The author chose not to run that test:
the best case it supports is one or two cents of closing-line value at thin
early lines against several cents of vig, which is not a betting proposition.
The ingesters here store a poll time on every row, so anyone who wants the
answer can collect it.

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
| `nbatotals/model/` | Projector interface (`base.py`), registry, the pre-registered formula (`projection.py`, `pace_eff.py`) and the two examples |
| `nbatotals/evaluate/` | Consensus and devig, walk-forward fit, grading, leakage checks, legacy adapters |
| `nbatotals/ingest/` | BallDontLie, The Odds API (live polling and `theodds_history` backfill), Dunks & Threes stub |
| `nbatotals/today.py`, `nbatotals/cli.py` | The `today` CSV and the command line |
| `config/params.yaml` | Every number the engine uses |
| `nbatotals/experiments/`, `nbatotals/features/players.py` | Experiment 2: input gate, report, player inputs for `lineup_pace_eff` |
| `docs/` | Pre-registration, results, full backtest reports, schema, features; `docs/experiments/` for later pre-registered experiments |
| `tests/` | Offline tests on synthetic data, including the leakage self-test |
| `nbatotals/demo.py`, `nbatotals/report.py`, `nbatotals/synthetic.py` | The offline demo, the HTML report and the made-up league both use |
| `nbatotals/scaffold.py`, `docs/YOUR_FIRST_MODEL.md` | `new-model` and the walkthrough whose template it writes |
| `scripts/check.sh` | Lint, types, complexity budget and tests in one command ([docs/CODE_QUALITY.md](docs/CODE_QUALITY.md)) |

## Licence and data

Code: MIT ([LICENSE](LICENSE)). Data: none is included, and none should be
committed. BallDontLie, The Odds API and Dunks & Threes data is licensed to
whoever fetched it, so fetch it with your own keys into the git-ignored `data/`
folder. `.gitignore` excludes `.env*`, `data/`, databases, parquet, CSV, logs and
model binaries; keep it that way.

The author no longer runs live collection. The fetch paths (`ingest-*`,
`today`, `backfill-odds`) were last exercised on synthetic fixtures, the
providers' documentation and, for `backfill-odds`, recorded responses; if a
provider has changed something, issues and pull requests are welcome.
