# Strategy Leaderboard — walk-forward verdict

**Source:** `data/historical_setups_y1_2026-04-30.parquet` (18712 setups)
**Period:** 2025-05-01 → 2026-04-29
**Folds:** 4 × ~90d each
**Verdict thresholds:** PF≥1.5 AND N≥10 per fold; ≥3/4 → STABLE, ≥2/4 → MARGINAL, else OVERFIT

## Summary

| Detector | All N | All WR% | All PF | Avg PnL$ | Positive folds | Verdict |
|---|---:|---:|---:|---:|:---:|:---:|
| `long_pdl_bounce` | 1863 | 37.1 | 1.55 | +4.97 | 3/4 | **STABLE** |
| `long_dump_reversal` | 5576 | 35.9 | 1.23 | +2.40 | 1/4 | **OVERFIT** |
| `short_pdh_rejection` | 2424 | 33.6 | 1.20 | +1.96 | 1/4 | **OVERFIT** |
| `short_rally_fade` | 6178 | 29.2 | 1.08 | +0.79 | 0/4 | **OVERFIT** |
| `short_overbought_fade` | 43 | 37.2 | 0.60 | -4.80 | 1/4 | **OVERFIT** |
| `grid_booster` | 2616 | 0.0 | 0.00 | +0.00 | 0/4 | **OVERFIT** |
| `long_oversold_reclaim` | 12 | 8.3 | 0.01 | -26.57 | 0/4 | **TOO_FEW_SAMPLES** |

## Per-detector fold breakdown

### `long_pdl_bounce` — STABLE

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 467 | 39.0 | 1.60 | +5.18 |
| 2 | 620 | 34.5 | 1.42 | +4.05 |
| 3 | 399 | 37.1 | 1.60 | +5.96 |
| 4 | 376 | 39.4 | 1.66 | +5.00 |

### `long_dump_reversal` — OVERFIT

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 812 | 38.7 | 1.51 | +4.98 |
| 2 | 1429 | 34.7 | 1.22 | +2.42 |
| 3 | 1437 | 38.8 | 1.31 | +3.41 |
| 4 | 1898 | 33.5 | 1.05 | +0.53 |

### `short_pdh_rejection` — OVERFIT

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 793 | 27.2 | 1.04 | +0.52 |
| 2 | 857 | 33.0 | 1.02 | +0.23 |
| 3 | 449 | 40.5 | 1.84 | +6.23 |
| 4 | 325 | 40.9 | 1.42 | +3.34 |

### `short_rally_fade` — OVERFIT

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 1621 | 26.0 | 0.94 | -0.62 |
| 2 | 1792 | 26.6 | 1.20 | +1.66 |
| 3 | 1289 | 36.1 | 1.40 | +3.27 |
| 4 | 1476 | 30.1 | 0.93 | -0.73 |

### `short_overbought_fade` — OVERFIT

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 16 | 68.8 | 3.34 | +10.96 |
| 2 | 18 | 16.7 | 0.16 | -13.39 |
| 3 | 7 | 14.3 | 0.07 | -18.65 |
| 4 | 2 | 50.0 | 0.50 | -5.04 |

### `grid_booster` — OVERFIT

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 588 | 0.0 | 0.00 | +0.00 |
| 2 | 648 | 0.0 | 0.00 | +0.00 |
| 3 | 708 | 0.0 | 0.00 | +0.00 |
| 4 | 672 | 0.0 | 0.00 | +0.00 |

### `long_oversold_reclaim` — TOO_FEW_SAMPLES

| Fold | N | WR% | PF | Avg PnL$ |
|---|---:|---:|---:|---:|
| 1 | 1 | 0.0 | 0.00 | -22.07 |
| 2 | 3 | 0.0 | 0.00 | -30.84 |
| 3 | 5 | 0.0 | 0.00 | -33.04 |
| 4 | 3 | 33.3 | 0.05 | -13.02 |

## Verdict actions

### OVERFIT — candidates for **disable**:
  - `long_dump_reversal` (only 1/4 folds positive, all-period PF=1.23)
  - `short_pdh_rejection` (only 1/4 folds positive, all-period PF=1.20)
  - `short_rally_fade` (only 0/4 folds positive, all-period PF=1.08)
  - `short_overbought_fade` (only 1/4 folds positive, all-period PF=0.60)
  - `grid_booster` (only 0/4 folds positive, all-period PF=0.00)

### STABLE — keep + monitor:
  - `long_pdl_bounce` (PF=1.55, N=1863)
