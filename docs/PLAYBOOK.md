# PLAYBOOK — Каталог торговых приёмов

**Last update:** 2026-04-27 v1.1
**Назначение:** machine-readable источник для `/advise` и What-If backtest. Когда мы правим этот файл — код подхватывает изменения.

---

## §0 СТРУКТУРА ПРИЁМА

Каждый приём описан блоком:

```yaml
id: P-N
name: краткое название
status: confirmed | hypothesis | rejected | dry-run-only
n_episodes: число подтверждённых эпизодов
trigger:           # условия активации (детекторы из MASTER §4)
  required: [список AND]
  any_of: [список OR]
  context: [сессионный/портфельный контекст]
action:            # что делать (из MASTER §5)
  type: A-XXX
  params: {...}
cancel:            # условия отмены/выхода
  - условие 1
  - условие 2
expected_outcome:  # что ожидаем
  pnl_direction: positive/negative/neutral
  time_horizon: 15min/1h/4h/24h
  risk: low/medium/high
notes: free text
ict_context: [где в killzones работает лучше]
episodes: [список реальных эпизодов в истории]
```

---

## §0.1 Real Validation Status (tracker window)

Срез реальной валидации на tracker snapshots: `docs/REAL_SUMMARY_2026-04-28.md` (TZ-043).

- P-4, P-12: validated on real data for `TEST_3` (2026-04-28)
- P-1, P-2, P-6, P-7: insufficient real episodes в текущем tracker×features окне (market regime limitation)
- BTC-LONG-B/BTC-LONG-C: inverse (позиция не в BTC) — real replay v1 для этих ботов некорректен без конвертации единиц

---

## §1 ОСНОВНЫЕ ПРИЁМЫ

### P-1: Контролируемая раскачка boundary за хай

```yaml
id: P-1
name: controlled_raise_boundary
status: confirmed
n_episodes: many (вся апрельская конкурсная неделя)
trigger:
  required:
    - D-MOVE-STRONG OR D-MOVE-CRITICAL  # рост ≥2% за 1ч
    - price_above_current_upper_boundary
  any_of:
    - delta_1h > 3%
    - delta_4h > 4.5%
  context:
    - hold_above_boundary_min: 15  # минут удержания цены выше границы
action:
  type: A-RAISE-BOUNDARY
  params:
    new_top: current_high * (1 + offset_pct/100)
    offset_pct: [0.3, 0.5, 0.7, 1.0]  # grid
    discrete_step: true  # не плавно за хаем
cancel:
  - price_below_new_lower_bound
  - reversal_confirmed (откат >0.5% от нового хая)
expected_outcome:
  pnl_direction: neutral_to_positive
  time_horizon: 4-24h
  risk: medium  # позиция растёт
notes: |
  Не "гонка за ценой", а умножение позиции на хороших ценах.
  Альтернатива dsblin=true ОТВЕРГНУТА (volume падает).
ict_context:
  - лучше работает при пробое PDH или KZ-high с подтверждением
  - хуже при ложном выносе у round number (78000, 80000)
episodes:
  - 2026-04-22 07:57 (рост +5.04% за 1ч, шорты выжили на raise)
  - 2026-04-20 08:47 (+7.19% за 1ч, TEST_1 +$37..$86)
```

### P-2: Stack-бот на остановке роста / откате (ГЛАВНЫЙ ПРИЁМ)

```yaml
id: P-2
name: stack_bot_on_pullback
status: confirmed
n_episodes: regularly used, 5+ раз в неделю
trigger:
  required:
    - D-MOVE-STRONG OR D-MOVE-MEDIUM  # рост был
    - momentum_loss_detected  # рост остановился
  any_of:
    - latest_bar_close < previous_bar_high
    - 2-3_consecutive_neutral_or_red_candles
    - approach_to_known_resistance (PDH, KZ-H, round)
  context:
    - existing_short_position_exists
    - main_short_in_drawdown
action:
  type: A-LAUNCH-STACK-SHORT
  params:
    entry: current_market_price
    size: same_as_main_or_aggressive  # ← OPEN: уточнить у оператора
    target: 0.2-0.5%  # от entry
    grid_step: same_as_main
cancel:
  - target_hit (профит зафиксирован)
  - opposite_setup (глубокий откат подтверждён)
  - rally_resumes (рост продолжился)
  - timeout: 4-24h
expected_outcome:
  pnl_direction: positive  # стак закроется в плюс на откате
  time_horizon: 1-6h
  risk: low_to_medium
notes: |
  ВАЖНО: триггер — НЕ сам рост, а ОСТАНОВКА роста или начало отката.
  Доп. бот набирает позицию по высоким ценам → средняя всего шорт-портфеля
  поднимается. На откате — закрываешь стак с профитом, основной шорт
  остаётся работать со своей позицией.
ict_context:
  - оптимально: подход к KZ-high в London/NY с потерей momentum
  - оптимально: rejection у PDH/PWH
  - плохо: открытый сильный тренд без признаков остановки
episodes:
  - 2026-04-22 07:57 (момент закрытия LONG-B перед остановкой роста)
```

