# RUNNING SERVICES INVENTORY — 2026-04-30

Inventoried by: TZ-RUNNING-SERVICES-INVENTORY  
Method: grep-based audit of all `send_message`/`send_telegram_alert` call sites + app_runner task list  
Scope: `services/`, `src/`, `core/`, `app_runner.py`

---

## Active services (running in production)

### 1. orchestrator_loop

- **Module:** `core/orchestrator/orchestrator_loop.py`
- **Asyncio task:** `orchestrator_task` — `app_runner.py:154`
- **Telegram output:** YES
  - **Entry point:** `send_telegram_alert()` → `TelegramAlertClient.send()` → `bot.send_message(CHAT_ID, text)`
  - **Trigger 1 — state change:** `dispatch_orchestrator_decisions()` returns `result.changed` → `_format_change_alert(change, regime)` — fired every loop tick when action transitions occur
  - **Trigger 2 — alert:** `result.alerts` items → `str(alert.text)` sent as plain text
  - **Trigger 3 — daily report:** `_maybe_send_daily_report()` at time set by `ORCHESTRATOR_DAILY_REPORT_TIME`
  - **Format (change alert):**
    ```
    🔄 ОРКЕСТРАТОР: ИЗМЕНЕНИЕ

    Категория: BTC ЛОНГ
    Действие: РАБОТАЕТ → ПАУЗА
    Причина: <reason_ru>

    Режим: trend_down
    Модификаторы: <list if any>

    Боты: <list if any>
    ```
  - **No inline buttons.** Plain text only.
  - **Gate:** `ORCHESTRATOR_ENABLE_AUTO_ALERTS` config flag (default True)
- **Last commit:** `7870ed7`
- **Purpose:** Notifies operator of regime-driven bot action transitions and daily summary
- **Status:** ACTIVE

---

### 2. DecisionLogAlertWorker (thread inside telegram_polling task)

- **Module:** `services/telegram_runtime.py` — class `DecisionLogAlertWorker`
- **Asyncio task:** `telegram_polling` — `app_runner.py:153`  
  *(worker is a `threading.Thread` spawned by `TelegramBotApp`, not a separate asyncio task)*
- **Telegram output:** YES
  - **Entry point:** `self.bot.send_message(chat_id, text, reply_markup=markup)` — `telegram_runtime.py:490`
  - **Trigger:** polls `state/events.jsonl` every 15s, sends any WARNING or CRITICAL events not yet seen
  - **Format:**
    ```
    🟡 Зафиксировано: BOUNDARY_BREACH

    Бот 12:
    <event.summary>

    📍 Контекст в этот момент:
    Цена: $76,000 (+1.2% за 1ч)
    Режим: trend_down
    Шорты: $-50
    Свободная маржа: 30.0%

    Это было твоё решение?
    ```
  - **With InlineKeyboard:** ✅ Моё решение | 🤖 Автомат | ➕ Добавить причину | 👀 Игнорировать
- **Last commit:** `8a3a614` (fix: pre-seed `_seen_event_ids` on startup)
- **Purpose:** Real-time alerts for WARNING/CRITICAL decision log events; operator annotation flow
- **Status:** ACTIVE

---

### 3. protection_alerts

- **Module:** `services/protection_alerts.py`
- **Asyncio task:** `protection_task` — `app_runner.py:155`
- **Telegram output:** YES
  - **Entry point:** `_emit()` → `send_telegram_alert()` — `protection_alerts.py:172–173`
  - **Triggers:** BTC fast move (1m OHLCV), position stress (per-bot unrealized loss), liquidity danger (proximity to liq clusters)
  - **Format:** plain text, varied — e.g.:
    ```
    ⚠️ BTC: быстрое движение -X.X% за 5мин — <level>
    ДЕЙСТВИЕ ТРЕБУЕТСЯ: ...
    ```
  - **Debounce:** per-key in-memory debounce (`_should_send()` with `debounce_min`)
  - **Dry-run mode:** `self._dry_run` flag — logs but does not send if enabled
  - **No inline buttons.**
