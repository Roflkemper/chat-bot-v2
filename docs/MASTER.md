# MASTER — Grid Orchestrator

**Last update:** 2026-04-27
**Owner:** Алексей (ROFLKemPer)
**Architect/reviewer:** Claude (этот чат)
**Code executor:** Claude Code (VS Code)
**Heavy compute:** локально на твоей машине

---

## §0 ПРАВИЛА ОБЩЕНИЯ (важнее всего, читать каждую сессию)

1. Кратко, по делу. Без преамбул.
2. Не повторять уже сказанное.
3. «Не знаю» / «нужно уточнение» — допустимые ответы.
4. Не выдумывать логику если не определена.
5. Экономить контекст.
6. Код — только необходимый минимум.
7. Архитектура → структура и логика → потом код.
8. Не переписывать проект без необходимости.
9. **Не плодить .md файлы.** Правки — в существующие.
10. Решения должны быть практически выполнимы.
11. Не спрашивать оператора "передал ли ты ТЗ исполнителю" — это его операционная работа, не блокер для следующего шага.
12. Когда работа завершена и Code/Codex отрапортовали — сразу формулировать следующий шаг или фиксировать handoff. Не ждать подтверждения "всё ок".
13. Не выдумывать данные/числа/статусы. Если факта нет в контексте или памяти — спросить или сказать "не знаю".
14. При завершении сессии каждое живое ТЗ должно существовать как файл `docs/specs/TZ-XXX.md`. ТЗ озвученные в чате без файла — не считаются переданными. Перед закрытием сессии Claude проверяет: для каждого ТЗ в очереди MASTER §11 существует соответствующий `.md` файл. Если нет — оформить как часть handoff'а.
15. Никаких строчных команд оператору. Все изменения, проверки, правки PLAYBOOK/MASTER/SESSION_LOG/spec'ов и техдолга — только через цельное ТЗ исполнителю.
16. ТЗ-целостность: каждое ТЗ исполнителю — один цельный самодостаточный блок, готовый к копированию. Никогда не "см.выше / в предыдущем сообщении". При правке существующего ТЗ — переписать весь ТЗ заново с правкой внутри, не давать дельту/добавление. Оператор не должен листать чат и собирать ТЗ по кускам.

**Анти-косяки (что я ломал в прошлом):**
- К14: «Code сделал» ≠ «работает в проде» (рестарт app_runner.py обязателен)
- К15: Если фикс не двигает числа → диагностика, не следующий фикс
- К16: Не предполагать список ботов — спрашивать /portfolio или память
- К17: Не писать ТЗ для несуществующей фазы (управление вместо аналитики на фазе 5)
- К18: Дочитывать материал до конца, не делать выводы по половине
- К24: Не делать новые алерты без дедупликации by default. LEVEL_BREAK 27.04 — пример как не надо.
- К25: "X тестов зелёных" в отчёте ≠ работает в проде (повтор К14). Обязательная проверка через продовый лог через 24h после деплоя.

---

## §1 ГЛАВНАЯ ЦЕЛЬ ПРОЕКТА

**Зарабатывать деньги всеми возможными способами**, опираясь на данные, не на интуицию.

Структурировать ручной процесс → собрать аналитику → прогнать все варианты → находить оптимальное по цифрам → использовать все возможности ботов и портфеля.

**Долгосрочная цель:** алгоритм торгует сам. Только когда докажет что **не хуже** оператора. До этого — аналитик-помощник.

**НЕ цель:** конкурс GinArea (1 место не догонять, отрыв 2.2x). Бонус-цель: $8-10M оборот.

---

## §2 ФАЗЫ ПРОЕКТА

| Фаза | Сейчас | Что делаем | Условие перехода |
|---|---|---|---|
| 5 | ✅ | Аналитик-помощник, dry-run, сбор данных | N≥10-30 эпизодов с outcome |
| 6 | | Полуавтомат: бот предлагает → оператор подтверждает | Точность ≥X% на N эпизодов |
| 7 | | 2 маленьких бота автоматически | Стабильный плюс на полуавтомате |
| 8 | | Масштабирование | Доказанная стратегия |

