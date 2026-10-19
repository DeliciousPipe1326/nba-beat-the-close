# Tier A features and projection

Code: [`nbatotals/features/pointintime.py`](../nbatotals/features/pointintime.py),
[`nbatotals/model/projection.py`](../nbatotals/model/projection.py). Every number
is in [`config/params.yaml`](../config/params.yaml).

## The cut-off rule

For a game dated D (the NBA's Eastern schedule date), every feature uses only
rows with `game_date < D`. Other games played on day D are excluded too, as is
the game's own score. The projection call takes only the fixture (id, date,
season, home, away), so it runs unchanged on tonight's games.

## Features (per side, home and away)

| Feature | Built from | Cut-off |
|---|---|---|
| `n` | count of the team's team_box rows | same team, same season, date < D |
| `pace_l3`, `ortg_l3`, `drtg_l3` | the team's last 3 games | same team, same season, date < D |
| `pace_l10`, `ortg_l10`, `drtg_l10` | the team's last 10 games | same team, same season, date < D |
| `pace_season`, `ortg_season`, `drtg_season` | all the team's games this season | same team, same season, date < D |
| `pace`, `ortg`, `drtg` | blend of the three windows, shrunk to the prior | as above, plus the league reference below |
| `rest_days`, `b2b` | days since the team's previous game, minus 1; `b2b` = rest 0 | games table (schedule dates only), same team, same season, date < D; NaN and not B2B for a season opener |

Plus, per game:

| Feature | Built from | Cut-off |
|---|---|---|
| `league_pace`, `league_ortg` | season-to-date league averages shrunk towards a base value | all teams, same season, date < D; base = previous season's full league average (all dated < D), or the constants in params.yaml |
| `league_n` | team-games in the season-to-date average | same |

Window rates are possession-weighted, not averages of per-game numbers:
`pace = 48 · Σpossessions / Σminutes`, `ortg = 100 · Σpoints / Σpossessions`,
`drtg = 100 · Σpoints allowed / Σpossessions`. Windows shorter than their size
(the first 9 games for L10) use what exists.

**Blend and shrinkage.** With `n` games played:
`blended = w3·L3 + w10·L10 + ws·season`, then
`final = (n·blended + k·prior) / (n + k)`. On opening night `n = 0` and the team
is exactly the prior. The prior is the league reference (pace for pace,
league points per 100 for both ortg and drtg). If `team_carryover_weight` is
above 0 (default 0), the prior becomes
`w · last season's team rate + (1 − w) · league`. That is the only route by which
a team's previous season can reach its numbers.

**League reference.** With `m` team-games played league-wide before D:
`league = (m·raw + K·base) / (m + K)`, where `K = league.shrinkage_team_games`.

**Optional home/away split.** With `home_away_split: true`, the home side uses
only its earlier home games and the away side only its earlier away games.

## Projection

```
pace_proj = L_pace + pace_weight · ((home_pace − L_pace) + (away_pace − L_pace))
off_home  = L_ortg + off_weight · (home_ortg − L_ortg) + def_weight · (away_drtg − L_ortg)
off_away  = L_ortg + off_weight · (away_ortg − L_ortg) + def_weight · (home_drtg − L_ortg)
total     = pace_proj · (off_home + off_away) / 100
            + home_court_total + b2b_total_per_team · (home_b2b + away_b2b)
```

No machine learning. The walk-forward harness (Phase 3) may re-choose only the
pre-registered set: the three blend weights, `team_shrinkage_games`,
`pace_weight`, `home_court_total` and `b2b_total_per_team`. `off_weight`,
`def_weight`, the carry-over weight and the league settings stay fixed.

## Leakage self-test

[`nbatotals/evaluate/leakage.py`](../nbatotals/evaluate/leakage.py), run by
`tests/test_leakage.py`.

1. **Truncation.** For a sample of games, delete every games and team_box row
   dated on or after D, blank the game's own score, rebuild, and require every
   one of the 33 feature columns to be bit-identical to the full-history value.
   The sample is stratified by season and by early, mid and late season (thirds
   of each season's dates), and always includes every opening-night game, where a
   season-boundary leak would show. Also run with the home/away split on, with
   carry-over at 0.5, and with constant league priors.
2. **Correlation.** For each window and blended stat, compare its correlation
   with the game's actual total against the correlation of the same feature as
   it stood at the team's previous game. A feature that includes the game
   itself correlates far more. The literal rule "must not exceed" fails for
   honest features, which hold one extra earlier game and so are slightly more
   informative. The test therefore allows an excess of 0.03 and proves the check
   has teeth with a deliberately leaky control (cut-off one day late), which must
   exceed 0.03 on every feature.
3. **Explicit checks** in `tests/test_features.py`: opening night equals the
   prior exactly and windows are empty after the season boundary; the league
   reference equals a hand computation from earlier rows; rest and B2B are
   unchanged when every box score and score is deleted (schedule only);
   windows, blend and shrinkage match hand computation.

Results on 20 Oct 2026:

| Data | Truncation sample | Values compared | Max abs diff | Mismatches | Correlation excess, honest (max) | Leaky control excess (min) |
|---|---|---|---|---|---|---|
| Synthetic league (offline, 2 seasons) | 223 games | 7,359 | 0.0 | 0 | 0.019 | 0.048 |
| Legacy DB, 2021-22 to 2024-25 | 248 games (20 per season-third + 8 opening-night games) | 8,184 | 0.0 | 0 | 0.020 (pace_l3) | 0.038 (pace_season) |