### P-3: Counter-LONG как hedge с TTL

```yaml
id: P-3
name: counter_long_hedge_with_ttl
status: dry-run-only
n_episodes: 1 (24.04 18:17)
trigger:
  required:
    - D-LIQ-CASCADE-LONG  # каскад long-liq ≥15-20 BTC за 60s
    - D-LIQ-CASCADE-WITH-REVERSAL  # цена развернулась за 5min
  any_of:
    - existing_short_position_large
    - delta_risk_high
  context:
    - NOT D-LIQ-CASCADE-NO-REVERSAL  # без подтверждения отката НЕ открывать
action:
  type: A-LAUNCH-COUNTER-LONG
  params:
    side: LONG inverse XBTUSD
    entry: current_market_price
    size: small  # ~10-20% депозита, не основная позиция
    target: 0.25-0.35%
    stop: -0.5 to -1%
    ttl_minutes: 15-45
mode: hedge_not_strategy  # КРИТИЧНО
cancel:
  - target_hit
  - stop_hit
  - ttl_expired (15-45 min без движения)
  - cascade_continues (продолжение падения после открытия)
expected_outcome:
  pnl_direction: positive_OR_small_loss
  time_horizon: 30-60min
  risk: low (ограничен TTL и stop)
notes: |
  НЕ стратегия заработка, а страховочный hedge для снижения delta-risk
  больших шортов. Маленький размер, жёсткий TTL.
  N=1 эпизод — анекдот, не паттерн. Нужно ≥5-10 для подтверждения.
ict_context:
  - лучше работает в NY AM / NY PM (ликвидность высокая)
  - хуже в Asia (тонкие движения, ложные каскады)
  - sweep PDL + reversal = сильный сигнал
episodes:
  - 2026-04-24 18:17 (62 BTC long-liq за 1мин → -0.4% за 5мин → +0.4% за час)
```

### P-4: PAUSED state — стоп новых IN

```yaml
id: P-4
name: paused_no_new_entries
status: confirmed
n_episodes: documented W1-W3 эпизоды
trigger:
  required:
    - D-MOVE-STRONG OR D-MOVE-CRITICAL
    - D-NO-PULLBACK
  context:
    - existing_position_in_drawdown
    - direction_against_position
action:
  type: A-STOP  # шорты при ралли, лонги при дампе
  params:
    affected: bots_with_side_against_trend
    keep_positions_open: true
    target_hits_continue: true  # OUT работают, новые IN — нет
cancel:
  - pullback_detected (откат >0.3-1% от пика)
  - regime_flip_to_range
  - timeout (для UNLOAD)
expected_outcome:
  pnl_direction: neutral  # защита от ухудшения, не заработок
  time_horizon: 1-12h
  risk: low (но volume останавливается)
notes: |
  Альтернативы которые менее радикальны:
  - уменьшить order_size + увеличить grid_step
  - перейти на Far Short preset
ict_context:
  - применять с пониманием killzone — если PAUSED активирован в начале NY,
    скорее всего нужно держать до конца NY PM
episodes:
  - 2026-04-17 14:43 (TEST_1 pos -0.154, uPnL -$376 — стоило применить PAUSED раньше)
```

### P-5: Частичная разгрузка (UNLOAD)

