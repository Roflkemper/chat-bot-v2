# ВАРИАНТЫ ВЫХОДА — SHORT 79k / 82.3k / anchor 75.2k (reconciled v3)

**Тип:** аналитический READ-ONLY документ
**Дата:** 2026-05-06
**Версия:** v3 (reconciled из v1 + v2)
**Архив:**
  - [`_archive/SHORT_EXIT_OPTIONS_2026-05-06_v1.md`](_archive/SHORT_EXIT_OPTIONS_2026-05-06_v1.md)
  - [`_archive/SHORT_EXIT_OPTIONS_2026-05-06_v2.md`](_archive/SHORT_EXIT_OPTIONS_2026-05-06_v2.md)
**Скрипты:** [`scripts/_short_exit_multifactor.py`](../../scripts/_short_exit_multifactor.py), [`scripts/_short_exit_options_analysis.py`](../../scripts/_short_exit_options_analysis.py)
**Raw data:** [`_short_exit_multifactor.json`](_short_exit_multifactor.json), [`_short_exit_options_2026-05-06.json`](_short_exit_options_2026-05-06.json)

Без trading advice. Без прогнозов. Только числа.

---

## §1 Контекст позиции

| Поле | Значение |
|---|---:|
| Direction | SHORT BTCUSDT linear |
| Size | 1.416 BTC |
| Entry | 79,036 |
| Текущая цена | 82,300 |
| Anchor роста | 75,200 |
| Unrealized PnL | −$3,572 |
| Funding | −0.0082% / 8h |
| Distance to liq | ~18% |

Базовая выборка: **406 аналогов** из [`UPTREND_PULLBACK_ANALOGS_2026-05-06.md`](UPTREND_PULLBACK_ANALOGS_2026-05-06.md).
Общая база исходов: 14.3% down_to_anchor / 24.9% up_extension / 40.6% pullback_continuation / 20.2% sideways.

---

## §2 Reconciliation note (откуда v3)

v1 и v2 дали разные классификации текущего setup'а: v1 → `vola_compressing + fund_neg` (n=52), v2 → `стабильный/стабильная/funding_near_zero` (n=38). После проверки: v2 nearest_groups определялся через Euclidean distance в пространстве с `volume_ratio_30d=4.315x`, причём 4.315x — артефакт сравнения live `market_1m.csv` (BTC volumes) против `full_features_1y` (Binance USDT volumes), разные источники → невалидное сравнение. v1 funding bucket (`<0`) и v2 funding bucket (`<-5e-5`) обе помечают operator's −8.2e-5 как negative. Reconciled primary group построен вручную на пересечении валидных факторов (см. §11).

---

## §3 Доступные данные

| Source | Содержимое | Покрытие | Cadence | Использование в v3 |
|---|---|---|---|---|
| `data/forecast_features/full_features_1y.parquet` | close, volume, funding_rate, sum_open_interest, RSI, ATR_14, rvol_20 | 2025-05-01 → 2026-05-01 | 5m → 1h | основная база, 406 analog enrichment |
| `state/pattern_memory_BTCUSDT_1h_2025.csv`, `…_2026.csv` | OHLCV (real high/low) | 2025-01-01 → 2026-04-30 | 1h | реальный ATR-like для historical analogs |
| `market_live/market_1m.csv` | live OHLCV | 2026-04-24 → 2026-05-06 | 1m | трекинг текущего setup'а **только для close/HH/pullback**, **не для volume baseline** |
| `data/regime/BTCUSDT_features_1h.parquet` | 17 features | 2024-04-25 → 2026-04-29 | 1h | availability only |

| Source | Status |
|---|---|
| Full-year liquidation log | **NOT retained** |
| Full-year orderbook | **NOT retained** |
| Full-year trades parquet | NOT found |
| Apples-to-apples live volume baseline | **NOT available** (live и historical из разных feeds) |

---

## §4 Multi-factor distributions (объединённые таблицы)