- **Last commit:** present in baseline
- **Purpose:** Protect against fast market moves and margin stress before human can react
- **Status:** ACTIVE

---

### 4. counter_long_manager

- **Module:** `services/counter_long_manager.py`
- **Asyncio task:** `counter_long_task` — `app_runner.py:156`
- **Telegram output:** YES
  - **Entry point:** `_notify()` → `send_telegram_alert()` — `counter_long_manager.py:405–407`
  - **Trigger:** cascade event detected (large BTC volume spike), resolved after timeout
  - **Format:**
    ```
    🟡 COUNTER-LONG триггер: каскад X.X BTC at 76,000
    Post-hoc resolve через Nмин.
    ```
  - **No inline buttons.**
- **Last commit:** present in baseline (TZ-ADAPTIVE-GRID era, 2026-04-26)
- **Purpose:** Notify when counter-long cascade condition is triggered
- **Status:** ACTIVE

---

### 5. boundary_expand_manager

- **Module:** `services/boundary_expand_manager.py`
- **Asyncio task:** `boundary_expand_task` — `app_runner.py:157`
- **Telegram output:** YES
  - **Entry point:** `_notify()` → `send_telegram_alert()` — `boundary_expand_manager.py:469–471`
  - **Triggers:** boundary expansion executed, daily limit reached, max offset reached
  - **Format:** plain text, e.g.:
    ```
    ⚠️ BOUNDARY EXPAND: BotAlias достиг лимита 3 расширений/24ч
    ```
  - **No inline buttons.**
- **Last commit:** present in baseline
- **Purpose:** Notify of grid boundary expansion actions and limit guards
- **Status:** ACTIVE

---

### 6. adaptive_grid_manager

- **Module:** `services/adaptive_grid_manager.py`
- **Asyncio task:** `adaptive_grid_task` — `app_runner.py:158`
- **Telegram output:** YES
  - **Entry point:** `_notify()` → `send_telegram_alert()` — `adaptive_grid_manager.py:586–588`
  - **Triggers:** grid tighten/release action, API error, daily limit reached
  - **Format:** plain text, e.g.:
    ```
    ⚠️ ADAPTIVE GRID: BotAlias достиг лимита 5 затяжек/24ч
    ❌ ADAPTIVE GRID API ERROR: BotAlias tighten — проверьте логи
    ```
  - **No inline buttons.**
- **Last commit:** `TZ-ADAPTIVE-GRID` 2026-04-26
- **Purpose:** Notify of adaptive grid parameter adjustments
- **Status:** ACTIVE

---

### 7. paper_journal

- **Module:** `services/advise_v2/paper_journal.py`
- **Asyncio task:** `paper_journal_task` — `app_runner.py:159`
- **Telegram output:** NO — writes only to `state/advise_signals.jsonl` / `state/advise_null_signals.jsonl`
- **Last commit:** `ef74db7`
- **Purpose:** Phase 1 — log advisor recommendations to JSONL for paper tracking
- **Status:** ACTIVE (no Telegram)

---

### 8. decision_log

- **Module:** `services/decision_log/auto_capture.py`
- **Asyncio task:** `decision_log_task` — `app_runner.py:160`
- **Telegram output:** NO — detector has `notifier=None`. Telegram goes through `DecisionLogAlertWorker` (see §2 above).
  - Detector runs `detector_run_once()` + `outcome_resolver_run_once()` every 300s
  - Writes events to `state/events.jsonl`; worker thread reads and sends
- **Last commit:** `TZ-DECISION-LOG-V2-NOISE-REDUCTION` 2026-04-30
- **Purpose:** Capture portfolio events and resolve outcomes; Telegram notification separated to worker
- **Status:** ACTIVE (no direct Telegram, indirect via worker)

---

### 9. dashboard

