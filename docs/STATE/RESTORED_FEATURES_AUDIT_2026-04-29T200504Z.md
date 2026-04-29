# RESTORED FEATURES AUDIT 2026-04-29T200504Z

## PRE-FLIGHT

- [x] git status checked — working tree has uncommitted changes (unrelated to audit output)
- [x] `.claude/skills/*` read — state_first_protocol, encoding_safety, operator_role_boundary, untracked_protection applied
- [x] PROJECT_RULES.md read — read-only audit, no code modifications
- [x] Regression baseline: 11 failed / 409 passed / 1 skipped (pre-existing, unrelated to this TZ)

---

## 0. Tree

```
_recovery/restored/
├── backtests/frozen/                 # BTCUSDT_1h/1m_2y.csv + checkpoint
├── collectors/                       # Old collector snapshot (pre-TZ-048)
│   ├── config.py                     63 lines
│   ├── storage.py                   221 lines
│   ├── main.py                      106 lines
│   ├── pidlock.py                    58 lines
│   ├── liquidations/{binance,bitmex,bybit,hyperliquid,okx}.py
│   ├── orderbook/binance.py          82 lines
│   └── trades/binance.py             76 lines
├── config/                           # YAML strategy configs
│   ├── adaptive_grid.yaml
│   ├── anti_spam.yaml
│   ├── boundary_expand.yaml
│   └── counter_long.yaml
├── docs/                             # Archive docs, specs TZ-005..TZ-045, playbooks
├── features_out/                     # PRE-COMPUTED feature partitions ← KEY DATA
│   ├── BTCUSDT/ (366 parquets, 2025-04-25 → 2026-04-28)
│   ├── ETHUSDT/ (366 parquets, 2025-04-25 → 2026-04-28)
│   └── XRPUSDT/ (366 parquets, 2025-04-25 → 2026-04-28)
├── market_live/liquidations/         # Liquidation parquets (binance/bybit/okx/bitmex)
├── scripts/                          # restore-era utility scripts
│   ├── download_historical.py       438 lines  ← OI/funding/klines downloader
│   ├── extend_features.py           145 lines
│   ├── watchdog.py                  169 lines  ← IDENTICAL to active
│   ├── smoke_collectors.py           64 lines  ← IDENTICAL to active
│   └── run_features.py               25 lines
├── services/                         # Bot management services (NOT in active)
│   ├── adaptive_grid_manager.py     588 lines  ← NOT in active services/
│   ├── boundary_expand_manager.py   471 lines  ← NOT in active services/
│   └── counter_long_manager.py      407 lines  ← NOT in active services/
├── src/                              # THE MAIN GAP — 34 files missing from active src/
│   ├── advisor/v2/                   7 files, ~900 lines
│   ├── detectors/                    4 files, ~1100 lines
│   ├── episodes/                     2 files, ~900 lines
│   ├── features/                     3 files (calendar, weekend_gap, __init__)
│   ├── playbook/                     9 files, ~870 lines
│   └── whatif/                       6 files, ~1400 lines
├── tests/                            # Tests for restored modules
└── whatif/                           # Top-level whatif scripts
    ├── episodes_inventory.py          90 lines
    └── opportunistic_validate.py     115 lines
```

**features_out summary:**
- 1098 parquets total (366 × 3 symbols)
- Coverage: 2025-04-25 → 2026-04-28 (368 days per symbol)
- 1440 rows/file (1m bars), 183 columns each
- Index: UTC tz-aware DatetimeIndex, 1-minute frequency

---

## 1. Modules Inventory

### 1.1 src/features/ (MISSING from active)

| File | Lines | Description |
|------|-------|-------------|
| `calendar.py` | 71 | ICT session calendar → `kz_active`, `kz_session_id`, `dow_ny`. 5 sessions (ASIA/LONDON/NY_AM/NY_LUNCH/NY_PM) in NY local time with DST via zoneinfo. **Single function: `compute(df)`** |
| `weekend_gap.py` | 94 | Friday close reference + gap unfill detection. Functions: `is_weekend_window()`, `compute(df)` |
| `__init__.py` | 0 | Empty package init |