### §4.1 Volume trend (CP2 классификация)

| Условие | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `растёт` | 121 | 5.8% | **44.6%** | 25.6% | 24.0% |
| `стабильный` | 217 | **23.0%** | 17.5% | 39.2% | 20.3% |
| `падает` | 68 | 1.5% | 13.2% | **72.1%** | 13.2% |

### §4.2 Volatility trend (одинаково в v1 и v2)

| Условие | n (v2) | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `расширяется` | 125 | 3.2% | **47.2%** | 25.6% | 24.0% |
| `стабильная` | 122 | **32.8%** | 11.5% | 48.4% | 7.4% |
| `сжимается` | 159 | 8.8% | 17.6% | 46.5% | 27.0% |

### §4.3 Funding bucket — расхождение v1/v2

| Bucket (v2 strict) | v2 boundary | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---|---:|---:|---:|---:|---:|
| `funding_negative` | <−5e-5 | 42 | **0.0%** | **59.5%** | 40.5% | 0.0% |
| `funding_near_zero` | [−5e-5, +5e-5] | 135 | 6.7% | 25.2% | 59.3% | 8.9% |
| `funding_positive` | >+5e-5 | 229 | 21.4% | 18.3% | 29.7% | 30.6% |

| Bucket (v1 loose) | v1 boundary | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---|---:|---:|---:|---:|---:|
| `fund_now<0` | <0 | 81 | **0.0%** | 53.1% | 46.9% | 0.0% |
| `fund_now>=0` | ≥0 | 325 | 17.8% | 17.8% | 39.1% | 25.2% |

**Reconciled:** обе bucket logic дают тот же качественный signal — отрицательный funding → **0% down_to_anchor**. v2 strict bucket даёт более чистое разделение (59.5% up_ext vs 53.1% при <0).

### §4.4 OI и structure (v1)

| Условие | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `oi_grew_>5%` | 208 | **25.5%** | 26.9% | 32.2% | 15.4% |
| `oi_flat_-5_to_5%` | 156 | 3.2% | 28.8% | 35.9% | 32.1% |
| `oi_fell_>5%` | 42 | 0.0% | 0.0% | **100.0%** | 0.0% |
| `higher_highs >= 20` | 307 | 17.6% | 21.8% | 36.2% | 24.4% |
| `higher_highs 10–19` | 99 | 4.0% | **34.3%** | **54.5%** | 7.1% |

### §4.5 Combos с самым сильным разделением

| Combo | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `падает / funding_near_zero / сжимается` | 47 | (87.2% pullback or anchor) | 0.0% | dominantly pullback | 12.8% |
| `растёт / funding_near_zero / расширяется` | 23 | 17.4% (combined) | **82.6%** | — | 0.0% |
| `vol_up + fund_neg` (v1) | 19 | 0.0% | **100.0%** | 0.0% | 0.0% |
| `many_higher_highs + fund_neg` (v1) | 36 | 0.0% | 72.2% | 27.8% | 0.0% |

---

## §5 Текущий factor profile (после reconciliation)

| Factor | Значение | Bucket / trend |
|---|---:|---|
| Цена | 82,300 | — |
| Anchor | 75,200 | — |
| Рост за 6 дней | +9.44% | — |
| **Volume ratio 30d** | **NOT VALID** | live vs historical разные источники; CP2 4.315x — артефакт |
| Volume trend (live last 144h) | растёт (CP2) | использовать с осторожностью |
| Volatility ratio 30d | 0.961x (CP2) | стабильно (близко к 30d baseline) |
| Volatility trend | сжимается (CP2 + v1 single bar match) | matches `сжимается` bucket |
| Funding | −8.2e-5 за 8h | `funding_negative` (CP2 strict) И `fund_now<0` (v1 loose) |
| Funding в percentile 1y | ниже **p10** (p10 = −3.1e-5) | глубоко в нижнем хвосте |
| Higher highs (live last 144h) | 24 | bucket `>=20` |
| Final impulse 12h | +1.96% | impulse_mid |
| Max internal pullback | 1.94% | мягкий internal drawdown |

