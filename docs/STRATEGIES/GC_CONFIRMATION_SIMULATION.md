# GC-confirmation simulation impact (90d)

**Lookback:** 90d, GC threshold score>=3, ±60min window
**Hard-block list:** ['long_double_bottom', 'long_multi_divergence', 'long_rsi_momentum_ga', 'short_double_top']

Categories per emit:
- **aligned**: GC confirms direction → +15% confidence boost
- **misaligned**: GC contradicts → if in hard-block list = BLOCKED, else -30% conf
- **neutral**: GC has no strong signal → pass-through
- **no_gc_data**: emit outside GC time range (rare)

## Per-detector impact

| detector                      | setup_type             |   total |   aligned_% |   misaligned_% |   neutral_% |   no_gc_% | hard_block_list   |   would_block |   would_keep |   keep_rate_% |
|:------------------------------|:-----------------------|--------:|------------:|---------------:|------------:|----------:|:------------------|--------------:|-------------:|--------------:|
| detect_long_multi_divergence  | long_multi_divergence  |     341 |         6.2 |            7.6 |        86.2 |         0 | True              |            26 |          315 |          92.4 |
| detect_double_bottom_setup    | long_double_bottom     |     187 |         8.6 |            2.1 |        89.3 |         0 | True              |             4 |          183 |          97.9 |
| detect_double_top_setup       | short_double_top       |     183 |         1.1 |            6.6 |        92.3 |         0 | True              |            12 |          171 |          93.4 |
| detect_long_dump_reversal     | long_dump_reversal     |     160 |        39.4 |            0   |        60.6 |         0 | False             |             0 |          160 |         100   |
| detect_short_pdh_rejection    | short_pdh_rejection    |      30 |        33.3 |            0   |        66.7 |         0 | False             |             0 |           30 |         100   |
| detect_long_rsi_momentum_ga   | long_rsi_momentum_ga   |      26 |         0   |           80.8 |        19.2 |         0 | True              |            21 |            5 |          19.2 |
| detect_short_rally_fade       | short_rally_fade       |      21 |        66.7 |            0   |        33.3 |         0 | False             |             0 |           21 |         100   |
| detect_long_pdl_bounce        | long_pdl_bounce        |      20 |        20   |            0   |        80   |         0 | False             |             0 |           20 |         100   |
| detect_short_mfi_multi_ga     | short_mfi_multi_ga     |       7 |        28.6 |            0   |        71.4 |         0 | False             |             0 |            7 |         100   |
| detect_long_div_bos_confirmed | long_div_bos_confirmed |       7 |         0   |            0   |       100   |         0 | False             |             0 |            7 |         100   |
| detect_long_div_bos_15m       | long_div_bos_15m       |       6 |         0   |            0   |       100   |         0 | False             |             0 |            6 |         100   |
| detect_short_overbought_fade  | short_overbought_fade  |       5 |        60   |            0   |        40   |         0 | False             |             0 |            5 |         100   |
| detect_long_oversold_reclaim  | long_oversold_reclaim  |       4 |        75   |            0   |        25   |         0 | False             |             0 |            4 |         100   |
| detect_short_div_bos_15m      | short_div_bos_15m      |       1 |         0   |            0   |       100   |         0 | False             |             0 |            1 |         100   |

## Aggregate impact

- **Total emits across all detectors:** 998
- **Hard-blocked by GC (multi_divergence + double_top/bottom misaligned):** 63
- **Aligned (boosted):** ~137
- **Suppression rate:** 6.3% of all signals filtered out