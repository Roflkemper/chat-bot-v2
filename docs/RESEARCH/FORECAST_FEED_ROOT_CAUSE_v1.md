# Forecast feed root cause v1

**Date:** 2026-05-05
**TZ:** TZ-FORECAST-FEED-ROOT-CAUSE
**Investigation type:** read-only diagnostic. No fixes applied. No configs changed. No processes restarted.

**Symptom under investigation:** `dashboard_state.json` shows `forecast.bar_time = 2026-05-01T00:00:00+00:00` while `last_updated_at` is current (2026-05-05). The P0 staleness banner from TZ-DASHBOARD-USABILITY-FIX-PHASE-1 surfaces this gap as 113.5 hours stale, but does not fix it. This TZ identifies why.

---

## §1 Producer pipeline (data flow)

```
                        ┌────────────────────────────────────────────────────────┐
                        │ Live feeds (running):                                  │
                        │   market_collector/collector.py     → snapshots.csv,   │
                        │       indicators, levels, liquidations, signals.csv   │
                        │   ginarea_tracker/tracker.py        → snapshots.csv   │
                        │   app_runner.py                     → state/*.json    │
                        └─────────────────┬──────────────────────────────────────┘
                                          │
                                          │  (NONE of these feed into the forecast pipeline)
                                          ▼
                        ┌────────────────────────────────────────────────────────┐
                        │ Frozen / batch-built data (NOT live):                  │
                        │   backtests/frozen/derivatives_1y/  ← directory MISSING│
                        │       BTCUSDT_OI_5m_1y.parquet         ← MISSING       │
                        │       BTCUSDT_LS_5m_1y.parquet         ← MISSING       │
                        │       BTCUSDT_funding_8h_1y.parquet    ← MISSING       │
                        │   data/ict_levels/BTCUSDT_*.parquet                    │
                        │       last bar: 2026-04-29 17:13 UTC   (~6d stale)     │
                        │   data/whatif_v3/btc_1m_enriched_2y.parquet            │
                        │       (integer index, not datetime — separate issue)   │
                        └─────────────────┬──────────────────────────────────────┘
                                          │
                                          ▼
                        ┌────────────────────────────────────────────────────────┐
                        │ services/market_forward_analysis/feature_pipeline.py    │
                        │   build_full_features(force_rebuild=False)             │
                        │   short-circuits when cache exists; cache is from      │
                        │   May 4 00:03 build that read pre-existing parquets.   │
                        │   → data/forecast_features/full_features_1y.parquet    │
                        │     last bar: 2026-05-01 00:00 UTC                     │
                        └─────────────────┬──────────────────────────────────────┘
                                          │
                                          ▼
                        ┌────────────────────────────────────────────────────────┐
                        │ scripts/forecast_regime_split.py (one-shot, manual run)│
                        │   reads full_features_1y.parquet                       │
                        │   → data/forecast_features/regime_splits/              │
                        │       regime_markup.parquet  last: 2026-04-27 04:40    │
                        │       regime_markdown.parquet last: 2026-04-28 14:55   │
                        │       regime_range.parquet    last: 2026-05-01 00:00   │
                        └─────────────────┬──────────────────────────────────────┘
                                          │
                                          ▼
                        ┌────────────────────────────────────────────────────────┐
                        │ scripts/dashboard_bootstrap_state.py (one-shot, manual)│
                        │   _pick_latest_bar(): max(last index across 3 regime   │
                        │     parquets) = 2026-05-01 00:00 UTC (RANGE bar)       │
                        │   writes:                                              │
                        │     data/regime/switcher_state.json                    │
                        │     data/forecast_features/latest_forecast.json        │
                        │       bar_time = 2026-05-01T00:00:00+00:00             │
                        │       updated_at = 2026-05-04T21:25:47Z (last manual run)│
                        │       source = "scripts/dashboard_bootstrap_state.py"  │
                        └─────────────────┬──────────────────────────────────────┘
                                          │
                                          ▼
                        ┌────────────────────────────────────────────────────────┐
                        │ services/dashboard/state_builder.py                    │
                        │   reads latest_forecast.json                           │
                        │   → docs/STATE/dashboard_state.json                    │
                        │     forecast.bar_time = 2026-05-01T00:00:00+00:00      │
                        │     forecast.staleness.is_stale = True (P0 detected)   │
                        └────────────────────────────────────────────────────────┘
```

