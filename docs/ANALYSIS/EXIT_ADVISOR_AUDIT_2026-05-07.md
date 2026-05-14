# Exit Advisor — критический аудит

**Дата**: 2026-05-07 14:56 (incident report)
**Триггер**: оператор получил alert "EMERGENCY: Close ALL SHORT — liquidation imminent" с EV +$2 (= one of 4 options с identical scoring), сигнализировал "цифры не корректные, советы не адекватные".
**Состояние**: ⚠️ **`send_fn` отключён** в app_runner до починки. Loop работает, jsonl пишется, но в Telegram **молчит**.

---

## Что сломано

### 1. EV scoring — фундаментально неправильный

`services/exit_advisor/strategy_ranker.py:226` использует функцию `_compute_ev_from_history(df, regime, session)`. Она:
- Берёт `data/historical_setups_y1_2026-04-30.parquet` (18,712 setup'ов)
- Считает mean PnL **всех** сетапов которые были в этом regime+session
- Возвращает один и тот же mean всем стратегиям (close 25%, raise boundary, tighten grid, ...)

**Это не EV конкретного action**, это среднее по **setup detector data** (PDH rejection, FVG fill, etc.) — данных, которые описывают **новые трейды**, а не **управление позицией в DD**.

### 2. Стратегии и parquet — несовместимые домены

В parquet столбцы: `setup_type, entry_price, tp1_price, stop_price, hypothetical_pnl_usd`.
В strategy_ranker стратегии: `Raise boundary +0.5%`, `Close 25% SHORT`, `Tighten grid (target x0.7)`.

**Эти миры не связаны**. Невозможно считать EV для "raise boundary" по setup outcomes — это разные действия.

### 3. n=9933 — обманчиво

Telegram показывает "Уверенность: ВЫСОКАЯ уверенность (n=9933)" для всех 4 вариантов. Это размер subset'а в parquet'е (например, всего setup'ов в `trend_up` regime). Никак не относится к конкретной стратегии "Close ALL SHORT".

### 4. EMERGENCY: Close ALL SHORT — против HARD BAN операционных правил

OPPORTUNITY_MAP_v2 §16.4 (MASTER §16.4) явно фиксирует HARD BAN:
- **P-5 partial unload**: avg impact -$26
- **P-8 force close + restart**: avg impact -$192
- **P-10 rebalance close + reenter**: avg impact -$46
- **Force close в минус = P0 violation**

Текущий exit_advisor не знает про этот HARD BAN и предлагает закрыть в минус как "URGENT" опцию **с тем же EV** что и raise boundary.

### 5. Отсутствие факта что closing in DD ≠ exit, а **lock loss**

При -4.5% unrealized у бота 6399265299 close 100% = **зафиксированный убыток $1084**. Текущий "EV +$2" игнорирует это. Реальный EV closure = -$1084 + (потенциальный recovery если бы держал — обычно положительный за 24-72ч в RANGE/MARKDOWN regime).

---

## Что нужно для **честной** advisory

Минимум 3-5 часов работы:

1. **Удалить fake EV** из renderer'а. Не показывать число которое не имеет смысла.

2. **Action-specific outcome датасет** — построить отдельно для каждого action class:
   - `raise_boundary_outcomes`: для каждого случая когда оператор поднимал boundary (history) → результат через 4h/24h
   - `tighten_grid_outcomes`: то же
   - `close_partial_outcomes`: то же
   - **Это требует tracker который сейчас не пишет** — нужен log_decision callback от Telegram кнопок (тоже не реализован).

3. **Rule-based scoring** до накопления данных — на основе MASTER §16:
   - Closing in DD → HARD BAN флаг
   - Raise boundary → +$X based on observed price reversal odds в текущем regime
   - PAUSED → +$0 (защитный, не profit)

4. **Правильный price feed** — уже починен сегодня (PR commit c7cf6a5).

5. **Persist dedup_cache** — уже починен.

---

## Решение на сегодня

`EXIT_ADVISOR_SEND_TELEGRAM=0` (default). Loop работает в фоне для observability но в Telegram молчит. Когда rebuild готов — `EXIT_ADVISOR_SEND_TELEGRAM=1` и реактивация.

## Кандидат на rebuild

Не строить новый exit_advisor с нуля. Лучший путь:

1. **Honest advisor v0.1**: showcase 1 информации **без рекомендаций** — текущее состояние, scenario class, distance to liq, age in DD, сравнение с MASTER §16 HARD BAN list.
2. Когда оператор выберет действие → **log в decision_log** → tracker накапливает outcomes.
3. После 30+ outcomes per action class — включаем EV scoring **с реальными данными**.

Это правильно vs текущий fake EV который опасен.

---

## Linked

- `services/exit_advisor/strategy_ranker.py` — fake EV
- `services/exit_advisor/loop.py` — loop OK, send_fn flag добавлен 2026-05-07
- `app_runner.py:184` — `EXIT_ADVISOR_SEND_TELEGRAM` env flag
- MASTER §16.4 — HARD BAN list
- OPPORTUNITY_MAP_v2 — full reference
