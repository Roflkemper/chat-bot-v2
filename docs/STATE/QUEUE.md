# Queue Navigator — 2026-04-29 evening

> Живой навигатор очереди. Обновлять при каждом изменении статуса.

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
| TZ-062 | OHLCV ingestion script | Code | 1h | (б) инфраструктура | — | ⬜ OPEN |
| TZ-063 | AGM dry-run analyzer | Code | 2h | (а) тактически | — | ⬜ OPEN |

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

## Окно оператора

| ID | Задача | Кто | Время | Trader-first | Блокер | Статус |
|---|---|---|---|---|---|---|
| TZ-051 | Collectors leak fix rollout (taskkill PID 3456) | Оператор | 5m | (б) инфраструктура | — | ⬜ OPEN |
| TZ-067 | OHLCV догрузка 25.04..now | Оператор | 15m | (б) инфраструктура | TZ-062 | ⬜ OPEN |

---

## Долги

| ID | Долг | Статус |
|---|---|---|
| DEBT-02 | Re-arm logic в bt-симуляторе | 📋 BACKLOG |
| DEBT-03 | 12 pre-existing failures в test_protection_alerts.py | 📋 BACKLOG |
| DEBT-04 | 49 collection errors в RUN_TESTS | 📋 BACKLOG |
| DEBT-05 | Naming sync collectors vs market_collector в docs | 📋 BACKLOG |

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
