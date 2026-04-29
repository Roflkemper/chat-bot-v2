# MARKET DATA AUDIT 2026-04-29T192514Z

## PRE-FLIGHT

- [x] git status checked — working tree has uncommitted changes from Codex (whatif, advise_v2), no conflict with audit output files (docs/STATE/)
- [x] `.claude/skills/*` read — state_first_protocol, encoding_safety, operator_role_boundary applied
- [x] PROJECT_RULES.md read — read-only audit, no modifications to existing files
- [x] TZ-RECONCILE-METHODOLOGY-FIX committed (fd003ff) before this TZ — no conflict

---

## 0. Search methodology

**Directories scanned:**
- `market_live/` — active collector output (untracked, current data)
- `market_live_dev/` — dev instance output
- `market_live_profiler/` — profiler instance output
- `_recovery/restored/market_live/` — recovered data from dangling git trees (TZ-049)
- `_recovery/restored/scripts/frozen/` — frozen historical data restored
- `collectors/` — new multi-exchange collector (Python package)
- `market_collector/` — legacy collector (Binance + Bybit)
- `core/market_data/` — market data utilities (code only)
- `market_data/` — empty (no data files)
- `state/`, `docs/STATE/`, `ginarea_live/` — side-channel check for inline feeds

**Grep patterns used:**
- `liquid`, `forceorder`, `funding`, `openinterest`, `open_interest`, `longshort`, `long_short`, `whale`, `oi_`, `liq_`

**Skipped:**
- `.venv/` — Python dependencies, no data
- `__pycache__/` — compiled artifacts
- Files > 5 MB in logs — oversized for text grep
- `backtests/frozen/` — OHLCV only, covered by separate TZ-062

**Open questions resolved:**
1. **Grep patterns**: used patterns listed above + directory walk for `.parquet` / `.csv` / `.jsonl`
2. **Active collector detection**: via `run/*.pid` (kill -0 test) + log timestamp + file mtime. Result: PIDs stale but log written 1-2 min before audit run → process active under unknown PID.
3. **Large files**: orderbook parquets sampled (4 files/symbol), row count via pandas len(); no single file > 5 MB found.

---

## 1. Liquidations data (priority 1)

### 1a. Active feed — `market_live/liquidations/`

**Source: collectors/main.py** (new multi-exchange collector, TZ-048/049)

| Exchange | Symbols | Valid files | Corrupt/open | Rows | First ts | Last ts | Freshness |
|----------|---------|-------------|--------------|------|----------|---------|-----------|
| Bybit | BTCUSDT (all symbols) | 5 | 5 | 418 | 2026-04-28T23:01 | 2026-04-29T18:50 | 30 min |
| OKX | BTCUSDT | 5 | 5 | 89 | 2026-04-28T22:30 | 2026-04-29T18:53 | 28 min |
| OKX | ETHUSDT | 6 | 6 | 201 | 2026-04-28T22:33 | 2026-04-29T18:55 | 28 min |
| OKX | XRPUSDT | 4 | 3 | 18 | 2026-04-28T22:49 | 2026-04-29T19:21 | 28 min |
| BitMEX | BTCUSDT (XBTUSD mapped) | 4 | 2 | 9 | 2026-04-28T22:50 | 2026-04-29T19:05 | 53 min |
| Binance | — | 0 | — | 0 | — | — | **ABSENT** |
| Hyperliquid | — | 0 | — | 0 | — | — | **ABSENT** |

**Schema (uniform across all sources):**
```
ts_ms            int64     Unix timestamp in milliseconds
exchange         str       'bybit' | 'okx' | 'bitmex' | 'binance' | 'hyperliquid'
symbol           str       'BTCUSDT' | 'ETHUSDT' | 'XRPUSDT' | ''(bybit: no per-sym field)
side             str       'long' | 'short'  (liquidated position side)
qty              float64   Position size (BTC for BTCUSDT, etc.)
price            float64   Liquidation price
value_usd        float64   Notional USD value of liquidation
source_rate_limited bool   True for Binance (batched 1/sec), False for others
```

