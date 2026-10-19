# Local store schema

One SQLite file, by default `data/nbatotals.db` (git-ignored). The DDL lives in
[`nbatotals/store.py`](../nbatotals/store.py); this page explains it. Teams are
always the 3-letter aliases in [`nbatotals/teams.py`](../nbatotals/teams.py).

Nothing in the store is ever committed. Every user fills their own store with
their own API keys (see the README).

## games

| column | type | meaning |
|---|---|---|
| id | INTEGER PK | BallDontLie game id |
| game_date | TEXT | The NBA's schedule date (US Eastern), `YYYY-MM-DD` |
| tip_utc | TEXT | Scheduled tip in UTC, ISO-8601; NULL when the source did not give one |
| season | INTEGER | Start year: `2024` is 2024-25 |
| postseason | INTEGER | 1 for games the source flags as postseason |
| home, away | TEXT | Team aliases |
| home_pts, away_pts | INTEGER | Final score; NULL until the game is final |
| periods | INTEGER | 4 for regulation, 5 for one overtime, and so on |
| status | TEXT | `final` or `scheduled` |
| source | TEXT | Which ingester wrote the row |

**Deviation from the original brief.** The brief named this column `date_utc`.
It stores the NBA's own (Eastern) calendar date instead, because a UTC date puts
a 7:30 pm ET tip on the next day and a 1 pm ET tip on the same day, so two games
by the same team can share a UTC date. All point-in-time filtering ("rows strictly
before the game date") uses `game_date`. The exact moment is in `tip_utc`.

**Postseason flag.** In the legacy data the flag puts the 2021-22 play-in in the
postseason, but leaves the play-in (and, from 2023-24, the NBA Cup final) in the
regular season for 2022-23 onwards: 1,236 or 1,237 "regular" games instead of
1,230. The harness uses the flag as given and says so.

## team_box

One row per team per final game.

| column | meaning |
|---|---|
| game_id, team | Primary key |
| opp, is_home | Opponent alias; 1 if this team was at home |
| minutes | Game length in minutes: `48 + 5 * overtimes` |
| pts, fgm, fga, fg3m, fg3a, ftm, fta, orb, drb, tov | Box-score counts |
| possessions | Game possessions: mean of both sides' `FGA - ORB + TOV + 0.44 * FTA` |
| pace | Possessions per 48 minutes: `48 * possessions / minutes` |
| ortg | Points scored per 100 possessions |
| drtg | Points allowed per 100 possessions |

`possessions`, `pace`, `ortg` and `drtg` are always recomputed from the counts by
[`nbatotals/boxscore.py`](../nbatotals/boxscore.py), whatever the source, so the
legacy backtest and the live engine see identical definitions.

The legacy DB's own `pace` column turned out to be raw game possessions, not
possessions per 48. It matches our `possessions` to 1e-14 on all 10,566 team rows
and our `pace` in regulation games, but is inflated in the 542 overtime team rows.
We do not use it.

## odds_snapshots

One row per game, bookmaker, market and anchor.

| column | meaning |
|---|---|
| game_id, book, market, anchor | Primary key. `market` in `totals`, `spreads`, `h2h`; `anchor` in `open`, `pretip`, `close` |
| captured_utc | When the snapshot was taken. NULL when the source did not record it (all legacy rows) |
| nominal_hours_before | The anchor's intended lead time before tip |
| line | Totals: the total. Spreads: the home spread. h2h: NULL |
| over_price, under_price | Totals only, decimal odds |
| home_price, away_price | Spreads and h2h only, decimal odds |
| source | Which ingester wrote the row |

Prices are stored as decimal odds, as The Odds API sends them. The legacy
adapter uses the legacy table's decimal columns, which match the raw payloads
exactly; its American columns were rounded from those decimals (1.91 became
−109), so they are only a fallback where a decimal is missing. Only totals feed the model; spreads
and h2h are kept so nothing has to be refetched later.

**Anchors.** The live ingester (The Odds API) takes `open` (first snapshot seen),
`pretip` (a configurable lead before tip, default 60 minutes) and `close` (the
last snapshot before tip), each with its real `captured_utc`.

The legacy labels are wrong. Measured from the raw payloads, the legacy
`open` is mostly in-play, `noon_local` is about 17 h before tip and `close` about
6 h before tip. The backtest therefore does not use the legacy table's anchors:
it rebuilds early (~23h), overnight (~17h) and afternoon (~6h) anchors from the
raw payloads by measured capture time
(`nbatotals/evaluate/adapters/legacy_lake.py`; see docs/RESULTS.md, "Data
defect"). When `NBA_LEGACY_ODDS_LAKE` is set, the legacy adapter also stamps
each legacy row with its real capture time and drops in-play rows.

The primary backtest uses a second, better legacy source: multi-region payloads
polled at seven fixed offsets before each tip, down to a true close 15 minutes
out (`nbatotals/evaluate/adapters/legacy_multiregion.py`, path from
`NBA_LEGACY_MULTIREGION`). Its quotes are built in memory in the
`odds_snapshots` shape with `anchor` set to the bucket name, so they are not
written to the store, whose `anchor` column is limited to the live anchors.

## injuries

| column | meaning |
|---|---|
| observed_utc, player_id | Primary key: when the report was fetched, and the BallDontLie player id |
| team, player_name, status, description, return_date | As reported |
| source | Which ingester wrote the row |

Tier A does not use injuries. The table exists so a user can build an
injury adjustment from their own snapshots; past injury reports cannot be
fetched after the fact, so start collecting early if you want one.

## api_usage

One row per paid API call: provider, endpoint, and the quota headers the
provider returned (The Odds API reports requests used, remaining and the cost of
the last call).

## Legacy adapter verification (run 20 Oct 2026)

`python -m nbatotals.evaluate.adapters.legacy_nba_db` against the maintainer's
private DB. Counts only; no data from it is in this repository.

Final games and complete box-score pairs:

| season | regular | box pairs | postseason | box pairs |
|---|---|---|---|---|
| 2021-22 | 1,230 | 1,230 | 93 | 93 |
| 2022-23 | 1,236 | 1,236 | 84 | 84 |
| 2023-24 | 1,237 | 1,237 | 82 | 82 |
| 2024-25 | 1,237 | 1,237 | 84 | 84 |

(2025-26 has 222 final games in the DB, through 19 Nov 2025, with no box scores
or odds; it is not used.)

Totals snapshots (all games, both seasons phases):

| season | anchor | rows | games | books | missing a price | line outside 150-300 |
|---|---|---|---|---|---|---|
| 2021-22 | open | 16,271 | 1,198 | 19 | 21 | 3 |
| 2021-22 | pretip | 12,816 | 1,196 | 19 | 0 | 0 |
| 2021-22 | close | 22,412 | 1,306 | 19 | 3 | 16 |
| 2022-23 | open | 19,219 | 1,240 | 21 | 12 | 12 |
| 2022-23 | pretip | 14,942 | 1,076 | 21 | 3 | 7 |
| 2022-23 | close | 24,994 | 1,320 | 21 | 8 | 8 |
| 2023-24 | open | 15,277 | 1,293 | 16 | 0 | 0 |
| 2023-24 | pretip | 15,547 | 1,308 | 16 | 0 | 0 |
| 2023-24 | close | 18,536 | 1,319 | 16 | 0 | 0 |
| 2024-25 | open | 11,577 | 1,317 | 11 | 0 | 0 |
| 2024-25 | pretip | 13,040 | 1,321 | 11 | 0 | 0 |
| 2024-25 | close | 13,126 | 1,321 | 11 | 0 | 0 |

Regular-season games with at least one complete closing totals quote: 1,213 of
1,230 (2021-22), and every game in 2022-23, 2023-24 and 2024-25.

Integrity checks: box points reproduce the final score in every row (0
mismatches); 0 odds rows point at an unknown game; 0 odds rows disagree with the
games table on who is home; 0 duplicate (game, book, market, anchor) keys.

**Not every totals snapshot has both prices.** 47 of 197,757 legacy totals rows
lack an over or under price (gtbets 19, pointsbetus 26, williamhill_us 2). The
adapter drops them, leaving 197,710. Separately, 46 rows carry a line outside
150-300 (half or quarter totals filed as full-game totals, and a few `0.0`
lines, mostly mybookieag); the consensus rule in the pre-registration removes
these by distance from the cross-book median rather than by a fixed band.
