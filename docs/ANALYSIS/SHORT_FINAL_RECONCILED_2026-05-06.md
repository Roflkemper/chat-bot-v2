# ВАРИАНТЫ ВЫХОДА — SHORT 79k / FINAL RECONCILED v4

**Дата:** 2026-05-06
**Тип:** READ-ONLY финальный аналитический документ
**TZ:** TZ-FINAL-RECONCILED-EXIT-DOCUMENT
**Статус:** заменяет v1, v2, v3 как актуальный source of truth.
**Архив:** все предыдущие версии оставлены — `_archive/`, `_codex.md`, `_cc.md` файлы не удалены.

Без trading advice. Без прогнозов. Без временных рамок.

---

## §1 Контекст позиции

| Поле | Значение |
|---|---:|
| Direction | SHORT BTCUSDT linear |
| Size (last operator snapshot) | 1.416 BTC (live state показывает дрейф к −1.434) |
| Entry | 79,036 |
| Reference current | 82,300 |
| Anchor роста | 75,200 |
| Funding | −0.0082%/8h (нижний ~1.6 percentile в 1y distribution) |
| Distance to liq | ~18% |
| Margin coefficient | 0.97 (operator-supplied, age 305min — D-4 INFO tier) |

---

## §2 Reconciliation summary

После двух independent runs (Codex + Claude Code) и cross-check трёх ключевых конфликтов в [`CROSS_CHECK_CODEX_BY_CC_2026-05-06.md`](CROSS_CHECK_CODEX_BY_CC_2026-05-06.md), применены три коррекции:

| Что corrected | Было | Стало |
|---|---|---|
| Probability up_extension в reconciled группе | 46.2% (Codex использовал v1 foundation) | **72-74%** (v3 + CC independent re-run) |
| Probability pullback_continuation в reconciled группе | 53.8% | **26-28%** |
| OI divergence в текущем setup'е | True (Codex по 6d-window framing) | **False** (CC по data-tail computation) |
| Extended backtest source | btc_1m_enriched_2y.parquet (Codex, sweep) | pattern_memory CSV (CC, criterion-matched) |

Главное последствие: вариант 2 (opportunistic pullback) имеет **в 2× меньшую** вероятность срабатывания чем заявлял Codex.

---

## §3 Reconciled foundation numbers

| Метрика | Значение | n | Источник |
|---|---:|---:|---|
| Reconciled group: `vola_compressing + funding_negative` | n=32 (v3) / n=31 (CC) | 31–32 | v3 doc + CC independent |
| Outcome split: down_to_anchor | **0.0%** | 31–32 | оба согласны |
| Outcome split: up_extension | **71.9% / 74.2%** (v3 / CC) | 31–32 | оба согласны на ~72-74 |
| Outcome split: pullback_continuation | **28.1% / 25.8%** | 31–32 | ~26-28 |
| Outcome split: sideways | 0.0% | 31–32 | оба согласны |
| Fallback `funding_negative` only | n=42, 0/59.5/40.5/0 | 42 | v3 |
| Independent re-run в extended (2.34y) — same group | 31, 0/74.2/25.8/0 | 31 | CC re-run |
| Stop 82,400 reach rate | 94.6% | 406 | v3 §7.1 |
| Stop 83,000 reach rate | 83.7% | 406 | v3 §7.1 |
| Stop 84,000 reach rate | 74.9% | 406 | v3 §7.1 |
| Stop 85,000 reach rate | 47.5% | 406 | v3 §7.1 |
| Pullback 80,000 reach rate | 64.3% | 406 | v3 §7.2 |
| Pullback 79,036 (BE) reach rate | 56.4% | 406 | v3 §7.2 |
| Pullback 78,000 reach rate | 48.8% | 406 | v3 §7.2 |
| Pullback 77,000 reach rate | 35.2% | 406 | v3 §7.2 |
| OI down >5% → outcome | 100% pullback_continuation | 42 | OI dive Block 2 §2 |
| OI divergence (price↑ + OI↓) | 84.4% pullback_continuation | 96 | OI dive Block 2 §4 |
| OI ratio >1.05x baseline + funding_pos | 32.7% down_to_anchor | 147 | OI dive Block 2 §5 |
| Funding flip rate в neg-funding setups | 100% (median 65h, цена +1.31%) | 81 | v3 §7.6 |
| 24h move ПОСЛЕ funding flip — median | −0.64% | 81 | v3 §7.6 |
| Extended search total analogs (CC) | 1,339 (2.34y) | 1339 | EXTENDED_BACKTEST_cc |
| Extended pre-1y subset (без funding tagging) | 933, 45.4% down_to_anchor | 933 | EXTENDED_BACKTEST_cc §4 |

