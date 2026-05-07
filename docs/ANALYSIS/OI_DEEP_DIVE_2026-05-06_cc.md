# OI DEEP DIVE — 2026-05-06 (Claude Code independent run)

**Тип:** READ-ONLY анализ Open Interest на 406 аналогах
**TZ:** TZ-EXTENDED-BACKTEST-OI-EXIT-OPTIONS-INDEPENDENT-RUN, Блок 2
**Скрипт:** [`scripts/_oi_deep_dive_cc.py`](../../scripts/_oi_deep_dive_cc.py)
**Raw output:** [`_oi_deep_dive_cc.json`](_oi_deep_dive_cc.json)

Без trading advice. Без прогнозов.

---

## §1 OI метрики для каждого аналога (n=406)

Источник: `data/forecast_features/full_features_1y.parquet` колонка `sum_open_interest`. На каждый аналог рассчитан:

| Метрика | Описание |
|---|---|
| `oi_setup` | OI на момент setup (raw value) |
| `oi_change_pct` | (OI_end / OI_start − 1) × 100 в окне 144h |
| `oi_ratio_30d` | mean(OI window) / mean(OI 30d baseline) |
| `oi_trend` | bucket по `oi_change_pct`: `OI_up_>5%` / `OI_flat_±5%` / `OI_down_>5%` |
| `oi_divergence` | True если price_up в окне И oi_change_pct < 0 |

---

## §2 Outcome distribution по OI trend (одна ось)

| OI trend | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| **`OI_up_>5%`** | **208** | **25.5%** | 26.9% | 32.2% | 15.4% |
| `OI_flat_±5%` | 156 | 3.2% | 28.8% | 35.9% | 32.1% |
| **`OI_down_>5%`** | **42** | **0.0%** | **0.0%** | **100.0%** | 0.0% |

**Главное наблюдение:** все 42 случая с падающим OI (>5% drop в окне роста) дали **pullback_continuation** — ни один не дошёл до anchor, ни один не дал up_extension. OI падающий при растущей цене — это сигнал short-covering или distribution, и эпизод исторически разрешался через откат с восстановлением.

---

## §3 OI ratio 30d (одна ось)

| OI ratio bucket | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `OI_ratio_>1.05` | 142 | **35.2%** | 19.7% | 26.8% | 18.3% |
| `OI_ratio_~1.0` | 130 | 0.0% | 35.4% | 41.5% | 23.1% |
| `OI_ratio_<0.95` | 134 | 8.2% | 19.4% | 47.0% | 25.4% |

**Высокий OI ratio (>1.05x от 30d baseline) — самый сильный предсказатель `down_to_anchor`** (35.2% vs 0% при ratio ~1.0). Раздутый OI на росте часто разрешается через сброс и заход к anchor.

---

## §4 OI vs price divergence

| Divergence | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `True` (цена↑ + OI↓) | 96 | 5.2% | 5.2% | **84.4%** | 5.2% |
| `False` | 310 | 17.1% | 31.0% | 27.1% | 24.8% |

**OI divergence (price up + OI down)** — **84.4% pullback_continuation**. Только 5.2% дают up_extension. Это второй сильнейший signal в сторону отката.

---

## §5 Cross-tab OI × Funding (n ≥ 10)

| OI + Funding | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `OI_up + funding_negative` | **40** | **0.0%** | **57.5%** | 42.5% | 0.0% |
| `OI_up + funding_near_zero` | 21 | 23.8% | 38.1% | 38.1% | 0.0% |
| `OI_up + funding_positive` | 147 | **32.7%** | 17.0% | 28.6% | 21.8% |
| `OI_flat + funding_near_zero` | 80 | 5.0% | 32.5% | 47.5% | 15.0% |
| `OI_flat + funding_positive` | 74 | 1.4% | 23.0% | 24.3% | **51.4%** |
| `OI_down + funding_near_zero` | 34 | 0.0% | 0.0% | **100.0%** | 0.0% |

**Ключевые наблюдения:**
1. `OI_up + funding_negative` (n=40): 0% down_to_anchor, 57.5% up_extension — **OI растёт + funding negative = squeeze setup**.
2. `OI_up + funding_positive` (n=147): 32.7% down_to_anchor — растущий OI при positive funding — самая bear-friendly комбо.
3. `OI_down + funding_near_zero` (n=34): 100% pullback_continuation — без исключений.

---

## §6 Triple cross OI × Funding × Volatility (n ≥ 5)

Самые информативные комбо:

| OI + Fund + Vola | n | down | up_ext | pullback | side |
|---|---:|---:|---:|---:|---:|
| **`OI_up + fund_neg + compressing`** | **31** | **0.0%** | **74.2%** | 25.8% | 0.0% |
| `OI_up + fund_neg + stable` | 9 | 0.0% | 0.0% | **100.0%** | 0.0% |
| `OI_up + fund_pos + stable` | 46 | **89.1%** | 0.0% | 10.9% | 0.0% |
| `OI_up + fund_pos + compressing` | 15 | 46.7% | 0.0% | 40.0% | 13.3% |
| `OI_flat + fund_near_zero + compressing` | 43 | 0.0% | 2.3% | **72.1%** | 25.6% |
| `OI_flat + fund_near_zero + expanding` | 22 | 18.2% | **81.8%** | 0.0% | 0.0% |
| `OI_down + fund_near_zero + compressing` | 15 | 0.0% | 0.0% | **100.0%** | 0.0% |
| `OI_down + fund_near_zero + stable` | 19 | 0.0% | 0.0% | **100.0%** | 0.0% |

**Контрастные пары:**
- `OI_up + fund_neg + compressing` (n=31) → **74.2% up_extension** vs `OI_up + fund_pos + stable` (n=46) → **89.1% down_to_anchor**. Тот же OI-up, но funding и vola меняют исход на противоположный.

---

## §7 Текущий OI status (proxy)

Из последнего бара 1y window (2026-04-30 23:00 UTC, 6 дней назад относительно операторского setup):

| Метрика | Значение | Bucket |
|---|---:|---|
| `oi_setup` | 95,322.9 | — |
| `oi_change_pct_window` | −0.94% | `OI_flat_±5%` |
| `oi_ratio_30d` | 1.014 | `OI_ratio_~1.0` |
| `oi_divergence` | False | — |
| Funding bucket (operator current) | `funding_negative` | (per v3) |
| Volatility trend | `compressing` | (per v3) |

**Caveat:** OI здесь — proxy на 2026-04-30. Live OI на 2026-05-06 не доступен в файле. Реальный OI к моменту setup'а оператора может отличаться, но за 6 дней без существенного движения price/OI инверсии вряд ли изменился bucket.

---

## §8 Match текущего setup'а в OI cross-tabs

Ближайшая комбинация по proxy данным: `OI_flat + funding_negative + compressing`.

| Combo | n | down | up_ext | pullback | side |
|---|---:|---:|---:|---:|---:|
| `OI_flat + funding_negative` (без vola) | 2 | 0.0% | 100.0% | 0.0% | 0.0% |
| `OI_flat + funding_near_zero + compressing` (proxy fallback) | 43 | 0.0% | 2.3% | 72.1% | 25.6% |
| `OI_up + funding_negative + compressing` (если OI растёт) | 31 | 0.0% | 74.2% | 25.8% | 0.0% |

**Проблема:** `OI_flat + funding_negative` имеет всего **n=2** в 1y subset — слишком мало для distribution-claim. Возможные интерпретации:

1. Если OI bucket текущего setup'а действительно `OI_flat`, то ближайшая большая группа (`OI_flat + fund_near_zero + compressing`, n=43) даёт **72.1% pullback / 0% down / 2.3% up_ext**. Но funding_near_zero ≠ операторскому funding_negative.
2. Если фактический OI окажется растущим (OI_up bucket), то применима группа n=31 с **74.2% up_ext / 25.8% pullback**. То же что и без OI-кондиционирования.
3. Конфликт с funding-кондиционированной группой `funding_negative` (n=42): 0/59.5/40.5/0.

**Reconciled OI-aware interpretation:** OI flat при funding negative — структурно более редкая ситуация (n=2 в 1y). Без OI-кондиционирования группа `funding_negative` (n=42) даёт **59.5% up_extension / 40.5% pullback / 0% down**. Это лучшая базовая оценка в условиях недостаточной OI-выборки.

---

## §9 OI-based signals для мониторинга

| Signal | Smysl |
|---|---|
| OI начинает падать (>5% за 6 дней) | Historical 100% pullback_continuation, **0% up_extension** (n=42) |
| OI vs price divergence (price up + OI down) | Historical 84.4% pullback_continuation (n=96) |
| OI ratio к 30d > 1.05x | Historical 35.2% down_to_anchor (n=142) |
| OI растёт + funding flips от negative к ≥0 | Меняет combo с up-ext-leaning на down-leaning (см. §5) |

---

## §10 Что foundation НЕ говорит

| Вопрос | Ответ |
|---|---|
| Что именно делает OI прямо сейчас (live) | Файл данных заканчивается 2026-04-30 |
| OI dynamics за 2024 | Нет данных в pattern_memory |
| Order book imbalance | Не сохранён |
| Liquidation events | Не сохранён за 1y |
| Что станет с OI после flip funding | OI и funding evolve взаимно, причинная связь не моделируется |

---

**Конец Блока 2.** Главные OI-сигналы: падающий OI (>5%) → 100% pullback; OI divergence → 84% pullback; OI ratio >1.05x + funding_pos → 32.7% down_to_anchor. Текущий setup в OI_flat — недостаточно данных для OI-уточнения reconciled группы.
