# OPERATOR NIGHT DOWNLOAD — 1s OHLCV BACKFILL

**Goal:** Unblock Phase 0.5 engine validation by extending `BTCUSDT_1s_2y.csv` from 30 days → full GA ground-truth window (365 days, 2025-05-01 → 2026-04-30).

**Why night:** ~3–6 hours wall-clock + ~1.6 GB disk write. Set it up, sleep, verify in the morning.

---

## Current state

| File | Span | Size |
|------|------|------|
| `backtests/frozen/BTCUSDT_1s_2y.csv` | 2026-04-02 → 2026-05-02 | 143 MB |
| `backtests/frozen/BTCUSDT_1m_2y.csv` | 2024-04-25 → 2026-04-29 | 88 MB |
| GA window | 2025-05-01 → 2026-04-30 | — |

**Gap to fill:** 2025-05-01 → 2026-04-02 (336 days, ~29M bars, ~1.6 GB).

---

## Why we can't just `--start-date` and append

`scripts/ohlcv_ingest.py` only appends **forward** from the last existing timestamp. The current 1s file already ends at 2026-05-02; running the script with `--start-date 2025-05-01` will be ignored ("file exists, ignoring --start-date"). We need to either back-fill behind the file or rebuild from scratch.

**Plan:** rename the existing 143 MB file as a safety backup, then run a fresh full download from 2025-05-01.

---

## Pre-flight check (30 sec)

Make sure ~2 GB free on the drive holding `c:\bot7\backtests\frozen\`:

```powershell
Get-PSDrive C | Select-Object Used,Free
```

You want **at least 2 GB free**.

---

## Step 1 — Backup the existing 1s CSV

```powershell
cd c:\bot7
move backtests\frozen\BTCUSDT_1s_2y.csv backtests\frozen\BTCUSDT_1s_30d_backup.csv
```

(Renames so the script will treat it as a fresh download.)

---

## Step 2 — Kick off the night download

**Single command — copy/paste:**

```powershell
cd c:\bot7
python scripts/ohlcv_ingest.py --symbol BTCUSDT --interval 1s --start-date 2025-05-01T00:00:00Z --target-end 2026-04-30T23:59:59Z --workers 4
```

**What it does:**
- Downloads ~29M 1-second bars from Binance public REST
- 4 parallel workers, ~8 req/s effective rate (well under Binance 1200/min limit)
- Appends to a new `backtests/frozen/BTCUSDT_1s_2y.csv`
- Logs progress every 100 batches with ETA
- Validates continuity, writes summary to `docs/STATE/ohlcv_ingest_log.jsonl`

**Expected runtime:** 3–6 hours (Binance throttles 1s klines harder than 1m).

**Run in a window that won't sleep.** On Windows, easiest:

```powershell
# Disable sleep for the duration:
powercfg /change standby-timeout-ac 0
# (run download command)
# After done in the morning, restore:
powercfg /change standby-timeout-ac 30
```

Or just plug in the laptop and disable sleep in Windows Settings → Power.

**No API credentials needed** — Binance public REST is open, no auth.

---

## Step 3 — Morning verification (1 command, 5 sec)

```powershell
cd c:\bot7
python -c "from services.calibration.reconcile_v3 import csv_span_iso, DEFAULT_OHLCV_1S; s,e = csv_span_iso(DEFAULT_OHLCV_1S); print(f'span: {s} -> {e}'); ok = s <= '2025-05-01' and e >= '2026-04-29'; print('VERIFY:', 'OK' if ok else 'FAIL')"
```

**Expected output (success):**
```
span: 2025-05-01T00:00:00+00:00 -> 2026-04-30T23:59:59+00:00
VERIFY: OK
```

**If FAIL:** the download was incomplete. Re-run Step 2 — the script will append forward from the last successful bar (no need to start over).

---

## Step 4 — After verification: unblock reconcile_v3

Once VERIFY: OK, run reconcile in **direct_k mode** (the mode that was previously aborting with `DATA_GAP`):

```powershell
cd c:\bot7
python -m services.calibration.reconcile_v3 --mode direct_k
```

This is the call that produces the K-factor result for engine_v2 validation. It will read both `BTCUSDT_1s_2y.csv` and `BTCUSDT_1m_2y.csv`, run sim against ground truth, and print per-config K factors.

**This step is automated** — no operator review needed mid-run. It writes results to `data/calibration/`. After it finishes, ping me with the output and I'll interpret it.

---

## Step 5 — Optional cleanup

Once Step 4 succeeds, you can delete the backup:

```powershell
del backtests\frozen\BTCUSDT_1s_30d_backup.csv
```

---

## Recap (one-line summary for tomorrow)

1. Backup existing 1s file → run download command → sleep → verify command in the morning → run reconcile.
2. Download command:
   ```
   python scripts/ohlcv_ingest.py --symbol BTCUSDT --interval 1s --start-date 2025-05-01T00:00:00Z --target-end 2026-04-30T23:59:59Z --workers 4
   ```
3. Verify command:
   ```
   python -c "from services.calibration.reconcile_v3 import csv_span_iso, DEFAULT_OHLCV_1S; s,e = csv_span_iso(DEFAULT_OHLCV_1S); print(f'span: {s} -> {e}')"
   ```

---

## What if I want XRP too?

Same script, swap `--symbol XRPUSDT`. Run **after** BTCUSDT finishes (running both in parallel doubles the rate-limit pressure):

```powershell
move backtests\frozen\XRPUSDT_1s_2y.csv backtests\frozen\XRPUSDT_1s_old_backup.csv
python scripts/ohlcv_ingest.py --symbol XRPUSDT --interval 1s --start-date 2025-05-01T00:00:00Z --target-end 2026-04-30T23:59:59Z --workers 4
```

Estimated time: same 3–6 hours. **Skip this for the first night** — focus on BTC first to unblock engine validation.