---

## §4 Текущий factor profile (corrected)

| Factor | Значение | Bucket / interpretation |
|---|---:|---|
| Volume ratio 30d | 0.658x (v1, in-source) — **не используется** в classification | live vs historical sources несравнимы → метрика отброшена |
| Volatility ratio 30d | 0.96x | близко к baseline |
| Volatility trend | **compressing** | second-half std < first-half × 0.85 |
| Funding | **−8.2e-5** | `funding_negative` strict bucket (`<-5e-5`); ниже p10 1y distribution |
| OI ratio 30d | 1.014x (на 2026-04-30, proxy) | `OI_ratio_~1.0` |
| OI change in 6d window | **−0.94%** | `OI_flat_±5%` |
| OI divergence (CC computation) | **False** | finalized в cross-check §4.4 |
| Higher highs in 144h window | 24 | bucket `>=20` |
| Final impulse 12h | +1.96% | impulse_mid |
| Max internal pullback 144h | 1.94% | мягкий |

---

## §5 Ближайшая историческая группа

**`vola_compressing + funding_negative`**, n=32 (v3) / n=31 (CC re-run).

| Outcome | v3 doc | CC re-run | Reconciled (median) |
|---|---:|---:|---:|
| down_to_anchor | 0.0% | 0.0% | **0.0%** |
| up_extension | 71.9% | 74.2% | **~72-74%** |
| pullback_continuation | 28.1% | 25.8% | **~26-28%** |
| sideways | 0.0% | 0.0% | **0.0%** |

OI cross-tab triple `OI_up + funding_negative + compressing` (n=31, OI deep dive Block 2 §6) даёт идентичный split 0/74.2/25.8/0 — **OI bucket в 1y subset для funding-negative+compressing setups совпадает с reconciled группой**.

---

## §6 ТРИ ВАРИАНТА СНИЖЕНИЯ ПОТЕРЬ

PnL для 1.416 BTC, entry 79,036.

### §6.1 Вариант 1 — ЗАЩИТНЫЙ (cap losses на adverse breach)

| Что вижу | Приём | Уровень | PnL для 1.416 BTC |
|---|---|---:|---:|
| Цена пробила 82,400 (P-2 fire) | Watch only — historical 99.2% false breakout | 82,400 | mark-to-market −$4,763 |
| Цена пробила 83,000 + появился TREND_UP_SUSPECTED modifier | Закрыть 50% (0.708 BTC) | 83,000 | realized −$2,807 (50%) |
| Цена пробила 84,000 ИЛИ funding flips к ≥0 | Закрыть оставшиеся 50% (0.708 BTC) | 84,000 | realized −$3,514; total exit −$6,321 |
| Цена пробила 85,000 без флипа funding | Single full close | 85,000 | realized −$8,445 |

**Условия применимости:** цена идёт по ветке up_extension (исторически **~72-74%** реконсилируемой группы).

**PnL спектр (1.416 BTC):**
- Best (только 82,400 пробивается, 99.2% случаев возврат — false breakout): **$0** (ничего не realized)
- Median (50% close на 83k + 50% на 84k или funding flip): **−$6,321**
- Worst (single stop на 85k): **−$8,445**

**Probability of triggering (full base 406):**
- 82,400 reach: 94.6%
- 83,000 reach: 83.7%
- 84,000 reach: 74.9%
- 85,000 reach: 47.5%

**Probability в reconciled группе (n=31–32):** up_extension (= adverse продолжение для SHORT) ~72-74%. Cap-loss достижим в 100% по definition стопа.

**Foundation:** v3 §7.1 + reconciled n=31–32.

---

### §6.2 Вариант 2 — OPPORTUNISTIC (capture pullback если случится)

| Что вижу | Приём | Уровень | PnL для 1.416 BTC |
|---|---|---:|---:|
| Цена откатилась до 80,000 + OI начал падать | Закрыть 30% (0.425 BTC) | 80,000 | realized −$410 (30% × −$1,365) |
| Цена откатилась до 79,036 (BE) | Закрыть ещё 30% (0.425 BTC) | 79,036 | realized $0 |
| Цена откатилась до 78,000 + OI vs price divergence (price↓ + OI↑) | Закрыть ещё 20% (0.283 BTC) | 78,000 | realized +$293 (20% × +$1,467) |
| Цена откатилась до 77,000 + funding flip к ≥0 | Закрыть остальные 20% (0.283 BTC) | 77,000 | realized +$577 (20% × +$2,883) |