**Текущая фаза 5.** До перехода в 6 — никаких управляющих модулей (PUT /params, авто-actions). Только сбор и анализ.

---

## §3 АРХИТЕКТУРА СИСТЕМЫ

### Слои данных (сверху вниз)

**L1: Сырые данные** (raw)
- OHLCV 1m с Binance (BTC + ETH + XRP, 1 год истории)
- Open Interest 5m с Binance Futures (1 год)
- Funding rate 8h с Binance (1 год)
- Long/Short ratio с Binance (1 год)
- Liquidations real-time WS (Binance + Bybit + Hyperliquid)
- Snapshots ботов из ginarea_tracker (1m частота)
- Order book L2 — собирается с момента запуска коллектора

**L2: Фичи** (features)
- Технические: ATR, RSI, движение за N часов, объём-спайк, pin bar, engulfing
- ICT-сессионные: killzone active, distance to PDH/PDL/PWH/PWL/D-open, session H/L/midpoint, mitigation status
- Деривативы: OI delta, funding extreme, mark-spot premium, L/S ratio
- Кросс-актив: BTC↔ETH divergence, XRP impulse vs BTC
- Портфельные: позиции, distance to liq, свободная маржа, idle bots

**L3: Детекторы ситуаций**
Каждая минута истории → вектор активных ситуаций (полный список ниже)

**L4: What-If Backtest engine**
Берёт slice истории + действие из каталога + state портфеля → симулирует → outcome через 1ч/4ч/24ч

**L5: Карта возможностей**
Таблица: ситуация × действие × финансовый результат × вероятность. Обновляется при изменении детекторов или каталога действий.

**L6: Live `/advise`**
Утренняя сводка + реактивные алерты, потребляет Карту возможностей и текущие фичи.

**L7: Телеметрия**
advisor_log.jsonl + advisor_outcomes.jsonl — каждая рекомендация → через 1ч/4ч/24ч сравнение с фактом → метрика реальной точности.

---

## §4 ДЕТЕКТОРЫ СИТУАЦИЙ (draft, итерируется)

### Технические
- D-RANGE-NARROW: ATR(1h) < 0.3%
- D-RANGE-WIDE: 0.3% ≤ ATR(1h) < 0.5%
- D-MOVE-WEAK: |Δprice 1h| 0.5-1.5%
- D-MOVE-MEDIUM: |Δprice 1h| 1.5-2%
- D-MOVE-STRONG: |Δprice 1h| 2-3%
- D-MOVE-CRITICAL: |Δprice 1h| > 3%
- D-NO-PULLBACK: 3+ часовые свечи в одну сторону без коррекции
- D-PIN-BAR: тело ≤30%, тень ≥2× тела, close в противоположной трети [параметризуется]
- D-ENGULFING: текущая свеча поглощает предыдущую
- D-VOLUME-SPIKE: vol > k × SMA20(vol) [k параметр]
- D-RSI-EXTREME-1H: RSI(14, 1h) <30 / >70
- D-RSI-DIVERGENCE: цена new high, RSI lower high (или зеркально)

### ICT-сессионные
- D-SESSION-ASIA: 03:00-07:00 Warsaw
- D-SESSION-LONDON: 09:00-12:00 Warsaw
- D-SESSION-NY_AM: 16:30-18:00 Warsaw
- D-SESSION-NY_LUNCH: 19:00-20:00 Warsaw
- D-SESSION-NY_PM: 20:30-23:00 Warsaw
- D-AT-PDH: |price - PDH| < 0.2% [previous day high]
- D-AT-PDL: |price - PDL| < 0.2%
- D-AT-PWH / D-AT-PWL: previous week high/low
- D-AT-D-OPEN: подход к открытию дня
- D-AT-KZ-HIGH: подход к high активной killzone
- D-AT-KZ-LOW
- D-KZ-MID-MAGNET: цена возвращается к midpoint killzone
- D-KZ-RANGE-EXPANDED: текущая killzone больше avg(5)
- D-KZ-SWEEP: пробой killzone H/L и быстрый возврат внутрь
- D-NYO-FALSE-MOVE: первый час NY движение в одну сторону потом разворот