The pipeline **has no live producer**. Every layer above the dashboard reader is either a frozen file or a one-shot manually invoked script. The supervisor (`bot7-supervisor`) manages `app_runner`, `tracker`, `collectors`, and `watchdog` — none of which run the bootstrap or refresh the cached parquets.

---

## §2 Investigation findings

### Step 1 — Forecast data source identified

`services/dashboard/state_builder.py:20`:
```python
LATEST_FORECAST_PATH = Path("data/forecast_features/latest_forecast.json")
```

File content (read 2026-05-05 17:48 UTC):
```json
{
  "regime": "RANGE",
  "regime_confidence": 0.85,
  "bar_time": "2026-05-01T00:00:00+00:00",
  "updated_at": "2026-05-04T21:25:47Z",
  "horizons": { "1h": {...}, "4h": {...}, "1d": {...} },
  "source": "scripts/dashboard_bootstrap_state.py"
}
```

File system metadata: `latest_forecast.json` mtime **2026-05-04 21:25:47 UTC** (~20.4 hours ago).

Producer: `scripts/dashboard_bootstrap_state.py`. Its module docstring states explicitly (line 1-13):

> "One-shot bootstrap: produce regime/forecast state files for dashboard. … Live wiring (per-bar emission inside an orchestrator loop) is a **Day 2+ task**; this script keeps the dashboard meaningful in the meantime."

**Verdict for Step 1:** the producer is a manually invoked one-shot script — by design, not a live worker.

### Step 2 — Producer service status

`bot7-supervisor` is running and healthy. `python -m bot7 status` reports:
```
component   pid    health  last_log
supervisor  25164  OK      -
app_runner  17964  OK      10s ago   [OK]
tracker     7616   OK      4m ago    [OK]
collectors  23576  OK      5s ago    [OK]
watchdog    20160  OK      3m ago    [OK]
```

Component definitions (`src/supervisor/process_config.py`): only `app_runner`, `tracker`, `collectors`. Searching the supervisor codebase for `dashboard_bootstrap_state` or `build_full_features`:
```
$ grep -rn 'dashboard_bootstrap_state\|build_full_features' --include='*.py'
scripts/dashboard_bootstrap_state.py  (the script itself)
services/market_forward_analysis/calibration.py:384:  return {"error": "features not built — run build_full_features() first"}
services/market_forward_analysis/feature_pipeline.py:389:  def build_full_features(...)
```

No supervisor component, scheduled task, or app_runner code path invokes either. The script is **only ever run manually**.

**Verdict for Step 2:** there is no producer service running. The bootstrap script was last run on **2026-05-04 21:25:47 UTC**, presumably by the operator from a shell.

### Step 3 — Upstream input feeds