---

## §6 Reconciled primary nearest group

Manually-built combo на пересечении валидных факторов: `(сжимается, funding_negative)` со strict bucket из CP2.

| Combo | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| **`сжимается + funding_negative`** | **32** | **0.0%** | **71.9%** | **28.1%** | **0.0%** |
| `funding_negative` (любой volatility) | 42 | 0.0% | 59.5% | 40.5% | 0.0% |
| `vola_compressing + fund_neg` (v1, looser fund) | 52 | 0.0% | 46.2% | 53.8% | 0.0% |

**Reconciled choice:** primary group = **`сжимается + funding_negative`** (n=32). Все три варианта согласны на **0% down_to_anchor**, расходятся в split между up_extension и pullback_continuation.

В этой группе — **71.9% (23 из 32) дали up_extension**, **28.1% (9 из 32) дали pullback_continuation**, **0%** дошли до anchor, **0%** sideways.

---

## §7 Варианты выхода — числа из истории

PnL для 1.416 BTC, entry 79,036.

### §7.1 Вариант 1 — Stop-buy на пробой

| Stop level | Loss USD | % достигли (n=406) | % ложного пробоя из достигших | % дальнейшего роста +2% от target |
|---:|---:|---:|---:|---:|
| 82,400 | −4,763 | **94.6%** | 99.2% | 78.9% |
| 83,000 | −5,613 | 83.7% | 96.8% | 72.1% |
| 84,000 | −7,029 | 74.9% | 73.4% | 51.3% |
| 85,000 | −8,445 | **47.5%** | 62.7% | 46.6% |

«Ложный пробой» = после касания target цена возвращается ниже setup point (82,300 эквивалент).

### §7.2 Вариант 2 — Pullback exit

| Target | PnL USD | % достигли (n=406) | % разворот вверх через setup из достигших |
|---:|---:|---:|---:|
| 80,000 | −1,365 | **64.3%** | 39.8% |
| 79,036 (BE) | 0 | 56.4% | 29.7% |
| 78,000 | +1,467 | 48.8% | 22.2% |
| 77,000 | +2,883 | **35.2%** | 25.2% |

### §7.3 Вариант 3 — Trailing 30/30/40 на 81k / 79,036 / 77k

| Метрика | Full base 406 | v2 primary group (n=38, archived) | v1 primary group (n=52) |
|---|---:|---:|---:|
| Expected PnL | −12,828 | −4,219 | мягче (no zero fills) |
| Median PnL | +319 | +319 | n/a |
| Full fill (все 3 уровня) | 35.2% | 55.3% | n/a |
| Partial fill (1–2 уровня) | 50.5% | 36.8% | n/a |
| Zero fill | 14.3% | 7.9% | n/a |

### §7.4 Вариант 4 — Hold до anchor 75,200

| Метрика | Значение |
|---|---:|
| Trigger | цена достигает 75,200 |
| PnL | **+5,432** |
| % full sample | 14.3% (58/406) |
| % v1 group `fund_now<0` (n=81) | **0.0%** |
| % v2 group `funding_negative` (n=42) | **0.0%** |
| % reconciled group `сжимается + funding_negative` (n=32) | **0.0%** |

Все три definition'а funding-negative подгруппы согласны: **ноль случаев** дошли до anchor.

### §7.5 Вариант 5 — Pyramiding (+1 BTC на 83k)

| Метрика | Full base 406 | v2 primary group (n=38) |
|---|---:|---:|
| Add level | 83,000 | 83,000 |
| Success cases | 163 | (high) |
| Fail cases | 177 | (high) |
| Success rate after add-trigger | **47.9%** | **78.9%** |
| Median added PnL — success | +3,964 USD | +3,964 USD |
| Median added loss — fail | −24,970 USD | −20,567 USD |

«Success» = после add рынок возвращается к scaled BE (79,036).

