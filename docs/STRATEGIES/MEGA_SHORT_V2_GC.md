# SHORT mega v2 — detector + grid_coordinator confluence

**Period:** 365d | **GC threshold:** score>=3 | **Window:** ±60min | **Dedup:** 4h
**Trade params:** SL=+0.8%, TP1=-2.0%, TP2=-4.0%, hold=240min

## Results (sorted by total_pnl_pct)

| combo                                       |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct | wf_pos_folds   |
|:--------------------------------------------|----:|-----:|------:|----------------:|--------------:|:---------------|
| detect_short_overbought_fade + GC_upside>=3 |  15 | 40   | 0.411 |           -4.02 |       -0.2677 | 1/4            |
| detect_short_rally_fade + GC_upside>=3      |  39 | 38.5 | 0.462 |           -9.13 |       -0.2341 | 0/4            |
| detect_short_pdh_rejection + GC_upside>=3   |  52 | 46.2 | 0.542 |           -9.23 |       -0.1775 | 0/4            |
| GC_upside>=3 ALONE (baseline)               | 170 | 20   | 0.109 |          -88.45 |       -0.5203 | 0/4            |

## ❌ No SHORT edge from GC confluence