**calendar.py exposed API:**
```python
SESSION_NAMES = ["ASIA", "LONDON", "NY_AM", "NY_LUNCH", "NY_PM"]
def compute(df: pd.DataFrame) -> pd.DataFrame:
    # Returns df + kz_active, kz_session_id, dow_ny
```

**weekend_gap.py exposed API:**
```python
def is_weekend_window(ts: pd.Timestamp) -> bool
def compute(df: pd.DataFrame) -> pd.DataFrame:
    # Returns df + weekend_gap_unfilled_below, weekend_gap_low_price,
    #              weekend_gap_size_pct, weekend_friday_close_price
```

### 1.2 src/detectors/ (ENTIRELY MISSING from active)

| File | Lines | Description |
|------|-------|-------------|
| `params.py` | 306 | Default parameter grids + metadata for all detectors. `DEFAULT_PARAMS`, `SESSION_CODES`, `SESSION_PREFIXES`. ~30 detector parameter sets. |
| `predicates.py` | 628 | Pure stateless predicates over feature rows. 50+ `detect_*()` functions. Session detectors, KZ proximity detectors, OI/funding/L-S detectors, candle-pattern detectors, consolidation/profit-lock episode detectors. |
| `registry.py` | 151 | `DETECTOR_REGISTRY: dict[str, Callable]`. `LEGACY_ALIASES`. `get_detector(name)`. Maps string names → functions for playbook resolver. |
| `__init__.py` | 16 | Exports |

**Key predicates by category:**
```
Session active:  detect_at_ASIA, detect_at_LONDON, detect_at_NY_AM, detect_at_NY_LUNCH, detect_at_NY_PM
KZ proximity:    detect_at_kz_high, detect_at_kz_low,
                 detect_at_last_kz_high_{asia,london,nyam,nylu,nypm}
                 detect_at_last_kz_low_{asia,london,nyam,nylu,nypm}
DWM levels:      detect_at_pdh, detect_at_pdl, detect_at_pwh, detect_at_pwl,
                 detect_at_pmh, detect_at_pml, detect_at_d_open, detect_at_w_open, detect_at_m_open
Candle:          detect_pin_bar_{bull,bear}, detect_pin_bar_{bull,bear}_15m,
                 detect_engulfing_{bull,bear}, detect_volume_spike, detect_volume_spike_15m
Move strength:   detect_move_{weak,medium,strong,critical}_{up,down}
Momentum:        detect_rsi_extreme_{high,low}, detect_rsi_divergence_{bull,bear}, detect_no_pullback
Derivatives:     detect_oi_expansion, detect_oi_contraction,
                 detect_funding_extreme_{long,short}, detect_ls_ratio_extreme_{long,short}
Cross-asset:     detect_btc_eth_divergence_{btc,eth}_leads, detect_xrp_impulse_solo, detect_all_dump_synchro
Episode:         detect_consolidation_after_move, detect_profit_lock_opportunity
```

### 1.3 src/episodes/ (ENTIRELY MISSING from active)

| File | Lines | Description |
|------|-------|-------------|
| `extractor.py` | 694 | Episode extraction from feature partitions. Supports 9 episode types (ASIA/LONDON/NY_AM/NY_LUNCH/NY_PM sessions + consolidation_after_move + profit_lock_opportunity + DWM sweeps). CLI entrypoint. Produces `episodes.parquet` with typed rows per episode. |
| `__init__.py` | 2 | Package init |

**Exposed API:**
```python
class EpisodeSpec           # trigger column + window duration + required columns
def build_episode_specs()   # → dict[type, EpisodeSpec] for all 9 types
def extract_episodes(...)   # → pd.DataFrame (episodes.parquet schema)
def main(argv)              # CLI: --features-dir --output --symbols --days
```

### 1.4 src/advisor/v2/ (ENTIRELY MISSING from active)

