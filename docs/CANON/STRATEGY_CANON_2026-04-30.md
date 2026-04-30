# STRATEGY CANON 2026-04-30

**Source of truth для проекта Grid Orchestrator.**
**Последнее обновление:** 2026-04-30
**Создан в session:** 30.04.2026 utc
**Принцип:** этот документ читается ПЕРВЫМ при старте любой
новой сессии Claude/Code/Codex. Ссылается на existing docs.

---

## §1 АРХИТЕКТУРА ДВУХ ДВИЖКОВ

(Из устного описания оператора 2026-04-30, согласовано architect'ом)

### LONG-side
- Контракты: USDT-M (linear)
- Размер: USD-номинирован (например $100/$200 за ордер)
- PnL: USD-номинирован
- Поведение: цена ↑ на 1% → прямой +1% к notional
- Live боты: BTC-LONG-C, BTC-LONG-D (см. CUSTOM_BOTS_REGISTRY.md)

### SHORT-side
- Контракты: COIN-M (inverse)
- Размер: BTC-номинирован (например 0.001-0.003 BTC за ордер)
- PnL: BTC-номинирован
- Поведение: цена ↑ на 1% → потеря в BTC, НО BTC сам стал дороже на 1%
  в USD → частичная currency-валютная компенсация
- Live боты: TEST_1, TEST_2, TEST_3 (см. CUSTOM_BOTS_REGISTRY.md)

### Поведение в режимах рынка

**Боковик** (идеальный setup):
- Net direction risk ≈ 0
- Оба grid-движка независимо генерируют trades + realized PnL
- Volume растёт в обоих контрактах одновременно
- НЕ "ничего не теряешь" — обе стороны работают, **PnL =
  positive double-sided grind**

**Bull move:**
- LONG получает прямой directional gain (USD-номинирован)
- LONG-grid молотит микро-TPs на пути вверх
- SHORT-grid: позиция накапливается, unrealized in BTC
- BTC ↑ в USD → BTC-номинированный убыток конвертируется в меньший
  USD-убыток (currency cushion)
- SHORT-grid продолжает ловить downswings внутри тренда (накопление
  realized BTC, которые становятся ценнее)

**Bear move:** зеркально

### Volume metric — first-class objective
- Конкурс GinArea ranking'ует по volume + PnL
- Прежний результат конкурса оператора: $618k volume → 1-е место
- 30-day target оператора: $10.5M (из устного описания, расширение
  от docs/MASTER §1 "$8-10M бонус")
- Стратегия с двумя движками генерирует volume в 2× больше чем
  одна сторона на том же депозите

### Метрики которые нужны
Никогда не считать только USD-PnL. Правильный вид:
- Realized PnL (native): USD для LONG, BTC для SHORT
- Realized PnL (USD-norm at exit price): USD для обеих сторон
- Trading volume (USD): обе стороны
- Trades count: per-side и total
- Net BTC exposure: +size_long_USD/price − size_short_BTC
- Currency hedge ratio: f(size_long_USD, size_short_BTC, price)
- PnL/volume velocity (efficiency)
- PnL per day (rate)

---

## §2 SIZING RULES

### Идеальная схема (как оператор хочет, идеализированно)

(Из устного описания 2026-04-30)

| Режим | LONG-side | SHORT-side | Логика |
|---|---|---|---|
| Тренд вверх | 2 LONG-бота × $400 | 1 SHORT-бот × $200 | 4:1 в сторону тренда |
| Тренд вниз | зеркально | зеркально | 4:1 в сторону тренда |
| Range после роста | оба максимально работают | оба максимально работают | Volume-rich режим |

### Реальное поведение (что происходит на самом деле)

(Из устного описания 2026-04-30, прямая цитата оператора)

> "На сильном росте лонги быстро сокращаются. Я люблю закрывать
> в момент ускорения в зоне ликвидаций, чтобы перезайти в long ниже
> на откате. Шорты в это время растут (по позиции) — если не
> ставить на паузу набор позиций, то довольно сильно. Понятно, они
> сбрасывают на откате — но если это тренд, тут риски."

GAP между идеалом и реальностью — это где автоматизация поможет
(см. §3 Боли и §6 Roadmap).

### Существующие dimensions (из docs/OPPORTUNITY_MAP_v1.md L51-68)

> Три режима (conservative/normal/aggressive), default = normal.
> Депозит ~$15k, идёт реинвест, плановое пополнение +$10-20k.
> conservative=0.05 BTC, normal=0.10 BTC, aggressive=0.18 BTC.

(см. STRATEGY_DIGEST_2026-04-30.md §1 для полной таблицы)

---

## §3 ЧЕТЫРЕ ГЛАВНЫЕ БОЛИ ОПЕРАТОРА

(Сформулированы architect'ом, согласованы оператором 2026-04-30)

### Боль #1 — Стресс-мониторинг
**Симптом:** ралли в 5 утра — оператор должен схватить телефон
и решать
**Корень:** решения принимаются человеком, человек спит/занят/не у экрана
**Status:** Manual. Решается Layer 2-3 (Phase 2: dashboard +
proactive alerts) и Layer 4 (Phase 3: structural confirmation gate).

### Боль #2 — Detection ложных выносов vs реального тренда
**Симптом:** "Это вынос для squeeze'а или реальный пробой?" —
на этом моменте оператор колеблется, теряет время
**Корень:** нет formal gate "structural confirmation vs spike"
перед действием. P-1 trigger = просто delta_1h>3%, не учитывает
PDH break / volume / hold time / round number / killzone.
**Status:** Manual. Решается TZ-STRUCTURAL-CONFIRMATION-GATE
(Phase 3).

### Боль #3 — Manual sizing rebalance
**Симптом:** менять order_size 5 ботов вручную при смене режима —
медленно, забывается
**Корень:** параметры статичны, режим динамичен
**Status:** Manual. Решается TZ-TREND-MODE-DYNAMIC-SIZING (Phase 4),
зависит от Phase 3.

### Боль #4 — Drift к катастрофе
**Симптом:** unrealized −$200 → −$500 → −$1000 → паника. Нет точки
"стоп, дальше нельзя"
**Корень:** принцип P0 (никогда не закрывать в минус) не имеет
circuit breaker'а на extreme. P-12 adaptive tighten увеличивает
обороты, но не решает направление. Без HARD BAN'а P-8/P-5/P-10 —
формального exit'а в минус нет.
**Status:** Manual. Решается Layer 2 (TZ-CIRCUIT-BREAKER-V1) после
backtest validation thresholds через Stage 1.2 framework.

### Цикл-смерти на затяжном тренде

(Сформулирован architect'ом, согласован оператором 2026-04-30)

Цена растёт, SHORT-grid набирает позицию по уползающему avg
Realized у LONG капает копейки (быстрые TPs)
Unrealized у SHORT уползает: -$200 → -$500 → -$1000
P-12 adaptive tighten увеличивает обороты но не решает направление
P-4 PAUSED останавливает новые entries (если оператор успел нажать)
P-1 raise boundary расширяет диапазон (если тренд подтверждён)
Без HARD BAN'а P-8/P-5/P-10 — формального exit'а в минус НЕТ
Точка ликвидации или вынужденного force-close = ВНЕ playbook

Усугубляющие gaps (см. STRATEGY_DIGEST_2026-04-30.md §10):
- G-2: точные пороги P-4 не зафиксированы
- G-7: P-9 параметры — диапазоны, не числа
- G-4: N для D-LIQ-CASCADE не задано

---

## §4 ПРИНЦИПЫ ТОРГОВЛИ

(Из docs/MASTER.md L218-246, дословно)

> **P0:** Никогда не закрывать в минус (без крайней необходимости).
> Сетка должна вытащить через работу, не через ножницы. Исключения
> только при риске ликвидации или конце конкурсного периода.
>
> **P1:** Защита > возможность. При конфликте сигналов (рост >3% +
> каскад с разворотом): сначала остановить, потом наблюдать, потом
> действовать.
>
> **P2:** Boundaries = анти-сквиз, не рабочая зона. Бот должен
> работать везде на любой цене. По мере подтверждённого тренда —
> контролируемо двигать границу.
>
> **P8:** Каскады, ралли, каждое движение — возможность. Зарабатываем
> на всём. Нет "ждём идеального момента". Если в ситуации X есть
> edge — действуем.

### Trader-first filter (из session memory)

Каждый TZ должен пройти один из критериев:
- (а) лучшее risk-profile в реальной торговле
- (б) тестирование hypothesis на real data
- (в) защита капитала от bugs/runtime issues

Если ни один не выполняется — TZ не релизится без явного permission.

---

## §5 КАТАЛОГ ПАТТЕРНОВ P-1..P-12

(Полная таблица в docs/CANON/HYPOTHESES_BACKLOG.md и в
docs/PLAYBOOK.md L50-514, ссылка туда)

Confirmed (используются live):
- P-1 controlled_raise_boundary
- P-2 stack_bot_on_pullback
- P-4 paused_no_new_entries
- P-6 shorts_on_short_squeeze_cascade
- P-7 longs_after_confirmed_dump
- P-9 long_fix_or_reinforce_on_rally
- P-11 weekend_gap_false_breakout

Dry-run only:
- P-3 counter_long_hedge_with_ttl (1 эпизод 24.04 18:17)
- P-12 adaptive_grid_tighten_in_drawdown

HARD BAN (никогда не предлагать):
- P-5 partial_unload (used_but_not_measured, в HARD BAN)
- P-8 force_close_re_entry
- P-10 rebalance_close_reenter

Rejected (не используются):
- P-13 liquidity_harvester
- P-14 profit_lock_and_restart

Pending validation (новые гипотезы):
- P-15 rolling-trend-rebalance (см. HYPOTHESES_BACKLOG.md)
- P-16 post-impulse-booster (см. HYPOTHESES_BACKLOG.md)

---

## §6 ENGINE STATUS И BACKTEST FRAMEWORK

### Calibration результат 2026-04-30

(см. docs/calibration/CALIBRATION_VS_GINAREA_2026-04-30.md)

**Engine sim_engine_v2 имеет 3 bugs:**
- Anomaly A: SHORT realized хаотичен и пересекает знак
- Anomaly B: LONG realized stable но с инвертированным знаком
  (K=-0.89)
- Anomaly C: K_volume сильно различается между LINEAR/INVERSE
  (12.5 vs 3.0)

**Все прежние backtest results под пересмотром:**
- H10 sweep (53k trades, май 2024 → апрель 2026) — pending re-run
  после fix'а
- H1-H9 hypotheses — pending re-run
- Любые H-проверки до починки engine невалидны

### Pending TZ pipeline

(см. docs/CANON/INDEX.md для текущего состояния очереди)

Stage 1.1 — Engine investigation+fix:
- TZ-ENGINE-BUG-INVESTIGATION (Code, done 2026-04-30) →
  ENGINE_BUG_HYPOTHESES_2026-04-30.md
- TZ-ENGINE-BUG-FIX (Code, pending) → 3 fixes in order:
  A2 verdict() / A1+B1 combo_stop / A3 normalization fill
- Re-run calibration → ожидаем CV<10% для обеих групп

Stage 1.2 — Managed grid framework:
- TZ-MANAGED-GRID-SIM-FRAMEWORK (Codex, pending до фиksing engine)

Stage 1.3 — Hypothesis validation:
- P-15 backtest sweep
- P-16 backtest sweep
- Operator's Q-1..Q-N (см. OPERATOR_QUESTIONS.md)

Stage 1.4 — Production rollout:
- TZ-CIRCUIT-BREAKER-V1 (с proven thresholds из Stage 1.3)
- TZ-TREND-MODE-DYNAMIC-SIZING

---

## §7 КОНКУРС GINAREA

### Текущая позиция (на 2026-04-30 12:48 utc)
- Rank: 🥇 #1 по PnL
- PnL за 9 дней: $1,429.38
- Volume за 9 дней: $1,801,649
- PnL/Volume ratio: 0.0794% (12.5× выше чем H10 sim предсказывал)

### Цель оператора 30 дней
- Volume target: $10,500,000
- Текущий темп: ~$200K/день (проекция $6M на 30 дней)
- Gap: $4.5M или ~$214K/день дополнительно
- Days remaining: 21 (как на 2026-04-30)

### Ребейт оценка
- Fee: 0.035% market order (GinArea через UI, есть только market)
- Rebate: до $10M → ~$500, $10M+ → $1500-$2500
- Net effect на стратегию: выгодно держать выше $10M ребейт-tier

### Эмпирические данные H10 (pending recalc)
- 2 года, 53k trades, total volume $562M
- PnL/volume gross: 0.0064% (sim — после починки engine может
  пересчитаться)
- После real fee 0.035%: гипотетический результат — все 10
  конфигураций убыточны
- **Pending re-validation после engine fix**

---

## §8 ДОПОЛНИТЕЛЬНЫЕ КОНТЕКСТНЫЕ ФАЙЛЫ

### Custom боты оператора
См. docs/CANON/CUSTOM_BOTS_REGISTRY.md

### Гипотезы для будущего backtest'а
См. docs/CANON/HYPOTHESES_BACKLOG.md

### Open questions оператора (что он сам хочет проверить)
См. docs/CANON/OPERATOR_QUESTIONS.md

### Навигация по CANON/
См. docs/CANON/INDEX.md

---

## §9 КОММУНИКАЦИОННЫЕ ПРАВИЛА (ИЗ MEMORY)

(Зафиксированы оператором 2026-04-29)

1. Brief, clear, to the point
2. No long preambles
3. No repetition
4. If uncertain — say "Don't know" / "Need clarification"
5. Don't invent logic
6. Conserve context
7. Code — only необходимый минимум
8. Architecture — структура/логика first, then code
9. Don't rewrite project without necessity
10. Solutions must be executable for mass backtest runs

### TZ integrity rule (2026-04-29)
Каждый TZ к executor = один полный self-contained блок, ready to
copy. Никаких "see above". При editing — переписывать весь TZ,
не давать delta.

### Workflow operator ↔ architect (2026-04-30)
- Параметрические числа/диапазоны → даёт backtest framework
- Архитектурные/смысловые вопросы → architect задаёт оператору
  если непонятно из docs
- Open questions у оператора — фиксируются в OPERATOR_QUESTIONS.md,
  становятся приоритетом backtest runs

---

## §10 GAPS BACKLOG

(Из STRATEGY_DIGEST_2026-04-30.md §10 + новые из session 30.04)

| # | Gap | Источник |
|---|---|---|
| G-1 | Volume targeting (конкурсный режим) — нет правил | MASTER §1 |
| G-2 | Точные пороги PAUSED не зафиксированы | PLAYBOOK P-4 |
| G-3 | Liquidation cluster reentry rules не определены | PLAYBOOK P-3 |
| G-4 | Порог N для D-LIQ-CASCADE не задан | MASTER §4 |
| G-5 | Калибровка размеров после пополнения — нет формулы | OPPORTUNITY_MAP §5 |
| G-6 | Multi-horizon правила для defensive plays | OPPORTUNITY_MAP §6 |
| G-7 | P-9 точные параметры — диапазоны, не числа | PLAYBOOK P-9 |
| G-8 | ICT killzone context для P-4 не операционализирован | PLAYBOOK P-4 |
| G-9 | P-2 stack-bot size — OPEN | PLAYBOOK P-2 |
| G-10 | Статус P-5 (HARD BAN, но используется) | PLAYBOOK P-5 |
| G-11 | Engine bugs (3 anomalies) | CALIBRATION_VS_GINAREA |
| G-12 | Custom bot 6399265299 — не в формальной документации | session 30.04 |
| G-13 | Workflow auto-rebalance qty при regime flip | session 30.04 |
