# Cross-Asset Lead-Lag Backtest — BTC follows ETH/XRP

**Период:** ~2y BTCUSDT 1h, target=BTCUSDT, leads=['ETHUSDT', 'XRPUSDT']

**Стратегия:**
- В каждом 1h баре считаем return BTC и return альта (ETH или XRP) за `lookback_h` часов
- spread = alt_return - btc_return
- если spread > +threshold → LONG BTC (BTC догонит)
- если spread < -threshold → SHORT BTC
- hold N часов; cooldown 4h между trade-ми
- fees 2×0.075% taker, size $1000.0

**Sweep:** lookback=[4, 8, 12, 24], threshold=[0.5, 1.0, 1.5, 2.0], hold=[2, 4, 6, 12], direction=['both', 'long_only', 'short_only'], lead=['ETHUSDT', 'XRPUSDT']. Total combos: 384

## Топ-25 по PnL

| lead | lb | th% | hold | dir | N | PnL ($) | PF | WR% | avg | DD | pos |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| ETHUSDT | 4 | 2.0 | 6 | short_only | 136 | +136 | 1.18 | 46 | +1.0 | 192 | 3/4 |
| ETHUSDT | 4 | 2.0 | 12 | long_only | 174 | +95 | 1.09 | 41 | +0.5 | 267 | 2/4 |
| ETHUSDT | 4 | 2.0 | 12 | both | 309 | +84 | 1.04 | 43 | +0.3 | 249 | 2/4 |
| ETHUSDT | 4 | 2.0 | 4 | short_only | 136 | +78 | 1.11 | 47 | +0.6 | 210 | 3/4 |
| ETHUSDT | 4 | 1.5 | 12 | long_only | 311 | +75 | 1.04 | 42 | +0.2 | 539 | 2/4 |
| ETHUSDT | 4 | 2.0 | 6 | both | 309 | +69 | 1.04 | 43 | +0.2 | 227 | 3/4 |
| ETHUSDT | 4 | 2.0 | 12 | short_only | 136 | +13 | 1.01 | 45 | +0.1 | 223 | 3/4 |
| ETHUSDT | 4 | 2.0 | 2 | short_only | 136 | -89 | 0.86 | 46 | -0.7 | 209 | 2/4 |
| ETHUSDT | 4 | 2.0 | 6 | long_only | 174 | -95 | 0.89 | 41 | -0.5 | 189 | 2/4 |
| ETHUSDT | 4 | 2.0 | 4 | both | 309 | -125 | 0.92 | 43 | -0.4 | 257 | 1/4 |
| XRPUSDT | 4 | 2.0 | 6 | long_only | 402 | -148 | 0.93 | 46 | -0.4 | 448 | 2/4 |
| ETHUSDT | 8 | 2.0 | 12 | long_only | 332 | -155 | 0.93 | 42 | -0.5 | 512 | 2/4 |
| ETHUSDT | 8 | 2.0 | 2 | short_only | 274 | -160 | 0.84 | 45 | -0.6 | 240 | 1/4 |
| XRPUSDT | 4 | 2.0 | 4 | long_only | 402 | -164 | 0.90 | 44 | -0.4 | 282 | 1/4 |
| ETHUSDT | 4 | 1.5 | 6 | long_only | 311 | -165 | 0.89 | 44 | -0.5 | 298 | 0/4 |
| ETHUSDT | 8 | 2.0 | 4 | short_only | 274 | -180 | 0.88 | 43 | -0.7 | 313 | 2/4 |
| ETHUSDT | 4 | 1.5 | 2 | long_only | 311 | -193 | 0.80 | 41 | -0.6 | 306 | 1/4 |
| ETHUSDT | 8 | 2.0 | 6 | short_only | 274 | -200 | 0.89 | 39 | -0.7 | 431 | 2/4 |
| ETHUSDT | 4 | 2.0 | 2 | long_only | 174 | -200 | 0.67 | 36 | -1.2 | 205 | 0/4 |
| XRPUSDT | 4 | 1.5 | 4 | long_only | 606 | -202 | 0.92 | 42 | -0.3 | 429 | 1/4 |
| ETHUSDT | 4 | 1.0 | 12 | long_only | 628 | -203 | 0.95 | 44 | -0.3 | 907 | 2/4 |
| ETHUSDT | 4 | 2.0 | 4 | long_only | 174 | -204 | 0.75 | 39 | -1.2 | 196 | 0/4 |
| ETHUSDT | 8 | 2.0 | 12 | short_only | 274 | -204 | 0.92 | 46 | -0.7 | 454 | 1/4 |
| XRPUSDT | 4 | 2.0 | 12 | long_only | 402 | -228 | 0.92 | 46 | -0.6 | 644 | 2/4 |
| XRPUSDT | 8 | 2.0 | 12 | long_only | 572 | -244 | 0.94 | 46 | -0.4 | 670 | 3/4 |

## Best per lead (filtered: PF>=1.3, N>=50, pos>=3)

### ETHUSDT
_No combo qualified._

### XRPUSDT
_No combo qualified._


## Verdict

❌ No combos passed filter PF≥1.3, N≥50, 3+/4 folds.