- **Module:** `services/dashboard/loop.py` + `services/dashboard/state_builder.py`
- **Asyncio task:** `dashboard_task` — `app_runner.py:161`
- **Telegram output:** NO — writes `docs/STATE/dashboard_state.json` every 300s
- **Last commit:** `TZ-DASHBOARD-LIVE-STRATEGY-VIEW` 2026-04-30
- **Purpose:** Build dashboard state JSON for the HTML dashboard viewer
- **Status:** ACTIVE (no Telegram)

---

### 10. telegram_polling (TelegramBotApp)

- **Module:** `services/telegram_runtime.py` — class `TelegramBotApp`
- **Asyncio task:** `polling_task` — `app_runner.py:153`
- **Telegram output:** YES (reactive — responses to user commands)
  - Commands handled: `/status`, `/protect_status`, `/protect_off`, `/protect_on`, `/protect_threshold`, `/boundary_status`, `/boundary_off`, `/boundary_on`, `/adaptive_grid_status`, `/adaptive_grid_off`, `/adaptive_grid_on`, `/logs`, `/restart`, `/advisor`, `/advisor_log`, `/snapshot`, `/roadmap`, `/events`, `/event`, `/outcomes`
  - Also handles callback queries (decision log annotation buttons)
  - **No proactive sends from this task directly** — only responds
- **Last commit:** `8a3a614`
- **Purpose:** User interaction layer; houses `DecisionLogAlertWorker` thread
- **Status:** ACTIVE

---

### 11. src/supervisor/daemon (separate process)

- **Module:** `src/supervisor/daemon.py` — `_send_telegram_alarm()`
- **Asyncio task:** NONE — runs as a separate OS process (supervisor daemon)
- **Telegram output:** YES (raw HTTP, no pyTelegramBotAPI)
  - **Entry point:** `requests.post(f"https://api.telegram.org/bot{token}/sendMessage", ...)` — `daemon.py:67`
  - **Credentials:** `config.TELEGRAM_BOT_TOKEN` and `config.AUTHORIZED_CHAT_IDS`
    - ⚠️ **UNCERTAIN:** `TELEGRAM_BOT_TOKEN` and `AUTHORIZED_CHAT_IDS` are NOT defined in `config.py` by those names. Current `config.py` exports `BOT_TOKEN` and `CHAT_ID`. If daemon imports these and they don't exist, `_send_telegram_alarm` will silently fail (wrapped in bare `except`).
  - **Triggers:** component crash loop (>N crashes in window), memory ALARM (≥500MB RSS), memory CRITICAL + auto-restart (≥750MB RSS)
  - **Format:**
    ```
    🚨 bot7 supervisor: <component> crashed Nx in N min — auto-restart disabled.
    Run: python -m bot7 restart <component>
    ```
    or: `bot7: MEMORY CRITICAL: app_runner PID=X RSS=NMB >= NMB — auto-restarting`
- **Last commit:** in baseline
- **Purpose:** Crash and memory guard — independent of app_runner lifecycle
- **Status:** ACTIVE (but Telegram delivery UNCERTAIN due to config var name mismatch)

---

## Telegram message routing

All Telegram output flows through **two independent clients** using the same bot token:

### Channel A: `TelegramAlertClient` (singleton)

Used by: orchestrator_loop, protection_alerts, counter_long_manager, boundary_expand_manager, adaptive_grid_manager, decision_log (daily report)  
Reads: `config.BOT_TOKEN` + `config.CHAT_ID`  
Method: `pyTelegramBotAPI TeleBot.send_message()`  
**No inline buttons** — plain text only

### Channel B: `TelegramBotApp.bot` (pyTelegramBotAPI instance)

Used by: `DecisionLogAlertWorker`, command responses  
Reads: `config.BOT_TOKEN` + `config.ALLOWED_CHAT_IDS` (normalized from `ALLOWED_CHAT_IDS` + `CHAT_ID`)  
Method: same `TeleBot.send_message()`, but with `reply_markup` for decision log events  
**Can have inline buttons**