| Source | Path | Last bar / mtime | Age vs 2026-05-05 17:48 UTC | Status |
|---|---|---|---:|---|
| **Live** snapshots.csv | `ginarea_live/snapshots.csv` | last row ts_utc 2026-05-05 17:48:27 UTC | 0 min | live, fresh ✓ |
| OHLCV / liquidations / signals | `signals.csv`, `state/*.json` | live | live | live, fresh ✓ |
| **Frozen** ICT 1m | `data/ict_levels/BTCUSDT_ict_levels_1m.parquet` | last bar 2026-04-29 17:13 UTC | ~6.0 d | stale, file mtime May 1 |
| **Frozen** whatif v3 1m | `data/whatif_v3/btc_1m_enriched_2y.parquet` | integer index (1057994 rows) | n/a — index is not datetime | format mismatch, see §3 |
| **MISSING** Derivatives 5m OI | `backtests/frozen/derivatives_1y/BTCUSDT_OI_5m_1y.parquet` | does not exist | — | directory `backtests/frozen/derivatives_1y/` does not exist at all |
| **MISSING** Derivatives 5m LS | same dir | — | — | missing |
| **MISSING** Derivatives 8h funding | same dir | — | — | missing |
| **Cached output** full_features_1y | `data/forecast_features/full_features_1y.parquet` | last bar 2026-05-01 00:00 UTC, mtime 2026-05-04 00:03 | ~4.7 d | fixed cache, can no longer rebuild |
| Regime split MARKUP | `data/forecast_features/regime_splits/regime_markup.parquet` | last bar 2026-04-27 04:40 UTC | ~8.5 d | derived from above; stale |
| Regime split MARKDOWN | `regime_markdown.parquet` | last bar 2026-04-28 14:55 UTC | ~6.1 d | derived; stale |
| Regime split RANGE | `regime_range.parquet` | last bar 2026-05-01 00:00 UTC | ~4.7 d | **this is the bar_time the dashboard sees** |
| latest_forecast.json | `data/forecast_features/latest_forecast.json` | bar_time 2026-05-01 00:00; updated_at 2026-05-04 21:25 | bar 4.7 d / file 20.4 h | written by bootstrap from above |

**Verdict for Step 3:** the live tracker / collectors are healthy and producing fresh data. Everything in the **forecast pipeline** is built on **frozen, missing-or-stale parquets**. The pipeline cannot rebuild even if asked, because the input directory `backtests/frozen/derivatives_1y/` no longer exists on disk.

### Step 4 — Failure mode mapping

Per the brief's failure-mode taxonomy:
- ❌ (a) Forecast worker process down / crashed — **n/a; there has never been a live forecast worker.** The supervisor doesn't define one.
- ❌ (b) Forecast worker running but loop blocked — **n/a; same reason.**
- ✅ (c) **Input feed (regime classifier, features) stale → no input to process.** The cached `full_features_1y.parquet` stops at 2026-05-01. The regime-split parquets derived from it are equally stale or older. The bootstrap script always reports the most recent bar across regime-split parquets, which is permanently 2026-05-01 unless the underlying cache is regenerated.
- ❌ (d) Output write path blocked — **no.** The bootstrap writes successfully when invoked (file mtime confirms 2026-05-04 21:25). Write target permissions OK.
- ❌ (e) Configuration drift — **no.** The dashboard reads from exactly the same path the bootstrap writes to: `data/forecast_features/latest_forecast.json`.
- ✅ (f) **Feature pipeline broken upstream (bigger issue).** The `build_full_features` function references a directory `backtests/frozen/derivatives_1y/` that does not exist on disk. If `force_rebuild=True` were passed today, `_load_oi` (line 36 of `feature_pipeline.py`) would raise `FileNotFoundError`. The pipeline depends on **frozen 1-year derivative parquets** that have been removed or never restored after a checkpoint cleanup.

The actual root cause is the **conjunction of (c) and (f)**:
- The forecast pipeline was *designed* as a batch reload of frozen 1-year datasets, NOT a streaming append. There is no live derivative-data ingest.
- Even the batch reload no longer works because the frozen-derivative input dir is gone.
- Therefore the cached output (last build May 4) is permanent until those frozen inputs are restored or replaced by a live pipeline.

---

## §3 Identified root cause (with evidence)

**Root cause:** The forecast pipeline has **never had a live data source**. It was constructed against a frozen 1-year backtest snapshot of derivatives data (`backtests/frozen/derivatives_1y/`). At some point that snapshot directory was removed (the directory does not exist as of 2026-05-05). The cached output parquet (`full_features_1y.parquet`, built 2026-05-04 00:03) still exists from before that removal, last bar 2026-05-01. The dashboard bootstrap script, when manually invoked, picks the most recent bar from regime-splits derived from this stale cache and writes a `latest_forecast.json` with `bar_time = 2026-05-01`.