### Деривативы
- D-OI-EXPANSION: OI растёт > X% за час при росте цены (тренд)
- D-OI-CONTRACTION: OI падает > X% при росте цены (short squeeze)
- D-FUNDING-EXTREME-LONG: funding > 0.05% / 8h (перегретый лонг)
- D-FUNDING-EXTREME-SHORT: funding < -0.03% / 8h
- D-PREMIUM-EXTREME: |mark - index| > 0.1%
- D-LS-RATIO-EXTREME: top trader L/S > 3 или < 0.33

### Ликвидации
- D-LIQ-CASCADE-LONG: sum(liq.long) > N BTC за 60s
- D-LIQ-CASCADE-SHORT: sum(liq.short) > N BTC за 60s
- D-LIQ-CASCADE-WITH-REVERSAL: cascade + цена развернулась в противоположную сторону за 5min
- D-LIQ-CASCADE-NO-REVERSAL: cascade + продолжение движения

### Кросс-актив
- D-BTC-ETH-DIVERGENCE: BTC растёт, ETH стоит
- D-XRP-IMPULSE-SOLO: XRP +N% без движения BTC
- D-ALL-DUMP-SYNCHRO: BTC+ETH+XRP синхронно вниз с большим OI

### Портфельные
- D-PORT-IDLE: бот без сделок > 2h в активные часы
- D-PORT-LIQ-DANGER: distance to liq < 15%
- D-PORT-DEEP-DD: unrealized < -X% депозита
- D-PORT-SHORT-OVERLOAD: суммарный short > Y BTC
- D-PORT-MULTIPLE-PAIN: 3+ ботов одновременно в DD
- D-PORT-FROZEN: позиция максимум, цена за boundary, нет циклов > Z часов

**Параметры в квадратных скобках — для grid search.**

---

## §5 КАТАЛОГ ДЕЙСТВИЙ (draft)

Все действия которые What-If бэктест должен симулировать.

### Управление существующим ботом
- A-NOTHING: ничего не делать (baseline)
- A-STOP: stop бота, позиция остаётся
- A-RESUME: resume остановленного бота
- A-CLOSE-ALL: stop + close всех позиций бота
- A-CLOSE-PARTIAL-X: закрыть X% позиции (X = 25/50/75)
- A-RAISE-BOUNDARY: поднять upper (для шорта) или lower (для лонга) на N% [N параметр]
- A-LOWER-BOUNDARY: симметрично
- A-CHANGE-TARGET: изменить target_profit_pct
- A-CHANGE-GS: изменить grid_step
- A-CHANGE-SIZE: изменить order_size
- A-RESTART-WITH-NEW-PARAMS: rebalance — close + start с новыми параметрами

### Запуск нового бота
- A-LAUNCH-STACK-SHORT: новый шорт с тем же или другим preset
- A-LAUNCH-STACK-LONG: новый лонг
- A-LAUNCH-COUNTER-LONG: hedge LONG на каскаде, малый размер, TTL 15-45min
- A-LAUNCH-COUNTER-SHORT: hedge SHORT
- A-LAUNCH-IMPULSE: импульсный бот по триггеру

### Структурные
- A-CHANGE-CONTRACT-TYPE: переключить linear/inverse
- A-CHANGE-LEVERAGE: изменить плечо

**Параметры в квадратных скобках — для grid search.**

---

## §6 КАТАЛОГ ПРЕСЕТОВ БОТОВ

| Preset | side | gs | target | size | when |
|---|---|---|---|---|---|
| Range Volume | both | 0.2-0.3% | 0.19-0.21% | 0.003-0.009 BTC | боковик, нужен volume |
| Range Safe | both | 0.3-0.4% | 0.25-0.29% | 0.002-0.006 BTC | боковик + рынок выше средней |
| LONG-D-volume | long | 0.025-0.03% | 0.20-0.21% | $100 | основной лонг для volume |
| Far Short [HYP] | short | 0.5-0.8% | 0.4-0.6% | 0.001-0.003 BTC | критический рост >3% |
| Counter-LONG hedge | long | 0.3% | 0.25-0.35% | малый, TTL 15-45min | каскад short-liq + reversal |
| Impulse Long [REJ] | long | 0.3% | 0.8% | $900 | опровергнут на N=1 |

