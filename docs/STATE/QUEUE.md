# Queue Navigator — 2026-05-02

> Живой навигатор очереди. Обновлять при каждом изменении статуса.

---

## Сегодня (поток B — Code)

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-COORDINATED-GRID-TRIM-DETAILS | Механика asymmetric trim победившего конфига $2k → playbook для оператора | Code | 2-3h | (а) стратегически | — | ✅ DONE |

---

## Сегодня (поток A — оператор + Claude)

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| A1 | Разбор live позиций под H10 логикой | Оператор+Claude | 30-60m | (а) стратегически | — | ⬜ OPEN |
| A2 | /advise v2 архитектура → ADVISE_V2.md | Оператор+Claude | 1-2h | (а) стратегически | — | ⬜ OPEN |

---

## Сегодня (поток B — Code, последовательно)

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-060 | Tracker analyzer (snapshots.csv 16-29.04) | Code | 1h | (а) тактически | — | ⬜ OPEN |
| TZ-061 | Live dashboard backend (JSON endpoint) | Code | 2h | (б) инфраструктура | — | ⬜ OPEN |
| TZ-062 | OHLCV ingestion script | Code | 1h | (б) инфраструктура | — | ✅ DONE |
| TZ-063 | AGM dry-run analyzer | Code | 2h | (а) тактически | — | ⬜ OPEN |

---

## Поток B — новые

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-ADD-BOT-PARAMS-TO-STATE | Добавить machine-readable params в state_latest.json | Code | 2h | (а) стратегически | — | ✅ DONE |
| TZ-RECONCILE-01-RETRY | Backtest vs real reconciliation (8 ботов) | Code | 3h | (а) стратегически | — | ✅ DONE (RED — stale-init) |
| TZ-PARAMS-FRESHNESS-GUARD | state_snapshot.py: guard params.csv age >15min + tracker not running → anomaly | Code | 15m | (в) защита капитала | — | ⬜ OPEN |

> RECONCILE-01-RETRY: engine_health=RED. Причина: stale-init artifact (не баг движка). Все 6 симулированных ботов — FAIL из-за каскадного срабатывания синтетических ордеров при инициализации. Требует TZ-ENGINE-FIX-STALE-INIT. См. [RECONCILE_01_2026-04-29T183424Z.md](RECONCILE_01_2026-04-29T183424Z.md)

---