**Evidence:**

1. `services/market_forward_analysis/feature_pipeline.py:27`:
   ```python
   _DERIV_DIR = _ROOT / "backtests" / "frozen" / "derivatives_1y"
   ```
   `ls` shows: `backtests/frozen/derivatives_1y/` does not exist. Only `backtests/frozen/1y_ingest/` exists.

2. `data/forecast_features/full_features_1y.parquet`: 105 117 rows, last index `2026-05-01 00:00:00 UTC`. File mtime `2026-05-04 00:03` — frozen since.

3. `feature_pipeline.py:399`:
   ```python
   if _OUT_PATH.exists() and not force_rebuild:
       return pd.read_parquet(_OUT_PATH)
   ```
   The cache short-circuit means even if you ran `build_full_features()` again today, it would just return the same cached frame and never even attempt to read the missing derivative inputs.

4. `scripts/dashboard_bootstrap_state.py:1-13` documents that this is intended as a temporary scaffold:
   > "Live wiring (per-bar emission inside an orchestrator loop) is a Day 2+ task; this script keeps the dashboard meaningful in the meantime."

5. `bot7-supervisor` `process_config.py` defines components: `app_runner`, `tracker`, `collectors`. No forecast worker. No invocation of `dashboard_bootstrap_state`.

6. Supervisor logs (`logs/current/supervisor.log`, `app_runner.log`, `collectors.log`) show all three components running and healthy as of investigation time. `app_runner.log` does not mention `forecast`, `feature_pipeline`, or `dashboard_bootstrap_state`.

7. `data/forecast_features/regime_splits/regime_range.parquet` last index `2026-05-01 00:00 UTC` — exactly matches the `bar_time` reported by the dashboard.

The chain of reasoning is closed: stale cache → bootstrap reads stale → dashboard reads stale.

---

## §4 Proposed fix path

The fix is **not in scope for this TZ** (anti-drift bound: "Don't fix outside scope; don't auto-restart processes; don't change configuration before reporting"). But the path is concrete:

### Option A — Restore frozen derivatives snapshot + add scheduled regenerator

1. Locate or re-fetch `backtests/frozen/derivatives_1y/` parquets:
   - `BTCUSDT_OI_5m_1y.parquet`
   - `BTCUSDT_LS_5m_1y.parquet`
   - `BTCUSDT_funding_8h_1y.parquet`
   These were presumably checkpointed somewhere; check git history (`git log --all -- backtests/frozen/derivatives_1y/`).
2. Rebuild `full_features_1y.parquet` with `build_full_features(force_rebuild=True)`.
3. Rerun `forecast_regime_split.py` to refresh regime-split parquets.
4. Rerun `dashboard_bootstrap_state.py` to refresh `latest_forecast.json`.
5. Add a daily/hourly scheduler entry that repeats steps 2-4 — either as a new supervisor component or as a Windows scheduled task.

**Pros:** keeps the existing batch-reload architecture; minimum code churn. **Cons:** still snapshot-based; the `bar_time` stays at most 1-day old in the best case; forecast quality is questionable on a frozen 1-year window.

### Option B — Build a true live forecast loop

Replace the bootstrap script with a worker that:
1. Subscribes to the live `collectors` data stream (snapshots, OHLCV, OI / LS / funding from a live exchange feed — not the frozen parquet).
2. Updates `full_features_1y.parquet` (or a streaming equivalent) on each new 5-minute bar.
3. Emits regime classification on the new bar.
4. Writes `latest_forecast.json` per bar.
5. Registers as a `forecast_worker` component in `bot7-supervisor`.

**Pros:** matches the operator's mental model of "live forecast". `bar_time` always within 5 min of now. **Cons:** substantial work — needs live OI/LS/funding ingest (collectors don't currently write those — verify), feature recompute logic for online updates, and supervisor wiring.

