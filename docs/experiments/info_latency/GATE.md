# Experiment 2, Phase A gate: are the inputs point-in-time?

Computed 20 October 2026 with `python -m nbatotals.experiments.info_latency_gate`
(needs NBA_LEGACY_DB, NBA_LEGACY_DNT, NBA_LEGACY_PLAYER_EPM, NBA_LEGACY_PROPS_DB),
against the thresholds committed in [PREREGISTRATION.md](PREREGISTRATION.md)
(98a89f7) before any of these numbers existed. No odds were read.

## Outcome

| input | gate | used? |
|---|---|---|
| Dunks & Threes projected minutes (`p_mp`) | **G1 passes** (pooled, as pre-registered) | yes, in every season; 2024-25 flagged (below) |
| Dunks & Threes player ratings (`player_epm`, game_optimized = 0) | **G2 passes**, by a wide margin | yes |

**G1, minutes.** R² of projected vs actual minutes is 0.79 (bar ≤ 0.90; a file
back-filled from the box would be near 1). 1.6% of players projected for 20+
minutes played none (bar ≥ 0.5%): late scratches, which a back-filled file could
not have. Overtime does not raise the projected sum (−0.9 minutes; real minutes
rise by about 25 a period). The mean team sum is 237 (bar 225–255).

**G2, ratings.** The rating is trailing, not a season-final number broadcast to
every game. A player's rating change into a game is unrelated to how he plays in
that game (correlation 0.016) and strongly related to how he played in the game
before (0.456). No player-season with 20+ games has a constant rating. A
player's rating at his first game of a season is close to his last of the
previous season (correlation 0.98) and further from his last of the same season
(0.86).

## Flag: 2024-25 files carry more same-day availability news

The pre-registered gate is pooled, and it passes. By season, 2024-25 is
different from 2021-22 to 2023-24 (descriptive table below):

- Of players who played 25+ minutes in their team's previous game and then sat
  out, DnT projected under 5 minutes for 93% in 2024-25, against 70–75% before.
- Only 0.45% of players projected for 20+ minutes sat out (about 2% before).
  That is just under the 0.5% bar if it were applied to that season alone.
- 31% of team-games project under 220 total minutes (14–17% before).
- Not a copy of the box score: 5.6% of the players DnT projected out in
  2024-25 did play, and R² stays at 0.81.

So the 2024-25 snapshots look as if they were taken later on the game day (or
DnT changed how it handles questionable players). Either way, 2024-25 projections
may contain news that reached the market after noon. As pre-registered, the file
is used in every season. Phase C reports CLV by season, and the late-news check
(CLV from the near-close and late-evening anchors) decides whether noon CLV is
something a bettor at noon could have had. In 2021-22 to 2023-24, every player
DnT projected out after a 25+ minute game did sit out (1,609 of 1,609). That fits
DnT zeroing only players already ruled out, since 25–30% of absences were still
unanticipated.

**Provenance (added after the results, from DnT's methodology page, October
2026):** DnT says its archived game predictions are the final pre-tip version,
updated with official player status in the last 30 minutes. For 2024-25 on they
are the predictions published at the time; earlier seasons are re-predictions by
a later model. That explains this flag: 2024-25 is a different kind of file. It
also means G1 shows "made before tip", not "made by noon". DnT also says Expected
EPM never includes games on that date, which agrees with G2. See RESULTS.md,
"Provenance of the Dunks & Threes inputs".

## Matching and join

Players: DnT names were matched to the BallDontLie player box by normalised name
within season and team. 99.1% of DnT rows with `p_mp` ≥ 10 matched (bar 90%), as
did 98.8% of rating rows. 98 DnT rows in 2024-25 have no projection at all
(`p_mp` null, all fringe players). They are read as 0 minutes; the
pre-registration did not cover this.

## Tables (as printed by the gate module)

### Join

| regular_games | dnt_games_joined |
|---|---|
| 4,940 | 4,918 |

Regular-season games joined to DnT by season: 2021: 1,211 of 1,230, 2022: 1,233 of 1,236, 2023: 1,237 of 1,237, 2024: 1,237 of 1,237

### G1: projected minutes

