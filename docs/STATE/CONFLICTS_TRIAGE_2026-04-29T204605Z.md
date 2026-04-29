# CONFLICTS TRIAGE 2026-04-29T204605Z

## PRE-FLIGHT
- git status: 9d7e5c2 HEAD (TZ-PROJECT-MEMORY-DEFENSE), clean staged area
- Skills read: project_inventory_first, session_handoff_protocol, regression_baseline_keeper, operator_role_boundary, encoding_safety
- PROJECT_RULES.md read: TZ Template — Inventory Check present
- docs/STATE/PROJECT_MAP.md read: 93 active modules, 57 conflict pairs
- docs/STATE/project_map.json read: 57 pairs fully enumerated

## 0. Sources

- `docs/STATE/project_map.json` @ 2026-04-29T22:34Z
- 57 pairs analyzed
- Root: `c:\bot7`

---

## 1. Summary

| Classification | Count | Description |
|---|---|---|
| FALSE_POSITIVE | 44 | Common interface symbols (`_parse/run` WebSocket pattern, `compute` feature interface, `_run` script entrypoint) |
| RESTORED_VS_ACTIVE | 12 | Same file exists in both active and `_recovery/restored/`; active is strictly newer or identical |
| PARTIAL_OVERLAP | 1 | `profit_lock_restart.py` re-defines `Fill/StateAtMinute` dataclasses locally despite importing from `horizon_runner` |
| REAL_DUPLICATE | 0 | — |
| EVOLVED_VERSIONS | 0 | — |
| UNCLEAR | 0 | — |
| **TOTAL** | **57** | |

**Key finding:** 44 of 57 pairs (77%) are false positives caused by uniform WebSocket collector interface (`_parse, run` in every collector module). The detector produces an N×M cross-product of all active collectors × all restored collectors. Whitelist patterns will suppress these in future runs.

**Known conflict NOT in 57 pairs:** `services/advise_v2/setup_matcher.py` (active) vs `_recovery/restored/src/advisor/v2/cascade.py` (restored) — both evaluate plays P-1..P-12. Not detected by symbol-overlap algorithm because they have different symbol names (different architectural layers). Documented in `RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json` with recommendation: `leave_as_restored`.

---

## 2. Per-pair detail

_Abbreviations: `col/liq/` = `collectors/liquidations/`, `col/ob/` = `collectors/orderbook/`, `col/tr/` = `collectors/trades/`, `r/` = `_recovery/restored/`_

