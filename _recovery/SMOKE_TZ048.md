# SMOKE TZ-048 — Collectors Memory Leak Fix

**Date:** 2026-04-29  
**Branch:** feature/tz-048-collectors-leak

---

## Root Cause Analysis

`pq.ParquetWriter` was kept open per day (only closed at midnight or on shutdown).
PyArrow's C++ `FileMetaDataBuilder` accumulates row group metadata (statistics, offsets,
schema per column) in native heap for every `write_table()` call.  The metadata is only
released on `writer.close()`.  With writers open for up to 24 hours across 8 active
buffers, this causes linear RSS growth.

**8 active buffers:** orderbook/{BTCUSDT,ETHUSDT,XRPUSDT}, liquidations x5 (Binance,
Bybit, Hyperliquid, BitMEX, OKX).  The orderbook buffers are highest frequency
(continuous L2 snapshots) and contribute most to metadata accumulation.

## Production Baseline (before fix) — from memory.log

| Timestamp (UTC) | Collectors RSS |
|---|---|
| 2026-04-28 22:08 | 96.9 MB |
| 2026-04-28 22:18 | 100.0 MB |
| 2026-04-28 22:28 | 104.2 MB |
| 2026-04-28 22:38 | 108.5 MB |
| 2026-04-28 22:48 | 112.9 MB |
| 2026-04-29 00:08 | 86.9 MB *(new process after restart)* |
| 2026-04-29 01:08 | 100.1 MB |

Rate (session 1): **+24 MB/hour**  
Rate (session 2): **+13.2 MB/hour**  
Acceptance criterion: ≤ 5 MB / 60 min

## Fix

File: `collectors/storage.py` + `collectors/config.py`

Thresholds (defaults):

| Threshold | Value | Rationale |
|---|---|---|
| `WRITER_MAX_ROWS` | 100,000 rows | ~20min for orderbook at peak; days for liquidations |
| `WRITER_MAX_BYTES` | 50 MB | safety: prevents single over-large files |
| `WRITER_MAX_AGE_S` | 1800 s (30 min) | age-based bound regardless of row count |

Rotation logic: after `write_table()`, if any threshold exceeded — `writer.close()`,
`_rows_written = 0`, `_writer_opened_at = 0.0`, path advanced to next suffix via
`_parquet_path()` (existing naming: `{date}_N.parquet`).  No schema changes.
No downstream impact (readers use CSV, not collector parquets).

## Dev Smoke (profile_writers.py — 90s, WRITER_MAX_AGE_S=10s)

Forced rapid rotation (every 10s) to confirm rotation mechanism works and memory is
bounded in a short test window.

**Result:** Rotation confirmed working. In 90 seconds with `WRITER_MAX_AGE_S=10`:
- BTCUSDT orderbook: 7 rotated files (2026-04-29.parquet … 2026-04-29_7.parquet)
- 21 total part-files across all 8 buffers — rotation triggered at ~10s intervals as expected
- All files readable (valid parquet footers — writers closed cleanly on rotation)

Mechanism verified. Production rotation at 30-min age will bound C++ heap growth to
~1.5MB per buffer per session (vs unbounded until midnight).

## Unit Tests

5 new tests in `tests/test_collectors_storage_rotation.py` — all pass:

1. `test_writer_rotates_after_max_rows` — writer closes + path advances after row threshold
2. `test_writer_rotates_after_max_age` — writer closes on age threshold
3. `test_rotated_files_all_readable` — all part-files are valid parquet
4. `test_no_row_loss_across_rotation` — total rows preserved across rotation boundary
5. `test_no_rotation_below_threshold` — writer stays open below threshold

Full suite: **12 failed / 315 passed** (12 failures pre-existing, unchanged from TZ-049).

## Production Rollout

**NOT performed in this TZ.**  Decision for operator.

Steps when ready:
1. Note current collectors RSS as baseline (`memory.log` or `psutil`)
2. `SIGTERM` to shim PID (watchdog will restart collectors with new code)
3. Monitor `memory.log` for 60 min — expect growth ≤ 5MB
4. If growth > 8MB — investigate secondary source (tracemalloc in process)