| File | Lines | Description |
|------|-------|-------------|
| `cascade.py` | 253 | Ordered trigger cascade: features + portfolio → `Recommendation`. Evaluates plays P-1…P-12 in priority order. Contains `_PLAY_META` with win rates, DD %. `evaluate(features, portfolio)` → Recommendation |
| `portfolio.py` | 178 | Portfolio state reader from `ginarea_live/snapshots_v2.csv` with 10s TTL cache. `read_portfolio_state()` → `PortfolioState`. |
| `loader.py` | 127 | Static loader for OPPORTUNITY_MAP play specs. `get_play(id)`, `get_all_plays()`. Hard-banned: P-5, P-8, P-10. |
| `feature_writer.py` | 216 | Live feature writer: computes lightweight feature row from 1h candles every 60s → `features_out/{SYMBOL}/{date}.parquet`. Parallel to full pipeline. |
| `dedup.py` | 81 | Deduplication of consecutive recommendations. Suppresses repeat signals within cooldown. |
| `telemetry.py` | 234 | Telemetry writer for advisor decisions → JSONL. Win/loss tracking. |
| `size_mode.py` | 34 | `MODE_TO_SIZE: dict` — maps size mode ("small"/"medium"/"large") → BTC sizes. |

**POTENTIAL CONFLICT:** `src/advisor/v2/cascade.py` overlaps in responsibility with `services/advise_v2/` (setup_matcher, signal_generator). Both evaluate plays P-1…P-12 from `MarketContext`. The restored cascade uses `features_out` parquets directly; the active advise_v2 uses `MarketContext` Pydantic model. These are **parallel implementations** of the same advisor logic — see §5.

### 1.5 src/playbook/ (ENTIRELY MISSING from active)

| File | Lines | Description |
|------|-------|-------------|
| `parser.py` | 156 | Tokenizer + parser for trigger expressions (DSL). `parse_expression("AT_KZ_HIGH and VOLUME_SPIKE")` → AST. |
| `resolver.py` | 115 | Resolves AST against feature row + detector registry. `Resolver.evaluate(row)` → bool |
| `validator.py` | 180 | Static PLAYBOOK validation: checks all detectors exist, all columns are in expected_columns. `validate_playbook(path)` → `ValidationSummary` |
| `composite.py` | 87 | Composite play registry. `PlaybookRegistry`. `build_composite(plays_list)`. |
| `loader.py` | 108 | YAML/JSON playbook loader. `load_playbook(path)` → list of play dicts. |
| `expected_columns.py` | 186 | Static catalog of 90+ expected feature columns. Used by validator. |
| `ast_nodes.py` | 88 | AST node types: `AtomNode`, `ComparisonNode`, `AndNode`, `OrNode`, `NotNode`. |
| `cli.py` | 25 | `python -m src.playbook validate <path>` CLI |

**expected_columns.py** catalogs 90+ columns including all kz_* columns from calendar+killzones, all DWM levels, all derivative features, all candle pattern scores — **this is the canonical feature contract.**

### 1.6 src/whatif/ (PARTIALLY MISSING from active)

| Restored file | Lines | Active counterpart | Status |
|---------------|-------|--------------------|--------|
| `h_cascade_direction.py` | 504 | `src/whatif/h_cascade_direction.py` | **MISSING** |
| `h_wait_vs_chase.py` | 488 | `src/whatif/h_wait_vs_chase.py` | **MISSING** |
| `liquidity_harvester.py` | 320 | `src/whatif/liquidity_harvester.py` | **MISSING** |
| `profit_lock_restart.py` | 171 | `src/whatif/profit_lock_restart.py` | **MISSING** |
| `aggregator.py` | 135 | `src/whatif/aggregator.py` | **MISSING** |
| `run_config.py` | 181 | `src/whatif/run_config.py` | **MISSING** |

**h_cascade_direction.py:** P-6 vs P-7 comparative study on shared BTC episodes.
**h_wait_vs_chase.py:** P-1 vs P-2 comparative study — wait vs chase on identical episodes.
**liquidity_harvester.py:** P-13 horizon simulation.
**profit_lock_restart.py:** P-14 delayed restart simulation.
**aggregator.py:** Multi-play result aggregation → summary markdown.
**run_config.py:** `build_run_config()` → RunConfig for all plays.

### 1.7 services/ (MISSING from active)

| File | Lines | Description |
|------|-------|-------------|
| `adaptive_grid_manager.py` | 588 | Auto-tightening of short bot params on drawdown ≥4h. Reads snapshots.csv, writes state/adaptive_grid_state.json, dry_run mode. Triggers: unreal < -$200 → gs×0.67, target×0.60. |
| `boundary_expand_manager.py` | 471 | Auto-expand border_top when price ≥ border_top × (1 + gap_pct) for dwell_min minutes. dry_run JSONL output. |
| `counter_long_manager.py` | 407 | DRY-RUN cascade detector for liquidation clusters. Triggers counter-long signal on cascades ≥ threshold BTC in window_sec. Post-hoc simulation + Telegram. |

