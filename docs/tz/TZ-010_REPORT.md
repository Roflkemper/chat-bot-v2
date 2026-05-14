# TZ-010 Report

## 1. Changed / created files

- `app_runner.py` - added unified runtime entry point that runs Telegram polling and orchestrator in one process with coordinated shutdown.
- `RUN_APP.bat` - added Windows launcher for the unified runtime entry point.
- `services/telegram_runtime.py` - added `TelegramBotApp.run_polling_blocking()` for single-pass polling startup without the legacy external restart loop.
- `telegram_bot_runner.py` - added `DeprecationWarning` pointing users to `app_runner.py`.
- `orchestrator_runner.py` - added `DeprecationWarning` pointing users to `app_runner.py`.
- `tests/test_app_runner.py` - added coverage for unified runtime startup, crash propagation, graceful shutdown, polling startup, and legacy runner warnings.

## 2. RUN_TESTS.bat output

Run in `C:\bot7`:

```text
[INFO] Running regression shield tests...
....................s................................................... [ 29%]
........................................................................ [ 59%]
........................................................................ [ 88%]
...........................                                              [100%]
242 passed, 1 skipped in 70.69s (0:01:10)

[OK] Regression Shield passed.
```

## 3. Baseline backtest output

Run in `C:\bot7` via `RUN_BACKTEST_180D_FREEZE_DATA.bat`:

```text
============================
BACKTEST 180D START [FREEZE DATA]
============================
[INFO] Using project venv python

[INFO] Freezing 180d data...
FROZEN_DATA_SAVED: backtests/frozen/BTCUSDT_1h_180d_frozen.json
BARS: 1000

[INFO] Running 180d frozen backtest...
DATA_SOURCE: FROZEN:backtests/frozen/BTCUSDT_1h_180d_frozen.json
BACKTEST 180D
Trades: 24
Winrate: 79.17%
Avg RR: 0.4471
PnL: 18.7663%
Max DD: -2.1542%
IF-THEN:
- triggered: 417
- armed: 24
- entered: 24
- closed: 24
- failed: 45
EXITS:
- tp_hit: 3
- stop: 16
- timeout: 5
REPORT: backtests/backtest_180d_report.json

[INFO] Exit code: 0
============================
BACKTEST 180D FINISHED
============================
```

Expected baseline from TZ: `23 / 78.26% / +16.1393% / -2.1542%`.

This did **not** match in `C:\bot7`. I did not modify `core/orchestrator/*`, `core/pipeline.py`, `config.py`, `backtests/*`, `handlers/*`, or `services/telegram_alert_*`; the code changes are limited to runtime / runner files listed above. The mismatch is therefore reported as an acceptance blocker, not hidden.

## 4. What was actually done

- Added a new unified async entry point that starts Telegram long polling in an executor thread and the orchestrator as an asyncio task.
- Added coordinated shutdown logic so either signal, polling failure, or orchestrator failure triggers shared teardown.
- Kept legacy runner behavior intact and only added `DeprecationWarning` messages to redirect runtime usage.
- Added a dedicated `run_polling_blocking()` path in `TelegramBotApp` so unified runtime can reuse the existing bot setup without the legacy infinite restart loop.
- Added tests for clean stop, orchestrator crash, polling crash, signal-driven shutdown, polling startup, and deprecation warnings.
- Verified the regression suite passes with the new tests included.

## 5. Non-obvious decisions

- `app_runner.main()` accepts injectable `stop_event`, signal installer, and shutdown timeout to make shutdown behavior testable without changing the CLI entry point contract.
- `run_in_executor()` was kept as the polling bridge, following the design doc, so polling remains synchronous and exceptions still propagate into asyncio supervision.
- Legacy `run()` in `TelegramBotApp` was left unchanged to preserve backward compatibility for old runners.

## 6. Not completed / blockers

- Baseline acceptance metric did not reproduce in `C:\bot7`; actual output was `24 / 79.17% / +18.7663% / -2.1542%`.
- Manual Telegram smoke test (`/help`, `/portfolio`, orchestrator tick, Ctrl+C`) was not executed in this session.