```yaml
id: P-5
name: partial_unload
status: used_but_not_measured
n_episodes: упоминается, эпизоды не зафиксированы
trigger:
  required:
    - paused_state_active OR D-PORT-DEEP-DD
  any_of:
    - paused_duration_hours > X  # X = grid [2, 4, 8]
    - unrealized_pct < Y  # Y = grid [-1%, -2%, -3%]
    - D-PORT-LIQ-DANGER
  context:
    - large_position
action:
  type: A-CLOSE-PARTIAL-X
  params:
    close_fraction: [25, 50, 75]  # grid
    method: market  # руками в GinArea UI
cancel: N/A (одноразовое)
post_action:
  - wait_for_resume_trigger (рост ≥1.3% за 30 мин)
  - then_re_entry
expected_outcome:
  pnl_direction: negative_immediately (фикс убытка) but lowers_risk
  time_horizon: immediate + recovery
  risk: minus_realized fixed, future risk reduced
notes: |
  Минус: фиксируешь часть unrealized как realized.
  Плюс: освобождаем капитал, оставшиеся ордера работают с меньшим риском.
  Параметры (X часов, Y%, fraction) — все для grid search.
ict_context:
  - оптимально: разгрузка перед закрытием NY PM (если позиция большая на ночь)
  - плохо: разгрузка в начале сессии когда движение ещё может развернуться
episodes:
  - нужно собрать из истории
```

### P-6: Шорты на каскаде ликвидаций вверх

```yaml
id: P-6
name: shorts_on_short_squeeze_cascade
status: subset_of_P-1
n_episodes: часть P-1
trigger:
  required:
    - D-LIQ-CASCADE-SHORT  # прокол вверх со short-liq
    - D-LIQ-CASCADE-WITH-REVERSAL
action:
  type: combined
  steps:
    - A-RAISE-BOUNDARY (P-1)
    - A-LAUNCH-STACK-SHORT (P-2)
cancel:
  - rally_continues (если рост продолжается после cascade — стоп ботов)
expected_outcome:
  pnl_direction: positive (отторговать проторговку отката)
  time_horizon: 1-4h
  risk: medium
notes: подмножество P-1 + P-2 в специфичной ситуации
ict_context:
  - лучше после sweep PDH или KZ-high
episodes:
  - различные cascade up в W1-W3
```

### P-7: Лонги после подтверждённой просадки

```yaml
id: P-7
name: longs_after_confirmed_dump
status: confirmed
n_episodes: 16-17.04 эпизоды
trigger:
  required:
    - D-LIQ-CASCADE-LONG OR D-MOVE-CRITICAL (down)
    - reversal_confirmation (отскок ≥1.5% за 30 мин)
action:
  type: A-RESUME (лонг ботов) или A-LAUNCH-STACK-LONG
cancel:
  - dump_resumes
  - target_hit
expected_outcome:
  pnl_direction: positive
  time_horizon: 1-6h
  risk: medium
notes: |
  Лонги работают по сигналу разворота, не постоянно.
  Зеркальный приём к P-2/P-6 для шортов.
ict_context:
  - sweep PDL/PWL + reversal = сильный сетап
  - в Asia слабее, в NY сильнее
episodes:
  - 16-17.04 various
```

### P-8: Force-close + re-entry (HYPOTHESIS)

```yaml
id: P-8
name: force_close_re_entry
status: rejected
n_episodes: 0
trigger:
  any_of:
    - position_large AND D-PORT-LIQ-DANGER
    - D-PORT-FROZEN  # сетка работает впустую
    - end_of_competition_period AND ROE_high
action:
  type: A-CLOSE-ALL + A-RESTART-WITH-NEW-PARAMS
  params:
    new_boundaries: based_on_current_price
    keep_other_params: true
cancel: N/A
expected_outcome:
  pnl_direction: depends
  time_horizon: immediate + recovery
  risk: high (теряешь позицию которая отторгуется на возврате)
notes: |
  В тренде = минус (потеря позиции).
  В боковике = небольшой плюс (свежий volume).
  Текущая ситуация (фр.0): distance to liq 33-51%, маржи свободно — НЕ выгодно.
ict_context: TBD
episodes: 0
```

### P-9: Лонг — fix на быстром росте / усиление на контролируемом

