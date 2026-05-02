# PROJECT CONTEXT — Grid Orchestrator
# Версия: 1.0 | Дата: 2026-05-02
# СТАТУС: Static reference. Обновляется только при изменении фундаментального понимания.
# НАЗНАЧЕНИЕ: Читается новым Claude в начале сессии для немедленного входа в контекст.

---

## §1 СУТЬ ПРОЕКТА — одной фразой

**Автоматизация двусторонней сеточной торговли на GinArea** (BTC/XRP) при условии:
«стабильный плюс + я понимаю почему это работает» — не автоматизация любой ценой.

Проект называется **Grid Orchestrator**. Это не трейдинг-бот, это система помощи оператору
в управлении ботами GinArea (и в будущем — автоматического управления ими).

---

## §2 МЕХАНИКА GINAREA — то что НУЖНО знать

### Типы контрактов в портфеле

| Направление | Контракт | Qty в | PnL в | Почему |
|---|---|---|---|---|
| SHORT | Linear USDT-M (BTCUSDT) | BTC | USDT | Убыток линеен при росте BTC |
| LONG | Inverse COIN-M (XBTUSD) | USD | BTC | Double-win при росте: profit↑ + BTC↑ |

### Жизненный цикл IN-ордера

```
Indicator trigger → цена идёт против бота → Instop check → IN открыт
→ цена достигает target_profit_pct → выставляется stop-profit (min_stop_pct от триггера)
→ откат ≥ min_stop_pct → закрыто, profit = target − min_stop
→ или: несколько IN объединяются в Out Stop Group → trailing с max_stop_pct
```

### Indicator gate — РАЗОВАЯ ПРОВЕРКА (подтверждено оператором)

- Indicator (Price%, RSI и т.д.) проверяется ОДИН РАЗ на цикл
- Цикл = старт бота OR full-close позиции (position_size = 0)
- Out Stop ≠ full-close. Если остались открытые IN — бот работает без перепроверки
- После full-close → флаг сбрасывается → ждём новый indicator signal
- В engine_v2: `is_indicator_passed` flag в `bot.py`, reset в `_check_full_close()`

### Instop — ДВЕ СЕМАНТИКИ

**Семантика A (наши TEST_1/2/3 — DEFAULT/DYNAMIC):** задержка открытия IN-ордеров.
IN открывается только после отскока на `instop_pct` от локального экстремума.
При пропущенных уровнях → один combined IN = N × order_size.

**Семантика B (некоторые другие боты):** расстояние стопа для IN-ордера.
Открытый вопрос — в каких именно режимах активна.

### Out Stop Group — комбо-стоп

- IN-ордера, достигшие target, объединяются в Out Stop Group
- Trailing с max_stop_pct от extremum
- При закрытии: ранние IN в плюсе, поздние IN в минусе, взвешенно — в плюсе
- `max_stop_pct = 0` → стоп прямо на триггере, без trailing

### Widen target / disable_in

- `widen_target` (изменение target_profit_pct) влияет ТОЛЬКО на новые IN-ордера,
  существующие сохраняют свой target от момента открытия
- `disable_in` останавливает новые IN, существующие OUT-ордера продолжают работать

### Живые параметры (SHORT, linear BTCUSDT)

| | TEST_1 | TEST_2 | TEST_3 |
|---|---|---|---|
| order_size | 0.001 BTC | 0.001 BTC | 0.001 BTC |
| grid_step | 0.03% | 0.03% | 0.03% |
| target | 0.25% | 0.25% | 0.25% |
| min_stop | 0.006% | 0.008% | 0.01% |
| max_stop | 0.015% | 0.025% | 0.04% |
| instop | 0 | 0.018% | 0.03% |
| indicator | Price% > 0.3% / 30min | same | same |

---

## §3 СТРАТЕГИЯ ОПЕРАТОРА

Оператор (Алексей) торгует:
- **Сеточно, контртрендово** — не trend-following
- **Двусторонняя сетка LONG + SHORT одновременно** — в боковике оба работают
- **Ложные выносы** (2.5%+ с RSI≤45 → 84% reversal на XRP)
- **Pin bars и диапазоны** вручную — где именно войти/выйти
- **НЕ ждём идеального момента** — в любой ситуации с edge действуем (P-8)

### Поведение в режимах рынка

**Боковик:** оба бота молотят, PnL positive с обеих сторон

**Сильный рост:**
- LONG получает directional gain
- SHORT-grid накапливает позицию вверх (unrealized в BTC)
- BTC currency cushion: BTC↑ → BTC-убыток меньше в USD

**Цикл-смерти на затяжном тренде:**
SHORT набирает avg по уползающей цене → unrealized −$200 → −$500 → −$1000
→ P-12 tighten крутит обороты, но не спасает от направления
→ P-4 PAUSED только если оператор успел нажать
→ Без HARD BAN'а — нет формального exit'а

### Principles