**Текущая live конфигурация:**
- TEST_1/2/3: SHORT, 0.001 BTC, 200 ордеров, gs 0.03%, target 0.25%, instop 0/0.018/0.03%, boundaries 68000-78600
- BTC-LONG-C/D: LONG inverse, $100, 220 ордеров, target 0.20-0.21%
- KLOD_IMPULSE: заморожен (триггер слишком строгий, 0 срабатываний за неделю)

---

## §7 ПРИНЦИПЫ ТОРГОВЛИ (фундаментальные правила оператора)

### P0: Никогда не закрывать в минус (без крайней необходимости)
Сетка должна вытащить через работу, не через ножницы. Исключения только при риске ликвидации или конце конкурсного периода.

### P1: Защита > возможность
При конфликте сигналов (рост >3% + каскад с разворотом): сначала остановить, потом наблюдать, потом действовать.

### P2: Boundaries = анти-сквиз, не рабочая зона
Бот должен работать **везде** на любой цене. Boundaries — только страховка от безумного движения. По мере подтверждённого тренда — контролируемо двигать границу.

### P3: Асимметрия контрактов
SHORT linear (BTCUSDT, qty в BTC, PnL в USDT). LONG inverse (XBTUSD, qty в USD, PnL в BTC). Не зеркалить правила.

### P4: Портфельная структура
2 шорта + 1 лонг минимум. Cross-margin pool. Net delta ≠ сумма позиций.

### P5: Сессионный контекст важен (ICT)
Один и тот же приём в Asia ≠ в NY AM. Учитывать killzone H/L, PDH/PDL, D-open.

### P6: «Что в голову — что в grid»
В голове — общая логика. Все числа — параметры grid search, не вопросы оператору. Если Claude спрашивает число — это сигнал что вопрос не туда.

### P7: Реальная торговля = сессии 1-4 недели
Не 2 года статичных границ. Окна теста должны соответствовать реальным сессиям.

### P8: Каскады, ралли, каждое движение — возможность
Зарабатываем на всём. Нет «ждём идеального момента». Если в ситуации X есть edge — действуем.

---

## §8 ИСТОЧНИКИ ДАННЫХ (только бесплатные)

| Данные | Источник | Период | Метод |
|---|---|---|---|
| OHLCV 1m | data.binance.vision | 1+ год | curl/wget zip |
| OI 5m историч. | Binance Futures API | 30 дней rolling | REST `/futures/data/openInterestHist` |
| OI long historic | data.binance.vision/futures/um/daily/metrics | 1+ год | curl |
| Funding 8h | data.binance.vision | 1+ год | curl |
| Long/Short ratio | data.binance.vision metrics | 1+ год | curl |
| Liquidations historic | Binance Futures forceOrders / собирать самим | partial | WS + storage |
| Liquidations real-time | Binance + Bybit + Hyperliquid WS | live | WS подписки |
| Order book L2 | Binance / Bybit WS | с момента запуска | WS + parquet writer |
| Bot snapshots | ginarea_tracker (наш) | от 23.04.26 | уже работает |

**Решение по покупным:** не покупаем (CoinGlass, Tardis, Amberdata) пока не упрёмся в потолок бесплатного. data.binance.vision покрывает 90% потребностей.

---

## §9 ИНДИКАТОР ICT KILLZONES (от оператора 26.04)

Pine Script скачан, логика понятна. Реализуем на Python независимо от TradingView.

**Сессии (NY time, в скобках Warsaw):**
- Asia 20:00-00:00 NY (03:00-07:00 Warsaw)
- London 02:00-05:00 NY (09:00-12:00 Warsaw)
- NY AM 09:30-11:00 NY (16:30-18:00 Warsaw)
- NY Lunch 12:00-13:00 NY (19:00-20:00 Warsaw)
- NY PM 13:30-16:00 NY (20:30-23:00 Warsaw)

**Что вычисляет:**
- Killzone H/L (пивоты до пробоя)
- Killzone midpoint (магнит)
- Range tracking (текущий + avg за N сессий)
- Pivot mitigation status (пробит/непробит)
- D/W/M open
- PDH/PDL/PWH/PWL/PMH/PML
- Day of week labels

