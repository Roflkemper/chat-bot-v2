# OI DEEP DIVE — BTC analog outcomes

## §1 Coverage

| Source | Период | Cadence | Что использовано |
|---|---|---:|---|
| `data/forecast_features/full_features_1y.parquet` | 2025-05-01 00:00 UTC → 2026-05-01 00:00 UTC | 1h resample | `close`, `sum_open_interest`, `funding_rate` |
| `docs/ANALYSIS/_uptrend_analog_search.json` | 406 analogs | setup list | `ts`, `setup_price`, `rise_pct`, `outcome` |

Текущий OI status ниже основан на последнем доступном historical bar.
Live OI на `2026-05-06` в retained storage не найден.

## §2 OI distributions

| OI условие | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| OI растёт > 5% | 208 | 25.5% | 26.9% | 32.2% | 15.4% |
| OI стабильный ±5% | 156 | 3.2% | 28.8% | 35.9% | 32.1% |
| OI падает > 5% | 42 | 0.0% | 0.0% | 100.0% | 0.0% |
| OI divergence: price↑, OI↓ | 96 | 5.2% | 5.2% | 84.4% | 5.2% |

Ключевой сигнал:
`OI падает > 5%` дал `42/42` случаев `pullback_continuation`.
`OI divergence` дал `81/96` случаев `pullback_continuation`.

## §3 Cross-classification: OI × funding × volatility

| Комбинация | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| OI растёт + fund_neg + compressing | 32 | 0.0% | 75.0% | 25.0% | 0.0% |
| OI падает + fund_neg + compressing | 12 | 0.0% | 0.0% | 100.0% | 0.0% |
| OI flat + fund_neg + compressing | 8 | 0.0% | 0.0% | 100.0% | 0.0% |

Разделение здесь резкое:
при `fund_neg + compressing` направление OI сдвигает outcome
между `75.0% up_extension` и `100.0% pullback_continuation`.

## §4 Текущий OI status

| Метрика | Значение |
|---|---:|
| Latest historical bar | 2026-05-01 00:00 UTC |
| `sum_open_interest` | 95,322.905 |
| OI ratio к 30d baseline | 0.999x |
| OI delta по setup window | -0.94% |
| OI bucket | stable ±5% |
| OI divergence | да |

Ближайшая OI-only группа:

| Группа | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| OI стабильный ±5% | 156 | 3.2% | 28.8% | 35.9% | 32.1% |

Дополнение:
флаг `price↑ + OI↓` уже активен.
По divergence bucket это `84.4% pullback_continuation` на `n=96`.

## §5 Ограничения

| Ограничение | Статус |
|---|---|
| Full-year live OI after 2026-05-01 | нет |
| Full-year liquidations | нет |
| Full-year orderbook | нет |
| Timing-statements | намеренно исключены |

Итог:
OI deep dive не даёт прогноза.
Он только показывает, что падение OI и divergence исторически были сильным pullback-маркером внутри найденных аналогов.
