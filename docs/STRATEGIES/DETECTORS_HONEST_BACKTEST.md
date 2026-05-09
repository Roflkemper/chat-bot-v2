# Detectors honest backtest — 2026-05-09

**Engine:** intra-bar SL/TP simulator on 1m data
**Fee model:** maker rebate -0.0125% IN + taker 0.075% OUT + 0.02% slippage
**Period:** last 1,174,306 1m bars (~815 days)
**Folds:** 4 × ~293,576 bars

## Verdicts

| Detector | N total | Avg PF | Pos folds | Total PnL | Verdict |
|---|---:|---:|:---:|---:|:---:|
| `detect_long_rsi_momentum_ga` | 872 | 1.03 | 0/4 | $+128 | **OVERFIT** |
| `detect_long_pdl_bounce` | 1178 | 1.05 | 0/4 | $+12 | **OVERFIT** |
| `detect_long_div_bos_confirmed` | 204 | 1.05 | 1/4 | $-3 | **OVERFIT** |
| `detect_short_mfi_multi_ga` | 52 | 1.35 | 0/4 | $-62 | **OVERFIT** |
| `detect_long_div_bos_15m` | 223 | 0.86 | 1/4 | $-175 | **OVERFIT** |
| `detect_short_div_bos_15m` | 167 | 0.7 | 1/4 | $-250 | **OVERFIT** |
| `detect_long_oversold_reclaim` | 99 | 0.3 | 0/4 | $-326 | **OVERFIT** |
| `detect_short_overbought_fade` | 216 | 0.47 | 0/4 | $-410 | **OVERFIT** |
| `detect_short_pdh_rejection` | 1687 | 0.9 | 0/4 | $-648 | **OVERFIT** |
| `detect_double_top_setup` | 6244 | 0.74 | 0/4 | $-5,034 | **OVERFIT** |
| `detect_long_dump_reversal` | 6704 | 0.7 | 0/4 | $-6,392 | **OVERFIT** |
| `detect_double_bottom_setup` | 6976 | 0.66 | 0/4 | $-7,321 | **OVERFIT** |
| `detect_short_rally_fade` | 8469 | 0.64 | 0/4 | $-8,431 | **OVERFIT** |
| `detect_long_multi_divergence` | 11372 | 0.68 | 0/4 | $-12,371 | **OVERFIT** |

## Per-fold details