**Применение для ботов:**
- PDH/PDL пробой → BOS, расширить boundaries в направлении
- Возврат к midpoint → mean reversion
- KZ H/L пробит и не вернулся → P-2 stack-bot
- Approach Asia low в London/NY → sweep ликвидности → P-3 counter-LONG
- Asia range очень узкий → прорыв в London/NY с продолжением

---

## §10 PLAYBOOK ПРИЁМЫ (краткая ссылка)

Полный каталог в **PLAYBOOK.md**. Список приёмов:

- P-1: Контролируемая раскачка boundary за хай (дискретные шаги)
- P-2: Stack-бот на остановке роста / откате (главный приём)
- P-3: Counter-LONG как hedge с TTL
- P-4: PAUSED state — стоп новых IN, ждать откат
- P-5: Частичная разгрузка (UNLOAD)
- P-6: Шорты на каскаде ликвидаций вверх
- P-7: Лонги — только после подтверждённого разворота
- P-8: Force-close + re-entry (гипотеза)
- P-9: Лонг fix на быстром росте / усиление на контролируемом
- P-10: Rebalance — close + перезаход
- P-11: Weekend gap false breakout
- P-12: Adaptive grid tighten in drawdown

---

## §11 ТЕКУЩИЙ СТАТУС (2026-04-29 final)

### В проде работает
- ginarea_tracker v2 (TZ-014) — 24/7, snapshots/events/params
- /portfolio в Telegram (TZ-015), 76 тестов 90% coverage
- /market, /regime команды
- COUNTER-LONG-AUTO с dual_alert (15/15 acceptance, dry-run)
- BOUNDARY-EXPAND (15/15, dry-run)
- ANTI-SPAM RSI (27/38=71% попадание)
- ADAPTIVE-GRID (закрыт после исправлений)
- app_runner.py — единый процесс orchestrator+telegram

### Live боты (на момент 27.04)
- ROFLKemPer: SHORT -0.576 BTC entry $78248, liq $102434 (запас 27.7%)
- LONG 7500 USD entry $77779
- Балланс $126,946 (+3.8% за 24ч)

### Закрыто / зафиксировано
- TZ-027: ✅ DONE 2026-04-29
- TZ-028-Codex: ✅ DONE 2026-04-29 (с ADDENDUM-2)
- TZ-032-Codex: ✅ DONE 2026-04-29 (verdict: rejected)
- TZ-029-A: ✅ DONE 2026-04-29
- TZ-029-B: ✅ DONE 2026-04-29
- TZ-030: ✅ DONE 2026-04-29
- TZ-031: ✅ DONE 2026-04-29
- TZ-D-ADVISOR-V1: ✅ DONE 2026-04-29
- TZ-D-ADVISOR-V1-FIX-1: ✅ DONE 2026-04-29
- TZ-D-ADVISOR-V1-FIX-2: ✅ DONE 2026-04-29
- TZ-D-ADVISOR-V1-FIX-3: ✅ DONE 2026-04-29
- TZ-D-ADVISOR-V1-FIX-3-FOLLOWUP: ✅ DONE 2026-04-29
- TZ-D-ADVISOR-V1-FIX-3-PATCH: ✅ DONE 2026-04-29
- TZ-033: ✅ DONE 2026-04-29
- TZ-034: ✅ DONE 2026-04-29
- TZ-034-FIX-1: ✅ DONE 2026-04-29
- TZ-035: ✅ DONE 2026-04-29
- TZ-035-FIX-1: ✅ DONE 2026-04-29
- TZ-036: ✅ DONE 2026-04-29
- TZ-038: ✅ DONE 2026-04-29
- TZ-038-FOLLOWUP: ✅ DONE 2026-04-29
- TZ-039: ✅ DONE 2026-04-29
- TZ-041-Codex: ✅ DONE 2026-04-29 (verdict: rejected)
- TZ-042: ✅ DONE 2026-04-29
- TZ-044: ✅ DONE 2026-04-29
- TZ-045: ✅ DONE 2026-04-29
- TZ-046: ✅ DONE 2026-04-29
- TZ-047: ✅ DONE 2026-04-28 (multi-asset episodes BTC+ETH+XRP, 7401 эпизодов)
- TZ-DEBT-07: ✅ DONE 2026-04-29 (закрыт через TZ-045)

