# Grid coordinator vs detectors — co-firing analysis

**Period:** last 90 days BTC
**Window:** ±60 min
**Grid_coordinator threshold:** score >= 3
**GC signals total:** 258

**Aligned co-firing logic:**
- LONG detector emit + grid_coordinator DOWNSIDE signal (oversold) = aligned
- SHORT detector emit + grid_coordinator UPSIDE signal (overbought) = aligned
- Mismatched direction = misaligned (signals contradict)

## Detector co-firing rates with grid_coordinator

| detector                      |   n_detector_emits |   n_gc_total |   co_aligned |   co_misaligned |   p_co_aligned_% |   p_co_misaligned_% |   uplift_factor |
|:------------------------------|-------------------:|-------------:|-------------:|----------------:|-----------------:|--------------------:|----------------:|
| detect_long_dump_reversal     |                160 |          258 |           84 |               0 |             52.5 |                 0   |            0.33 |
| detect_long_multi_divergence  |                341 |          258 |           31 |              32 |              9.1 |                 9.4 |            0.12 |
| detect_short_rally_fade       |                 21 |          258 |           17 |               0 |             81   |                 0   |            0.07 |
| detect_short_pdh_rejection    |                 30 |          258 |           12 |               0 |             40   |                 0   |            0.05 |
| detect_long_pdl_bounce        |                 20 |          258 |            6 |               0 |             30   |                 0   |            0.02 |
| detect_short_overbought_fade  |                  5 |          258 |            4 |               0 |             80   |                 0   |            0.02 |
| detect_double_bottom_setup    |                187 |          258 |            4 |              18 |              2.1 |                 9.6 |            0.02 |
| detect_long_oversold_reclaim  |                  4 |          258 |            3 |               0 |             75   |                 0   |            0.01 |
| detect_short_mfi_multi_ga     |                  9 |          258 |            2 |               0 |             22.2 |                 0   |            0.01 |
| detect_double_top_setup       |                183 |          258 |            2 |              17 |              1.1 |                 9.3 |            0.01 |
| detect_long_rsi_momentum_ga   |                 26 |          258 |            0 |              26 |              0   |               100   |            0    |
| detect_long_div_bos_confirmed |                  7 |          258 |            0 |               1 |              0   |                14.3 |            0    |
| detect_long_div_bos_15m       |                  6 |          258 |            0 |               0 |              0   |                 0   |            0    |
| detect_short_div_bos_15m      |                  1 |          258 |            0 |               0 |              0   |                 0   |            0    |

## Interpretation

- **High p_co_aligned (≥30%)** = detector usually agrees with grid_coordinator. These are naturally confirmed by GC — entry condition: detector fires AND GC shows aligned direction within ±60min.
- **High p_co_misaligned (≥30%)** = detector contradicts GC — these emissions are likely false signals (other side of market is exhausted, not entry side).
- **Low both** = detector and GC measure different things — independent signals (combining adds genuine information).