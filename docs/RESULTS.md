# Results: Tier A walk-forward retest

Status: search space declared; nothing has been run yet. This section is
committed before any parameter search, consensus or grading code runs.

## Search space (fixed before running)

Objective: RMSE of `total_proj` vs actual total over the **training seasons'**
regular-season games (`postseason = 0`), all games including opening weeks,
pooled across training seasons. No odds are read during the search.

Grid (full Cartesian product, 34,650 points per test season):

| Parameter | Values |
|---|---|
| `features.blend` (l3, l10, season) | every point of the 0.1-step simplex: each weight in {0.0, 0.1, ..., 1.0}, summing to 1 (66 points) |
| `features.team_shrinkage_games` | 0, 2, 5, 10, 20 |
| `projection.pace_weight` | 0.5, 0.75, 1.0 |
| `projection.home_court_total` | −2, −1, 0, 1, 2 |
| `projection.b2b_total_per_team` | −3, −2, −1, 0, 1, 2, 3 |

Everything else stays at the `config/params.yaml` defaults.

Training seasons per test season:

| Test season | Trained on |
|---|---|
| 2022-23 | 2021-22 |
| 2023-24 | 2021-22, 2022-23 |
| 2024-25 | 2021-22, 2022-23, 2023-24 |

Selection: the lowest training RMSE. Ties within 1e-9 go to the first point in
grid order (blend, shrinkage, pace weight, home court, B2B, each ascending).
Every evaluation is logged to `docs/search/fit_log.tsv.gz` (test season,
parameters, training RMSE, training n). The chosen point is frozen and the
whole test season is scored with it. A second run scores every season with the
untouched defaults.

## Anchor labels

The legacy odds have three anchors, all labels without a verified capture
time: **open** (nominally ~18 h before tip), **noon (~12h)** (the legacy
`noon_local` snapshot, stored as `pretip`; it is not the live ingester's
60-minute pre-tip anchor) and **close** (nominally ~0.5 h before tip). The open
anchor is the primary CLV comparison; noon is secondary.

## Market sanity checks (before any betting metric)

Per season and anchor: games scored, median books per game, consensus line
mean and SD, mean devigged p_over (expected near 0.50), share of consensus lines
on a quarter point, MAE of the consensus line vs the actual total (expected about
14.4 at the close), and, as an anchor-ordering check, the share of games whose
open and close consensus lines differ and the mean absolute open-to-close move.
If any of these is off, grading stops and the problem is reported first.