### В очереди / в работе (на 29.04 final)

**Code очередь:**
1. PROD-CHECK 24h наблюдение
2. TZ-029-C 24h validation коллекторов
3. Дальше по рапорту нового чата

**Codex очередь:**
1. TZ-040 real bot snapshots в What-If (implemented, data-blocked)

**Backlog:**
- TZ-025 — alert noise fix
- TZ-026 — grid simulation для stack-приёмов
- TZ-DEBT-05 — funding обновление frozen/
- TZ-DEBT-06 — schema consec naming
- TZ-DEBT-02 — re-arm в bt-симуляторе
- TZ-DEBT-08 — ProcessPoolExecutor WinError 5 на Windows

### Frozen датасет (исторические данные) ✅ DONE 26.04
- BTC + ETH + XRP за 1 год (25.04.2025 → 24.04.2026)
- klines 1m: 525,600 строк × 3 актива = 1,576,800 минут (0 пропусков)
- metrics 5m: ~105,117 × 3 = ~315k точек (OI, L/S ratio retail+top, taker vol)
- fundingRate: 1188 × 3 = 3564 точек (с 01.03.2025)
- Расположение: `C:\bot7\scripts\frozen\{symbol}\_combined_*.parquet`
- Размер: ~270 MB

### Backtest engine
- Минутный движок B1.00 валидирован на 8h окне 24.04 (PASS p95<1%)
- Часовой движок инвалидирован (15% ошибка на час → ×20 дрейф на 2 годах)
- Расположение: `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat`
- Запуск: `$env:PYTHONPATH="src"; python -m backtest_lab.runners.run_phase0`
- Frozen baseline: 24 trades / 75% WR / +14.34% PnL / -2.15% DD (canonical TZ-011)

---

## §ШАГ 5 РЕЗУЛЬТАТЫ — What-If бэктест MVP

**Статус:** работает на P-1, готов к расширению.

### Архитектура (закреплена 27.04)
- Episode-driven simulation (не end-to-end backtest)
- Snapshot из реальной точки → action → horizon N минут → outcome vs baseline
- Решает проблему TZ-DEBT-02 (re-arm) через короткие горизонты

### Что работает
- 5 position presets (flat/short_small_drawdown/short_large_drawdown/short_critical/long_small)
- 10 atomic actions из MASTER §5 + 2 composite (P-6, P-12)
- 12 plays из PLAYBOOK с composite triggers через TZ-019
- Grid search по параметрам action
- Baseline сравнение (pnl_vs_baseline, dd_vs_baseline)
- CLI: `python -m src.whatif.runner --play P-X`

### Первые результаты P-1
- 196 эпизодов BTCUSDT за год
- P-1 raise_boundary на 240-min горизонте: -$2 alpha, защищает от пикового DD
- Реалистично: P-1 — защитный приём, не зарабатывающий
- Для адекватной оценки defensive plays нужны longer horizons (v2)

### Ограничения v1
- Position state синтетический (5 presets), не из реальных bot snapshots
- Liquidation эпизоды не используются (требуют ≥30 дней TZ-016 коллекторов)
- Macro context отсутствует (требует TZ-022 macro feed)
- Re-arm logic не моделируется (snapshot+horizon обходят)
- Symbol только BTCUSDT для P-1/P-2/P-6/P-12 (другие приёмы — другие symbols)

### Где смотреть результаты
- `whatif_results/{play_id}_{date}.parquet` — детальные данные
- `whatif_results/{play_id}_{date}.md` — отчёт (Шаг 7 pending)
- `whatif_results/manifest.json` — версия и параметры прогона

## §12 ПЛАН РАБОТ (фаза 5)

### Шаг 1 (этот чат, сегодня) — Консолидация
- ✅ MASTER.md (этот файл)
- ✅ PLAYBOOK.md v1.0
- ✅ SESSION_LOG.md
- Гайд по очистке 21 старого файла

