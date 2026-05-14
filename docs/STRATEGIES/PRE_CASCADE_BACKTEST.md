# Pre-cascade alert backtest

**Period:** 501 1h ticks (28d binance_combined)
**Signal:** |funding|>=0.005% AND oi_change>=0.3% AND (LS>=1.05 or LS<=0.55)
**Success:** ±0.5% in expected direction within horizon

## Signal counts

- Total: 3
- short cascade expected: 0
- long cascade expected: 3

## Verdict matrix

| direction   |   horizon_min |   n |   TRUE |   FALSE |   NEUTRAL |   precision_% |   avg_move_% |
|:------------|--------------:|----:|-------:|--------:|----------:|--------------:|-------------:|
| long        |            15 |   3 |      0 |       0 |         3 |             0 |        0.043 |
| long        |            30 |   3 |      0 |       0 |         3 |             0 |       -0.064 |
| long        |            60 |   3 |      0 |       0 |         3 |             0 |       -0.052 |
| long        |           120 |   3 |      0 |       0 |         3 |             0 |        0.018 |

## Verdict

🟡 Best is long @ 15m: 0% on N=3. Below 60% precision threshold.
