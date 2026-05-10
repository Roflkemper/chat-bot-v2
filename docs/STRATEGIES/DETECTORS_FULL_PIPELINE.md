# Full pipeline: 14 detectors (filter+conf+GC) on 730d

**Pipeline:** raw emit → confirmation gate (+0.1% drift in 10min) → GC filter (HARD_BLOCK list drops misaligned)
**HARD_BLOCK:** ['long_double_bottom', 'long_multi_divergence', 'long_rsi_momentum_ga', 'short_double_top']

## Results sorted by pipeline_pnl%

| detector                      |   baseline_n |   baseline_pf |   baseline_pnl% |   after_conf |   after_gc |   pipeline_n |   pipeline_pf |   pipeline_pnl% | wf_pos_folds   | verdict   |
|:------------------------------|-------------:|--------------:|----------------:|-------------:|-----------:|-------------:|--------------:|----------------:|:---------------|:----------|
| detect_short_rally_fade       |          167 |         0.959 |           -2.11 |          112 |        112 |          112 |         1.456 |           11.95 | 2/4            | MARGINAL  |
| detect_long_pdl_bounce        |          280 |         1.151 |            9.39 |          231 |        231 |          231 |         1.153 |            8    | 1/4            | OVERFIT   |
| detect_long_rsi_momentum_ga   |          190 |         1.247 |           30.75 |           27 |          5 |            5 |         7.522 |            5.97 | 0/4            | OVERFIT   |
| detect_long_multi_divergence  |         2599 |         0.752 |         -218.58 |          241 |        228 |          228 |         1.062 |            5.65 | 1/4            | OVERFIT   |
| detect_short_pdh_rejection    |           49 |         1.312 |            3.6  |           42 |         42 |           42 |         1.563 |            4.86 | 2/4            | MARGINAL  |
| detect_double_bottom_setup    |         1545 |         0.69  |         -147.22 |          100 |        100 |          100 |         1.062 |            1.9  | 1/4            | OVERFIT   |
| detect_short_overbought_fade  |           43 |         0.309 |          -10.43 |            9 |          9 |            9 |         2.206 |            1.43 | 0/4            | OVERFIT   |
| detect_short_mfi_multi_ga     |           51 |         0.758 |           -2.6  |           10 |         10 |           10 |         0.827 |           -0.4  | 0/4            | OVERFIT   |
| detect_long_div_bos_15m       |           49 |         0.689 |           -5.03 |            1 |          1 |            1 |         0     |           -1.08 | 0/4            | OVERFIT   |
| detect_long_oversold_reclaim  |           24 |         0.183 |          -11.71 |            2 |          2 |            2 |         0     |           -1.74 | 0/4            | OVERFIT   |
| detect_long_div_bos_confirmed |           47 |         0.939 |           -1.85 |            3 |          3 |            3 |         0     |           -3.7  | 0/4            | OVERFIT   |
| detect_short_div_bos_15m      |           31 |         0.306 |          -10.06 |            4 |          4 |            4 |         0     |           -4.11 | 0/4            | OVERFIT   |
| detect_double_top_setup       |         1350 |         0.735 |         -117.92 |           98 |         98 |           98 |         0.904 |           -4.22 | 1/4            | OVERFIT   |
| detect_long_dump_reversal     |         1568 |         0.827 |          -77.6  |         1299 |       1299 |         1299 |         0.904 |          -33.04 | 0/4            | OVERFIT   |

## Verdict summary

- STABLE: 0 ([])
- MARGINAL: 2 (['detect_short_rally_fade', 'detect_short_pdh_rejection'])
- OVERFIT: 12 (['detect_long_pdl_bounce', 'detect_long_rsi_momentum_ga', 'detect_long_multi_divergence', 'detect_double_bottom_setup', 'detect_short_overbought_fade', 'detect_short_mfi_multi_ga', 'detect_long_div_bos_15m', 'detect_long_oversold_reclaim', 'detect_long_div_bos_confirmed', 'detect_short_div_bos_15m', 'detect_double_top_setup', 'detect_long_dump_reversal'])
