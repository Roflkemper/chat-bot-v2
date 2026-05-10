# Liquidation cluster detector backtest

**Period:** 2026-04-28 22:30:54.552000+00:00 → 2026-05-02 22:28:34.661000+00:00 (~3 days)
**Threshold:** $1M one-side / 5min, dominance ratio < 0.3
**Trade:** TP=+0.5%, SL=-0.4%, hold=60min, fees 0.165%

## Per-direction summary

| side   |   n |   n_TP |   n_SL |   n_TIMEOUT |   wr |    pf |   pnl_pct_total |   avg_pnl_pct |
|:-------|----:|-------:|-------:|------------:|-----:|------:|----------------:|--------------:|
| long   |  23 |      3 |      4 |          16 | 43.5 | 0.502 |           -1.95 |       -0.0846 |
| short  |  50 |      4 |     11 |          35 | 14   | 0.135 |          -11.34 |       -0.2268 |

## Verdict

❌ Both directions unprofitable. LONG: -1.95%, SHORT: -11.34%. Threshold/dominance/TP/SL need tuning, OR liquidations don't predict bounces in this regime.