- **P0:** Никогда не закрывать в минус без крайней необходимости
- **P1:** Защита > возможность. Сначала остановить, потом действовать
- **P2:** Boundaries = анти-сквиз. Двигать контролируемо при подтверждённом тренде
- **P8:** Зарабатываем на всём. Edge есть → действуем

### HARD BAN (никогда не предлагать)

- **P-5 partial_unload** — использовался, но не измерен
- **P-8 force_close_re_entry** — стресс-паника, запрещён
- **P-10 rebalance_close_reenter** — запрещён

### Confirmed паттерны (P-1..P-12)

P-1 controlled_raise_boundary, P-2 stack_bot_on_pullback, P-4 paused,
P-6 shorts_on_squeeze, P-7 longs_after_dump, P-9 long_fix_or_reinforce,
P-11 weekend_gap — все confirmed live.

---

## §4 ИЕРАРХИЯ ИНСТРУМЕНТОВ (куда идём)

```
Inst.1 Research           — backtests, calibration, hypothesis validation
Inst.2 Detector           — live setup detection (setup_detector_loop)
Inst.3 Playbook           — docs/PLAYBOOK.md, P-1..P-12
Inst.4 Analyzer           — paper journal, /advise, decision log
Inst.5 Automation         — Phase 3-4: auto bot management via GinArea API
```

### Phase roadmap

| Фаза | Название | Статус | Exit criteria |
|---|---|---|---|
| 0 | Infrastructure | in_progress | Все конфликты классифицированы, DEBT-04 resolved |
| 0.5 | Engine validation | in_progress | Reconcile GREEN/YELLOW с documented tolerances |
| 1 | Paper Journal | in_progress | 14 дней непрерывно + weekly report |
| 2 | Operator Augmentation | planned | /advise влияет на решения + edge > 10% vs no-action |
| 3 | Tactical Bot Management | planned | 30+ дней Phase 2, GinArea API dry-run |
| 4 | Full Auto | planned | 100+ paper signals, edge > 25%, Sharpe > 1.2 |

**Текущий активный фокус:** Phase 0.5 + Phase 1 параллельно

---

## §5 ENGINE V2 — CALIBRATION FINDINGS

### Calibration K-факторы (2026-05-02)

| Сторона | K_mean | Статус | Примечания |
|---|---|---|---|
| SHORT (LINEAR) | 9.637 | STABLE (CV 3.0%) | Надёжен для scaling |
| LONG (INVERSE) | 4.275 | TD-DEPENDENT (CV 24.9%) | Structural: без instop в sim |

K = ga_realized / sim_realized. GridBotSim намеренно не имеет instop/indicator_gate —
K компенсирует эту разницу. TD-зависимость LONG — не баг, структурная особенность.

### Combo-stop geometry fix (B1+A1, 2026-04-30)

**Был баг (до фикса):** для LONG с td_pct < max_stop_pct:
`raw_stop = trigger × (1 − max_stop/100) < entry_price`
→ combo_stop ниже entry → позиции закрывались в убыток → K = −0.99

**Фикс применён** (`engine_v2/group.py:58`):
`init_stop = max(raw_stop, entry_floor)` — stop не ниже entry

### Indicator gate в engine_v2

- `engine_v2/bot.py` — ПРАВИЛЬНАЯ реализация: разовая проверка на цикл
- `services/calibration/sim.py` — намеренно БЕЗ indicator gate (K компенсирует)
- `services/coordinated_grid/simulator.py` — аналогично, by design

### GinArea backtest ground truth

Оператор предоставил 8 GinArea backtests из реальной платформы:
- 6 SHORT runs с varying TD: TD=0.25..0.50, result: +$31k..+$50k/year
- 6 LONG runs с varying TD: result: −0.5 BTC/year независимо от TD

**Сигнал:** LONG остаётся убыточным по ground truth данным.
Причина (hypothesis B2): indicator direction для LONG может быть инвертирован
(LONG стартует на РОСТЕ цены, не на падении). Открытый вопрос.

### Coordinated grid

Лучший результат: $37,769/year (без trim, asymmetric baseline).
Один год. Multi-year validation нужна для Phase 1 paper journal.

---

## §6 H10 SETUP DETECTOR

### Параметры детектора

- C1: price drop 1.5%+ за 2/3/4/6/8/12h → setup window
- C2: после C1, рост ≤2.5% за 6-48h → условие разворота
- 5/5 ground truth confirmed

### Combo filter (4 слоя)

```
Layer 1: GRID_* и DEFENSIVE_* → always ALLOW (exempt)
Layer 2: strength < 9 → BLOCK
Layer 3: (type × regime) → 2-way BLOCK/ALLOW table
Layer 4: (type × regime × session) → 3-way session blocks
```

### Backtest results (BTCUSDT 1y)

Best filter (strength=9, no consolidation): 4,495 setups, 43.1% WR, +$16,163

Profitable combos:
- LONG_PDL_BOUNCE × trend_down: 53.4% WR, +$5,165
- LONG_DUMP_REVERSAL × trend_down: 30.8% WR, +$8,851
- SHORT_PDH_REJECTION × trend_up: 41.8% WR, +$2,831