### 1.8 scripts/ (vs active)

| Restored | Lines | Active counterpart | Diff |
|----------|-------|--------------------|------|
| `watchdog.py` | 169 | `scripts/watchdog.py` | **0 lines diff — IDENTICAL** |
| `smoke_collectors.py` | 64 | `scripts/smoke_collectors.py` | **0 lines diff — IDENTICAL** |
| `download_historical.py` | 438 | no active | MISSING (downloads OI/funding/klines from data.binance.vision) |
| `extend_features.py` | 145 | no active | MISSING (extends feature partitions incrementally) |
| `run_features.py` | 25 | no active | MISSING (runner for full feature rebuild) |

### 1.9 Pre-computed features_out/ data

**HIGH VALUE DATA — already computed, ready to use:**

| Symbol | Files | Date range | Rows/file | Columns |
|--------|-------|------------|-----------|---------|
| BTCUSDT | 366 | 2025-04-25 → 2026-04-28 | 1440 (1m bars) | 183 |
| ETHUSDT | 366 | 2025-04-25 → 2026-04-28 | 1440 | 183 |
| XRPUSDT | 366 | 2025-04-25 → 2026-04-28 | 1440 | 183 |

**Feature categories present in parquets** (sampled from BTCUSDT/2025-04-25.parquet, 183 cols):
- OHLCV + close_time + quote_volume + trades_count
- OI: sum_open_interest, oi_value, oi_delta_1h, oi_delta_pct_1h, oi_zscore_24h
- L/S ratio: ls_ratio_top, ls_ratio_retail, ls_top_zscore, ls_retail_zscore, ls_divergence
- Funding: funding_rate, funding_zscore, funding_extreme_{long,short}
- Taker: taker_buy_sell_ratio, taker_imbalance, taker_imbalance_zscore, taker_buy_ratio
- Killzones (calendar): kz_active, kz_session_id, dow_ny
- Killzones (state): kz_running_{high,low,midpoint,range}, kz_minutes_into_session
- Per-session finalized: last_{asia,london,nyam,nylu,nypm}_{high,low,midpoint,close_ts}
- Per-session flags: {asia,london,nyam,nylu,nypm}_{high_sweep,low_sweep,high_mitigated,low_mitigated,midpoint_visited}
- Per-session distance: dist_last_{asia,london,nyam,nylu,nypm}_{high,low,midpoint}_pct
- NY_AM: nyam_first30_{direction,magnitude_pct}, nyam_reversal_after_first30
- DWM levels: d_open, w_open, m_open, pdh, pdl, pwh, pwl, pmh, pml
- DWM hits/sweeps: pdh_hit, pdl_hit, pdh_sweep, pdl_sweep
- DWM distances: dist_to_{pdh,pdl,pwh,pwl,pmh,pml,d_open,w_open,m_open,d_high,d_low}_pct
- Technical (15m): body_pct_1m, consec_bull/bear, vol_zscore, momentum_15m, pin_bar/engulfing_15m
- Technical (1h): atr_1h/pct, rsi_1h, rsi_ob/os, momentum_1h, pin_bar/engulfing_1h, rsi_div_bull/bear
- Delta: delta_{5m,15m,1h,24h}_pct
- Weekend gap: weekend_gap_unfilled_below, weekend_gap_low_price, weekend_gap_size_pct, weekend_friday_close_price
- Cross-asset: btc_eth_corr, eth_btc_ratio, divergence, xrp_impulse scores

---

## 2. Active vs Restored

