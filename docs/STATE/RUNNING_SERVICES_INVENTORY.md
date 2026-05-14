# Running Services Inventory

**Последнее обновление**: 2026-05-07 (regenerated from app_runner.py:229-244)
**Source**: `app_runner.py` (16 asyncio tasks) + `src/supervisor/daemon.py` (4 managed processes)

> Старая версия 30.04 заархивирована в `docs/ARCHIVE/superseded_2026-05-07/RUNNING_SERVICES_INVENTORY_2026-04-30.md` — ценна как snapshot до добавления paper_trader / stale_monitor / setup_detector / exit_advisor / market_intelligence / market_forward_analysis.

---

## Supervisor (4 processes)

Управляются `python -m src.supervisor.daemon`. См. `src/supervisor/process_config.py`.

| Component | Cmd | Health threshold | Telegram alarm |
|---|---|---|---|
| supervisor | `python -m src.supervisor.daemon` | self | crash via `_send_telegram_alarm` |
| app_runner | `python app_runner.py` | log stale 5 min | crash 3× → Telegram + restart disabled |
| tracker | `python ginarea_tracker/tracker.py` | log stale 15 min | same |
| collectors | `python -m market_collector.collector` | log stale 5 min | same |

Memory monitor: WARN 300 MB, ALARM 500 MB Telegram, RESTART 800 MB (app_runner only).

---

## app_runner asyncio tasks (16 шт.)

7 шлют Telegram, 9 не шлют (writers / pollers).

| # | Task name | Module | Telegram | Format prefix |
|---|---|---|---|---|
| 1 | telegram_polling | services/telegram_runtime.py:TelegramBotApp | ✅ | command response |
| 2 | orchestrator_loop | core/orchestrator/orchestrator_loop.py | ✅ | "🔄 ОРКЕСТРАТОР: ИЗМЕНЕНИЕ" |
| 3 | protection_alerts | services/protection_alerts/ | ✅ | "⚠️ ..." |
| 4 | counter_long | services/counter_long_manager.py | ✅ | "🟡 COUNTER-LONG триггер:" |
| 5 | boundary_expand | services/boundary_expand_manager.py | ✅ | "⚠️ BOUNDARY EXPAND:" |
| 6 | adaptive_grid | services/adaptive_grid_manager.py | ✅ | "⚠️ ADAPTIVE GRID:" |
| 7 | paper_journal | services/advise_v2/paper_journal.py | — | jsonl writer |
| 8 | decision_log | services/decision_log/ | ✅ (DecisionLogAlertWorker) | "🟡/🔴 Зафиксировано:" |
| 9 | dashboard | services/dashboard/ | — | dashboard_state.json updater |
| 10 | setup_detector | services/setup_detector/loop.py | — | setups.jsonl writer |
| 11 | paper_trader | services/paper_trader/loop.py | ✅ | "📈 PAPER LONG/SHORT @ ..." |
| 12 | stale_monitor | services/stale_monitor/ | ✅ | "⚠️ STALE DATA" / "✅ RECOVERED" |
| 13 | setup_tracker | services/setup_detector/tracker.py | — | setup outcomes writer |
| 14 | exit_advisor | services/exit_advisor/loop.py | ✅ | exit advisory |
| 15 | market_intelligence | services/market_intelligence/loop.py | ✅ | session brief, confluence alert, key event |
| 16 | market_forward_analysis | services/market_forward_analysis/loop.py | ⚠️ через signals.csv | — |

Внутри telegram_runtime запущены sub-workers: SignalAlertWorker (читает signals.csv), DecisionLogAlertWorker (читает events.jsonl), AlertWorker (market alerts).

---

## Ключевые observations

1. **Decision log != Orchestrator.** Decision log пассивный, фиксирует events с inline кнопками. Orchestrator активный, выдаёт recommendations / автоматические действия по action matrix.

2. **Многие P-* паттерны автоматизированы:**
   - P-1 raise boundary → boundary_expand task
   - P-3 counter-LONG hedge → counter_long task
   - P-12 adaptive grid tighten → adaptive_grid task
   - P-4 PAUSED via orchestrator

3. **Persistent dedup (state файлы)**:
   - `state/signal_alert_last_sent.json` — LEVEL_BREAK / RSI_EXTREME (TTL 30 min)
   - `state/telegram_sent_dedup.json` — full-text Telegram dedup (TTL 30 min)
   - `data/telegram/dedup_state.json` — DecisionLogAlertWorker dedup_layer (POSITION_CHANGE / BOUNDARY_BREACH / PNL_EXTREME)

4. **Critical vs non-critical task distinction**: telegram_polling, orchestrator_loop = critical (their crash → full shutdown). Все остальные non-critical (логируют ошибку, но main loop продолжается).

---

## Известные проблемы / технический долг

- **src/supervisor/daemon.py имел import bug** (config.TELEGRAM_BOT_TOKEN vs config.BOT_TOKEN) — supervisor crash/memory alarms могли тихо не работать. Pending fix через TZ-CONFIG-SUPERVISOR-FIX. Проверить на 2026-05-07.
- **Windows venv shim false-DEAD**: до 2026-05-07 supervisor `is_running()` ловил false-DEAD каждые 30s, плодя orphan процессы (был случай 34 одновременных Python). Закрыто в commit 247d4db (`is_running()` использует psutil cmdline-match как fallback).

---

## Как регенерировать этот inventory

```bash
grep -nE "^async def _run_|asyncio.create_task" app_runner.py
```

Или скриптом `scripts/state_snapshot.py` (генерирует `docs/STATE/PROJECT_MAP.md`).