```yaml
id: P-9
name: long_fix_or_reinforce_on_rally
status: confirmed
n_episodes: 22.04 07:57 + другие
trigger:
  required:
    - existing_long_position
    - rally_in_progress
  fix_branch:
    - rapid_rally  # +X% за Y минут [grid: X=2-3%, Y=15-60min]
    - approach_to_resistance (PDH, KZ-H, round)
    - liquidation_zone_of_shorts  # из стакана/heatmap
  reinforce_branch:
    - controlled_rally  # медленный устойчивый рост
    - support_holding  # откаты выкупаются
action:
  fix_branch:
    type: A-CLOSE-PARTIAL-X or A-CLOSE-ALL (long bot)
  reinforce_branch:
    type: A-CHANGE-SIZE (увеличить) or A-LAUNCH-STACK-LONG
cancel:
  fix_branch: N/A (фиксация done)
  reinforce_branch: target_hit, reversal_signal
expected_outcome:
  pnl_direction: positive
  time_horizon: 30min-4h
  risk: low (fix) / medium (reinforce)
notes: |
  Триггер «быстрый» нужно калибровать. На быстром росте откат тоже резкий.
  На медленном — рост продолжается дольше.
  УТОЧНЕНИЕ: 26.04 22:15 закрыл лонг в зоне ликвидаций шортистов на пробое.
  Это подвид fix_branch с дополнительным контекстом liquidation zone.
ict_context:
  - fix перед NYO (12:00 NY = 19:00 Warsaw) часто эффективен
  - reinforce в London часто продолжается до NY
episodes:
  - 2026-04-22 07:57 (закрыл LONG-B при +5%)
  - 2026-04-26 22:15 (закрыл лонг 1000 USD при подходе к 78400 zone)
  - АНТИ-ПРИМЕР: 2026-04-17 13:55 закрытие на пике дало худший возможный исход
    (бот зашёл через 3ч на $78,089 = выше цены закрытия)
```

### P-10: Rebalance — close + re-entry на новых уровнях

```yaml
id: P-10
name: rebalance_close_reenter
status: confirmed
n_episodes: 4 кейса (17.04, 23.04)
trigger:
  any_of:
    - D-MOVE-CRITICAL  # резкий рост >3%
    - D-MOVE-CRITICAL down
  context:
    - position_significantly_offside
action:
  type: A-RESTART-WITH-NEW-PARAMS
  params:
    close_then_reenter_at: current_price ± 1-2%
    keep_size_and_grid: true
cancel: N/A
expected_outcome:
  pnl_direction: depends
  time_horizon: immediate + recovery
  risk: medium
notes: один из 4 режимов портфеля. Используется реже чем P-2.
ict_context:
  - rebalance перед сменой killzone (например после NY PM в Asia)
episodes:
  - 2026-04-23 10:12 (закрытие LONG-B/C)
  - 2026-04-23 15:24 (закрытие LONG-B/C)
```

### P-11: Weekend gap false breakout

```yaml
id: P-11
name: weekend_gap_false_breakout
status: confirmed
n_episodes: 1 (2026-04-27)
trigger:
  required:
    - D-MOVE-STRONG OR D-MOVE-CRITICAL
    - weekend_gap_unfilled_below
  any_of:
    - macro_no_support_for_rally
    - delta_recent < -1.0%
  context:
    - weekend_gap_low_price
    - gap_target_pct: 1.5
    - boundary_safety_buffer_pct: 0.3
    - reentry_offset_pct: 0.2
    - boundary_offset_pct: 0.3
action:
  type: A-LAUNCH-STACK-SHORT or A-RAISE-BOUNDARY
  params:
    gap_target_pct: 1.0-2.0
    boundary_safety_buffer_pct: 0.2-0.5
    reentry_offset_pct: 0.1-0.3
cancel:
  - weekend_gap_filled
  - macro_support_returns
expected_outcome:
  pnl_direction: positive
  time_horizon: 4-12h
  risk: medium
notes: |
  Это play на ложный вынос weekend gap вверх без подтверждения от более широкого рынка.
  Эталонный эпизод: top 79200 (00:55 UTC) → 77600 (08:30 UTC).
ict_context:
  - важен слабый follow-through после weekend pump
  - лучше работает до открытия London/NY, пока гэп не переварен
episodes:
  - 2026-04-27 00:00-09:00 UTC (top 79200 → 77600, false breakout)
```

### P-12: Adaptive grid tighten in drawdown

