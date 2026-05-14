# H10 parameter sweep

**Period:** 365d BTCUSDT 1m honest engine
**TP/SL/hold:** +0.5% / -0.8% / 120min
**Detection frequency:** every 60 1m bars (1h)

## Sweep results

| config              |    n |   wr |    pf |   pnl_pct |   long_n |   short_n |
|:--------------------|-----:|-----:|------:|----------:|---------:|----------:|
| A_STRICT (current)  | 5650 | 35.8 | 0.627 |   -451.68 |     2912 |      2738 |
| B_RELAXED (TZ-053a) | 1566 | 31.8 | 0.507 |   -135.71 |      757 |       809 |
| C_MEDIUM            | 4989 | 35.2 | 0.596 |   -424.81 |     2619 |      2370 |
| D_LOOSE             | 6338 | 35.8 | 0.642 |   -491.34 |     3276 |      3062 |

## Verdict

❌ Even best config gives PF=0.642. H10 doesn't work as live strategy at these params.