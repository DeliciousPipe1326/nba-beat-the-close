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

One row per provider event, bookmaker, market and anchor.

| column | meaning |
|---|---|
| event_id, book, market, anchor | Primary key. `event_id` is the odds provider's event id; `market` in `totals`, `spreads`, `h2h` |
| game_id | The BallDontLie game, matched by the tip's US Eastern date and both team aliases. NULL until the fixture is in `games` (`ingest-games` fills it in) |
| captured_utc | When the provider was polled |
| commence_utc | The event's scheduled tip, as the provider reported it at that poll |
| lead_minutes | `commence_utc − captured_utc`. Live rows are always pre-tip (> 0) |
| home, away | Team aliases as the provider named the teams |
| line | Totals: the total. Spreads: the home spread. h2h: NULL |
| over_price, under_price | Totals only, decimal odds |
| home_price, away_price | Spreads and h2h only, decimal odds |
| source | Which ingester wrote the row |

Prices are stored as decimal odds, as The Odds API sends them. Only totals feed
the model; spreads and h2h are kept so nothing has to be refetched later.

**Live anchors** (`nbatotals/ingest/theodds.py`): `opening` (the first odds
snapshot of the event), `t-10h`, `t-5h`, `t-3h`, `t-2h`, `t-1h`, `t-15m` (the
first poll once the event is within that many minutes of tip; offsets in
params.yaml, matching the buckets the backtest graded), and `close`, which every
pre-tip poll overwrites, so it ends as the last snapshot before tip. Named
anchors keep their first capture. The real lead is in `lead_minutes`, because it
depends on how often you poll. Nothing polled at or after tip is stored.

**Legacy rows.** The legacy adapter's `write_store` stores the old table's rows
under `legacy_open`, `legacy_noon_local` and `legacy_close`, because those labels
do not describe when the snapshots were taken: measured from the raw payloads,
the legacy open is mostly in-play, noon_local is about 17 h before tip and close
about 6 h (docs/RESULTS.md, Appendix B). It uses the legacy table's decimal
prices, which match the raw payloads exactly; the American columns were rounded
from them (1.91 became −109). When `NBA_LEGACY_ODDS_LAKE` is set, each row is
also stamped with its real capture time, and in-play rows are dropped.

The backtest does not read odds from the store at all. It rebuilds anchors in
memory from the raw payloads by measured capture time: primarily the
multi-region payloads polled at seven offsets down to a true close 15 minutes
before tip (`nbatotals/evaluate/adapters/legacy_multiregion.py`,
`NBA_LEGACY_MULTIREGION`); and, as a cross-check, the three-a-day temporal
payloads (`legacy_lake.py`, `NBA_LEGACY_ODDS_LAKE`).

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

| season | anchor | rows | games | books | missing an American price | line outside 150-300 |
|---|---|---|---|---|---|---|
| 2021-22 | legacy open | 16,271 | 1,198 | 19 | 21 | 3 |
| 2021-22 | legacy noon_local | 12,816 | 1,196 | 19 | 0 | 0 |
| 2021-22 | legacy close | 22,412 | 1,306 | 19 | 3 | 16 |
| 2022-23 | legacy open | 19,219 | 1,240 | 21 | 12 | 12 |
| 2022-23 | legacy noon_local | 14,942 | 1,076 | 21 | 3 | 7 |
| 2022-23 | legacy close | 24,994 | 1,320 | 21 | 8 | 8 |
| 2023-24 | legacy open | 15,277 | 1,293 | 16 | 0 | 0 |
| 2023-24 | legacy noon_local | 15,547 | 1,308 | 16 | 0 | 0 |
| 2023-24 | legacy close | 18,536 | 1,319 | 16 | 0 | 0 |
| 2024-25 | legacy open | 11,577 | 1,317 | 11 | 0 | 0 |
| 2024-25 | legacy noon_local | 13,040 | 1,321 | 11 | 0 | 0 |
| 2024-25 | legacy close | 13,126 | 1,321 | 11 | 0 | 0 |

Regular-season games with at least one complete closing totals quote: 1,213 of
1,230 (2021-22), and every game in 2022-23, 2023-24 and 2024-25.

Integrity checks: box points reproduce the final score in every row (0
mismatches); 0 odds rows point at an unknown game; 0 odds rows disagree with the
games table on who is home; 0 duplicate (game, book, market, anchor) keys.

**Prices.** 47 of 197,757 legacy totals rows lack an American over or under
price (gtbets 19, pointsbetus 26, williamhill_us 2). The adapter originally
dropped them. Since it switched to the provider's decimal columns, which are
present for those rows and match the raw payloads, none is dropped for that
reason. Separately, 46 rows carry a line outside 150–300 (half or quarter
totals filed as full-game totals, and a few `0.0` lines, mostly mybookieag). The
pre-registered consensus rule removes these by their distance from the
cross-book median rather than by a fixed band.

These are counts of the legacy table as it stands. Its anchor labels are wrong
(docs/RESULTS.md, Appendix B), and the backtest does not use it for odds.
