# Session Breakout × Other Detectors — Pair-wise Backtest

**Method:** for each session_breakout signal, check if PARTNER
detector fired same side within last `window_h`. Bucket into PAIR (yes) or SOLO (no).
Trade only on the session_breakout bar, hold 3h, fees 2×0.075%.

**Total session_breakout signals:** 2935

## Results

| partner | window_h | PAIR N | PAIR PnL | PAIR PF | PAIR WR% | SOLO N | SOLO PnL | SOLO PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| multi_divergence | 2 | 254 | -295 | 0.68 | 41 | 2681 | -3,612 | 0.67 |
| multi_divergence | 4 | 418 | -381 | 0.75 | 41 | 2517 | -3,527 | 0.66 |
| multi_divergence | 6 | 569 | -734 | 0.66 | 40 | 2366 | -3,174 | 0.68 |
| multi_divergence | 12 | 929 | -1,207 | 0.66 | 39 | 2006 | -2,700 | 0.68 |
| pdl_bounce | 2 | 196 | -332 | 0.59 | 40 | 2739 | -3,575 | 0.68 |
| pdl_bounce | 4 | 300 | -367 | 0.70 | 43 | 2635 | -3,541 | 0.67 |
| pdl_bounce | 6 | 395 | -440 | 0.73 | 43 | 2540 | -3,467 | 0.66 |
| pdl_bounce | 12 | 555 | -532 | 0.75 | 43 | 2380 | -3,376 | 0.66 |
| pdh_rejection | 2 | 203 | -286 | 0.58 | 34 | 2732 | -3,621 | 0.68 |
| pdh_rejection | 4 | 321 | -379 | 0.64 | 38 | 2614 | -3,529 | 0.68 |
| pdh_rejection | 6 | 404 | -420 | 0.68 | 40 | 2531 | -3,487 | 0.67 |
| pdh_rejection | 12 | 578 | -828 | 0.62 | 39 | 2357 | -3,080 | 0.68 |
| cascade_proxy | 2 | 48 | +146 | 1.63 | 56 | 2887 | -4,053 | 0.65 |
| cascade_proxy | 4 | 134 | +23 | 1.04 | 49 | 2801 | -3,931 | 0.65 |
| cascade_proxy | 6 | 191 | +19 | 1.02 | 49 | 2744 | -3,927 | 0.64 |
| cascade_proxy | 12 | 349 | -308 | 0.81 | 41 | 2586 | -3,600 | 0.65 |

## Сравнение pair vs solo по detector × window

| partner | window | pair_PF / solo_PF | edge boost (pair PnL - solo avg) |
|---|---:|---|---:|
| multi_divergence | 2h | 0.68 / 0.67 | $+0.19/trade |
| multi_divergence | 4h | 0.75 / 0.66 | $+0.49/trade |
| multi_divergence | 6h | 0.66 / 0.68 | $+0.05/trade |
| multi_divergence | 12h | 0.66 / 0.68 | $+0.05/trade |
| pdl_bounce | 2h | 0.59 / 0.68 | $-0.39/trade |
| pdl_bounce | 4h | 0.70 / 0.67 | $+0.12/trade |
| pdl_bounce | 6h | 0.73 / 0.66 | $+0.25/trade |
| pdl_bounce | 12h | 0.75 / 0.66 | $+0.46/trade |
| pdh_rejection | 2h | 0.58 / 0.68 | $-0.08/trade |
| pdh_rejection | 4h | 0.64 / 0.68 | $+0.17/trade |
| pdh_rejection | 6h | 0.68 / 0.67 | $+0.34/trade |
| pdh_rejection | 12h | 0.62 / 0.68 | $-0.13/trade |
| cascade_proxy | 2h | 1.63 / 0.65 | $+4.44/trade |
| cascade_proxy | 4h | 1.04 / 0.65 | $+1.58/trade |
| cascade_proxy | 6h | 1.02 / 0.64 | $+1.53/trade |
| cascade_proxy | 12h | 0.81 / 0.65 | $+0.51/trade |

## Verdict

Лучшая пара: **session_breakout + cascade_proxy** (window=2h) → PAIR PF 1.63 (vs solo PF 0.65), N=48, PnL $+146.

Это значит: когда session_breakout срабатывает И в последние 2 часов уже был сигнал cascade_proxy в ту же сторону — edge **значительно сильнее** обычного.

Confluence boost которое мы добавили в loop.py будет автоматически усиливать confidence для таких setups.
