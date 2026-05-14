# SHORT mega-setup confluence backtest

**Date:** 2026-05-10 | **Lookback:** 365d 1m honest
**Window:** ±60min | **Dedup:** 4h
**Trade params:** SL=+0.8%, TP1=-2.0%, TP2=-4.0%, hold=240min
**Min triggers for evaluation:** 15

## Constituent baselines (each SHORT detector alone)

| detector                     |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct |
|:-----------------------------|----:|-----:|------:|----------------:|--------------:|
| detect_short_rally_fade      |  75 | 52   | 1.533 |            9.87 |        0.1316 |
| detect_short_pdh_rejection   | 212 | 29.2 | 0.558 |          -26.8  |       -0.1264 |
| detect_short_overbought_fade |  25 | 36   | 0.282 |           -5.86 |       -0.2343 |
| detect_short_mfi_multi_ga    |  35 | 37.1 | 0.954 |           -0.24 |       -0.0068 |
| detect_short_div_bos_15m     |  14 | 21.4 | 0.612 |           -1.98 |       -0.1411 |

## Confluence results (sorted by PnL)

| combo                                                |   n_constituents |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct | wf_pos_folds   |
|:-----------------------------------------------------|-----------------:|----:|-----:|------:|----------------:|--------------:|:---------------|
| detect_short_rally_fade + detect_short_pdh_rejection |                2 |  16 | 56.2 | 1.021 |             0.1 |        0.0065 | 1/4            |

## Verdict

❌ **No SHORT confluence yields edge.** Best is detect_short_rally_fade + detect_short_pdh_rejection PF=1.021 — not above 1.2 threshold.