В reconciled primary group `сжимается + funding_negative` (n=32) — 71.9% up_extension. Это означает что в большинстве случаев pyramid loss не возвращается к BE; pyramid в этой группе **исторически чаще приводил к fail-сценарию** (loss больше).

### §7.6 Вариант 6 — Funding flip exit

| Метрика | v1 calc (n=81) | v2 in primary group (n=7) |
|---|---:|---:|
| Negative-funding setups | 81 | 7 |
| Flip rate | **100.0%** | 100.0% |
| Часов до flip — median | 65h | n/a |
| Цена в момент flip — median | +1.31% от setup (~83,378) | n/a |
| После flip — up_extension | 53.1% | 85.7% |
| После flip — pullback_continuation | 46.9% | 14.3% |
| После flip — down_to_anchor | 0.0% | 0.0% |
| 24h move ПОСЛЕ flip — median | −0.64% | n/a |

В 100% случаев setup'ов с отрицательным funding в течение 240h funding flipped к ≥0. Median — через 65h на цене ~+1.3% выше setup.

---

## §8 Сводная таблица — reconciled probabilities

Probability из reconciled primary group `сжимается + funding_negative` (n=32) где доступно.

| Вариант | Trigger | PnL USD | Probability (full base) | Probability (reconciled n=32) | Источник |
|---|---|---:|---:|---:|---|
| **1A** Stop 82,400 | пробой | −4,763 | 94.6% | (group reaches 82,400 ≥ all) | v1+v2 совпадают |
| **1B** Stop 83,000 | пробой | −5,613 | 83.7% | high | v1+v2 |
| **1C** Stop 84,000 | пробой | −7,029 | 74.9% | high | v1+v2 |
| **1D** Stop 85,000 | пробой | −8,445 | 47.5% | medium | v1+v2 |
| **2A** Exit 80,000 | откат | −1,365 | 64.3% | depends, 28.1% see pullback in group | reconciled |
| **2B** BE 79,036 | откат до entry | 0 | 56.4% | low (28.1% pullback) | reconciled |
| **2C** Exit 78,000 | глубокий откат | +1,467 | 48.8% | 28.1% upper bound | reconciled |
| **2D** Exit 77,000 | очень глубокий откат | +2,883 | 35.2% | <28.1% (subset) | reconciled |
| **3** Trailing 80/79/77 | partial fills | до +$743 при full | 35.2% full | n/a в reconciled (n слишком мал) | v1 |
| **4** Hold до 75,200 | full anchor | +5,432 | 14.3% | **0.0%** | reconciled (consistent v1+v2) |
| **5** Pyramid +1 BTC @ 83k | breach + add | +3,964 / −24,970 | 47.9% / 52.1% | 71.9% up_ext (loss) / 28.1% pullback (success) | reconciled |
| **6** Funding flip | rate ≥ 0 | depends | 100% (median 65h, цена +1.31%) | 100% | v1 |

---

## §8b Что выбор reconciled classification меняет

| | v1 закрепил | v2 закрепил | v3 reconciled |
|---|---|---|---|
| Primary group | `vola_compressing + fund_neg` n=52 | `стабильный/стабильная/funding_near_zero` n=38 | `сжимается + funding_negative` n=32 |
| up_extension % | 46.2% | 21.1% | **71.9%** |
| pullback_continuation % | 53.8% | 78.9% | **28.1%** |
| down_to_anchor % | 0.0% | 0.0% | **0.0%** (consistent) |
| Главная причина различия | funding порог <0 (loose) | bug: nearest_groups через Euclidean с битым volume_ratio | strict funding bucket + corrected volatility match |

**Главное reconciled наблюдение:** в подгруппе с компрессирующейся волатильностью + глубоко отрицательным funding (32 случая в 1y) **исторически 72% разрешались up_extension'ом**, не pullback'ом. v1 недооценил up_extension долю из-за более слабого funding порога; v2 mис-классифицировал из-за volume baseline bug.