```yaml
id: P-12
name: adaptive_grid_tighten_in_drawdown
status: dry-run-only
n_episodes: 1 (2026-04-27 dry-run)
trigger:
  required:
    - bot_side
    - bot_status
  any_of:
    - bot_unrealized_pnl_below
    - bot_dwell_in_drawdown_hours > K
    - delta_recent < -1.0%
  context:
    - target_factor
    - gs_factor
    - cooldown_hours
    - max_cycles_per_24h
    - bot_unrealized_pnl_above
action:
  type: A-CHANGE-TARGET + A-CHANGE-GS
  params:
    target_factor: 0.60
    gs_factor: 0.67
    cooldown_hours: 2
    max_cycles_per_24h: 3
cancel:
  - bot_unrealized_pnl_above
  - cooldown_hours_active
expected_outcome:
  pnl_direction: neutral_to_positive
  time_horizon: 4-24h
  risk: medium
notes: |
  В просадке временно затягивает short-grid, чтобы увеличить обороты и быстрее подтянуть avg_entry.
  После выхода из глубокой просадки возвращает исходные параметры.
ict_context:
  - применять только как портфельный приём поверх шорт-ботов
  - на направленном рынке без откатов требует отдельной калибровки в What-If
episodes:
  - 2026-04-27 dry-run on 3 short bots
```

### P-13: Liquidity harvester

```yaml
id: P-13
name: liquidity_harvester
status: rejected
n_episodes: 0
trigger:
  required:
    - D-CONSOLIDATION-AFTER-MOVE
action:
  type: A-LAUNCH-LIQUIDITY-HARVESTER
  params:
    side: [long, short, both]
    offset_pct: [0.5, 0.7, 1.0, 1.5, 2.0]
    width_pct: [0.5, 1.0, 1.5, 2.0]
    target_pct: 0.25
    gs_pct: 0.05
    size_btc: 0.05
    ttl_min: 240
cancel:
  - ttl_expired
  - far_boundary_touched
expected_outcome:
  pnl_direction: positive_or_neutral
  time_horizon: 4h
  risk: medium
notes: |
  Временный sub-bot вокруг зоны ликвидности после сильного движения и консолидации.
  Все параметры идут в grid search; play добавлен как hypothesis.
  TZ-032-Codex (28.04) backtest verdict: edge не подтверждён.
  Best mean_pnl_vs_baseline = +$15.19 НО win_rate 2.91% —
  97% эпизодов в убыток. Hi-variance distribution неприемлемо
  для торговой системы. after_dump = -$10.69, after_rally
  = -$29.26. Подробности: whatif_results/P-13_2026-04-28_summary.md.
ict_context:
  - лучше после сильного движения с последующей проторговкой
episodes:
  - TBD after backtest
```

---

## §2 ПРИНЦИПЫ КОТОРЫЕ ПРИМЕНЯЮТСЯ КО ВСЕМ ПРИЁМАМ

См. MASTER §7 для полного списка. Ключевые:
- P0: Никогда не закрывать в минус без крайней необходимости
- P2: Boundaries = анти-сквиз
- P5: ICT killzone context важен для каждого приёма
- P6: Числа — параметры grid search

---

## §3 ЭТАЛОННЫЕ ЭПИЗОДЫ (для бэктеста)

### Каскады
- **2026-04-27 00:55 UTC** — LIQ_CASCADE 41.978 BTC short-liq на пике 79200. Начало P-11.
- **2026-04-27 05:15 UTC** — LIQ_CASCADE 12.25 BTC long-liq при падении. Counter-LONG триггер сработал, target +0.30% за 1мин.
- **2026-04-27 06:31 UTC** — LIQ_CASCADE 16.18 BTC long-liq. Counter-LONG triggered, target hit за 1мин.
- **2026-04-24 18:17 UTC** — каскад 62 BTC long-liq → -0.37% за 5мин → +0.37% за час. P-3 эталон.
- **2026-04-19 22:00 UTC** — каскад -5.56% за 90мин. KLOD_IMPULSE НЕ сработал.

