# P-15 5m TF experiment

**Date:** 2026-05-10
**Lookback:** 30 days BTC
**Engine:** simulate_p15_harvest (honest fees 0.165% RT)

## Results

| config                           | dir   |   n |   wr% |   pf |   pnl$ |   avg$/trade |   max_dd$ |
|:---------------------------------|:------|----:|------:|-----:|-------:|-------------:|----------:|
| 15m baseline (R0.3 K1.0 dd3)     | short | 118 |  25.4 | 4.36 | 995.75 |        8.439 |    -39.95 |
| 15m baseline (R0.3 K1.0 dd3)     | long  |  21 |  33.3 | 4.99 | 169.14 |        8.054 |    -38.36 |
| 5m scaled (R0.1 K0.3 dd1.5)      | short | 131 |  19.1 | 2.24 | 316.72 |        2.418 |    -81.66 |
| 5m scaled (R0.1 K0.3 dd1.5)      | long  |  25 |  20   | 2.45 |  68.96 |        2.758 |    -36.99 |
| 5m conservative (R0.15 K0.5 dd2) | short | 120 |  22.5 | 3.2  | 494.43 |        4.12  |    -35.5  |
| 5m conservative (R0.15 K0.5 dd2) | long  |  25 |  24   | 3.44 | 109.92 |        4.397 |    -32.75 |
| 5m wider (R0.2 K0.6 dd2.5)       | short | 120 |  22.5 | 3.84 | 592.08 |        4.934 |    -32.66 |
| 5m wider (R0.2 K0.6 dd2.5)       | long  |  25 |  24   | 4.1  | 129.14 |        5.166 |    -31.02 |

## Verdict (2026-05-10)

**KEEP 15m. 5m is NOT better.**

15m baseline combined PnL (30d): **+$1165**, PF 4.7, avg $8.2/trade.
Best 5m variant (R=0.2 wider): **+$721** — only 62% of 15m at same risk.
Avg $/trade on 5m: $5.0 vs $8.2 on 15m → fees eat 38% of edge.
PF on 5m drops from 4.7 to 4.0.

**Conclusion:** higher cycle frequency on 5m does NOT compensate for the
lower per-trade edge. Hypothesis "5m gives +$200k/2y" rejected.

**Action:** keep `P15_TF=15m` in production. Do not attempt 5m migration.

## Closed: 2026-05-10
