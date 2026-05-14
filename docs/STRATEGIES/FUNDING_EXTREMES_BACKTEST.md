# Funding Extremes Backtest — XRPUSDT

**Funding window:** 2024-05-12 00:00:00 -> 2026-05-05 08:00:00.011000 (2171 8h periods)

**Стратегия:**
- funding > +threshold (% per 8h) → SHORT (longs переплачивают)
- funding < -threshold → LONG (shorts переплачивают)
- hold N часов → close at market
- fees: 2 × 0.075% taker (in + out)
- size: $1000.0 per trade

**Sweep:**
- threshold: [0.02, 0.03, 0.05, 0.08, 0.1] (% per 8h)
- hold: [4, 8, 12, 24, 48] (hours)
- direction: ['both', 'long_only', 'short_only']
- Total combos: 75

## Топ-20 по PnL

| threshold% | hold | direction | N | PnL ($) | PF | WR% | avg ($) | DD ($) | pos folds |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 0.02 | 48 | long_only | 22 | +411 | 3.44 | 73 | +18.7 | 99 | 2/4 |
| 0.02 | 12 | long_only | 22 | +295 | 2.47 | 64 | +13.4 | 73 | 2/4 |
| 0.02 | 8 | long_only | 22 | +202 | 2.27 | 64 | +9.2 | 70 | 2/4 |
| 0.02 | 4 | long_only | 22 | +178 | 2.38 | 68 | +8.1 | 54 | 2/4 |
| 0.03 | 12 | long_only | 3 | +114 | 6.47 | 67 | +38.0 | 21 | 2/4 |
| 0.03 | 8 | long_only | 3 | +112 | 5.90 | 67 | +37.3 | 23 | 2/4 |
| 0.03 | 4 | long_only | 3 | +91 | 4.09 | 67 | +30.4 | 29 | 2/4 |
| 0.02 | 24 | long_only | 22 | +87 | 1.26 | 64 | +3.9 | 93 | 1/4 |
| 0.03 | 4 | both | 27 | +63 | 1.18 | 48 | +2.3 | 208 | 3/4 |
| 0.05 | 12 | both | 4 | +45 | 1.68 | 75 | +11.3 | 0 | 1/4 |
| 0.05 | 12 | short_only | 4 | +45 | 1.68 | 75 | +11.3 | 0 | 1/4 |
| 0.03 | 48 | long_only | 3 | +41 | 1.82 | 67 | +13.6 | 50 | 2/4 |
| 0.02 | 4 | both | 67 | +36 | 1.05 | 51 | +0.5 | 274 | 2/4 |
| 0.05 | 4 | both | 4 | +36 | 2.09 | 75 | +8.9 | 33 | 1/4 |
| 0.05 | 4 | short_only | 4 | +36 | 2.09 | 75 | +8.9 | 33 | 1/4 |
| 0.03 | 24 | long_only | 3 | +23 | 1.46 | 67 | +7.6 | 49 | 2/4 |
| 0.05 | 4 | long_only | 0 | +0 | 0.00 | 0 | +0.0 | 0 | 0/4 |
| 0.05 | 8 | long_only | 0 | +0 | 0.00 | 0 | +0.0 | 0 | 0/4 |
| 0.05 | 12 | long_only | 0 | +0 | 0.00 | 0 | +0.0 | 0 | 0/4 |
| 0.05 | 24 | long_only | 0 | +0 | 0.00 | 0 | +0.0 | 0 | 0/4 |

## Худшие 5

| threshold% | hold | direction | N | PnL ($) | PF |
|---:|---:|---|---:|---:|---:|
| 0.03 | 48 | short_only | 24 | -1,054 | 0.29 |
| 0.02 | 24 | both | 67 | -1,243 | 0.47 |
| 0.02 | 24 | short_only | 45 | -1,330 | 0.34 |
| 0.02 | 48 | both | 67 | -2,049 | 0.39 |
| 0.02 | 48 | short_only | 45 | -2,460 | 0.23 |

## Best combo per direction

### both
- threshold=**0.03%**, hold=**4h**
- N=27, PnL=**$+63**, PF=1.18, WR=48%
- Pos folds: 3/4
- Per-fold PnL: [34.0, 35.0, -51.0, 44.0]

### long_only
- threshold=**0.02%**, hold=**48h**
- N=22, PnL=**$+411**, PF=3.44, WR=73%
- Pos folds: 2/4
- Per-fold PnL: [0.0, 255.0, 0.0, 156.0]

### short_only
- threshold=**0.05%**, hold=**12h**
- N=4, PnL=**$+45**, PF=1.68, WR=75%
- Pos folds: 1/4
- Per-fold PnL: [0.0, 45.0, 0.0, 0.0]

## Verdict

⚠️ Слабый edge: best PF 3.44, но мало данных или маргинально. Нужен 2y data перед prod.