---

## §9 Дополнительные signals для мониторинга

Из обоих прогонов:

| Signal | Источник | Что означает в данных |
|---|---|---|
| `oi_fell > 5%` в setup-окне | v1 | n=42 → **100% pullback_continuation**, 0% up_extension |
| `volume_trend = падает` | v2 | n=68 → 72.1% pullback_continuation, 1.5% down_to_anchor |
| `vol_divergence = True + fund→0` | v1 | n=92 → 31.5% down_to_anchor (рост anchor probability) |
| `funding flip к ≥0` | v1 | 100% реализуемость в neg-funding setups, median 65h, цена +1.31% выше setup |
| `vola_trend = расширяется + oi_growing` | v1 | n=92 → 33.7% up_ext / 33.7% pullback / 32.6% sideways (split) |
| Volume ratio как валидный signal | — | **NOT VALID** при текущих data sources (CP2 4.315x — артефакт) |

---

## §10 Что foundation НЕ говорит

| Вопрос | Ответ |
|---|---|
| Какой вариант лучший | Out of scope. Решение оператора. |
| Будет ли funding flip предшествовать развороту | Median 24h move после flip = −0.64%, слабый сигнал |
| Гарантия достижения уровня | Все «% достигли» — historical frequency, не prediction |
| Точная цена разворота | Distribution в JSON, не точечная цель |
| Liquidation cascade dynamics | 1y лог не сохранён |
| Orderbook depth | Не сохранён |
| Что произошло за 6 дней между концом 1y данных (2026-05-01) и сейчас | Foundation не покрывает |
| Apples-to-apples live volume signal | Невозможен — live и historical из разных feeds |

---

## §11 Reconciliation findings

| Что | v1 | v2 | Reconciled v3 | Обоснование |
|---|---|---|---|---|
| Funding bucket boundary | `<0` (loose) | `<-5e-5` (strict) | **strict** `<-5e-5` | Operator's −8.2e-5 в обоих негативный; strict даёт более чистое разделение (59.5% vs 53.1% up_ext) |
| Volatility classification | `expanding` / `stable` / `compressing` (15% threshold) | `расширяется` / `стабильная` / `сжимается` (15% threshold) | **same** | Идентичная логика, разные ярлыки |
| Volume ratio metric | `mean(window) / mean(30d)` в одном источнике | `mean(live 144h market_1m) / mean(historical 30d full_features)` | **deprecated** | v2 — apples-to-oranges (разные feeds); v1 — same source но низкая полезность как фактор |
| ATR source | proxy через abs close-to-close | real high/low из pattern_memory CSV | **real OHLC** | Real ATR доступен исторически; используем где можно |
| Higher highs counter | rolling 4h-window max compare | running max counter в 144h окне | **CP2** | Чище логика, but small numerical difference |
| Closest-group selection | manual filter по trend labels | **Euclidean distance** по 5-фактор vector с битым volume_ratio | **manual filter** | v2's nearest_groups не валидно: distance argued by buggy volume_ratio 4.3x |
| Closest group n | 52 | 38 | **32** | Strict funding + сжимается → меньшая группа но чище signal |
| Outcome distribution в primary | 0/46/54/0 | 0/21/79/0 | **0/72/28/0** | v3 даёт более concentrated up_extension lean |
| Volume trend label для current | not used | `растёт` (live) | **noted but not used in classification** | Volume signal not reliable cross-feed |

---

## §12 Anti-drift summary

- v1 и v2 не удалены, оба архивированы в `_archive/`
- v3 — единый source of truth для текущей сессии
- Где v1 и v2 расходятся — обе версии указаны в §4.3, §6, §8b с явным источником
- Все probability в §8 идут из reconciled группы (§6)
- Никаких trade actions / predictions в этом документе

---

**Конец документа.** Все цифры воспроизводимы через два driver скрипта; раздел §11 разъясняет где и почему версии расходятся.