| Detector | Fold | N | WR% | PF | Total PnL | Avg PnL |
|---|:---:|---:|---:|---:|---:|---:|
| `detect_long_dump_reversal` | 1 | 1534 | 14.3 | 0.61 | $-2,135 | $-1.39 |
| `detect_long_dump_reversal` | 2 | 1495 | 13.8 | 0.7 | $-1,489 | $-1.00 |
| `detect_long_dump_reversal` | 3 | 1793 | 7.9 | 0.8 | $-816 | $-0.46 |
| `detect_long_dump_reversal` | 4 | 1882 | 13.7 | 0.67 | $-1,952 | $-1.04 |
| `detect_long_pdl_bounce` | 1 | 225 | 31.1 | 1.18 | $+105 | $+0.46 |
| `detect_long_pdl_bounce` | 2 | 239 | 37.2 | 1.35 | $+199 | $+0.83 |
| `detect_long_pdl_bounce` | 3 | 412 | 17.7 | 0.78 | $-197 | $-0.48 |
| `detect_long_pdl_bounce` | 4 | 302 | 21.9 | 0.89 | $-95 | $-0.31 |
| `detect_long_oversold_reclaim` | 1 | 25 | 8.0 | 0.47 | $-69 | $-2.75 |
| `detect_long_oversold_reclaim` | 2 | 23 | 13.0 | 0.28 | $-84 | $-3.67 |
| `detect_long_oversold_reclaim` | 3 | 14 | 14.3 | 0.2 | $-47 | $-3.32 |
| `detect_long_oversold_reclaim` | 4 | 37 | 8.1 | 0.26 | $-126 | $-3.42 |
| `detect_short_rally_fade` | 1 | 1800 | 12.7 | 0.69 | $-1,624 | $-0.90 |
| `detect_short_rally_fade` | 2 | 2122 | 12.6 | 0.77 | $-1,302 | $-0.61 |
| `detect_short_rally_fade` | 3 | 2587 | 5.5 | 0.54 | $-2,786 | $-1.08 |
| `detect_short_rally_fade` | 4 | 1960 | 9.3 | 0.54 | $-2,718 | $-1.39 |
| `detect_short_pdh_rejection` | 1 | 290 | 33.4 | 1.39 | $+262 | $+0.90 |
| `detect_short_pdh_rejection` | 2 | 385 | 25.2 | 0.66 | $-374 | $-0.97 |
| `detect_short_pdh_rejection` | 3 | 640 | 20.3 | 0.76 | $-341 | $-0.53 |
| `detect_short_pdh_rejection` | 4 | 372 | 19.6 | 0.8 | $-195 | $-0.53 |
| `detect_short_overbought_fade` | 1 | 59 | 23.7 | 0.77 | $-54 | $-0.91 |
| `detect_short_overbought_fade` | 2 | 54 | 14.8 | 0.62 | $-73 | $-1.36 |
| `detect_short_overbought_fade` | 3 | 60 | 15.0 | 0.4 | $-108 | $-1.80 |
| `detect_short_overbought_fade` | 4 | 43 | 9.3 | 0.1 | $-175 | $-4.07 |
| `detect_double_bottom_setup` | 1 | 1484 | 12.6 | 0.55 | $-2,443 | $-1.65 |
| `detect_double_bottom_setup` | 2 | 1872 | 9.1 | 0.79 | $-966 | $-0.52 |
| `detect_double_bottom_setup` | 3 | 1768 | 8.6 | 0.62 | $-1,890 | $-1.07 |
| `detect_double_bottom_setup` | 4 | 1852 | 13.2 | 0.66 | $-2,022 | $-1.09 |
| `detect_double_top_setup` | 1 | 1800 | 16.6 | 0.88 | $-637 | $-0.35 |
| `detect_double_top_setup` | 2 | 1380 | 15.4 | 0.66 | $-1,851 | $-1.34 |
| `detect_double_top_setup` | 3 | 1628 | 11.7 | 0.69 | $-1,333 | $-0.82 |
| `detect_double_top_setup` | 4 | 1436 | 16.9 | 0.73 | $-1,212 | $-0.84 |
| `detect_long_rsi_momentum_ga` | 1 | 212 | 38.2 | 1.16 | $+259 | $+1.22 |
| `detect_long_rsi_momentum_ga` | 2 | 224 | 39.7 | 0.93 | $-112 | $-0.50 |
| `detect_long_rsi_momentum_ga` | 3 | 232 | 27.6 | 1.29 | $+409 | $+1.76 |
| `detect_long_rsi_momentum_ga` | 4 | 204 | 27.9 | 0.75 | $-428 | $-2.10 |
| `detect_short_mfi_multi_ga` | 1 | 8 | 0.0 | 0.39 | $-25 | $-3.14 |
| `detect_short_mfi_multi_ga` | 2 | 12 | 0.0 | 4.51 | $+11 | $+0.93 |
| `detect_short_mfi_multi_ga` | 3 | 16 | 0.0 | 0.49 | $-10 | $-0.62 |
| `detect_short_mfi_multi_ga` | 4 | 16 | 0.0 | 0.0 | $-38 | $-2.35 |
| `detect_long_div_bos_confirmed` | 1 | 40 | 25.0 | 2.08 | $+199 | $+4.97 |
| `detect_long_div_bos_confirmed` | 2 | 44 | 0.0 | 0.4 | $-140 | $-3.17 |
| `detect_long_div_bos_confirmed` | 3 | 52 | 0.0 | 0.53 | $-171 | $-3.29 |
| `detect_long_div_bos_confirmed` | 4 | 68 | 27.9 | 1.2 | $+109 | $+1.60 |
| `detect_long_div_bos_15m` | 1 | 43 | 16.3 | 1.52 | $+63 | $+1.48 |
| `detect_long_div_bos_15m` | 2 | 55 | 1.8 | 0.59 | $-98 | $-1.79 |
| `detect_long_div_bos_15m` | 3 | 72 | 0.0 | 0.72 | $-50 | $-0.70 |
| `detect_long_div_bos_15m` | 4 | 53 | 5.7 | 0.6 | $-90 | $-1.69 |
| `detect_short_div_bos_15m` | 1 | 39 | 17.9 | 0.59 | $-71 | $-1.83 |
| `detect_short_div_bos_15m` | 2 | 45 | 8.9 | 0.33 | $-135 | $-2.99 |
| `detect_short_div_bos_15m` | 3 | 41 | 0.0 | 0.28 | $-96 | $-2.34 |
| `detect_short_div_bos_15m` | 4 | 42 | 11.9 | 1.62 | $+52 | $+1.24 |
| `detect_long_multi_divergence` | 1 | 2664 | 20.8 | 0.58 | $-4,131 | $-1.55 |
| `detect_long_multi_divergence` | 2 | 2960 | 19.9 | 0.67 | $-3,822 | $-1.29 |
| `detect_long_multi_divergence` | 3 | 2508 | 10.0 | 0.67 | $-2,368 | $-0.94 |
| `detect_long_multi_divergence` | 4 | 3240 | 20.8 | 0.81 | $-2,050 | $-0.63 |
