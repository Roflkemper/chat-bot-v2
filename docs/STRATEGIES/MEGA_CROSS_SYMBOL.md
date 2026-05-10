# Cross-symbol mega-pair backtest

**Period:** 365d | **Constituents:** dump_reversal + pdl_bounce
**Trade params:** SL=-0.8% TP1=+2.0% TP2=+4.0% hold=240min

## Per-symbol summary

| symbol   |   n_triggers |   WR |    PF |   total_pnl_pct | wf_pos_folds   | verdict   |
|:---------|-------------:|-----:|------:|----------------:|:---------------|:----------|
| BTCUSDT  |          115 | 51.3 | 1.542 |           15.54 | 4/4            | STABLE    |
| ETHUSDT  |           54 | 44.4 | 0.932 |           -1.5  | 2/4            | OVERFIT   |
| XRPUSDT  |          100 | 48   | 1.437 |           15.27 | 1/4            | OVERFIT   |

## Walk-forward folds per symbol

|   fold |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct | symbol   |
|-------:|----:|-----:|------:|----------------:|--------------:|:---------|
|      1 |  30 | 53.3 | 1.427 |            2.62 |        0.0872 | BTCUSDT  |
|      2 |  41 | 51.2 | 1.588 |            5.89 |        0.1438 | BTCUSDT  |
|      3 |  26 | 46.2 | 1.553 |            4.22 |        0.1624 | BTCUSDT  |
|      4 |  18 | 55.6 | 1.574 |            2.81 |        0.156  | BTCUSDT  |
|      1 |  11 | 45.5 | 1.429 |            1.77 |        0.1613 | ETHUSDT  |
|      2 |  18 | 33.3 | 0.281 |           -5.93 |       -0.3295 | ETHUSDT  |
|      3 |  11 | 36.4 | 0.882 |           -0.73 |       -0.0662 | ETHUSDT  |
|      4 |  14 | 64.3 | 1.918 |            3.38 |        0.2417 | ETHUSDT  |
|      1 |  13 | 38.5 | 1.09  |            0.51 |        0.0391 | XRPUSDT  |
|      2 |  29 | 41.4 | 0.697 |           -3.23 |       -0.1113 | XRPUSDT  |
|      3 |  24 | 50   | 1.262 |            2.49 |        0.1039 | XRPUSDT  |
|      4 |  34 | 55.9 | 2.691 |           15.5  |        0.4558 | XRPUSDT  |

## Verdict

🟡 **Only BTCUSDT is STABLE.** Mega-pair edge is BTC-specific so far.