### Шаг 2 — Скачивание исторических данных ✅ DONE 26.04
Скрипт `download_historical.py` запущен оператором, все 2229 файлов скачаны без ошибок за 8.6 минут. Валидация прошла:
- BTC klines 1m: 525,600 строк, диапазон 25.04.2025 → 24.04.2026 (0 пропусков)
- BTC metrics 5m: 105,117 строк (OI, L/S ratio, taker vol)
- BTC fundingRate: 1188 строк (с 01.03.2025)
- Аналогично для ETH и XRP

Output: `C:\bot7\scripts\frozen\{symbol}\{datatype}\` + `_combined_*.parquet`. Размер ~270 MB.

### Шаг 3 (Claude Code, параллельно) — Real-time коллекторы
Два постоянных процесса (PID-lock, launchd-ready):
- WS liquidations (Binance + Bybit + Hyperliquid)
- WS order book L2 + trades (Binance, BTC/ETH/XRP)
- Output: `live/{date}/{symbol}/{datatype}.parquet`
- Через 1-3 месяца = свой high-frequency датасет

### Шаг 4 (Claude Code, 3-5 дней) — Feature engine
Модуль `features/`:
- Технические индикаторы (ATR, RSI, pin bar, etc)
- ICT-фичи (killzones, pivots, D/W/M opens)
- Деривативные фичи (OI delta, funding extreme)
- Кросс-активные (BTC↔ETH divergence)
- Output: для каждой минуты истории → feature vector

### Шаг 5 (Claude Code, 1-2 недели) — What-If Backtest engine
Симулятор: berёт slice истории + действие из каталога + state портфеля → outcome через 1ч/4ч/24ч.
Параллелится по ядрам твоей машины.
Полный прогон ситуаций × действий за 1 год = несколько часов.

### Шаг 6 (этот чат, 1 неделя) — Анализ Карты возможностей ✅ DONE 28.04
По результатам What-If: где edge, где нет, на каких типах ситуаций какие действия лучшие.
Результат зафиксирован в `docs/OPPORTUNITY_MAP_v1.md`.

### Шаг 7 — ADVISOR live + 24h validation 🟡 IN PROGRESS (дедлайн 29.04)
- `/advise` v1 в проде на BTC/ETH/XRP
- live features writer + cascade reader на parquet
- 24h PROD-CHECK после TZ-046 рестарта
- 24h validation коллекторов после cutover

### Шаг 8 — Расширение What-If через real bot snapshots
- TZ-040 real bot snapshots в What-If
- уйти от синтетических presets к реальным портфельным состояниям
- Статус 2026-04-28: replay-слой и CLI собраны, но для P-1/P-2/P-6/P-7
  в текущем workspace нет временного overlap между tracker snapshots
  (старт 2026-04-23/24) и доступными episode windows. CI ranking на real
  data пока не пересчитан.

### Шаг 9 — Пересмотр OPPORTUNITY_MAP с расширенными данными
- обновление ranking после real snapshots / multi-asset / накопления outcome
- пересмотр confidence там, где сейчас CI overlap

### Фаза 6 — полуавтомат
- только после завершения фазы 5 validation
- сначала подтверждённая точность и стабильность ADVISOR, потом полуавтоматические действия
Фиксация результата: [OPPORTUNITY_MAP_v1.md](/C:/bot7/docs/OPPORTUNITY_MAP_v1.md)

### Шаг 7 (Claude Code, 1 неделя) — `/advise` v2
- Утренняя сводка (прогноз, рекомендации по ботам, условия входа/выхода, что мониторить)
- Реактивные алерты (по событиям из плана дня)
- Проактивные предложения с action (не «наблюдаем»)
- Опирается на Карту возможностей

### Шаг 8 (постоянно) — Сбор телеметрии
- advisor_log.jsonl — каждая рекомендация
- advisor_outcomes.jsonl — через 1/4/24h факт
- Накопление статистики реальной точности

### Шаг 9 (этот чат, 2-4 недели) — Решение по фазе 6
По собранной телеметрии: переход в полуавтомат (бот предлагает → оператор подтверждает).

---

## §13 ОТКРЫТЫЕ ВОПРОСЫ

### Заблокированы (ждут оператора)
- Параметры P-2 (доп. шорт): обычно те же или агрессивнее? зависимость от ситуации?
- P-9 порог «быстрый рост»: точные числа?
- P-3 точный порог пролива: 1.5% — анекдот, нужна калибровка
- P-5 какой % закрывать: 30, 50, 70?
- C-2 «большая позиция» в числах: 0.3, 0.5, 1.0 BTC?
- PAUSED → UNLOAD триггеры: X часов = ? Y% = ?
- Принципы выхода из больших шорт-позиций ($45k+ при росте выше 80k)

**Решение по этим вопросам:** все цифры будут параметрами grid search в What-If бэктесте. Оператору отвечать не обязательно — найдём оптимальные на данных.

### Заблокированы (ждут данных)
- Реальная эффективность TEST_1/2/3 на разных instop — неделя данных мало
- Counter-LONG: только 1 эпизод, нужно ≥5-10 для подтверждения
- KLOD_IMPULSE: триггер не сработал ни разу, переоткалибровать или удалить

### Решено в этой сессии
- Покупать данные не нужно (бесплатных хватает)
- ETH и XRP добавляются (не только BTC)
- ICT killzones — реализуем на Python из переданного кода
- 21 файл консолидируется в 3 (MASTER + PLAYBOOK + SESSION_LOG)
- Главная задача — what-if бэктест приёмов, не gird search параметров ботов

---

## §14 ПРОТОКОЛ НАЧАЛА НОВОЙ СЕССИИ

Скопировать в новый чат как первое сообщение, приложив файлы MASTER.md, PLAYBOOK.md, OPPORTUNITY_MAP_v1.md, SESSION_LOG.md (последние 3 записи):

```
Прочти MASTER, PLAYBOOK, OPPORTUNITY_MAP_v1 и последние 3 записи SESSION_LOG.

