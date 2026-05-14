# EXTENDED BACKTEST — BTC uptrend analogs

## §1 Что найдено по данным

| Source | Период | Cadence | Колонки | Статус |
|---|---|---:|---|---|
| `data/whatif_v3/btc_1m_enriched_2y.parquet` | 2024-04-25 00:00 UTC → 2026-04-29 17:00 UTC | 1m | `open/high/low/close/volume`, ATR, RSI, session | использован для extended price-only search |
| `data/forecast_features/full_features_1y.parquet` | 2025-05-01 00:05 UTC → 2026-05-01 00:00 UTC | 5m | `close`, `volume`, `funding_rate`, `sum_open_interest` | использован как 1y control |
| `data/regime/BTCUSDT_features_1h.parquet` | 2024-04-25 00:00 UTC → 2026-04-29 17:00 UTC | 1h | ATR/ROC/regime features | не использован в bucket extension |
| `state/pattern_memory_BTCUSDT_1h_2024.csv` + `2025/2026` | 2024 → 2026 | 1h | OHLCV | доступно как fallback OHLC |

Gap:
старший `2y` source не содержит `funding_rate` и `sum_open_interest`.
Поэтому reconciled bucket `vola_compressing + fund_neg` нельзя расширить до 2024 теми же правилами.

## §2 Price-only extended search

Критерий поиска:

| Параметр | Значение |
|---|---|
| Рост окна | 7% → 12% |
| Длина окна | 4, 5, 6, 7, 8 дней |
| Max internal pullback | ≤ 5% |
| Setup bar | локальный максимум окна |
| Future window | 10 дней |

## §3 Результат extended search

| Выборка | N analogs | down_to_anchor | up_extension | pullback_continuation | sideways |
|---|---:|---:|---:|---:|---:|
| 1y control, тот же criterion | 154 | 19.5% | 26.0% | 46.1% | 8.4% |
| Extended 2024-04-25 → 2026-04-29 | 401 | 19.5% | 38.4% | 33.2% | 9.0% |
| Delta | +247 | 0.0 pp | +12.4 pp | -12.9 pp | +0.6 pp |

Delta к 1y control:
`401 / 154 = 2.60x`.
Это расширяет raw price-only foundation, но не заменяет reconciled группу `n=52`.

## §4 Что это значит для reconciled foundation

| Вопрос | Ответ |
|---|---|
| Можно ли расширить `vola_compressing + fund_neg` до 2024? | Нет, funding/OI в 2y parquet отсутствуют |
| Можно ли расширить raw analog universe? | Да, до `401` случаев |
| Совпадает ли extended search с исходным `406`? | Нет, criterion здесь другой: 7–12% / 4–8 дней / max pullback ≤5% |

Итог:
Блок 1 выполнен в режиме best-effort.
Расширение price-only прошло, а reconciled bucket extension задокументирован как data gap.