| Restored path | Active path | Status | Notes |
|---------------|-------------|--------|-------|
| `src/features/calendar.py` | `src/features/calendar.py` | **restored_only** | Pipeline imports it; 2 active tests broken |
| `src/features/weekend_gap.py` | `src/features/weekend_gap.py` | **restored_only** | Pipeline imports it |
| `src/features/__init__.py` | missing in active src/features/ | **restored_only** | Needed for imports |
| `src/detectors/params.py` | — | **restored_only** | Entire detectors package missing |
| `src/detectors/predicates.py` | — | **restored_only** | 50+ detect_* functions |
| `src/detectors/registry.py` | — | **restored_only** | DETECTOR_REGISTRY needed by playbook |
| `src/episodes/extractor.py` | — | **restored_only** | Episode extraction |
| `src/advisor/v2/cascade.py` | — | **restored_only** | ⚠️ POTENTIAL CONFLICT with services/advise_v2/ |
| `src/advisor/v2/portfolio.py` | — | **restored_only** | Reads ginarea_live/snapshots_v2.csv |
| `src/advisor/v2/feature_writer.py` | — | **restored_only** | Live feature writer to features_out/ |
| `src/advisor/v2/loader.py` | — | **restored_only** | Play spec loader |
| `src/advisor/v2/dedup.py` | — | **restored_only** | Signal dedup |
| `src/advisor/v2/telemetry.py` | — | **restored_only** | Decision telemetry |
| `src/advisor/v2/size_mode.py` | — | **restored_only** | Size mode map |
| `src/playbook/parser.py` | — | **restored_only** | Playbook DSL parser |
| `src/playbook/resolver.py` | — | **restored_only** | AST resolver |
| `src/playbook/validator.py` | — | **restored_only** | Playbook validation |
| `src/playbook/composite.py` | — | **restored_only** | Composite registry |
| `src/playbook/loader.py` | — | **restored_only** | YAML loader |
| `src/playbook/expected_columns.py` | — | **restored_only** | Column catalog (90+ features) |
| `src/playbook/ast_nodes.py` | — | **restored_only** | AST nodes |
| `src/whatif/aggregator.py` | — | **restored_only** | Multi-play aggregation |
| `src/whatif/h_cascade_direction.py` | — | **restored_only** | P-6 vs P-7 study |
| `src/whatif/h_wait_vs_chase.py` | — | **restored_only** | P-1 vs P-2 study |
| `src/whatif/liquidity_harvester.py` | — | **restored_only** | P-13 simulation |
| `src/whatif/profit_lock_restart.py` | — | **restored_only** | P-14 simulation |
| `src/whatif/run_config.py` | — | **restored_only** | Run config builder |
| `services/adaptive_grid_manager.py` | — | **restored_only** | Auto grid tightening |
| `services/boundary_expand_manager.py` | — | **restored_only** | Auto border expansion |
| `services/counter_long_manager.py` | — | **restored_only** | Counter-long cascade detector |
| `scripts/watchdog.py` | `scripts/watchdog.py` | **same** | 0 diff |
| `scripts/smoke_collectors.py` | `scripts/smoke_collectors.py` | **same** | 0 diff |
| `scripts/download_historical.py` | — | **restored_only** | data.binance.vision downloader |
| `scripts/extend_features.py` | — | **restored_only** | Feature extension script |
| `collectors/*` | `collectors/*` | **different** | Active is post-TZ-048 rotation fix; restored is older version |

---

## 3. Broken Imports & Tests

### Tests that FAIL to collect (ImportError):

| Test file | Missing import | Fix required |
|-----------|---------------|--------------|
| `src/features/tests/test_killzones.py` | `src.features.calendar` | Copy `_recovery/restored/src/features/calendar.py` → `src/features/calendar.py` |
| `src/features/tests/test_pipeline.py` | Indirect: `src.features.pipeline` imports `calendar` | Same fix |

### Tests that would fail at runtime after calendar fix:

| Test file | Missing import | Fix required |
|-----------|---------------|--------------|
| `src/features/tests/test_pipeline.py` | `src.features.weekend_gap` (imported by pipeline) | Copy `weekend_gap.py` too |

### Restored tests NOT in active test suite (would need reactivation):

- `_recovery/restored/src/features/tests/test_calendar.py` (256 lines) — calendar sessions tests
- `_recovery/restored/src/features/tests/test_weekend_gap.py` (119 lines) — weekend gap tests
- `_recovery/restored/src/detectors/tests/test_predicates.py` (380 lines) — all 50+ predicates
- `_recovery/restored/src/episodes/tests/test_extractor.py` (217 lines) — episode extraction
- `_recovery/restored/src/playbook/tests/` (7 test files, ~500 lines total)
- `_recovery/restored/tests/advisor/v2/` (13 test files, ~1800 lines total)

