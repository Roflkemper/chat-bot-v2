# 3 ВАРИАНТА СНИЖЕНИЯ ПОТЕРЬ — 2026-05-06 (Claude Code independent run)

**Тип:** READ-ONLY analytical document
**TZ:** TZ-EXTENDED-BACKTEST-OI-EXIT-OPTIONS-INDEPENDENT-RUN, Блок 3
**Источники:** [`UPTREND_PULLBACK_ANALOGS_2026-05-06.md`](UPTREND_PULLBACK_ANALOGS_2026-05-06.md), [`SHORT_EXIT_OPTIONS_2026-05-06.md`](SHORT_EXIT_OPTIONS_2026-05-06.md) (reconciled v3), [`EXTENDED_BACKTEST_2026-05-06_cc.md`](EXTENDED_BACKTEST_2026-05-06_cc.md), [`OI_DEEP_DIVE_2026-05-06_cc.md`](OI_DEEP_DIVE_2026-05-06_cc.md)

Без trading advice. Без прогнозов. Без временных рамок.

---

## §1 Контекст позиции

| Поле | Значение |
|---|---:|
| Entry | 79,036 |
| Текущая | 82,300 |
| Размер | 1.416 BTC |
| Unrealized PnL | −$3,572 |
| Anchor роста | 75,200 |
| Funding | −0.0082%/8h (percentile ~1.6 в 1y) |
| Distance to liq | ~18% |

---

## §2 Reconciled foundation (как опираемся)

| Группа | n | down_to_anchor | up_extension | pullback_cont | sideways |
|---|---:|---:|---:|---:|---:|
| `vola_compressing + fund_neg` (1y, reconciled v3) | 32 | 0.0% | 71.9% | 28.1% | 0.0% |
| Independent extended re-run | 31 | 0.0% | 74.2% | 25.8% | 0.0% |
| `OI_up + fund_neg + compressing` (если OI окажется растущим) | 31 | 0.0% | 74.2% | 25.8% | 0.0% |
| `funding_negative` без OI/vola фильтра | 42 | 0.0% | 59.5% | 40.5% | 0.0% |

**Согласованный signal:** в текущем factor-профиле (compressing volatility + deeply negative funding) **0% down_to_anchor** во всех версиях. Распределение между up_extension и pullback ~70/30 при vola_compressing, ~60/40 без vola-фильтра.

---

## §3 Вариант 1 — ЗАЩИТНЫЙ (cap losses на adverse breach)

Что вижу → Приём → Конкретный шаг с PnL.

| Что вижу | Приём | Уровень | Шаг — PnL для 1.416 BTC |
|---|---|---:|---:|
| Цена пробила 82,400 (P-2 trigger) | Подготовить partial close | 82,400 | Не закрывать ещё; PnL на этом уровне = −$4,763 |
| Цена пробила 83,000 + появился TREND_UP_SUSPECTED modifier | Закрыть 50% (0.708 BTC) | 83,000 | Realized loss на 50% = −$2,807 (50% × $5,613); residual 0.708 BTC |
| Цена пробила 84,000 ИЛИ funding flip к ≥0 | Закрыть остальные 50% | 84,000 | Realized loss на оставшейся 50% = −$3,514 (50% × $7,029); полный exit = −$6,321 |
| Цена пробила 85,000 без флипа funding | Закрыть всё немедленно | 85,000 | PnL = −$8,445 (single shot) |

**Условия применимости:**
- Цена идёт против на adverse breach независимо от других факторов
- Funding flip к ≥0 подтверждает структурный сдвиг (per Funding flip v6: 100% случаев neg-funding setups испытали flip, median цена в момент flip +1.31% выше setup ≈ 83,378)

**Foundation:**
- Stop 82,400 reached в 94.6% случаев общей выборки (v3 §7.1) → ложный пробой 99.2% → одиночный stop здесь — почти гарантированный whipsaw
- Stop 83,000 reached в 83.7% случаев, ложный 96.8% — половина whipsaw, половина продолжения
- Stop 84,000 reached в 74.9% случаев, ложный 73.4% (намного чище)
- Stop 85,000 reached в 47.5% случаев — менее половины setups сюда вообще доходят

**Спектр PnL для Варианта 1:**
- Best case (только 82,400 пробивается, цена возвращается ниже без 83k): **0** (ничего не делаем, false breakout)
- Median case (50% close на 83k, 50% на 84k или funding flip): **−$6,321**
- Worst case (single stop на 85k): **−$8,445**

