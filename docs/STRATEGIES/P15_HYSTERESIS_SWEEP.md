# P-15 Trend Gate Hysteresis Sweep

**Период:** ~2y BTC (78288 15m bars)
**Контекст:** Live P-15 теряет $765/24h из-за whipsaw в боковике.
Текущая логика: gate flip на одном баре → close + open циклы.
Гипотеза: требовать 2-3 bar confirmation для OPEN, сохранить single-bar для CLOSE.

**Fixed params:** R=0.3%, K=0.5%, dd_cap=3.0%, harvest=0.3, max_layers=6

## Sweep по confirm_bars

| confirm_bars | dir | N trades | sum PnL ($) | avg PF | pos folds | forced | natural |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | long | 6282 | -37,579 | 0.15 | 0/4 | 49 | 1871 |
| 1 | short | 5716 | -34,533 | 0.18 | 0/4 | 64 | 1713 |
| 2 | long | 5466 | -34,873 | 0.15 | 0/4 | 47 | 1378 |
| 2 | short | 4919 | -31,903 | 0.17 | 0/4 | 58 | 1233 |
| 3 | long | 5011 | -32,949 | 0.15 | 0/4 | 43 | 1177 |
| 3 | short | 4511 | -29,403 | 0.18 | 0/4 | 59 | 1053 |
| 5 | long | 4396 | -29,712 | 0.15 | 0/4 | 39 | 959 |
| 5 | short | 3899 | -26,274 | 0.18 | 0/4 | 59 | 804 |

## Verdict

**SHORT best:** confirm_bars=5 → $-26,274 (0/4 folds)

**LONG best:** confirm_bars=5 → $-29,712 (0/4 folds)

Per-fold PnL для best combo:
- SHORT confirm=5: [-7583.0, -8354.0, -6069.0, -4268.0]
- LONG confirm=5: [-8186.0, -10246.0, -6494.0, -4786.0]

## Direct comparison: cb=1 (current) vs cb=3 (proposed)

**LONG:**
- cb=1: PnL $-37,579 on N=6282
- cb=3: PnL $-32,949 on N=5011
- Δ PnL: $+4,631, Δ N: -1271 trades

**SHORT:**
- cb=1: PnL $-34,533 on N=5716
- cb=3: PnL $-29,403 on N=4511
- Δ PnL: $+5,130, Δ N: -1205 trades

