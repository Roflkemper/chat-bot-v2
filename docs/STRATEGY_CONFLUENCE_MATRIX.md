# Strategy Confluence Matrix

**Source:** `data/historical_setups_y1_2026-04-30.parquet` (18712 setups)
**Bucket:** 60 min
**Min co-fires to report:** 5

## Top 15 confluence pairs by WR boost

| # | Type A | Type B | N co-fire | WR(co) | WR(A alone) | WR(B alone) | Boost (pp) | Avg PnL$ |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | long_dump_reversal | long_pdl_bounce | 425 | 42.8% | 35.9% | 37.1% | +5.7 | +nan |
| 2 | short_pdh_rejection | short_rally_fade | 470 | 35.1% | 33.6% | 29.2% | +1.5 | +nan |
| 3 | grid_booster | long_oversold_reclaim | 12 | 0.0% | 0.0% | 8.3% | -8.3 | +nan |
| 4 | long_oversold_reclaim | long_pdl_bounce | 6 | 16.7% | 8.3% | 37.1% | -20.5 | -7.49 |
| 5 | short_overbought_fade | short_pdh_rejection | 32 | 15.6% | 37.2% | 33.6% | -21.6 | +nan |
| 6 | grid_booster | long_pdl_bounce | 128 | 0.0% | 0.0% | 37.1% | -37.1 | +nan |

## Per-type baseline

| Type | N | WR% | Avg PnL$ |
|---|---:|---:|---:|
| short_rally_fade | 6178 | 29.2 | +0.79 |
| long_dump_reversal | 5576 | 35.9 | +2.40 |
| grid_booster | 2616 | 0.0 | +nan |
| short_pdh_rejection | 2424 | 33.6 | +1.96 |
| long_pdl_bounce | 1863 | 37.1 | +4.97 |
| short_overbought_fade | 43 | 37.2 | -4.80 |
| long_oversold_reclaim | 12 | 8.3 | -26.57 |

## Reading the boost column

`Boost (pp)` = `WR(co)` − `max(WR(A alone), WR(B alone))`. Positive 
means the pair confirms each other; firing together has a higher win-rate 
than the better leg alone. Boost ≥ +10 pp with N ≥ 20 → mega-setup candidate.