| season | dnt_rows | rows_pmp_ge_10 | match_share_pmp_ge_10 | g1a_n | g1a_share_played_0 | g1b_r2 | g1b_n | g1c_ot_minus_reg | g1c_ot_team_games | g1d_mean_team_sum_reg | team_sum_sd_reg | reverse_share_pmp_lt5_played_25 | reverse_n | naive_prev_game_r2 | naive_n | naive_same_rows_pmp_r2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2021-22 | 41,302 | 22,653 | 0.9915 | 15,125 | 0.0209 | 0.7803 | 40,615 | -3.3803 | 114 | 238.3839 | 22.7494 | 0.0047 | 14,806 | 0.5937 | 40,120 | 0.7809 |
| 2022-23 | 41,001 | 22,916 | 0.9922 | 15,242 | 0.0187 | 0.7833 | 40,757 | 3.0190 | 160 | 238.8321 | 22.7746 | 0.0050 | 14,519 | 0.5867 | 40,261 | 0.7845 |
| 2023-24 | 43,602 | 22,792 | 0.9907 | 15,217 | 0.0212 | 0.7991 | 43,026 | -0.7081 | 118 | 239.7926 | 18.8550 | 0.0035 | 16,886 | 0.6374 | 42,506 | 0.7996 |
| 2024-25 | 43,613 | 22,099 | 0.9910 | 14,777 | 0.0045 | 0.8100 | 43,137 | -4.2710 | 122 | 229.2080 | 26.3817 | 0.0086 | 18,085 | 0.5864 | 42,619 | 0.8110 |
| pooled | 169,518 | 90,460 | 0.9913 | 60,361 | 0.0164 | 0.7933 | 167,535 | -0.8531 | 514 | 236.5357 | 23.2402 | 0.0055 | 64,296 | 0.6014 | 165,506 | 0.7941 |

| criterion | passes |
|---|---|
| matching >= 90% of p_mp >= 10 rows | 1 |
| G1a share >= 0.5% | 1 |
| G1b R2 <= 0.90 | 1 |
| G1c |OT - regulation| <= 5 | 1 |
| G1d mean team sum in 225-255 | 1 |
| G1 passes | 1 |

Descriptive: availability news in the file

| season | absences_after_25min_game | share_anticipated_p_mp_lt5 | projected_out_n | projected_out_share_played_0 | team_sum_lt_220 | team_sum_gt_260 | p_mp_missing_rows | g1a_share_played_0 |
|---|---|---|---|---|---|---|---|---|
| 2021-22 | 767 | 0.7223 | 554 | 1.0000 | 0.1709 | 0.1197 | 0 | 0.0209 |
| 2022-23 | 784 | 0.7474 | 586 | 1.0000 | 0.1606 | 0.1314 | 0 | 0.0187 |
| 2023-24 | 667 | 0.7031 | 469 | 1.0000 | 0.1419 | 0.1035 | 0 | 0.0212 |
| 2024-25 | 875 | 0.9257 | 858 | 0.9441 | 0.3056 | 0.0800 | 98 | 0.0045 |
| pooled | 3,093 | 0.7821 | 2,467 | 0.9805 | 0.1949 | 0.1086 | 98 | 0.0164 |

### G2: player ratings

| season | player_seasons_20plus | g2a_share_range_lt_0.05 | median_season_range | g2b_n | g2b_c_in | g2b_c_after |
|---|---|---|---|---|---|---|
| 2021-22 | 543 | 0.0000 | 1.7575 | 21,202 | 0.0200 | 0.4740 |
| 2022-23 | 517 | 0.0000 | 1.7077 | 21,568 | 0.0209 | 0.4722 |
| 2023-24 | 564 | 0.0000 | 1.6745 | 21,521 | 0.0104 | 0.4611 |
| 2024-25 | 561 | 0.0000 | 1.9078 | 21,632 | 0.0140 | 0.4246 |
| pooled | 2,185 | 0.0000 | 1.7627 | 85,923 | 0.0163 | 0.4561 |

| g2c_n | g2c_corr_first_vs_prev_last | g2c_corr_first_vs_same_last | g2c_mean_abs_first_minus_prev_last | g2c_mean_abs_first_minus_same_last |
|---|---|---|---|---|
| 1,393 | 0.9816 | 0.8633 | 0.4496 | 0.9314 |

Rating rows matched to a BallDontLie player: 0.9883

| criterion | passes |
|---|---|
| G2a broadcast share < 50% | 1 |
| G2b c_after > 0.05 | 1 |
| G2b c_after - c_in > 0.05 | 1 |
| G2b c_in < c_after / 2 | 1 |
| G2c corr(first, previous last) > corr(first, same last) | 1 |
| G2 passes | 1 |