## TZ-ENGINE-FIX (открыты по результатам RECONCILE-01-RETRY)

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-ENGINE-FIX-STALE-INIT | Reconcile v2: запустить sim с bot.started_at (16.04) вместо первого snapshot | Code | 3h | (а) стратегически | — | ✅ DONE (Fix #1 applied) |
| TZ-FIX-CONTRACT-TYPE-LABEL | state_snapshot.py: contract_type inverted (TEST_1/2/3 = linear, не inverse) | Code | 30m | (в) точность данных | — | ✅ DONE (state_snapshot.py:442 fixed) |
| TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | Верифицировать instop для LONG_C/D: Semant A или B? | Оператор+Code | 1h | (а) стратегически | — | ⬜ OPEN |
| TZ-ADD-ORDER-SIZE-TO-STATE | Добавить order_size в state_latest.json (хардкод из GINAREA_MECHANICS) | Code | 30m | (в) точность данных | — | ✅ INLINE DONE (reconcile only; state_latest.json pending) |
| TZ-ENGINE-FIX-RESOLUTION | Reconcile v3: 1-секундные bars для 0.03% grid (1m слишком грубо — 4–12× под-трейдинг) | Code | 4h | (а) стратегически | 1s OHLCV данные | ⬜ OPEN |

> RECONCILE-01-METHODOLOGY-FIX: engine_health=RED. Причина: 1m bar resolution слишком грубо для grid_step=0.03% (22 USDT). Реальный бот торгует по тикам → 4–12× больше сделок. Движок математически корректен. Требует TZ-ENGINE-FIX-RESOLUTION. См. [RECONCILE_01_2026-04-29T190838Z.md](RECONCILE_01_2026-04-29T190838Z.md)

---

## Перед сном

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| BT | Запуск overnight backtest H10 | Оператор | 5m | (а) стратегически | — | ⬜ OPEN |
| TZ-064 | HANDOFF document + STATE/QUEUE | Code | 1h | (в) нейтрально | — | ✅ DONE |

---

## Заблокировано (ждёт backtest утром)

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-057 | H10 bilateral dedup | Code | 2h | (а) стратегически | backtest results | 🔒 BLOCKED |
| TZ-065 | H10 live deployment (Telegram semi-auto) | Code | 3h | (а) стратегически | backtest results | 🔒 BLOCKED |
| TZ-066 | H10 calibration (data-driven thresholds) | Code | 2h | (а) стратегически | backtest results | 🔒 BLOCKED |

---

## Поток B — deferred

- TZ-TREND-STRENGTH-CAP-FIX: trend_strength_score не достигает 1.0 при regime trend_up. Добавить modifier +0.20 для |price_change_1h_pct| > 4.0% в trend_handler.py. ~10 мин Codex.

---

## Окно оператора

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-051 | Collectors leak fix rollout (taskkill PID 3456) | Оператор | 5m | (б) инфраструктура | — | ⬜ OPEN |
| TZ-067 | OHLCV догрузка 25.04..now | Оператор | 15m | (б) инфраструктура | TZ-062 | ⬜ OPEN |

---

## Долги

| ID | Долг | Статус |
|---|---|---|
| DEBT-02 | Re-arm logic в bt-симуляторе | 📋 BACKLOG — classified P2 / FIX-WHEN-TOUCH-AREA ([DEBT_CLASSIFICATION_2026-05-02.md](C:/bot7/docs/STATE/DEBT_CLASSIFICATION_2026-05-02.md)) |
| DEBT-03 | 12 pre-existing failures в test_protection_alerts.py | 📋 BACKLOG — classified P3 / ACCEPTED (stale debt; standalone test green) ([DEBT_CLASSIFICATION_2026-05-02.md](C:/bot7/docs/STATE/DEBT_CLASSIFICATION_2026-05-02.md)) |
| DEBT-04 | 49 collection errors в RUN_TESTS | ⬜ OPEN — split plan prepared (`TZ-DEBT-04-A`..`E`), current collect-only shows 91 errors ([debt_04_split_plan_2026-05-02.md](C:/bot7/reports/debt_04_split_plan_2026-05-02.md)) |
| DEBT-05 | Naming sync collectors vs market_collector в docs | 📋 BACKLOG — classified P3 / ACCEPTED ([DEBT_CLASSIFICATION_2026-05-02.md](C:/bot7/docs/STATE/DEBT_CLASSIFICATION_2026-05-02.md)) |

### DEBT-04 split backlog (Phase 0.5 / Phase 2 prep)

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-DEBT-04-A-IMPORT-SURFACE | Normalize import surface for `features/services/renderers/whatif/core` | Code | 2-3h | (б) инфраструктура | — | 📋 BACKLOG |
| TZ-DEBT-04-B-LEGACY-API-DRIFT | Fix missing exported symbols / stale API imports after import-surface cleanup | Code | 1-2h | (б) инфраструктура | TZ-DEBT-04-A | 📋 BACKLOG |
| TZ-DEBT-04-C-DUPLICATE-MODULE-NAMES | Resolve pytest import-mismatch / duplicate basename collisions | Code | 30-45m | (б) инфраструктура | — | 📋 BACKLOG |
| TZ-DEBT-04-D-SERVICE-SUBPACKAGES-COLLECT | Clean remaining grouped service test families after root import fixes | Code | 1-2h | (б) инфраструктура | TZ-DEBT-04-A | 📋 BACKLOG |
| TZ-DEBT-04-E-COLLECT-SHIELD | Add collect-only regression guard after cleanup | Code | 30-60m | (б) инфраструктура | TZ-DEBT-04-A/B/C/D | 📋 BACKLOG |

---

## Закрыто сегодня (29.04)

| ID | Задача | Результат |
|---|---|---|
| TZ-040 | Real-replay layer для What-If | ✅ Реализован с bot snapshot данными |
| TZ-041 | Episodes window regeneration | ✅ Data-blocked после 2026-04-24 |
| TZ-042 | Tests fixtures fix | ✅ Fixture-зависимости исправлены |
| TZ-044 | Backtest state isolation | ✅ Hermetic + детерминизм восстановлен |
| TZ-046 | app_runner leak fix | ✅ Утечка памяти устранена |
| TZ-048 | Collectors leak fix | ✅ ParquetWriter rotation; prod rollout pending |
| TZ-049 | Collectors recovery | ✅ Восстановлено из dangling git trees |
| TZ-053a | H10 MVP code | ✅ 150 setups, 79.3% win, max DD -1.16%, 20/20 тестов |
| TZ-055 | Critical docs recovery | ✅ PLAYBOOK+GINAREA восстановлены; pre-commit hook |
| TZ-056 | H10 detector rebuild | ✅ C1=[2,3,4,6,8,12]h ≥1.5%, C2=6-48h ≤2.5%; 5/5 GT ✓ |
| TZ-058 | Project Guard skill | ✅ PROJECT_RULES.md + regression_baseline_keeper skill |
| TZ-059 | 9 skills system | ✅ 9 skills + trigger index + bidirectional enforcement |
| TZ-064 | Handoff document | ✅ HANDOFF + STATE/QUEUE + hook + MASTER + SESSION_LOG |
| TZ-062 | OHLCV ingest script | ✅ scripts/ohlcv_ingest.py; BTCUSDT gap filled + XRPUSDT initial download |
| TZ-ADD-BOT-PARAMS-TO-STATE | Bot params → state_latest.json | ✅ API-primary + params.csv fallback; config_source logged |
| TZ-RECONCILE-01-RETRY | Reconcile 8 ботов | ✅ engine_health=RED (stale-init artifact). TZ-ENGINE-FIX-STALE-INIT opened |