### Ралли
- **2026-04-27 00:00-09:00 UTC** — полный эпизод P-11. Top 79200 → 77600 за 7ч. Эталон weekend gap false breakout.
- **2026-04-20 08:47 UTC** — критический +7.19% за 1ч. TEST_1 pos -0.076, uPnL +$37..+$86 (выжили).
- **2026-04-22 07:57 UTC** — +5.04% за 1ч. TEST_1 pos -0.169, uPnL -$250. P-9 fix.
- **2026-04-17 09:00-15:00 UTC** — ралли несколько фаз. TEST_1 в -$350 на 14:43 (pos -0.154). Главная боль шортов недели.
- **2026-04-17 09:31 UTC** — закрытие лонга #1, бот перезашёл через 4 мин на -0.7%.
- **2026-04-17 13:55 UTC** — АНТИ-ПРИМЕР P-9: закрытие на пике дало худший исход.
- **2026-04-26 22:15 UTC** — рост в зону ликвидаций шортистов (78400+), лонг закрыт, ждём откат.

### Боковики
- **2026-04-21 19:45-20:48 UTC** — -2.1% / +2.4% разворот.
- **2026-04-24 17:00-21:00 UTC** — реально боковик.
- **2026-04-24 09:18-18:00 UTC** — окно валидации движка (B1.00 PASS p95<1%).

### Портфельные вмешательства
- **2026-04-27 intraday UTC** — dry-run P-12: adaptive grid tightened на 3 шорт-ботах в просадке.

---

### P-14: Profit lock and restart

```yaml
id: P-14
name: profit_lock_and_restart
status: rejected
n_episodes: 0
trigger:
  required:
    - D-PROFIT-LOCK-OPPORTUNITY
action:
  type: A-CLOSE-ALL-AND-RESTART
  params:
    pnl_threshold_pct: [0.5, 1.0, 2.0, 3.0]
    offset_pct: [0.5, 1.0, 1.5, 2.0]
    restart_side: [same, reverse]
cancel:
  - ttl_expired
expected_outcome:
  pnl_direction: positive_or_neutral
  time_horizon: 4h
  risk: medium
notes: |
  Закрыть все позиции при накопленном профите и подтверждённом движении,
  затем перезапустить сетку с offset от текущей цены.
  Гипотеза оператора по реальной ситуации 28.04 14:55.
  Отличать от P-10: здесь trigger conditional, а не безусловный rebalance.
  TZ-041-Codex (28.04) backtest verdict: edge не подтверждён.
  Best mean_pnl_vs_baseline = +$12.27 НО win_rate 22.83% —
  77% эпизодов в убыток. Hi-variance distribution неприемлемо
  для торговой системы. Подробности: whatif_results/P-14_2026-04-28_summary.md.
ict_context:
  - лучше после подтверждённого тренда или reversal
episodes:
  - TBD after backtest
```

## §4 АНТИПАТТЕРНЫ

- ❌ **dsblin=true как защита** — volume падает, бот закрывает несколько ордеров и всё. Использовать P-1 raise или P-4 PAUSED вместо.
- ❌ **Закрытие на пике** — анти-пример 17.04 13:55, потерял рост и зашёл выше.
- ❌ **Boundaries как «рабочий диапазон»** — это анти-сквиз, не working zone.
- ❌ **Импульсный лонг -2.2%/RSI<49** — пропустил каскад -5.56%, опровергнут.
- ❌ **Counter-position на безоткатном движении** — P-3 нужен ТОЛЬКО при подтверждённом отскоке.
- ❌ **Зеркальные правила** к шортам и лонгам без подтверждения (асимметрия).
- ❌ **Boundary плавно за хаем на каждом баре** — это chasing, нужны дискретные шаги с подтверждением.
- ❌ **Закрытие позиций руками в минусе** (P0).
- ❌ **Торговля против пятничного движения после 15:00 NY**.

---

## §5 ИЗМЕНЕНИЯ ФАЙЛА

```
2026-04-27 v1.1 — Добавлены P-11 (weekend_gap_false_breakout) и P-12 
                  (adaptive_grid_tighten_in_drawdown). 
                  Эпизоды 27.04 в §3.
                  Composition layer (TZ-019) готов, валидация 12/12 OK.
2026-04-26 v1.0 — Объединение PLAYBOOK_DRAFT_v0.1 + v0.2 + переписки klod.txt
                  (все 150 фрагментов прочитаны).
                  Каждый приём в machine-readable формате (yaml блоки).
                  Добавлен ICT context для каждого приёма.
                  Добавлены эталонные эпизоды и антипаттерны.
                  Готов как источник для /advise и What-If backtest.
```
