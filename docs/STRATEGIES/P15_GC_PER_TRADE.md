# P-15 + grid_coordinator per-trade bucketing

**Period:** 365d | **GC threshold:** score>=3
**Total trades:** LONG=1094, SHORT=1012

## PnL by GC bucket at entry time

| direction   | bucket           |   n_trades |   win_rate_% |   total_pnl_usd |   avg_pnl_usd |
|:------------|:-----------------|-----------:|-------------:|----------------:|--------------:|
| long        | neutral          |        957 |         20.5 |            6946 |          7.26 |
| long        | aligned (down≥3) |        137 |          9.5 |             269 |          1.96 |
| short       | neutral          |        943 |         21.8 |            7550 |          8.01 |
| short       | aligned (up≥3)   |         69 |         11.6 |             350 |          5.07 |

## Verdict