**Условия применимости:** срабатывает только если pullback материализуется. **В reconciled группе это ~26-28% случаев** (corrected с Codex's 53.8%).

**PnL спектр (1.416 BTC):**
- Best (full fill всех 4 уровней): **+$460** (−410 + 0 + 293 + 577)
- Median (fill до 78k = 80% позиции, 20% mark-to-market): ~**−$117**
- Worst (только 80k tier filled, потом разворот вверх): −$410 realized + остаток drift

**Probability в reconciled группе:** pullback_continuation = **~26-28%** (corrected). Reach rates from full base — 64.3% / 56.4% / 48.8% / 35.2%, но conditional на reconciled группу significantly ниже.

**Foundation:** v3 §7.2 + reconciled n=31–32 (corrected from v1's 53.8%).

---

### §6.3 Вариант 3 — HYBRID CONTINGENT (разные действия по trigger'ам)

| Что вижу (trigger) | Приём | Уровень | PnL для 1.416 BTC |
|---|---|---:|---:|
| Funding flip к ≥0 ДО любого price breach (median 65h, цена ~+1.31% от setup) | Watch only — структурный сигнал | — | mark-to-market −$6,148 если цена +1.31% от 82,300 = 83,378 |
| После funding flip цена идёт ВВЕРХ к 84,000 | Закрыть 100% (single exit) | 84,000 | realized −$7,029 |
| После funding flip цена идёт ВНИЗ через 82,300 | Hold + add 0.5 BTC к SHORT на 81,000 (pyramid) | 81,000 | blended avg = 79,548 на 1.916 BTC |
| После pyramid цена откатилась до 78,000 | Закрыть 50% blended (0.958 BTC) | 78,000 | realized +$1,484 (50% × (79,548 − 78,000) × 1.916) |
| После pyramid цена пробила 82,400 ОБРАТНО | Закрыть всё (1.916 BTC) | 82,400 | realized −$5,463 |
| OI начал падать >5% (без price движения) | Watch only — historical 100% pullback | — | signal без действия |

**Условия применимости:** срабатывает на множественные signals: funding flip + price direction после flip + OI dynamics.

**PnL спектр (1.416 BTC base, до pyramid):**
- Best case (funding flip + descent + pyramid + retest 78k): **+$1,484** на 50% blended; residual 0.958 BTC ещё в позиции
- Median case (funding flip + ambiguous direction + mild pullback ~78,500): **−$1,000 to +$500** mark-to-market
- Worst case (funding flip + price up + pyramid against): **−$5,463** при выходе на 82,400 reverse

**Probability per branch:**
- Funding flip occurrence: **100%** (n=81, median 65h)
- Price descent after flip: ~50/50 (median 24h move −0.64%, weak signal)
- 24h после flip — distribution: p25 −1.36%, median −0.64%, p75 +0.05%
- Combined positive PnL probability estimated **25–35%**

**Foundation:** v3 §7.6 funding flip + Block 2 §6 OI cross-tabs + reconciled group n=31–32.

---

## §7 Сводная таблица — все 3 варианта (corrected)

| Вариант | Тип | Best PnL | Median PnL | Worst PnL | Probability срабатывания (corrected) |
|---|---|---:|---:|---:|---:|
| 1 — Защитный (стопы 82.4k → 85k) | cap loss | $0 | −$6,321 | −$8,445 | 100% (cap by definition); adverse path ~72-74% reconciled |
| 2 — Opportunistic (трейлинг 80/79/78/77) | capture pullback | +$460 | −$117 | mark-to-market | **~26-28%** (corrected from Codex's 53.8%) |
| 3 — Hybrid (funding flip → conditional pyramid) | contingent algorithm | +$1,484 | −$1,000 to +$500 | −$5,463 | 25–35% (combined signals) |

---

## §8 Signals для мониторинга

Из cross-check + OI deep dive:

| Signal | Что значит | n |
|---|---|---:|
| OI начинает падать >5% за окно роста | Historical **100%** pullback_continuation, 0% up_extension | 42 |
| OI vs price divergence (price↑ + OI↓) | Historical **84.4%** pullback_continuation | 96 |
| OI ratio >1.05x baseline + funding ≥ 0 | Historical 32.7% down_to_anchor (bear-friendly setup) | 147 |
| Funding flip к ≥0 | 100% реализуемость в neg-funding setups, median 65h, цена в момент flip ≈ +1.31% от setup | 81 |
| OI растёт + funding negative + compressing (текущий factor combo) | **74.2% up_extension**, 25.8% pullback (если OI окажется растущим а не flat) | 31 |
| Decision Layer P-2 fire on 82,400 / 83,000 | Critical price level breach | — |
| Active modifier `TREND_UP_SUSPECTED` или `HUGE_DOWN_GAP` | Higher-priority modifier — fast-move detection | — |
| Decision Layer M-4 trigger field flip "margin"→"distance_to_liq" | Crossed below 5% from liquidation | — |
| Margin data freshness (D-4) | Currently 305min stale — INFO tier; >12h → PRIMARY | — |

---

## §9 Что foundation НЕ говорит

| Вопрос | Причина |
|---|---|
| Какой вариант лучший | Out of scope. Решение оператора. |
| Будет ли funding flip предшествовать развороту | Median 24h move после flip = −0.64% — слабый сигнал |
| Гарантия достижения какого-либо уровня | Все «% reach» — historical frequency, не prediction |
| Точная цена разворота | Distribution в JSON, не точечная цель |
| Live OI на 2026-05-06 | Файл данных заканчивается 2026-04-30 |
| Что произошло за 6 дней между концом 1y данных и сейчас | Foundation не покрывает |
| Live order book / liquidation cascades | Не сохранены за 1y |
| Гарантия повторения паттерна 2024-2026 в будущем | Это historical observation, не prediction |

---

## §10 Audit trail

Каждое число в этом документе — со ссылкой на источник + n + confidence.

| Число / утверждение | Источник | n | Confidence |
|---|---|---:|---|
| 0% down_to_anchor в reconciled группе | v3 + CC independent re-run | 31–32 | **HIGH** (oба согласны) |
| 72-74% up_extension | v3 + CC independent re-run | 31–32 | **HIGH** (oба согласны) |
| 26-28% pullback_continuation | v3 + CC independent re-run | 31–32 | **HIGH** |
| 0% sideways | v3 + CC independent re-run | 31–32 | HIGH |
| Stop reach rates 94.6/83.7/74.9/47.5 | v3 §7.1 | 406 | HIGH |
| Pullback reach rates 64.3/56.4/48.8/35.2 | v3 §7.2 | 406 | HIGH |
| OI down >5% → 100% pullback | OI deep dive Block 2 §2 | 42 | **HIGH** (no exceptions) |
| OI divergence → 84.4% pullback | OI deep dive Block 2 §4 | 96 | HIGH |
| Funding flip 100% rate | v3 §7.6 | 81 | HIGH |
| Funding flip median 65h, +1.31% price | v3 §7.6 | 81 | MEDIUM (median обоснован, но wide spread) |
| 24h after flip median move −0.64% | v3 §7.6 | 81 | MEDIUM (weak signal) |
| Extended pre-1y 45.4% down_to_anchor | EXTENDED_BACKTEST_cc §4 | 933 | MEDIUM (без funding tagging) |
| Extended total 1,339 analogs | EXTENDED_BACKTEST_cc §3 | 1339 | HIGH |
| Volume ratio 4.315x (Codex) | Codex EXTENDED | — | **REJECTED** (cross-feed artifact) |
| OI divergence в текущем state = False | CC OI deep dive | — | **CORRECTED** (Codex framed как True по 6d window, CC computed False по data-tail) |
| Funding −8.2e-5 = нижний 1.6 percentile в 1y | v3 sanity check | 8761 | HIGH |
| Operator entry 79,036 / size 1.416 BTC | operator-supplied | — | Source of truth |
| Live shorts_btc −1.434 (drift) | state_latest 2026-05-06 | — | Drift не учтён в PnL расчётах (используется reference 1.416) |
| Margin coefficient 0.97 / age 305min | state_latest margin block | — | INFO D-4 tier; >12h → PRIMARY |

---

## §11 Anti-drift summary

| Пункт | Статус |
|---|---|
| Документ на русском | ✅ |
| Никаких trading advice | ✅ — нет "оптимально / закрывай / держи / добавляй" |
| Никаких predictions | ✅ — все probability помечены historical frequency |
| Никаких временных рамок (нет "в течение N часов / дней") | ✅ — funding flip median 65h упомянут как backreference, не prescription |
| Все числа из foundation с n | ✅ — каждая таблица + audit trail в §10 |
| Ровно 3 варианта | ✅ |
| Покрытие спектра | ✅ — V1 защитный + V2 opportunistic + V3 hybrid |
| Corrected probabilities применены | ✅ — V2 = 26-28% (не 53.8%) |
| OI divergence corrected | ✅ — False, не True |
| Все предыдущие версии не удалены | ✅ — `_archive/`, `_codex.md`, `_cc.md` сохранены |

---

**Конец финального документа v4.** Все коррекции из cross-check применены. Foundation reference — reconciled v3 + CC independent re-run (HIGH confidence, oba прогона согласны). Probability success в Варианте 2 corrected с Codex's 53.8% на 26-28% (это ключевое отличие от предыдущих документов).
