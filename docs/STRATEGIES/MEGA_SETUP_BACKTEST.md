# Mega-setup triple backtest

**Date:** 2026-05-10
**Lookback:** 365d BTCUSDT 1m honest engine
**Window:** ±60min between constituents
**Dedup:** 4h between consecutive megas
**Trade params:** SL=-0.8%, TP1=+2.0% (2.5RR), TP2=+4.0% (5.0RR), max_hold=240min
**Fees:** maker -0.0125% IN + taker 0.075% + slip 0.02% OUT = 0.165% RT

## Constituent baselines (each detector alone)

| detector                  |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct |   n_tp |   n_sl |   n_expire |
|:--------------------------|----:|-----:|------:|----------------:|--------------:|-------:|-------:|-----------:|
| detect_long_dump_reversal | 837 | 42.3 | 0.858 |          -31.28 |       -0.0374 |    116 |    237 |        377 |
| detect_long_pdl_bounce    | 150 | 42.7 | 1.333 |           10.27 |        0.0684 |     42 |     45 |         48 |

## Mega-triple result

- Triggers found: **115**

|   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct |   n_tp |   n_sl |   n_expire |
|----:|-----:|------:|----------------:|--------------:|-------:|-------:|-----------:|
| 115 | 51.3 | 1.542 |           15.54 |        0.1351 |      8 |     24 |         83 |

## Walk-forward (4 folds)

|   fold |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct |   n_tp |   n_sl |   n_expire |
|-------:|----:|-----:|------:|----------------:|--------------:|-------:|-------:|-----------:|
|      1 |  30 | 53.3 | 1.427 |            2.62 |        0.0872 |      1 |      4 |         25 |
|      2 |  41 | 51.2 | 1.588 |            5.89 |        0.1438 |      3 |      8 |         30 |
|      3 |  26 | 46.2 | 1.553 |            4.22 |        0.1624 |      3 |      7 |         16 |
|      4 |  18 | 55.6 | 1.574 |            2.81 |        0.156  |      1 |      5 |         12 |

## SL/TP parameter sweep

Tested 4×5 = 20 combos. Top 10 by total_pnl_pct:

|   SL_pct |   TP1_RR |   TP1_pct |   n |   wr |    pf |   total_pnl_pct |   avg_pnl_pct |   n_tp |   n_sl |   n_expire |
|---------:|---------:|----------:|----:|-----:|------:|----------------:|--------------:|-------:|-------:|-----------:|
|      0.8 |     2.5  |      2    | 115 | 51.3 | 1.542 |           15.54 |        0.1351 |      8 |     24 |         83 |
|      0.8 |     2    |      1.6  | 115 | 51.3 | 1.486 |           13.94 |        0.1212 |     13 |     24 |         78 |
|      1   |     2    |      2    | 115 | 51.3 | 1.453 |           13.78 |        0.1199 |      8 |     19 |         88 |
|      0.8 |     1.5  |      1.2  | 115 | 51.3 | 1.504 |           13.65 |        0.1187 |     20 |     22 |         73 |
|      1   |     2.5  |      2.5  | 115 | 51.3 | 1.428 |           13.03 |        0.1133 |      4 |     19 |         92 |
|      1   |     1.5  |      1.5  | 115 | 51.3 | 1.438 |           12.89 |        0.1121 |     15 |     18 |         82 |
|      0.8 |     1.25 |      1    | 115 | 50.4 | 1.455 |           12.31 |        0.107  |     25 |     22 |         68 |
|      1   |     1.25 |      1.25 | 115 | 51.3 | 1.397 |           11.69 |        0.1017 |     19 |     18 |         78 |
|      1   |     1    |      1    | 115 | 50.4 | 1.385 |           10.95 |        0.0952 |     25 |     17 |         73 |
|      0.8 |     1    |      0.8  | 115 | 49.6 | 1.398 |           10.78 |        0.0937 |     32 |     22 |         61 |

**Best:** SL=0.8%, TP1_RR=2.5 (TP1=+2.0%) → PF=1.542, PnL=15.54%, N=115.0, WR=51.3%

## Verdict

✅ **STABLE: PF=1.542, 4/4 folds positive.** Triple confluence DOES give edge. Promote to live wire test (mega_setup.py is already wired).