**Corrupt/open files note:** Files named `2026-04-29.parquet` (without suffix) are currently open for writing by the collector — PyArrow cannot read them. Files named `2026-04-29_2.parquet`, `_3.parquet` etc. are completed rotations (valid). This is by design (TZ-048 rotation logic).

**Binance absent:** Binance `!forceOrder@arr` collector is coded (collectors/liquidations/binance.py) and started in main.py, but no output directory `market_live/liquidations/binance/` exists. Last Binance liq file was in `_recovery/restored/` ~1117 min ago (Apr 27). Likely silently failing or writing to wrong path.

**Hyperliquid absent:** collectors/liquidations/hyperliquid.py exists, is started in main.py, but no `market_live/liquidations/hyperliquid/` directory. Collector may be failing to detect liquidations (filters by `liquidation` field in trades stream — sparse signal).

### 1b. Recovery data — `_recovery/restored/market_live/liquidations/`

| Exchange | Valid files | Rows | Coverage |
|----------|-------------|------|----------|
| Binance | 8 | 1124 | Apr 26-27 |
| BitMEX | 6 | 33 | Apr 26-28 |
| Bybit | 11 | 3852 | Apr 26-28 |
| OKX | 24 | 1859 | Apr 26-28 |
| **Total** | **49** | **6868** | Apr 26-28 |

Same schema as active feed. These are finalized (rotated) files recovered from dangling git trees (TZ-049).

### 1c. Legacy collector — `market_collector/liquidations.py`

Output path: `market_live/liquidations.csv` (flat CSV, not parquet).
Status: **file does not exist** — legacy collector not running.
Schema: `ts_utc, exchange, side, qty, price` (no value_usd, no symbol, no source_rate_limited).
Exchanges: Binance (`!forceOrder@arr`) + Bybit only.

### 1d. Combined availability

| Date | Bybit | OKX | BitMEX | Binance | Hyperliquid |
|------|-------|-----|--------|---------|-------------|
| Apr 26 | recovery | recovery | recovery | recovery | — |
| Apr 27 | recovery | recovery | recovery | recovery | — |
| Apr 28 | recovery + live | recovery + live | recovery + live | recovery | — |
| Apr 29 | live | live | live | **missing** | — |
| Apr 30+ | live (if running) | live (if running) | live (if running) | **missing** | — |

**Coverage gap:** Only ~4 days (Apr 26-29). For counterfactual analysis over the H10 backtest window (2024-04-28 to 2026-04-24), liquidation data covers less than 0.5% of the required period.

---

## 2. Funding rates (priority 2)

### 2a. Frozen historical — `_recovery/restored/scripts/frozen/`

| Symbol | Files | Rows | Period | Source | Freshness |
|--------|-------|------|--------|--------|-----------|
| BTCUSDT | 13 monthly + 1 combined | 1188 | 2025-03 to 2026-03 (last: Mar 31) | Binance (Bybit?) | ~1117 min (stale) |
| ETHUSDT | 13 monthly + 1 combined | 1188 | 2025-03 to 2026-03 | same | same |
| XRPUSDT | 13 monthly + 1 combined | (inferred ~1188) | 2025-03 to 2026-03 | same | same |

**Schema:**
```
calc_time                datetime64[ns, UTC]   Funding settlement time (8h intervals)
funding_interval_hours   int64                 Always 8 (Binance perpetual)
last_funding_rate        float64               Rate as decimal (e.g. -2.763e-05 = -0.002763%)
```

**Gap:** Latest funding record = 2026-03-31T16:00Z. Current date = 2026-04-29. Missing: entire April 2026 (~90 records per symbol).

**No live funding rate collection** — `collectors/main.py` does not include a funding rate task. No funding rate topic in any WS stream configured.

### 2b. Coverage for H10 backtest window

