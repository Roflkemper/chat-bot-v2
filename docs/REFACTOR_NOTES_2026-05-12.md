# Refactor Notes — 2026-05-12

Bugs found and fixes applied during the overnight cleanup-pass.

## ✅ Fixed

### 1. Collector restart-loop every 2-4 min (pre-existing, several weeks)

**Symptom:** `logs/watchdog.log` showed `market_collector` `NOT RUNNING — starting`
every 2-4 minutes, even though the collector reported no errors and OHLCV data
kept flowing. New process exited immediately with `collector.already_running — exiting`.

**Root cause:** PID-lock check used `os.kill(pid, 0)` to test liveness on
Windows. Windows recycles PIDs quickly — the recorded PID often belonged to an
**unrelated** process (PowerShell, browser, etc.), so the liveness check
falsely returned True, and collector exited thinking another copy was running.

**Fix:** [market_collector/collector.py](../market_collector/collector.py)
`_acquire_pid_lock()` Windows branch now also verifies the process cmdline
contains `market_collector` via psutil. False positives eliminated.

```python
def _process_is_our_collector(pid: int) -> bool:
    proc = psutil.Process(pid)
    if not proc.is_running():
        return False
    cmdline = " ".join(proc.cmdline() or [])
    return "market_collector" in cmdline
```

---

### 2. `_csv.Error: line contains NUL` in decision_log

**Symptom:** [logs/errors.log](../logs/errors.log) had recurring
`_csv.Error: line contains NUL` from `services.decision_log.event_detector._read_csv_latest_by_bot`
on `params.csv`. Loop iteration failed → decision_log silently skipped events.

**Root cause:** `params.csv` sometimes contains NUL bytes (`\x00`) — likely
when a writer is interrupted mid-write (Ctrl-C / kill during fsync).
Standard `csv.DictReader` aborts on first NUL.

**Fix:** [services/decision_log/event_detector.py](../services/decision_log/event_detector.py)
`_read_csv_latest_by_bot()` now reads file as bytes, strips `\x00`, then
parses. Handles partial-write corruption gracefully + logs once if NULs seen.

---

### 3. Dead-code duplicate `MIN_ALLOWED_STRENGTH` in constants.py

Was declared in both `combo_filter.py` (used) and `constants.py` (unused).
Removed declaration in `constants.py`, kept as documentation comment with
pointer to combo_filter.py.

---

### 4. Hyperliquid liquidations - claim "not feasible" was wrong

Earlier in the session I declared HL liq "blocked, no public stream". This
was wrong — `collectors/liquidations/hyperliquid.py` already had a working
implementation using `trades` channel + `liquidation` flag filter.

When I noticed `collectors.main` supervisor existed but wasn't running,
restoring it auto-enabled HL liq capture along with orderbook L2 + trade ticks.

---

### 5. Watchdog 2-hour silent gap (2026-05-11 22:02 → 00:00)

**Symptom:** `logs/watchdog.log` had no entries for 2 hours. Bot was effectively
unsupervised: had app_runner crashed, no auto-restart would happen.

**Diagnosis:** Task Scheduler config `MultipleInstances=IgnoreNew` meant new
triggers were dropped if previous run was still alive — and `psutil.process_iter`
likely hung on a zombie process.

**Fix:** Already applied earlier in session.
- [scripts/watchdog.py](../scripts/watchdog.py) `_install_self_timeout(90)` —
  daemon thread that `os._exit(2)` after 90s.
- Task Scheduler: `MultipleInstances=Parallel`, `ExecutionTimeLimit=PT2M`,
  `AllowHardTerminate=True`.
- [scripts/watchdog_health_check.py](../scripts/watchdog_health_check.py) —
  new task at 10-min interval, alerts TG if watchdog.log stale >8 min.

---

## ⚠️ Known issues — not fixed (documented for future)

### 6. 63 constants defined in 2+ files (DRY violation)

Scan found 63 named constants that exist in multiple files. Examples:
- `DERIV_LIVE_PATH` — 5 files all pointing to `state/deriv_live.json`
- `DEDUP_PATH` — 6 files (each per-service, mostly different paths, but pattern)
- `DEPOSIT_USD`, `COOLDOWN_SEC`, `FROZEN_1M`, `ETH_CORR_LOOKBACK` — multiple files

**Risk:** if one is changed in one place, others drift silently. **No live
incidents observed**, but bomb is set.

**Action proposed:** central `services/_paths.py` module that exports the
canonical constants; all services import from there. ~3 days of careful
refactor + tests. Not urgent.

### 7. Two parallel collector frameworks

`market_collector/` (sync, CSV, alert-feeding) and `collectors/` (async,
parquet, archive). Both now running. Documented in
[docs/COLLECTOR_FRAMEWORKS.md](COLLECTOR_FRAMEWORKS.md).

Not a bug — they serve different SLAs (latency vs throughput). Don't merge
without strong reason; the cost of integration outweighs the gain.

### 8. Orderbook collector — 8-day silent outage (2026-05-03 → 2026-05-11)

`collectors/main.py` was not autostarted by anything. orderbook L2 + trades
weren't being captured for 8 days. Fixed by adding `collectors_supervisor`
to watchdog [scripts/watchdog.py](../scripts/watchdog.py).

How could we have caught this earlier? Add a freshness alert to
`watchdog_health_check.py` — if any data dir's latest mtime is > 1h, alert.
**TODO** for next pass.

### 9. A2 sub-agent miscount of "5 working liquidation feeds"

The 2026-05-11 brainstorm session said "5 exchanges (Bybit, Binance, BitMEX,
OKX, Hyperliquid) working". Actually only Bybit was writing to the live CSV;
the others' WSes connected but produced no data due to per-symbol stream
quietness (Binance) or were never deployed (OKX, BitMEX, HL).

**Lesson learned:** sub-agents that summarize codebase state should verify
**disk-state freshness**, not just code presence. Memory file
`feedback_data_freshness_check.md` already documents this — agents need to
respect it.

---

## Tests

All passing after fixes:
- [tests/services/setup_detector/test_session_breakout.py](../tests/services/setup_detector/test_session_breakout.py) — 11
- [tests/services/setup_detector/test_p15_lifecycle.py](../tests/services/setup_detector/test_p15_lifecycle.py) — 5
- [tests/services/telegram/](../tests/services/telegram/) — 60
- [tests/market_collector/test_liquidations_parsing.py](../tests/market_collector/test_liquidations_parsing.py) — 11

Total: **87 tests pass**.

---

## Confluence detector (in flight)

Backtest running in background (PID ~2227, log at /tmp/confluence.log). Will
add results when finished.

---

## Files changed this pass

- `market_collector/collector.py` — Windows PID-lock cmdline verification
- `services/decision_log/event_detector.py` — robust CSV reader with NUL stripping
- `services/setup_detector/constants.py` — removed dead-code duplicate
- `docs/COLLECTOR_FRAMEWORKS.md` — new doc, explains two frameworks
- `docs/REFACTOR_NOTES_2026-05-12.md` — this file
- `tools/_backtest_confluence.py` — new, confluence backtest (running)