| # | Active | Restored | Overlap | Classification | Recommendation |
|---|--------|----------|---------|----------------|----------------|
| 00 | scripts/smoke_collectors.py | _recovery/profile_writers.py | `_run` | FALSE_POSITIVE | No action. `_run` is generic script entrypoint. Different purposes: smoke test vs RSS profiling. |
| 01 | col/liq/binance.py | r/col/liq/binance.py | `_parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (TZ-048 rotation fix + `_ensure_output_dirs`). |
| 02 | col/liq/bitmex.py | r/col/liq/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges, shared WebSocket interface. |
| 03 | col/liq/bybit.py | r/col/liq/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 04 | col/liq/hyperliquid.py | r/col/liq/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 05 | col/liq/okx.py | r/col/liq/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 06 | col/ob/binance.py | r/col/liq/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types (orderbook vs liquidations). |
| 07 | col/tr/binance.py | r/col/liq/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types (trades vs liquidations). |
| 08 | col/liq/binance.py | r/col/liq/bitmex.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 09 | col/liq/bitmex.py | r/col/liq/bitmex.py | `_parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (rotation fix). |
| 10 | col/liq/bybit.py | r/col/liq/bitmex.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 11 | col/liq/hyperliquid.py | r/col/liq/bitmex.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 12 | col/liq/okx.py | r/col/liq/bitmex.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 13 | col/ob/binance.py | r/col/liq/bitmex.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 14 | col/tr/binance.py | r/col/liq/bitmex.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 15 | col/liq/binance.py | r/col/liq/bybit.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 16 | col/liq/bitmex.py | r/col/liq/bybit.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 17 | col/liq/bybit.py | r/col/liq/bybit.py | `_parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (rotation fix). |
| 18 | col/liq/hyperliquid.py | r/col/liq/bybit.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 19 | col/liq/okx.py | r/col/liq/bybit.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 20 | col/ob/binance.py | r/col/liq/bybit.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 21 | col/tr/binance.py | r/col/liq/bybit.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 22 | col/liq/binance.py | r/col/liq/hyperliquid.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 23 | col/liq/bitmex.py | r/col/liq/hyperliquid.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 24 | col/liq/bybit.py | r/col/liq/hyperliquid.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 25 | col/liq/hyperliquid.py | r/col/liq/hyperliquid.py | `_parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (rotation fix). |
| 26 | col/liq/okx.py | r/col/liq/hyperliquid.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 27 | col/ob/binance.py | r/col/liq/hyperliquid.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 28 | col/tr/binance.py | r/col/liq/hyperliquid.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 29 | col/liq/binance.py | r/col/liq/okx.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 30 | col/liq/bitmex.py | r/col/liq/okx.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 31 | col/liq/bybit.py | r/col/liq/okx.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 32 | col/liq/hyperliquid.py | r/col/liq/okx.py | `_parse, run` | FALSE_POSITIVE | No action. Different exchanges. |
| 33 | col/liq/okx.py | r/col/liq/okx.py | `_parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (rotation fix). |
| 34 | col/ob/binance.py | r/col/liq/okx.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 35 | col/tr/binance.py | r/col/liq/okx.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 36 | collectors/main.py | r/collectors/main.py | `_main` | RESTORED_VS_ACTIVE | Delete restored copy. `_main` is standard entrypoint name. Active is newer. |
| 37 | col/liq/binance.py | r/col/ob/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 38 | col/liq/bitmex.py | r/col/ob/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 39 | col/liq/bybit.py | r/col/ob/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 40 | col/liq/hyperliquid.py | r/col/ob/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 41 | col/liq/okx.py | r/col/ob/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 42 | col/ob/binance.py | r/col/ob/binance.py | `_build_url, _parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (rotation fix). |
| 43 | col/tr/binance.py | r/col/ob/binance.py | `_build_url, _parse, run` | FALSE_POSITIVE | No action. Different data types (trades vs orderbook), same interface. |
| 44 | collectors/pidlock.py | r/collectors/pidlock.py | `PidLock, _process_alive` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer or identical. |
| 45 | collectors/storage.py | r/collectors/storage.py | `_parquet_path` | RESTORED_VS_ACTIVE | Delete restored copy. Active has rotation fix. |
| 46 | col/liq/binance.py | r/col/tr/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 47 | col/liq/bitmex.py | r/col/tr/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 48 | col/liq/bybit.py | r/col/tr/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 49 | col/liq/hyperliquid.py | r/col/tr/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 50 | col/liq/okx.py | r/col/tr/binance.py | `_parse, run` | FALSE_POSITIVE | No action. Different data types. |
| 51 | col/ob/binance.py | r/col/tr/binance.py | `_build_url, _parse, run` | FALSE_POSITIVE | No action. Different data types (orderbook vs trades), same WebSocket interface. |
| 52 | col/tr/binance.py | r/col/tr/binance.py | `_build_url, _parse, run` | RESTORED_VS_ACTIVE | Delete restored copy. Active is newer (rotation fix). |
| 53 | scripts/smoke_collectors.py | r/scripts/smoke_collectors.py | `_run` | RESTORED_VS_ACTIVE | Delete restored copy. Confirmed identical in RESTORED_FEATURES_AUDIT. |
| 54 | scripts/watchdog.py | r/scripts/watchdog.py | `_pid_alive, _read_pid` | RESTORED_VS_ACTIVE | Delete restored copy. Confirmed identical in RESTORED_FEATURES_AUDIT. |
| 55 | src/features/dwm.py | r/src/features/calendar.py | `compute` | FALSE_POSITIVE | No action. `compute(df)` is standard feature module interface. Completely different domains: DWM levels vs ICT kill zone sessions. |
| 56 | src/whatif/horizon_runner.py | r/src/whatif/profit_lock_restart.py | `Fill, StateAtMinute` | PARTIAL_OVERLAP | When reactivating `profit_lock_restart.py`: remove local `Fill`/`StateAtMinute` definitions (lines 14–30) and import from `horizon_runner` instead. |

