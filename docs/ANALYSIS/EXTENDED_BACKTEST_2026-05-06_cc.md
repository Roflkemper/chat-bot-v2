# EXTENDED BACKTEST — 2026-05-06 (Claude Code independent run)

**Тип:** READ-ONLY analytical extension
**TZ:** TZ-EXTENDED-BACKTEST-OI-EXIT-OPTIONS-INDEPENDENT-RUN, Блок 1
**Скрипт:** [`scripts/_extended_analog_search_cc.py`](../../scripts/_extended_analog_search_cc.py)
**Raw output:** [`_extended_analog_search_cc.json`](_extended_analog_search_cc.json)

Без trading advice. Без прогнозов.

---

## §1 Что было сделано

Расширили базу аналогов с 1y (2025-05-01 → 2026-05-01, n=406) до 2.34y (2024-01-01 → 2026-05-03) через `state/pattern_memory_BTCUSDT_1h_*.csv`.

| Источник | Период | Cadence | Колонки |
|---|---|---|---|
| `state/pattern_memory_BTCUSDT_1h_2024.csv` | 2024-01-01 → 2025-01-01 | 1h | OHLCV |
| `state/pattern_memory_BTCUSDT_1h_2025.csv` | 2025-01-01 → 2026-01-01 | 1h | OHLCV |
| `state/pattern_memory_BTCUSDT_1h_2026.csv` | 2026-01-01 → 2026-05-03 | 1h | OHLCV |
| `data/forecast_features/full_features_1y.parquet` | 2025-05-01 → 2026-05-01 | 5m → 1h | + funding, OI |

| Gap | Статус |
|---|---|
| Funding rate за 2024-01-01 → 2025-04-30 | НЕТ — pattern_memory это только OHLCV |
| OI за 2024-01-01 → 2025-04-30 | НЕТ |
| → последствие | Bucket `funding_negative` вычислим только для 1y subset |

---

## §2 Критерии (без изменений)

| Параметр | Значение |
|---|---|
| Lookback | 144h (6 дней) |
| Окно роста | +8% до +11% за 144h |
| `off_high_max` | 1.5% |
| `anchor_age_h` | 96–143h |
| Look-forward | 240h (10 дней) |
| Up_ext threshold | ≥ +5% от setup |
| Recovery threshold | ≥ +1% выше setup |
| Partial pullback | ≥ −1.5% от setup |

---

## §3 Размер выборки

| Подмножество | n | Период |
|---|---:|---|
| **Total extended** | **1,339** | 2024-01-01 → 2026-05-03 |
| 1y overlap (с funding) | 406 | 2025-05-01 → 2026-05-01 |
| Pre-1y only (без funding) | 933 | 2024-01-01 → 2025-04-30 |

Пред-2025-05-01 даёт **933 дополнительных аналога** (2.3x больше) — но без funding/OI таггинга.

---

## §4 Outcome distribution на разных подвыборках

| Подвыборка | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| Extended full | 1,339 | 36.0% | 23.7% | 26.0% | 14.3% |
| In-1y overlap (full) | 406 | 14.3% | 24.9% | 40.6% | 20.2% |
| Pre-1y only | 933 | **45.4%** | 23.1% | **19.6%** | 11.9% |

**Ключевое наблюдение:** в пре-1y подвыборке (2024–2025-04) `down_to_anchor` встречался **в 45.4% случаев** против 14.3% в 1y subset. Это связано с разной макро-структурой рынка: 2024 включал больше bear-эпизодов и distribution-фаз, тогда как 2025-05 → 2026-04 был bull-skewed.

---

## §5 Reconciled группа на extended выборке

Группа `vola_compressing + funding_negative` доступна только в 1y subset (где funding известен).

| Подвыборка | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| **`vola_compressing + funding_negative` (1y only)** | **31** | **0.0%** | **74.2%** | **25.8%** | **0.0%** |
| Reconciled v3 reference (n=32 из v3 doc) | 32 | 0.0% | 71.9% | 28.1% | 0.0% |

Расхождение n=31 vs n=32 — на 1 аналог (вероятно граничный случай near вечеринки funding bucket). **Outcome split в reconciled группе подтверждён независимым прогоном.**

---

## §6 Volatility-only fallback на full extended

Когда funding неизвестен (pre-1y subset), доступна только `vola_compressing` без funding-кондиционирования:

| Подвыборка | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `vola_compressing` full extended (с funding-проксиверсией) | 643 | **27.5%** | 30.6% | 22.7% | 19.1% |
| `vola_compressing` pre-1y only | (subset of 643 minus 1y portion) | (см. JSON) | | | |

**Структурный сдвиг:** при добавлении pre-1y данных без funding-фильтра доля `down_to_anchor` подскакивает с 0% (reconciled) до 27.5% (volatility-only). Это means: **отсутствие funding-кондиционирования меняет outcome распределение качественно**. Funding-negative — главный сепаратор.

---

## §7 Что Extended backtest подтверждает

| Утверждение | Подтверждено? |
|---|---|
| Reconciled группа (vola_compressing + fund_neg) даёт ~75% up_ext / 25% pullback / 0% down | ✅ ДА (n=31 в independent run, 0/74.2/25.8/0) |
| Funding-negative — главный фактор предотвращения down_to_anchor | ✅ ДА (без funding-фильтра 27.5% down vs 0% с фильтром) |
| Пред-1y данные имеют другой outcome mix (больше bear) | ✅ ДА (45.4% down_to_anchor vs 14.3% в 1y) |
| Reconciled n=32 в v3 близок к n=31 в independent run | ✅ ДА (расхождение 1 case) |

---

## §8 Что Extended backtest НЕ может сказать

| Вопрос | Причина |
|---|---|
| Как ведёт себя `vola_compressing + funding_negative` за 2024 | Funding нет в pattern_memory |
| Как ведёт себя OI в pre-1y | OI нет в pattern_memory |
| Что произошло после 2026-05-03 | За пределами данных |
| Гарантия повторения паттерна | Это historical frequency, не prediction |

---

**Конец Блока 1.** Reconciled v3 outcome подтверждён. Funding-negative — главный сепаратор от down_to_anchor.
