# HANDOFF 2026-04-29 evening

> Передача контекста новому чату. Читать в порядке разделов 1→9.

---

## 1. Project state at a glance

| Параметр | Значение |
|---|---|
| Active phase | 5 — data collection + analytics |
| Депозит | ~$15k + ожидается $10-20k через ~2 недели |
| Live позиции (29.04 14:00 UTC) | BTCUSDT шорт -0.708 BTC + BTCUSD лонг 14000 USD + 5 ботов BitMEX (BTC-LONG-B/C, GPT TEST 1/2/3) |
| Realized today | ~$2274 (бот + ручные) |
| Главный приоритет | H10 backtest на году → live deployment |
| Queue Navigator | [docs/STATE/QUEUE.md](STATE/QUEUE.md) |
| Главная ветка | main (HEAD 4c6fa28 = TZ-064) |
| Активные feature-ветки | feature/tz-043-features-coverage-extension, feature/tz-042-fix-tests-fixtures (содержимое в main, ветка оставлена для git-graph чистоты), feature/tracker-v2, feature/tz-015-portfolio-command |

---

## 2. Critical docs index

| Файл | Назначение |
|---|---|
| [docs/MASTER.md](MASTER.md) | Главный контекст проекта |
| [docs/PLAYBOOK.md](PLAYBOOK.md) | Приёмы P-1..P-12 |
| [docs/OPPORTUNITY_MAP_v1.md](OPPORTUNITY_MAP_v1.md) | Empirical playbook |
| [docs/SESSION_LOG.md](SESSION_LOG.md) | Журнал сессий |
| [docs/GINAREA_MECHANICS.md](GINAREA_MECHANICS.md) | Механика GinArea |
| [docs/STRATEGIES/H10.md](STRATEGIES/H10.md) | H10 спецификация и результаты |
| [.claude/PROJECT_RULES.md](../.claude/PROJECT_RULES.md) | Правила для Code |
| [.claude/skills/*.md](../.claude/skills/) | 9 skill-файлов |
| [docs/INCIDENTS.md](INCIDENTS.md) | Журнал инцидентов |

Все файлы tracked в git, защищены pre-commit hook (TZ-055 + TZ-058 + TZ-059 + TZ-064).

---

## 3. Closed today (12 ТЗ)

| ТЗ | Результат |
|---|---|
| TZ-040 real-replay layer | Реализован real-replay слой для What-If с bot snapshot данными |
| TZ-041 episodes window | Регенерация эпизодов на tracker window; data-blocked после 2026-04-24 |
| TZ-042 tests.fixtures fix | Исправлены fixture-зависимости в тестах |
| TZ-044 backtest state isolation | Backtest hermetic от live state/; детерминизм на frozen dataset восстановлен |
| TZ-046 app_runner leak fix | Фикс утечки памяти в app_runner.py |
| TZ-048 collectors leak fix | ParquetWriter rotation; prod rollout pending (TZ-051) |
| TZ-049 collectors recovery | Восстановление collectors/ из dangling git trees |
| TZ-053a H10 MVP code | 150 setups, 79.3% win rate, max DD -1.16%, 20/20 тестов |
| TZ-055 critical docs recovery | Восстановление PLAYBOOK+GINAREA из stash@{2}^3; pre-commit hook |
| TZ-056 H10 detector rebuild | C1=[2,3,4,6,8,12]h ≥1.5%, C2=6-48h ≤2.5%; 5/5 ground truth ✓ |
| TZ-058 Project Guard skill | .claude/PROJECT_RULES.md + regression_baseline_keeper skill |
| TZ-059 9 skills system | 9 skills + trigger index + bidirectional enforcement в pre-commit |

---

## 4. Tonight: backtest

```
scripts\run_backtest_h10_overnight.bat
```

- **Старт:** перед сном оператора
- **Лог:** `logs/backtest_overnight_<timestamp>.log`
- **ETA:** 8-10 часов
- **Утром:** открыть лог, найти итоговый отчёт `reports/h10_backtest_*.md`

---

## 5. Open queue — today's parallel work (10h)

**Поток A (оператор + Claude в чате):**

- A1: разбор live позиций под H10 логикой — 30-60 мин
- A2: `/advise` v2 архитектура → `docs/STRATEGIES/ADVISE_V2.md` — 1-2ч

**Поток B (Code, последовательно):**

- TZ-060: Tracker analyzer (snapshots.csv 16-29.04 анализ)
- TZ-061: Live dashboard backend (JSON endpoint)
- TZ-062: OHLCV ingestion script (запуск оператором отдельно)
- TZ-063: AGM dry-run analyzer

**Поток C (вечером):**

- TZ-064: handoff document (этот файл) ✅
- Запуск overnight backtest

---

## 6. Blocked queue (зависят от backtest results утром)

| ТЗ | Блокер |
|---|---|
| TZ-057: H10 bilateral dedup | Ждёт backtest results — нужна статистика по setup clustering |
| TZ-065: H10 live deployment | Ждёт backtest results — решение semi-auto через Telegram |
| TZ-066: H10 calibration | Ждёт backtest results — data-driven thresholds |

---

## 7. Operator window required

| ТЗ | Действие оператора |
|---|---|
| TZ-051: collectors leak fix rollout | `taskkill /PID 3456`, watchdog перезапустит на TZ-048 коде |
| TZ-067: OHLCV догрузка | Запуск TZ-062 на данных 25.04..now |

---

## 8. Backlog (debts)

| ID | Долг |
|---|---|
| DEBT-02 | Re-arm logic в bt-симуляторе |
| DEBT-03 | 12 pre-existing failures в test_protection_alerts.py |
| DEBT-04 | 49 collection errors в RUN_TESTS |
| DEBT-05 | Naming sync collectors vs market_collector в docs |

---

## 9. Onboarding instruction for new chat

Скопировать в первое сообщение нового чата:

```
Это продолжение проекта Grid Orchestrator. Прочитай:
1. docs/HANDOFF_2026-04-29_evening.md — текущий контекст
2. .claude/PROJECT_RULES.md — правила работы
3. .claude/skills/*.md — 9 skills для специфичных триггеров
4. docs/MASTER.md — общая картина проекта

После прочтения подтверди что готов работать по правилам:
- Trader-first фильтр (а)/(б)/(в) для каждого ТЗ
- PRE-FLIGHT CHECK обязателен
- Skills applied раздел в каждом ТЗ
- Прогон на больших данных — только локально оператором
- Деструктивные git операции — только с UNTRACKED PROTECTION блоком

Затем сообщи что нашёл в logs/backtest_overnight_*.log (результат ночного backtest H10).
```