H10 uses 2024-04-28 to 2026-04-24. Funding rate data starts 2025-03-01. Missing: 2024-04-28 to 2025-02-28 (10 months).

---

## 3. Open interest (priority 2)

**No data files found anywhere in the project.**

Code references exist:
- `core/derivatives_context.py`: `open_interest: float = 0.0` (always defaulted to zero)
- `core/context_consensus_filter.py`: reads `open_interest_change_pct` from payload (defaults 0.0 if missing)
- `core/analysis_service_V16_FIXED.py` + `core/services/analysis_service.py`: pass `open_interest=oi_close` but source is unclear (likely always 0.0)
- `src/features/pipeline.py:72`: column alias `sum_open_interest_value → oi_value` — only active if coinglass data is ingested

**Verdict:** OI infrastructure code exists but no data source. Currently always zero in live analysis.

---

## 4. Other feeds

### Long/Short ratio
- Code: `src/features/pipeline.py:73-74` aliases `ls_ratio_top`, `ls_ratio_retail`
- `core/context_consensus_filter.py`: reads `long_short_ratio` (defaults 1.0)
- **Data files: none found**

### Whale alerts / large orders
- **Data files: none found**
- No collector code for whale feeds

### Orderbook L2 (Binance)
- Path: `market_live/orderbook/binance/{BTCUSDT,ETHUSDT,XRPUSDT}/`
- Files: 69 + 70 + 66 = 205 parquet files
- **Last write: ~4166 min ago (~69h, Apr 26)** — collector was active but stopped
- Schema: `ts_ms, exchange, symbol, side (bid/ask), price, qty, level (0-indexed)`
- Rows: ~2.75M per symbol in sample (4 files), estimated 40-50M total
- Status: **STALE** — not being written by current collector

### Orderbook L2 (market_live_profiler)
- Path: `market_live_profiler/orderbook/binance/BTCUSDT/`
- 7 files (Apr 29), likely from profiling run
- Not part of main data pipeline

### Trades (Binance)
- `_recovery/restored/market_live/trades/binance/`: 3+2+3=8 files (BTCUSDT/ETHUSDT/XRPUSDT)
- Recovery only, no active trades collection in market_live

---

## 5. Active collectors

### New collector: `collectors/main.py` (multi-exchange)

```
Configuration:
  Output path: C:/bot7/market_live  (BOT7_LIVE_PATH env var)
  Symbols: BTCUSDT, ETHUSDT, XRPUSDT
  Tasks (11): 
    liq-binance, liq-bybit, liq-hyperliquid, liq-bitmex, liq-okx
    ob-binance-BTCUSDT/ETHUSDT/XRPUSDT (orderbook L2)
    trades-binance-BTCUSDT/ETHUSDT/XRPUSDT
    flush-loop
  Flush interval: 60s
  Parquet rotation: 100k rows / 50MB / 30min
  Compression: zstd level 3
```

**PID status:**
| File | PID | Process alive |
|------|-----|---------------|
| run/collectors.pid | 3968 | NO (stale) |
| run/collectors_lock.pid | 18540 | NO (stale) |

**Actual status: RUNNING** (based on evidence):
- `logs/current/collectors.log` last write: 2026-04-29T19:23:41Z (~1.5 min before audit)
- Log shows `heartbeat cycle=1285 buffers=8` — flush loop active
- `market_live/liquidations/bybit/`: last write 30 min ago
- `market_live/liquidations/okx/`: last write 28 min ago
- Conclusion: process running but PID files are stale (supervisor restarted process without updating PID files)

**Active data streams:**
| Task | Writing | Output | Notes |
|------|---------|--------|-------|
| liq-bybit | YES | market_live/liquidations/bybit/ | Active, ~418 rows in 5 valid files |
| liq-okx | YES | market_live/liquidations/okx/{BTCUSDT,ETHUSDT,XRPUSDT}/ | Active, ~308 rows |
| liq-bitmex | YES | market_live/liquidations/bitmex/BTCUSDT/ | Active, 9 rows (low frequency) |
| liq-binance | NO | market_live/liquidations/binance/ — **missing** | Failing silently |
| liq-hyperliquid | NO | market_live/liquidations/hyperliquid/ — **missing** | No signal or dir missing |
| ob-binance-* | NO | market_live/orderbook/ last write 69h ago | Stopped/failing |
| trades-binance-* | NO | market_live/trades/ not present | Not writing |

