# Config naming inventory

## Variables in config.py
- `BOT_TOKEN`
- `CHAT_ID`
- `CONFIG_SOURCE`
- `ENABLE_TELEGRAM`
- `ENABLE_ML`
- `LOOP_SECONDS`
- `AUTO_EDGE_ALERTS_ENABLED`
- `AUTO_EDGE_ALERTS_INTERVAL_SEC`
- `AUTO_EDGE_ALERTS_COOLDOWN_SEC`
- `AUTO_EDGE_ALERTS_TIMEFRAMES`
- `ML_MODEL_PATH`
- `MIN_CONFIDENCE_TO_TRADE`
- `MIN_RR`
- `MIN_URGENCY_TO_ACT`
- `BOT_LABELS`
- `COINGLASS_API_KEY`
- `COINGLASS_BASE_URL`
- `COINGLASS_TIMEOUT_SEC`
- `COINGLASS_CACHE_TTL_SEC`
- `KILLSWITCH_INITIAL_BALANCE_USD`
- `KILLSWITCH_DRAWDOWN_THRESHOLD_PCT`
- `KILLSWITCH_FLASH_THRESHOLD_PCT`
- `KILLSWITCH_FLASH_WINDOW_SEC`
- `ORCHESTRATOR_LOOP_INTERVAL_SEC`
- `ORCHESTRATOR_DAILY_REPORT_TIME`
- `ORCHESTRATOR_ENABLE_AUTO_ALERTS`
- `ADVISOR_DEPO_TOTAL`
- `ADVISOR_DD_THRESHOLD_USD`
- `ADVISOR_STALE_MAX_SEC`

## Import call sites
- `C:\bot7\app_runner.py:9` — `from config import (...)`
- `C:\bot7\services\telegram_runtime.py:13` — `import config`, uses `config.BOT_TOKEN`
- `C:\bot7\services\telegram_alert_client.py:7` — `import config`, uses `config.BOT_TOKEN` and `config.CHAT_ID`
- `C:\bot7\src\supervisor\daemon.py:61` — `from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_IDS`
- `C:\bot7\services\advise_v2\paper_journal.py:115` — `from config import ADVISOR_DEPO_TOTAL`
- `C:\bot7\src\advisor\v2\cascade.py:105` — `from config import ADVISOR_STALE_MAX_SEC`
- `C:\bot7\src\advisor\v2\portfolio.py:60` — `from config import ADVISOR_DD_THRESHOLD_USD`
- `C:\bot7\src\advisor\v2\portfolio.py:166` — `from config import ADVISOR_DEPO_TOTAL`

## Canonical naming decision
- Chosen: `BOT_TOKEN` / `CHAT_ID`
- Reason:
  - Existing live Telegram consumers already use `BOT_TOKEN` / `CHAT_ID`
  - `src/supervisor/daemon.py` is the outlier
  - `CHAT_ID` already supports single or comma-separated multiple ids in other live consumers, so supervisor can normalize it into a list locally without changing `config.py`

## Files to change
- `src/supervisor/daemon.py`
  - Replace dead import of `TELEGRAM_BOT_TOKEN` / `AUTHORIZED_CHAT_IDS`
  - Import `BOT_TOKEN` / `CHAT_ID`
  - Normalize `CHAT_ID` into a local list before HTTP send loop
- `tests/supervisor/test_daemon_imports.py`
  - Add regression coverage for importability and dead-import absence
- `tests/supervisor/__init__.py`
  - Package marker only

## Call sites intentionally not changed
- `services/telegram_runtime.py`
- `services/telegram_alert_client.py`
- `app_runner.py`
- advisor-related config consumers

They already use canonical names or unrelated config fields, so changing them would add regression risk without fixing the supervisor bug.
