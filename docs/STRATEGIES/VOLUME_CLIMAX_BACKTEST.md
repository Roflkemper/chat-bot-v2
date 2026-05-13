# Volume Climax Backtest — BTCUSDT 2y

**Стратегия:**
- LONG: vol_z >= threshold AND red candle AND close in lower 30% of range (capitulation low)
- SHORT: vol_z >= threshold AND green candle AND close in upper 30% of range (blow-off top)
- Hold N hours, market exit. Cooldown 4h per direction.
- fees: 2 × 0.075% taker. size: $1000.0.

**Sweep:**
- timeframes: ['1h', '15m']
- threshold (sigmas): [2.0, 2.5, 3.0, 3.5]
- hold_hours: [2, 4, 6, 12, 24]
- lookback (bars): [20, 50, 100]
- direction: ['both', 'long_only', 'short_only']
- Total combos: 360

## Топ-25 по PnL

| tf | z | hold | lb | dir | N | PnL ($) | PF | WR% | avg | DD | pos |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 15m | 2.5 | 24 | 100 | long_only | 579 | +385 | 1.07 | 51 | +0.7 | 654 | 1/4 |
| 15m | 2.0 | 24 | 100 | long_only | 758 | +290 | 1.04 | 50 | +0.4 | 883 | 2/4 |
| 15m | 2.0 | 24 | 50 | long_only | 944 | +158 | 1.02 | 50 | +0.2 | 914 | 2/4 |
| 1h | 3.0 | 24 | 20 | short_only | 147 | +123 | 1.11 | 54 | +0.8 | 205 | 3/4 |
| 1h | 2.5 | 24 | 50 | long_only | 228 | +107 | 1.05 | 50 | +0.5 | 422 | 2/4 |
| 1h | 2.5 | 24 | 100 | long_only | 195 | +70 | 1.04 | 50 | +0.4 | 446 | 2/4 |
| 1h | 3.0 | 24 | 50 | long_only | 175 | +53 | 1.03 | 49 | +0.3 | 345 | 2/4 |
| 1h | 2.0 | 24 | 100 | long_only | 260 | +23 | 1.01 | 48 | +0.1 | 567 | 2/4 |
| 1h | 2.0 | 24 | 20 | long_only | 394 | +19 | 1.00 | 51 | +0.0 | 787 | 2/4 |
| 1h | 3.5 | 24 | 20 | short_only | 87 | -17 | 0.98 | 53 | -0.2 | 223 | 2/4 |
| 1h | 3.0 | 24 | 100 | long_only | 126 | -26 | 0.98 | 52 | -0.2 | 284 | 2/4 |
| 15m | 3.5 | 24 | 100 | long_only | 365 | -28 | 0.99 | 48 | -0.1 | 513 | 2/4 |
| 1h | 2.5 | 24 | 20 | long_only | 280 | -34 | 0.99 | 49 | -0.1 | 413 | 1/4 |
| 1h | 2.5 | 12 | 100 | long_only | 195 | -41 | 0.98 | 49 | -0.2 | 333 | 2/4 |
| 1h | 3.5 | 2 | 20 | long_only | 83 | -62 | 0.83 | 42 | -0.7 | 140 | 1/4 |
| 1h | 3.5 | 6 | 100 | long_only | 90 | -67 | 0.91 | 47 | -0.7 | 169 | 2/4 |
| 15m | 2.5 | 24 | 20 | long_only | 847 | -87 | 0.99 | 51 | -0.1 | 1,133 | 2/4 |
| 1h | 3.5 | 4 | 20 | long_only | 83 | -93 | 0.79 | 45 | -1.1 | 199 | 2/4 |
| 1h | 3.0 | 6 | 50 | long_only | 175 | -99 | 0.91 | 47 | -0.6 | 225 | 1/4 |
| 1h | 3.5 | 2 | 100 | long_only | 90 | -105 | 0.78 | 42 | -1.2 | 127 | 1/4 |
| 1h | 3.0 | 2 | 20 | short_only | 147 | -108 | 0.81 | 46 | -0.7 | 141 | 1/4 |
| 1h | 3.5 | 4 | 100 | long_only | 90 | -111 | 0.83 | 47 | -1.2 | 150 | 1/4 |
| 1h | 2.5 | 6 | 50 | long_only | 228 | -130 | 0.91 | 47 | -0.6 | 284 | 2/4 |
| 1h | 2.0 | 6 | 100 | short_only | 273 | -130 | 0.93 | 45 | -0.5 | 319 | 1/4 |
| 1h | 2.5 | 6 | 100 | long_only | 195 | -139 | 0.89 | 50 | -0.7 | 241 | 1/4 |

## Худшие 5

| tf | z | hold | lb | dir | N | PnL ($) | PF |
|---|---:|---:|---:|---|---:|---:|---:|
| 15m | 2.0 | 4 | 20 | both | 2316 | -3,379 | 0.70 |
| 15m | 2.0 | 2 | 20 | both | 2317 | -3,397 | 0.61 |
| 15m | 2.5 | 12 | 20 | both | 1686 | -3,490 | 0.74 |
| 15m | 2.0 | 6 | 20 | both | 2315 | -3,692 | 0.72 |
| 15m | 2.0 | 12 | 20 | both | 2313 | -3,821 | 0.78 |

## Best combo per direction (filtered: PF>1, pos folds >=3)

### both
Нет комбинаций с PF>1 и 3+/4 pos folds.

### long_only
Нет комбинаций с PF>1 и 3+/4 pos folds.

### short_only
- tf=1h, z=3.0, hold=24h, lookback=20
- N=147, PnL=**$+123**, PF=1.11, WR=54%
- Pos folds: 3/4
- Per-fold PnL: [48.0, 133.0, -64.0, 7.0]


## Verdict

⚠️ Слабый edge: best PF 1.07, N=579. Possibly weak/marginal.