---

## 3. Recommended actions (priority list)

### Priority 1 — False positive detector fix (unblocks future TZs)
Update detector whitelist in `scripts/state_snapshot.py` `_detect_conflicts()`:

1. **Collector interface pattern** (`_parse`, `run`, `_build_url`): Any file under `collectors/` with these symbols — suppress cross-product pairs. ~42 false positives suppressed.
2. **Feature module interface** (`compute`): Any file under `src/features/` — suppress cross-feature pairs. 1 false positive suppressed.
3. **Script entrypoint** (`_run`, `_main`): Files directly under `scripts/` — suppress these generic names. 2 false positives suppressed.

Separate TZ: `TZ-PROJECT-MAP-WHITELIST`.

### Priority 2 — Clean up restored copies (RESTORED_VS_ACTIVE)
12 pairs where same file exists in both `collectors/` and `_recovery/restored/collectors/`. Active is strictly newer in all cases (TZ-048 rotation fix).

Bulk action: delete all of `_recovery/restored/collectors/` tree PLUS `_recovery/restored/scripts/smoke_collectors.py` and `_recovery/restored/scripts/watchdog.py`.

Authorization required (explicit per-path approval per PROJECT_RULES.md §Deletion). Separate TZ: `TZ-RESTORED-COLLECTORS-CLEANUP`.

### Priority 3 — Partial overlap resolution (before profit_lock_restart reactivation)
**Pair 56:** `profit_lock_restart.py` defines local `Fill` and `StateAtMinute` dataclasses at lines 14–30, despite importing other types from `horizon_runner`. Before reactivating this module (per audit recommendation `reactivate_plus_verify_imports`):
- Remove local `Fill`/`StateAtMinute` definitions from profit_lock_restart.py
- Add: `from src.whatif.horizon_runner import Fill, StateAtMinute`
- Verify compatibility (field names, types)

### Priority 4 — Note for cascade.py (outside 57 pairs)
`_recovery/restored/src/advisor/v2/cascade.py` evaluates plays P-1..P-12 from raw feature dicts. Active `services/advise_v2/setup_matcher.py` evaluates same plays from Pydantic `MarketContext`. NOT detected by symbol-overlap (completely different symbol names). Decision per audit: `leave_as_restored`. No action needed.

---

## 4. Whitelist (for detector update)

Format: `{file_glob, symbol_pattern, reason}` list for `_detect_conflicts()` suppression.

```json
[
  {
    "file_glob": "collectors/**/*.py",
    "symbol_patterns": ["_parse", "run", "_build_url"],
    "reason": "WebSocket collector interface — every collector implements _parse(msg)->rows and async run(). N*M cross-product of active×restored is always false positive."
  },
  {
    "file_glob": "src/features/**/*.py",
    "symbol_patterns": ["compute"],
    "reason": "Standard feature module interface — every feature module exposes compute(df)->df. Cross-feature pairs are always false positive."
  },
  {
    "file_glob": "scripts/*.py",
    "symbol_patterns": ["_run", "_main"],
    "reason": "Generic script entrypoint names — _run and _main appear in nearly all script utilities. Cross-script pairs on these names only are false positive."
  }
]
```

These whitelist patterns should be applied in `_detect_conflicts()` before returning the conflicts list.
Rule: if BOTH `active` AND `restored` match the same `file_glob`, and the overlap_symbols are a subset of `symbol_patterns` → suppress the pair.

---

## 5. Skills applied

- `project_inventory_first`: inventory check performed before triage (read project_map.json, PROJECT_MAP.md, RESTORED_FEATURES_AUDIT)
- `encoding_safety`: all writes use UTF-8 encoding
- `regression_baseline_keeper`: no code changes in this TZ, regression unaffected
- `operator_role_boundary`: report only, no code execution commands directed at operator
- `state_first_protocol`: triage based on current project_map.json state, not on memory
