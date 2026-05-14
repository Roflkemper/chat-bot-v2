# EPISODES_MULTIASSET — 2026-04-28

**Build date:** 2026-04-28T21:12:47Z  
**Days back:** 366  
**Episode types:** rally_strong, rally_critical, dump_strong, dump_critical, no_pullback_up_3h, no_pullback_down_3h  
**Total episodes:** 7401  

## Episode counts by symbol and type

| symbol | episode_type | count |
|--------|-------------|-------|
| BTCUSDT | dump_critical | 51 |
| BTCUSDT | dump_strong | 225 |
| BTCUSDT | no_pullback_down_3h | 524 |
| BTCUSDT | no_pullback_up_3h | 532 |
| BTCUSDT | rally_critical | 42 |
| BTCUSDT | rally_strong | 157 |
| ETHUSDT | dump_critical | 206 |
| ETHUSDT | dump_strong | 741 |
| ETHUSDT | no_pullback_down_3h | 519 |
| ETHUSDT | no_pullback_up_3h | 559 |
| ETHUSDT | rally_critical | 205 |
| ETHUSDT | rally_strong | 648 |
| XRPUSDT | dump_critical | 207 |
| XRPUSDT | dump_strong | 746 |
| XRPUSDT | no_pullback_down_3h | 566 |
| XRPUSDT | no_pullback_up_3h | 545 |
| XRPUSDT | rally_critical | 223 |
| XRPUSDT | rally_strong | 705 |

## Symbol details

### BTCUSDT
- Source: `C:\bot7\backtests\frozen\BTCUSDT_1m_2y.csv`
- Bars: 521,318
- Range: 2025-04-27 → 2026-04-24

### ETHUSDT
- Source: `C:\bot7\frozen\ETHUSDT_1m.parquet`
- Bars: 527,042
- Range: 2025-04-27 → 2026-04-28

### XRPUSDT
- Source: `C:\bot7\frozen\XRPUSDT_1m.parquet`
- Bars: 527,041
- Range: 2025-04-27 → 2026-04-28

## Magnitude sanity (rally_critical per symbol)

| symbol | mean_mag | min_mag | max_mag | count |
|--------|----------|---------|---------|-------|
| BTCUSDT | 3.53% | 3.00% | 8.89% | 42 |
| ETHUSDT | 3.65% | 3.00% | 11.36% | 205 |
| XRPUSDT | 3.99% | 3.00% | 65.06% | 223 |

## Regression check (BTC)

| metric | value |
|--------|-------|
| BTC episodes before rebuild | 184 |
| BTC episodes after rebuild | 1531 |
| PASS | ✓ |

## Average magnitude per symbol/type

| symbol | episode_type | avg_magnitude |
|--------|-------------|--------------|
| BTCUSDT | dump_critical | -3.19% |
| BTCUSDT | dump_strong | -2.14% |
| BTCUSDT | no_pullback_down_3h | 3.86% |
| BTCUSDT | no_pullback_up_3h | 3.85% |
| BTCUSDT | rally_critical | 3.53% |
| BTCUSDT | rally_strong | 2.46% |
| ETHUSDT | dump_critical | -3.20% |
| ETHUSDT | dump_strong | -2.15% |
| ETHUSDT | no_pullback_down_3h | 3.83% |
| ETHUSDT | no_pullback_up_3h | 3.85% |
| ETHUSDT | rally_critical | 3.65% |
| ETHUSDT | rally_strong | 2.53% |
| XRPUSDT | dump_critical | -3.24% |
| XRPUSDT | dump_strong | -2.15% |
| XRPUSDT | no_pullback_down_3h | 3.84% |
| XRPUSDT | no_pullback_up_3h | 3.87% |
| XRPUSDT | rally_critical | 3.99% |
| XRPUSDT | rally_strong | 2.64% |