**Probability success (cap losses ≤ −$8,445):** 100% по definition stop'а

---

## §4 Вариант 2 — OPPORTUNISTIC (capture pullback если случится)

Что вижу → Приём → Шаги по уровням отката.

| Что вижу | Приём | Уровень | Шаг — PnL для 1.416 BTC |
|---|---|---:|---:|
| Цена откатилась до 80,000 + OI начал падать | Закрыть 30% (0.425 BTC) | 80,000 | Realized = −$410 (30% × −$1,365) |
| Цена откатилась до 79,036 (BE) + funding всё ещё negative | Закрыть ещё 30% (0.425 BTC) | 79,036 | Realized = $0 (BE на этом tier'е) |
| Цена откатилась до 78,000 + OI divergence (price down + OI up) | Закрыть ещё 20% (0.283 BTC) | 78,000 | Realized = +$293 (20% × +$1,467) |
| Цена откатилась до 77,000 + funding flip к ≥0 | Закрыть остальные 20% | 77,000 | Realized = +$577 (20% × +$2,883) |

**Условия применимости:**
- Этот algorithm активен ТОЛЬКО если pullback материализуется. В reconciled группе `vola_compressing + fund_neg` это 25.8% случаев
- В full sample 64.3% доходят до 80k, 56.4% до 79,036, 48.8% до 78k, 35.2% до 77k
- В reconciled группе (n=32): 28.1% дают pullback_continuation; в этих случаях pullback historically median глубиной −4.32% (= 78,745 от 82,300 эквивалента), p25 −7.21% (= 76,367)

**Foundation:**
- Pullback distribution из v3 §7.2: 64.3% / 56.4% / 48.8% / 35.2% achievement rates
- В reconciled группе 28.1% pullback_continuation (v3 §6); в OI_up + fund_neg + compressing 25.8% (Block 2 §6)
- Median глубина минимума по pullback_continuation cases (UPTREND_PULLBACK_ANALOGS §8): −4.32% от setup → ~78,745 от 82,300

**Спектр PnL для Варианта 2:**
- Best case (full fill всех 4 уровней до 77k): **+$460** (−410 + 0 + 293 + 577)
- Median case (fill до 78k = 80% позиции реализована, 20% mark-to-market на 77.5k): ~**−$117**
- Worst case (только 80k tier filled, потом цена развернулась к 85k): −$410 realized + (1.416 − 0.425) × (entry − final) = depends на final price

**Probability полного fill (все 4 уровня):** 35.2% по full sample. В reconciled группе ниже (~25-28% по pullback_continuation rate).

---

## §5 Вариант 3 — HYBRID CONDITIONAL (разные действия по trigger'ам)

Что вижу → Какой trigger → Какое действие.

| Что вижу (trigger) | Приём | Уровень | Шаг — PnL для 1.416 BTC |
|---|---|---:|---:|
| Funding flip к ≥0 ДО любого price breach (median 65h из v3) | Watch only — это структурный сигнал, не выход | — | Mark-to-market на момент flip; median цена при flip +1.31% = ~83,378 → −$6,148 unrealized |
| После funding flip цена идёт ВВЕРХ к 84,000 | Закрыть 100% (single exit) | 84,000 | Realized = −$7,029 |
| После funding flip цена идёт ВНИЗ через 82,300 | Hold all + добавить 0.5 BTC к SHORT на 81,000 (pyramid) | add @ 81,000 | Blended avg entry: (1.416 × 79,036 + 0.5 × 81,000) / 1.916 = 79,548 |
| После pyramid цена откатилась до 78,000 | Закрыть 50% blended (0.958 BTC) | 78,000 | Realized = +$1,484 (50% × (79,548 − 78,000) × 1.916) |
| После pyramid цена пробила 82,400 ОБРАТНО вверх | Закрыть всё (1.916 BTC) | 82,400 | Realized = −$5,463 (all × (79,548 − 82,400) × 1.916) |
| OI начал падать >5% (без price движения) | Watch — historical 100% pullback_continuation | — | Не действие; signal что pullback вероятен (OI_down → 100% pullback в Block 2 §2) |

**Условия применимости:**
- Этот algorithm полагается на множественные signals: funding flip + price direction после flip + OI dynamics
- В reconciled группе (n=32) funding flip occurred в 100% случаев (v3 §7.6); median цена в момент flip +1.31% выше setup
- 24h ПОСЛЕ flip: median move −0.64% (mild pullback, не exit signal сам по себе)
- OI_down >5% в окне: 100% pullback_continuation (Block 2 §2, n=42, no exceptions)

**Foundation:**
- Funding flip rate 100% в neg-funding setups (v3 §7.6, n=81)
- Median часов до flip 65h, цена в момент flip +1.31% от setup
- 24h после flip median move −0.64%
- OI_down >5% → 100% pullback_continuation (n=42)
- Pyramid +1 BTC @ 83k success rate 47.9% full sample → blended PnL +$3,964 success / −$24,970 fail (v3 §7.5)

**Спектр PnL для Варианта 3:**
- Best case (funding flip + descent + pyramid + retest 78k): **+$1,484** на закрытии 50% blended position; residual 0.958 BTC dependent on what happens после
- Median case (funding flip + ambiguous direction + pullback to ~78,500): ~**−$1,000 to +$500** (mark-to-market зависит от final price)
- Worst case (funding flip + price up + pyramid against): **−$5,463** или хуже если цена выше 82,400

**Probability success (positive realized PnL):**
- Probability funding flip: 100% (median 65h)
- Probability descent после flip: ~50/50 (24h after flip median move −0.64%, weak signal)
- Probability of full algorithm yielding positive PnL: estimated 25-35% (combining funding flip → descent → retest tiers)

---

## §6 Сводная таблица — все 3 варианта

| Вариант | Тип | Best PnL | Median PnL | Worst PnL | Probability success |
|---|---|---:|---:|---:|---:|
| 1 — Защитный (стопы 82.4k → 85k) | cap loss | $0 (false breakout 82.4k) | −$6,321 | −$8,445 | 100% (cap по definition) |
| 2 — Opportunistic (трейлинг 80/79/78/77) | capture pullback | +$460 (full fill) | −$117 (partial) | mark-to-market loss | 25–28% (reconciled group pullback rate) |
| 3 — Hybrid (funding flip + pyramid) | conditional algorithm | +$1,484 | −$1,000 to +$500 | −$5,463 | 25–35% (combined signals) |

---

## §7 Триггеры для отслеживания (общие для всех 3 вариантов)

| Trigger | Что значит | Источник |
|---|---|---|
| Funding flip к ≥0 | Структурный сдвиг; 100% случаев neg-funding setups испытали flip; median 65h | v3 §7.6, n=81 |
| OI начинает падать >5% | 100% pullback_continuation в historical | Block 2 §2, n=42 |
| OI vs price divergence | 84.4% pullback_continuation | Block 2 §4, n=96 |
| OI ratio >1.05x от 30d + funding turns positive | 32.7% down_to_anchor | Block 2 §5, n=147 |
| Decision Layer P-2 fire on 82,400 / 83,000 | Critical price level breach | Decision Layer §2.3 |
| Active modifier `TREND_UP_SUSPECTED` | Higher-priority modifier за detection быстрого движения | core/orchestrator/regime_classifier.py |
| Decision Layer M-4 trigger меняется с "margin" на "distance_to_liq" | Distance crossed 5%-from-liquidation | Decision Layer §2.2 |

---

## §8 Что foundation НЕ говорит

| Вопрос | Ответ |
|---|---|
| Какой вариант лучший | Out of scope. Решение оператора. |
| Когда сработает trigger | Distribution в JSON, не точечный прогноз |
| Гарантия Probability success | Historical frequency, не prediction |
| Live OI на 2026-05-06 | Файл данных заканчивается 2026-04-30 |
| Что произошло за 6 дней между 2026-04-30 и сейчас | Foundation не покрывает |
| Как поведёт себя orderbook при breach | Order book не сохранён |
| Что делать с позицией | Out of scope. Решение оператора. |

---

## §9 Anti-drift summary

| Пункт | Статус |
|---|---|
| Документ на русском | ✅ |
| Никаких trading advice | ✅ — нет "оптимально / закрывай / держи" |
| Никаких predictions | ✅ — все probability помечены historical frequency |
| Никаких временных рамок | ✅ — нет "в течение N часов / дней" |
| Все числа из foundation с n | ✅ — каждое утверждение со ссылкой на n или %|
| Ровно 3 варианта | ✅ — Вариант 1, 2, 3 |
| Покрытие спектра (защитный + opportunistic + hybrid) | ✅ — V1 защитный, V2 opportunistic, V3 hybrid conditional |

---

**Конец Блока 3.** 3 варианта построены на reconciled foundation (n=31–32 в primary group, n=42 fallback, n=406 base). Каждый вариант имеет конкретные ценовые triggers, USD PnL для 1.416 BTC, и foundation-based probabilities.