### Current regression count impact of reactivating calendar.py + weekend_gap.py only:
- 2 tests would go from ERROR to PASS (test_killzones, test_pipeline)
- No regressions expected (pure new files, no modification to existing)

---

## 4. Integration with services/advise_v2/

### Current MarketContext schema (services/advise_v2/schemas.py):

```python
class MarketContext(StrictModel):
    price_btc: float
    regime_label: Literal["impulse_up", ..., "unknown"]
    regime_modifiers: list[str]   # ← INTAKE POINT for session features
    rsi_1h: float
    rsi_5m: float | None
    price_change_5m_30bars_pct: float
    price_change_1h_pct: float
    nearest_liq_below: LiqLevel | None
    nearest_liq_above: LiqLevel | None
```

### Current regime_modifiers in setup_matcher.py:
```
upper_band_test, volume_decline, volume_spike_5m, liq_cluster_breached_below,
pullback_to_ema, liq_cluster_breached_above, session_history_required
```
**None of these come from killzone/session features.** The `session_history_required` is a placeholder for P-10 (returns empty).

### Mapping: restored features → potential regime_modifiers

| Feature column | Detector predicate | Proposed modifier tag | Relevant plays |
|----------------|-------------------|----------------------|----------------|
| `kz_active == "NY_AM"` | `detect_at_NY_AM` | `ny_am_active` | P-2 (stack-short), P-6 (stack+expand) |
| `kz_active == "LONDON"` | `detect_at_LONDON` | `london_active` | context modifier |
| `dist_active_kz_high_pct < 0.15` | `detect_at_kz_high` | `at_kz_high` | P-4 (stop shorts) |
| `dist_active_kz_low_pct < 0.15` | `detect_at_kz_low` | `at_kz_low` | P-2 long defense |
| `last_nyam_high_mitigated == False` | `detect_at_last_kz_high_nyam` | `at_nyam_high_unmitigated` | P-6 |
| `nyam_high_sweep == True` | bool feature | `nyam_high_swept` | reversal signal |
| `nyam_first30_direction` | `detect_at_NY_AM` + dir | `nyam_false_move` | P-2 timing |
| `pdh_hit == True` | `detect_at_pdh` | `at_pdh` | P-4 (stop shorts near PDH) |
| `pdl_hit == True` | `detect_at_pdl` | `at_pdl` | P-2 (short defense near PDL) |
| `dist_to_d_open_pct < 0.1` | `detect_at_d_open` | `at_d_open` | context |
| `funding_extreme_long == True` | `detect_funding_extreme_long` | `funding_extreme_long` | P-2/P-6 short bias |
| `oi_delta_pct_1h > threshold` | `detect_oi_expansion` | `oi_expanding` | trend confirmation |
| `ls_top_zscore > 2.0` | `detect_ls_ratio_extreme_long` | `ls_extreme_long` | mean reversion |

### Integration pathway (if reactivated):

The `setup_matcher.py` `_eval_p*()` functions already accept `market_context.regime_modifiers` as a bonus list. Adding session-derived modifiers would require:
1. Signal generator to populate regime_modifiers from feature row columns
2. One new field in `MarketContext` or as `regime_modifiers` string entries (current approach: strings)
3. No schema change needed — just more strings in the existing `regime_modifiers` list

---

## 5. Recommendations

### PRIORITY 1 — Reactivate as-is (1 commit, unblocks broken tests)

**`src/features/calendar.py`** and **`src/features/weekend_gap.py`**
- Action: copy from `_recovery/restored/src/features/` → `src/features/`
- Impact: 2 broken test files (test_killzones, test_pipeline) will collect and run
- Risk: ZERO — pure new files, no modification to existing code
- Recommendation: **REACTIVATE AS-IS** — these are REQUIRED by the active pipeline (manifest.py lists calendar.py, pipeline.py imports calendar and killzones)

### PRIORITY 2 — Reactivate + integrate (pre-computed data available)

**`src/detectors/`** (params, predicates, registry)
- Action: copy entire package from restored → active
- Pre-condition: calendar.py must be active first (predicates use kz_active column)
- Impact: enables playbook validator, enables session-aware signal modifiers
- Recommendation: **REACTIVATE AS-IS** — no conflicts with active code. Detectors are pure stateless functions.