Подтверди в 5 строках:
1. Главная цель проекта
2. Текущая фаза по §2
3. Закрытые шаги §12 (1-N)
4. Какие ТЗ сейчас в работе у Code и Codex
5. Что следующее по плану

Правила общения (помимо memory):
- Коротко, чётко, по делу. Без преамбул. Без повторов.
- "Не знаю" / "нужно уточнение" — допустимые ответы.
- Не выдумывать данные, числа, статусы.
- Не спрашивать "передал ли я ТЗ" — это операционная работа оператора.
- Документация — только через ТЗ для Code/Codex.
- Следующий шаг формулировать сразу после рапорта о завершении.
- При завершении сессии каждое живое ТЗ должно существовать как файл `docs/specs/TZ-XXX.md`. ТЗ из чата без файла не считаются переданными.

Если что-то непонятно — один вопрос, потом работаем.
```
Прочти MASTER.md, PLAYBOOK.md и последние 3 записи SESSION_LOG.md.
Подтверди в 5 строках: главная цель проекта, текущая фаза, следующие 3 шага по плану §12.
Если что-то непонятно — спроси одним вопросом.
После этого работаем.
```

Если Claude в новой сессии ответил неверно — протокол требует правки. Откорректировать MASTER.md.

---

## §15 ИЗМЕНЕНИЯ ФАЙЛА

```
2026-04-26 v1.0 — Консолидация всех старых .md в один файл.
                  Источники: 21 файл (MASTER_CONTEXT v1-v1.3, STRATEGY v1-v1.4,
                  TZ_QUEUE v2-v3, DECISIONS v2-v3, LESSONS_LEARNED v1-v2,
                  SESSION_HANDOFF v2-v3, ROADMAP_BACKTEST, GINAREA_MECHANICS,
                  KILLSWITCH/CALIBRATION/ORCHESTRATOR/TELEGRAM design docs,
                  BASELINE_INVESTIGATION_DESIGN, PROJECT_MANIFEST, README).
                  Прочитаны 150 фрагментов переписки klod.txt полностью.
                  Добавлены: ICT killzones, новый каталог детекторов и действий,
                  план фаз 5-8, протокол начала сессии.
```
