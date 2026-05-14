# SHORT EXIT OPTIONS — 2026-05-06 (v1 / CP1 archive)

Архивный snapshot, реконструированный из:
- `scripts/_short_exit_multifactor.py`
- `docs/ANALYSIS/_short_exit_multifactor.json`

## Основа

| Поле | Значение |
|---|---:|
| Аналогов | 406 |
| Driver | `scripts/_short_exit_multifactor.py` |
| Source | `data/forecast_features/full_features_1y.parquet` |
| Classification | `vola_compressing + fund_neg` |
| n группы | 52 |
| Outcome split | 0.0% down / 46.2% up_ext / 53.8% pullback / 0.0% sideways |

## Current setup factors (CP1)

| Factor | Значение |
|---|---:|
| `vol_ratio_to_30d` | 0.658 |
| `vol_trend` | flat |
| `vola_ratio_to_30d` | 0.693 |
| `vola_trend` | compressing |
| `fund_now` | -2.9e-05 |
| `fund_trend` | less_negative |
| `higher_highs_count` | 13 |
| `final_impulse_pct` | 0.0 |
| `oi_change_pct` | -0.94 |

## Exit numbers (CP1)

| Вариант | Число |
|---|---:|
| Stop 82,400 reached | 94.6% |
| Stop 82,400 false breakout of reached | 99.2% |
| BE 79,036 reached | 56.4% |
| Hold to 75,200 | 14.3% full sample / 0.0% neg-funding subgroup |
| Funding flip median | 65h |
| Funding move at flip median | +1.31% |

## Notes

CP1 не использовал:
- live `market_live/market_1m.csv` для текущего setup
- real OHLC ATR из `pattern_memory_BTCUSDT_1h_*.csv`
- `volume_ratio_30d` как live anomaly metric

Этот файл архивный и не является итоговым reconciled документом.