### Option C — Document the gap explicitly and decommission forecast UI

Per `REGULATION_v0_1_1.md` §7 limitation 11, forecast actionability is already gated on `usability_band` (ACTIONABLE / WEAK_LEAN / NEUTRAL / STALE). The P0 staleness banner from TZ-DASHBOARD-USABILITY-FIX-PHASE-1 already prevents stale values from being read as actionable. If the operator is not currently using forecast for any decisions (per regulation, all forecast-actionable bands are absent in the live data), removing the forecast block from the dashboard is a valid choice.

**Pros:** zero engineering cost. **Cons:** loses optionality if the live forecast is later wanted. Operator has to make a strategic call.

### Recommendation

The diagnosis points to a **design-level gap** ("Day 2+ task" was never picked up), not a regression. Choosing among A / B / C is an operator + MAIN architectural decision, not a bug-fix. Whichever option is picked, it should be a **separate dedicated TZ** with its own scope and acceptance criteria.

---

## §5 In-scope verdict

**Verdict:** **Fix requires a separate TZ.** Not in scope for this diagnostic.

Rationale:
1. There is no single configuration knob to flip — the architecture is incomplete by design (bootstrap script's own docstring acknowledges this).
2. Option A requires restoring deleted frozen-data files (provenance investigation needed; may need re-fetching from archives).
3. Option B is a multi-day implementation effort requiring scope decisions: live OI/LS/funding feeds, online feature recompute, supervisor integration, calibration revalidation.
4. Option C is a product decision, not a code change.
5. Anti-drift forbids: "Don't fix outside scope (e.g. don't refactor forecast model)", "Don't auto-restart processes without operator confirm", "Don't change configuration before reporting."

**Mitigating control already in place:** the P0 staleness banner from TZ-DASHBOARD-USABILITY-FIX-PHASE-1 detects this exact failure mode at the dashboard layer and suppresses misleading values. Forecast users today see "FORECAST STALE — last bar 113.5h ago (threshold 2.0h); feed not updating", which is honest and prevents action on bad data. Until a follow-up TZ implements one of options A/B/C, the staleness banner is the operative safety net.

**Suggested follow-up TZs (proposed names):**
- `TZ-FORECAST-FEED-RESTORE-FROZEN` (Option A path)
- `TZ-FORECAST-LIVE-WORKER` (Option B path)
- `TZ-FORECAST-DECOMMISSION` (Option C path)

The operator should pick one and brief it as a separate piece of work.

---

## CP report

- **Output path:** [`docs/RESEARCH/FORECAST_FEED_ROOT_CAUSE_v1.md`](FORECAST_FEED_ROOT_CAUSE_v1.md)
- **Root cause summary (one paragraph):** The forecast pipeline has never had a live producer. It was built against a frozen 1-year derivatives snapshot at `backtests/frozen/derivatives_1y/`, and the only writer of `latest_forecast.json` is the manually invoked one-shot script `scripts/dashboard_bootstrap_state.py`. The frozen-derivatives input directory has since been removed, but a cache (`data/forecast_features/full_features_1y.parquet`, last bar 2026-05-01) survives and is read in preference to a rebuild. The bootstrap script picks the most recent bar from regime-splits derived from this stale cache, so `latest_forecast.json` is permanently anchored at 2026-05-01 until either the frozen inputs are restored, a true live worker is added to the supervisor, or the forecast block is decommissioned.
- **Proposed fix path:** Three options described in §4 — A (restore frozen + scheduler), B (live worker), C (decommission). Choice is operator + MAIN.
- **In-scope verdict:** **Requires separate TZ.** Not fixed in this investigation. The P0 staleness banner from TZ-DASHBOARD-USABILITY-FIX-PHASE-1 is the operative safety net until one of the three follow-up TZs is run.
- **Compute time:** ~1 minute (read-only inspection across feature_pipeline, supervisor config, parquet timestamps).
