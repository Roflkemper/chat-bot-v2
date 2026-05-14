# Funding Flip Backtest — 3 symbols, 2y

**Стратегия:**
- positive→negative flip (longs пр overpaying, then shorts paying): LONG entry
- negative→positive flip: SHORT entry
- both rates must |exceed| threshold (strong flip)
- size: $1000.0, fees: 2 × 0.075% taker

**Sweep:** thresholds=[0.001, 0.005, 0.01, 0.02], holds=[8, 24, 48, 72], directions=['both', 'long_only', 'short_only'], symbols=['BTCUSDT', 'ETHUSDT', 'XRPUSDT']. Total combos: 144

## Top-25 across all symbols by PnL

| symbol | flip% | hold | dir | N | PnL ($) | PF | WR% | avg | DD | pos |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| XRPUSDT | 0.001 | 48 | long_only | 209 | +949 | 1.27 | 50 | +4.5 | 707 | 3/4 |
| XRPUSDT | 0.001 | 24 | long_only | 209 | +538 | 1.20 | 52 | +2.6 | 414 | 3/4 |
| XRPUSDT | 0.005 | 72 | short_only | 49 | +388 | 1.41 | 51 | +7.9 | 544 | 3/4 |
| XRPUSDT | 0.001 | 24 | both | 422 | +363 | 1.06 | 52 | +0.9 | 500 | 3/4 |
| ETHUSDT | 0.001 | 24 | short_only | 102 | +354 | 1.32 | 54 | +3.5 | 195 | 3/4 |
| BTCUSDT | 0.001 | 72 | long_only | 97 | +325 | 1.24 | 51 | +3.4 | 310 | 4/4 |
| XRPUSDT | 0.001 | 48 | both | 422 | +284 | 1.03 | 52 | +0.7 | 517 | 3/4 |
| XRPUSDT | 0.001 | 72 | long_only | 209 | +284 | 1.06 | 47 | +1.4 | 1,681 | 3/4 |
| BTCUSDT | 0.001 | 48 | long_only | 97 | +281 | 1.24 | 53 | +2.9 | 250 | 4/4 |
| ETHUSDT | 0.005 | 72 | long_only | 7 | +240 | 7.09 | 57 | +34.2 | 19 | 4/4 |
| BTCUSDT | 0.001 | 72 | both | 196 | +233 | 1.08 | 51 | +1.2 | 291 | 3/4 |
| XRPUSDT | 0.005 | 72 | both | 93 | +209 | 1.09 | 46 | +2.2 | 676 | 2/4 |
| ETHUSDT | 0.005 | 72 | both | 16 | +208 | 1.86 | 50 | +13.0 | 191 | 3/4 |
| ETHUSDT | 0.005 | 24 | both | 16 | +188 | 2.69 | 56 | +11.7 | 80 | 3/4 |
| ETHUSDT | 0.005 | 48 | long_only | 7 | +181 | 8.59 | 71 | +25.9 | 14 | 3/4 |
| ETHUSDT | 0.005 | 48 | both | 16 | +178 | 1.92 | 62 | +11.2 | 123 | 3/4 |
| BTCUSDT | 0.001 | 24 | long_only | 97 | +118 | 1.13 | 48 | +1.2 | 163 | 3/4 |
| ETHUSDT | 0.005 | 24 | short_only | 9 | +107 | 2.18 | 44 | +11.9 | 47 | 2/4 |
| ETHUSDT | 0.005 | 24 | long_only | 7 | +80 | 5.10 | 71 | +11.5 | 18 | 4/4 |
| XRPUSDT | 0.01 | 48 | both | 1 | +60 | 999.00 | 100 | +60.3 | 0 | 1/4 |
| XRPUSDT | 0.01 | 48 | long_only | 1 | +60 | 999.00 | 100 | +60.3 | 0 | 1/4 |
| BTCUSDT | 0.005 | 72 | long_only | 5 | +56 | 4.54 | 80 | +11.2 | 16 | 2/4 |
| XRPUSDT | 0.005 | 24 | short_only | 49 | +48 | 1.07 | 57 | +1.0 | 435 | 2/4 |
| ETHUSDT | 0.005 | 8 | both | 16 | +35 | 1.42 | 56 | +2.2 | 48 | 3/4 |
| ETHUSDT | 0.005 | 8 | short_only | 9 | +26 | 1.64 | 67 | +2.9 | 35 | 2/4 |

## Best per symbol (filtered: PF>1.5, N>=20, pos>=3)

### BTCUSDT
_No combo with PF>1.5, N>=20, 3+/4 pos folds._

### ETHUSDT
_No combo with PF>1.5, N>=20, 3+/4 pos folds._

### XRPUSDT
_No combo with PF>1.5, N>=20, 3+/4 pos folds._


## Verdict

❌ Ни одна комбинация не прошла фильтр PF≥1.5, N≥20, 3+/4 фолда. Funding flip — редкое событие; статистики недостаточно для prod.