### Channel C: Supervisor daemon (raw HTTP)

Used by: `src/supervisor/daemon.py`  
Reads: `config.TELEGRAM_BOT_TOKEN` + `config.AUTHORIZED_CHAT_IDS` (**names differ from A/B — delivery UNCERTAIN**)  
Method: `requests.post` direct HTTP

---

## Conflicts / Overlaps

| Conflict | Description | Risk |
|---|---|---|
| **Duplicate crash notification** | Supervisor sends crash alarm; orchestrator also sends if it crashes internally | Low — different triggers |
| **Noise potential from BOUNDARY_BREACH** | Both `protection_alerts` and `decision_log_worker` can fire for same boundary event (one from market data, one from JSONL) | MEDIUM — dedup now improved by `_load_seen_ids()` fix |
| **`TelegramAlertClient` vs `TelegramBotApp.bot`** | Two TeleBot instances created with same token. Telegram tolerates multiple bots polling simultaneously but it can cause confusion | Low — they use same token, messages go to same chat |

---

## Observed message investigation

### Message at 2026-04-30 16:41 ("🤖 ОРКЕСТРАТОР: ИЗМЕНЕНИЕ")

- **Source module:** `core/orchestrator/orchestrator_loop.py`
- **File:line of send call:** `orchestrator_loop.py:77` → `send_telegram_alert(self._format_change_alert(change, regime))`
- **Format function:** `_format_change_alert()` at `orchestrator_loop.py:86–104`
- **Actual leading emoji in code:** `🔄` (not `🤖` — user likely misread or misremembered the emoji)
- **Content match:** `КАТЕГОРИЯ: BTC ЛОНГ` ← `i18n_ru.py:57 "btc_long": "BTC ЛОНГ"`; `ДЕЙСТВИЕ: РАБОТАЕТ → ПАУЗА` ← `i18n_ru.py:26 "RUN": "РАБОТАЕТ"`, `i18n_ru.py:29 "PAUSE": "ПАУЗА"`
- **Trigger condition:** `dispatch_orchestrator_decisions()` detected a bot state transition from `RUN` to `PAUSE` for a `btc_long` category bot. This happens every orchestrator tick when `PortfolioStore` state diverges from what the regime requires.
- **Why at 16:41:** App runner was restarted at 16:26 (`python -m bot7 restart app_runner tracker collectors`). Orchestrator re-ran first tick ~seconds later, found BTC-LONG bot in state that needed to change, sent the alert.
- **No inline buttons** — confirms it's NOT from `DecisionLogAlertWorker`
- **Status:** ACTIVE — expected production behaviour

---

## Recommendations

1. **Config var mismatch in supervisor daemon** — `daemon.py` imports `config.TELEGRAM_BOT_TOKEN` and `config.AUTHORIZED_CHAT_IDS`, but `config.py` only exports `BOT_TOKEN` and `CHAT_ID`. Supervisor crash/memory alarms may be silently failing. Should alias or rename to unify. (No action taken — inventory only.)

2. **BOUNDARY_BREACH double-notify potential** — `protection_alerts` fires on market data conditions; `decision_log_worker` fires when `event_detector.py` writes BOUNDARY_BREACH to JSONL. They are different triggers (market move vs. parameter comparison) but could overlap in high-volatility periods. Consider reviewing overlap policy. (No action taken.)

3. **`TelegramAlertClient` vs `DecisionLogAlertWorker` — two TeleBot instances** — Not a bug (Telegram tolerates it) but can be confusing to trace message origin. A unified routing layer would help in future. (No action taken.)

4. **orchestrator restart cascade** — The 16:41 message is EXPECTED: orchestrator detects regime state on first tick post-restart and sends alerts for any bot transitions. This is not a bug. If operator wants silence after restart, `ORCHESTRATOR_ENABLE_AUTO_ALERTS=false` for a cooldown window is the lever.