### Legacy collector: `market_collector/collector.py`

Exchanges: Binance (`!forceOrder@arr`) + Bybit (BTCUSDT only).
Output: `market_live/liquidations.csv` (CSV, no parquet).
Status: **NOT RUNNING** — output file does not exist, no PID file for legacy process.

---

## 6. Recommendations

| Data type | Verdict | Reason | Recommended TZ |
|-----------|---------|--------|----------------|
| Liquidations (Bybit, OKX, BitMEX) | **stale for backtest** | Only 4 days of data (Apr 26-29); H10 window needs 2024-04-28 to 2026-04-24 (~2 years). Schema ready. | TZ-LIQ-INGESTION: historical ingest from Coinglass or exchange REST API for 2024-04+ |
| Liquidations (Binance) | **needs fix + ingestion** | Collector silently failing in current run (no output dir). Historical also needed. | TZ-LIQ-FIX-BINANCE: debug collector + create missing output directory |
| Liquidations (Hyperliquid) | **needs_ingestion** | Collector code exists but no signal. HL trades stream rarely has `liquidation` field. | TZ-LIQ-FIX-HL: evaluate HL source viability; consider REST API fallback |
| Funding rates | **needs_ingestion** | Frozen data ends 2026-03-31; missing April + all pre-2025-03. No live collection. | TZ-FUNDING-INGEST: REST API fetch for April 2026 gap + live collection task |
| Open interest | **needs_ingestion** | No data files anywhere; code exists but always zero. | TZ-OI-INGEST: Binance /openInterest REST + WS stream task |
| Long/short ratio | **needs_ingestion** | No data files; code exists but always defaults to 1.0. | Same TZ as OI or separate |
| Orderbook L2 | **stale** | 205 files, ~40-50M rows, but last write 69h ago. Collector task not producing output in current run. | Investigate ob-binance task failure; restart or fix |
| Trades | **stale** | Recovery only (Apr 26-27); no active collection in market_live. | Lower priority; investigate trades-binance task |

**For Coinglass counterfactual analysis:**
- Current liquidation data (4 days) is **insufficient** for H10 backtest window (2 years)
- Coinglass subscription would provide: per-trade liquidations (real-time + historical), aggregated heatmaps, OI, L/S ratio in one feed
- Verdict: **TZ-LIQ-INGESTION is a blocker** for counterfactual analysis; data not ready

**Schema quality:**
- Liquidation schema is clean and uniform across all 5 exchanges (ts_ms, exchange, symbol, side, qty, price, value_usd, source_rate_limited)
- No normalization TZ needed — schema is production-ready
- `source_rate_limited` flag correctly marks Binance coarse-grained events

---

## 7. Skills applied

- **state_first_protocol**: state_latest.json freshness verified; docs/STATE/QUEUE.md read
- **encoding_safety**: UTF-8 explicit on all file writes; sys.stdout wrapped with utf-8
- **operator_role_boundary**: all execution by Code; no operator commands issued
- **data_freshness_check**: file mtime checked for all data sources; freshness_minutes computed
- **result_sanity_check**: row counts cross-verified against file counts; corrupt files counted separately
- **untracked_protection**: MARKET_DATA_AUDIT_*.json will be untracked (not in gitignore pattern); only .md committed

---

## FILES CHANGED (this TZ)

**New (tracked):**
- `docs/STATE/MARKET_DATA_AUDIT_2026-04-29T192514Z.md` — this file

**New (untracked artifact, per TZ spec):**
- `docs/STATE/MARKET_DATA_AUDIT_2026-04-29T192514Z.json`

**Modified:** none