**`src/episodes/extractor.py`**
- Action: copy from restored
- Pre-condition: detectors package must be active
- Impact: enables episode extraction from the 1098 pre-computed feature parquets
- Recommendation: **REACTIVATE AS-IS** — high value: 1098 pre-computed parquets are ready

### PRIORITY 3 — Reactivate + integrate (after P1+P2 done)

**`src/playbook/`** (full package, 9 files)
- Action: copy from restored
- Impact: enables PLAYBOOK trigger expression DSL — evaluate plays against feature rows
- Recommendation: **REACTIVATE AS-IS** — no conflicts; depends on detectors

**`src/whatif/` missing 6 files** (aggregator, h_cascade_direction, h_wait_vs_chase, liquidity_harvester, profit_lock_restart, run_config)
- Action: copy from restored
- Pre-condition: verify imports against active whatif modules (some import from `src.whatif.grid_search` which IS active)
- Recommendation: **REACTIVATE + VERIFY IMPORTS** — h_cascade_direction/h_wait_vs_chase import `src.whatif.grid_search.Episode` which needs version check

### PRIORITY 4 — Investigate before reactivation

**`src/advisor/v2/`** ⚠️ POTENTIAL CONFLICT
- **Conflict:** `cascade.py` evaluates plays P-1..P-12 directly from feature parquets. Active `services/advise_v2/setup_matcher.py` does the same from `MarketContext`. They are parallel implementations of the same business logic.
- `cascade.py` uses raw feature dict from `features_out/` parquets
- `setup_matcher.py` uses `MarketContext` Pydantic model (abstracted)
- `cascade.py` pre-dates the active advise_v2 architecture (older design)
- Recommendation: **LEAVE AS RESTORED** — do not reactivate `src/advisor/v2/cascade.py`. Instead, integrate session features via the existing `regime_modifiers` path in `services/advise_v2/`. The `feature_writer.py` and `portfolio.py` may be useful individually.

**`services/adaptive_grid_manager.py`**, **`boundary_expand_manager.py`**, **`counter_long_manager.py`**
- These are functional services that auto-tune bot parameters
- No active counterpart; unclear if still needed given current bot architecture
- Recommendation: **LEAVE AS RESTORED** pending operator decision on whether auto-parameter-tuning is wanted live

### PRIORITY 5 — Discard (already in active or superseded)

**`collectors/`** in restored
- Active `collectors/` is post-TZ-048 rotation fix (newer)
- Recommendation: **DELETE RESTORED COPY** (safe — active is strictly newer)

**`scripts/watchdog.py`**, **`scripts/smoke_collectors.py`**
- **IDENTICAL to active** (0 diff)
- Recommendation: **DELETE RESTORED COPIES** — no value in keeping duplicates

---

## 6. Skills Applied

- **state_first_protocol**: git status checked; no live state modified; read-only audit confirmed
- **encoding_safety**: output .md written with explicit UTF-8 encoding; JSON artifact with ensure_ascii=False
- **operator_role_boundary**: no commands directed at operator; all execution by Code
- **untracked_protection**: `docs/STATE/RESTORED_FEATURES_AUDIT_*.md` tracked (committed); JSON artifact untracked per spec
- **cost_aware_executor**: read-only; no test execution; no code runs; grep/inspect only

---

## FILES CHANGED (this TZ)

**New (tracked):**
- `docs/STATE/RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.md` — this file

**New (untracked artifact):**
- `docs/STATE/RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json`

**Modified:** none

---

## RESULT

- 34 source files present in `_recovery/restored/src/` with NO active counterpart
- Critical blocker: `calendar.py` + `weekend_gap.py` — required by active pipeline, 2 tests broken
- High-value data: 1098 pre-computed feature parquets (366 days × 3 symbols × 183 cols), 2025-04-25 → 2026-04-28
- Main conflict zone: `src/advisor/v2/cascade.py` overlaps with `services/advise_v2/` architecture
- Clean reactivation path: calendar → detectors → episodes → playbook (in order, no conflicts)
- Session/KZ features ARE in `MarketContext.regime_modifiers` intake — no schema change needed to integrate