Losing combos (BLOCK):
- LONG_DUMP_REVERSAL × consolidation: 19.9% WR, −$5,282
- SHORT_RALLY_FADE × consolidation: 17.9% WR, −$5,493

---

## §7 ЖИВАЯ СИСТЕМА — ТЕКУЩИЕ ПРОЦЕССЫ

### 11 asyncio tasks в app_runner

| Task | Назначение | Telegram |
|---|---|---|
| orchestrator_loop | Активные действия по regime+matrix | ✅ |
| telegram_polling (DecisionLogAlertWorker) | Алерты с inline кнопками | ✅ |
| protection_alerts | Защитные алерты | ✅ |
| counter_long | P-3 hedge активация | ✅ |
| boundary_expand | P-1 raise boundary auto | ✅ |
| adaptive_grid | P-12 tighten/release | ✅ |
| paper_journal | Запись advise_signals.jsonl | — |
| decision_log | Запись events.jsonl / outcomes | — |
| dashboard | Обновление dashboard_state.json | — |
| telegram_polling (TelegramBotApp) | Реактивные ответы на команды | ✅ |
| supervisor daemon | Crash/memory alarms | ✅ |

### Tracker (ginarea_tracker/)

Собирает snapshots каждые 60s → `ginarea_live/snapshots.csv`
Supervisor следит через PID lock + cmdline_must_contain.
Windows venv shim pattern: supervisor хранит PID shim, fallback по cmdline.

---

## §8 ДАННЫЕ

### Frozen OHLCV

| Файл | Период | Статус |
|---|---|---|
| backtests/frozen/BTCUSDT_1h_2y.csv | 2024-04 → 2026-04 | ✅ OK |
| backtests/frozen/BTCUSDT_1m_2y.csv | 2024-04 → 2026-04 | ✅ OK |
| backtests/frozen/XRPUSDT_1h_2y.csv | 2024-04 → 2026-04 | ✅ OK |
| backtests/frozen/XRPUSDT_1m_2y.csv | 2024-04 → 2026-04 | ✅ OK |

1s OHLCV для reconcile всё ещё не загружено (ждёт TZ-ENGINE-FIX-RESOLUTION).

### Snapshots

`ginarea_live/snapshots.csv` — dedup clean (2026-05-02), 115,194 строк.
`ginarea_live/events.csv` — OUT_FILL/IN_FILL события.

---

## §9 PROJECT RULES (критичные)

**Pre-flight для каждого TZ:**
1. Goal — конкретная trader/project проблема
2. Allowed files — явный список
3. Forbidden files — явный список (MASTER.md, PLAYBOOK.md, OPPORTUNITY_MAP*.md, GINAREA_MECHANICS.md всегда forbidden без явного разрешения)
4. Acceptance — с числами и путями, не "тесты прошли"
5. Safety/rollback

**Three-file rule:** Source of truth = MASTER.md + PLAYBOOK.md + SESSION_LOG.md.
Не создавать новые .md для концепций которые уже в этих файлах.

**Trader-first filter:** Каждый TZ должен:
(а) лучшее risk-profile в реальной торговле, или
(б) тестирование hypothesis на real data, или
(в) защита капитала от bugs

**Inventory first:** перед любым TZ для нового модуля — grep services/ src/ tests/.

**Long ops rule:** прогоны >1h — подготовить скрипт, smoke <5 мин, дать команду оператору, остановиться.

**Phase awareness:** Phase 2/3 TZs не нарезаются пока Phase 1 не closed.

---

## §10 COMMUNICATION RULES

1. Кратко и точно. Без преамбул.
2. Если неизвестно — сказать "не знаю"
3. Не изобретать логику
4. Каждый TZ = self-contained блок. Никаких "см. выше"
5. Числа из backtests — только из реально запущенных, не из расчётов головой
6. Ответы на русском если нет явного указания
7. Скриншоты от оператора — приоритетный источник контекста рынка

---

## §11 КЛЮЧЕВЫЕ ФАЙЛЫ ДЛЯ НАВИГАЦИИ

| Файл | Содержимое |
|---|---|
| docs/MASTER.md | Главный reference doc проекта |
| docs/PLAYBOOK.md | P-1..P-12 паттерны с параметрами |
| docs/GINAREA_MECHANICS.md | Детальная механика GinArea |
| docs/STATE/ROADMAP.md | Phase roadmap с exit criteria |
| docs/STATE/QUEUE.md | Текущая очередь TZ |
| docs/STATE/SESSION_LOG.md | Лог сессий |
| docs/CONTEXT/STATE_CURRENT.md | Текущее состояние проекта (обновляется ежедневно) |
| docs/CANON/STRATEGY_CANON_2026-04-30.md | Стратегия + sizing rules + боли оператора |
| .claude/PROJECT_RULES.md | Rules для Code executor |
| .claude/skills/*.md | 9+ skills с trigger conditions |
