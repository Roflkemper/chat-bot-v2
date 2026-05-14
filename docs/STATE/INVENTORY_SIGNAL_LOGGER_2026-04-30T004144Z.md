# INVENTORY SIGNAL LOGGER 2026-04-30T004144Z

## PRE-FLIGHT
- `git status`: dirty worktree confirmed; no code changes made in this audit.
- `.claude/PROJECT_RULES.md` read.
- Skills read: `state_first_protocol`, `project_inventory_first`, `encoding_safety`, `regression_baseline_keeper`, `operator_role_boundary`.
- [PROJECT_MAP](/C:/bot7/docs/PROJECT_MAP.md) read.
- Latest restored audit available as JSON, not Markdown: [RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json](/C:/bot7/docs/STATE/RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json).

## 0. Sources
- [_recovery/restored/src/advisor/v2/telemetry.py](/C:/bot7/_recovery/restored/src/advisor/v2/telemetry.py)
- [_recovery/restored/tests/advisor/v2/test_telemetry.py](/C:/bot7/_recovery/restored/tests/advisor/v2/test_telemetry.py)
- [_recovery/restored/tests/advisor/v2/test_fix2_reconcile.py](/C:/bot7/_recovery/restored/tests/advisor/v2/test_fix2_reconcile.py)
- [_recovery/restored/tests/advisor/v2/test_035_multi_asset.py](/C:/bot7/_recovery/restored/tests/advisor/v2/test_035_multi_asset.py)
- [scripts/ohlcv_ingest.py](/C:/bot7/scripts/ohlcv_ingest.py)
- [services/telegram_runtime.py](/C:/bot7/services/telegram_runtime.py:698)
- [docs/PROJECT_MAP.md](/C:/bot7/docs/PROJECT_MAP.md)
- [docs/STATE/RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json](/C:/bot7/docs/STATE/RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json)
- [.gitignore](/C:/bot7/.gitignore)

## 1. Existing implementations summary

### `_recovery/restored/src/advisor/v2/telemetry.py`
- Path: `_recovery/restored/src/advisor/v2/telemetry.py`
- Exposed API:
  - `_side_for_play(play_id)`
  - `_now_utc()`
  - `_parse_utc(ts)`
  - `_append(path, record)`
  - `_read_all(path)`
  - `log_recommendation(rec, portfolio_balance)`
  - `schedule_outcome_check(rec, price_at_rec)`
  - `reconcile_pending(current_price)`
  - `get_recent_log(n=10)`
  - `get_stats(days=7)`
- JSONL schema:
  - `advisor_log.jsonl`: recommendation rows with `ts_utc`, `play_id`, `play_name`, `symbol`, `trigger`, `size_mode`, `size_btc`, `expected_pnl`, `win_rate`, `dd_pct`, `params`, `reason`, `portfolio_balance`.
  - `advisor_outcomes.jsonl`: mixed record types:
    - pending rows with `type="pending"`, `ts_utc`, `play_id`, `symbol`, `trigger`, `price_at_rec`, `size_btc`, `side`, `expected_pnl`
    - outcome rows with `type="outcome"`, `rec_ts_utc`, `play_id`, `horizon_h`, `price_at_rec`, `price_now`, `pnl_proxy`, `hit`, `side`, `expected_pnl`, `ts_reconciled`
- Reader / iterator:
  - No lazy iterator API.
  - `_read_all()` loads full file into memory and returns `list[dict]`.
  - `get_recent_log()` returns last `n` decoded dicts.
- Aggregation helpers:
  - `get_stats(days=7)` aggregates by play count and 4h outcomes.
  - No generic count-by-time or count-by-pattern over validated envelopes.
- Dependencies:
  - Imports restored `Recommendation` from `src.advisor.v2.cascade`.
  - Uses only stdlib otherwise.
- Tests / coverage:
  - Direct tests in [_recovery/restored/tests/advisor/v2/test_telemetry.py](/C:/bot7/_recovery/restored/tests/advisor/v2/test_telemetry.py)
  - Reconciliation tests in [_recovery/restored/tests/advisor/v2/test_fix2_reconcile.py](/C:/bot7/_recovery/restored/tests/advisor/v2/test_fix2_reconcile.py)
  - Multi-asset field coverage in [_recovery/restored/tests/advisor/v2/test_035_multi_asset.py](/C:/bot7/_recovery/restored/tests/advisor/v2/test_035_multi_asset.py)
- Fit assessment:
  - This is telemetry for restored `advisor/v2` recommendations plus post-hoc outcomes.
  - It is not a `SignalEnvelope` logger and is coupled to restored cascade architecture.

### `scripts/ohlcv_ingest.py`
- Path: `scripts/ohlcv_ingest.py`
- Exposed JSONL-related API:
  - `_write_log(entry)`
- JSONL schema:
  - Operational run log rows for ingest jobs, not signal rows.
  - Writes `ts_run`, `source`, `symbol`, `target_end`, `result_1m`, `result_1h`, `range_filled`, `bars_count`, `gaps_found`.
- Reader / iterator:
  - None.
- Aggregation helpers:
  - None.
- Dependencies:
  - Stdlib + `pandas`.
- Fit assessment:
  - Useful only as a simple append pattern reference: `json.dumps(..., ensure_ascii=False) + "\n"` with parent dir creation.
  - No reusable JSONL utility abstraction extracted from this script.

### `services/telegram_runtime.py`
- Path: [services/telegram_runtime.py](/C:/bot7/services/telegram_runtime.py:698)
- JSONL usage:
  - Reads restored advisor telemetry through `src.advisor.v2.telemetry`.
  - `/advisor stats` uses `get_stats()`.
  - `/advisor log` uses `get_recent_log(n=5)`.
  - Default advisor flow calls `log_recommendation()` and `schedule_outcome_check()`.
- Data type:
  - Restored `Recommendation`, not `SignalEnvelope`.
- Fit assessment:
  - Confirms telemetry is already integrated into old advisor UX, not into active `services/advise_v2` pipeline.

### Restored tests around JSONL
- `_recovery/restored/tests/advisor/v2/test_telemetry.py`
  - Covers append writes, empty-file behavior, recent-log slicing, basic stats.
- `_recovery/restored/tests/advisor/v2/test_fix2_reconcile.py`
  - Covers pending/outcome lifecycle, idempotent reconcile, elapsed horizon checks, basic outcome stats.
- `_recovery/restored/tests/advisor/v2/test_035_multi_asset.py`
  - Verifies symbol field is persisted into `advisor_log.jsonl` and `advisor_outcomes.jsonl`.
- Fit assessment:
  - Good evidence that restored telemetry is stable for recommendation/outcome journaling.
  - No tests for `SignalEnvelope` validation, lazy streaming iterators, null-signal logs, or pattern-level aggregation over active advise_v2 schema.

### Project map / audit signals
- [PROJECT_MAP](/C:/bot7/docs/PROJECT_MAP.md) lists the expected project-map anchor for active modules and restored `_recovery/restored/src/advisor/v2/telemetry.py`.
- Latest restored audit marks [_recovery/restored/src/advisor/v2/cascade.py](/C:/bot7/_recovery/restored/src/advisor/v2/cascade.py) as `leave_as_restored` because it conflicts conceptually with active `services/advise_v2/`.
- `telemetry.py` depends on that restored advisor v2 recommendation model, so it inherits the same architectural boundary.

## 2. Requirements comparison matrix

| requirement | telemetry.py covers? | extension cost |
| --- | --- | --- |
| `log_signal(envelope)` | Partial at best. Has `log_recommendation(rec, portfolio_balance)`, but schema is recommendation-centric and not `SignalEnvelope`. | High |
| `log_null_signal(context, exposure, reason)` | No | Medium |
| `iter_signals()` with pydantic validation | No. Only `_read_all()` and `get_recent_log()` returning raw dict lists. | High |
| `iter_null_signals()` | No | Medium |
| `count_signals(since=None)` | No direct equivalent. `get_stats(days=7)` is recommendation/outcome oriented and fixed-shape. | Medium |
| `signals_by_pattern()` | Partial. `get_stats()` aggregates `by_play_count`, but only after full-file load and only for restored recommendation rows. | Medium |
| UTF-8 / append-only / concurrent-safe single-line writes | Yes. Uses UTF-8 append with newline and `ensure_ascii=False`. Same single-line atomicity assumption as the proposed TZ. | Low |

### Coverage summary
- Strong coverage: `1/7`
  - UTF-8 append-only single-line JSONL write pattern
- Partial coverage: `2/7`
  - recommendation logging
  - play-level aggregation
- Missing coverage: `4/7`
  - null-signal logging
  - lazy validated iterators
  - generic count with `since`
  - active-schema `SignalEnvelope` storage

### Architectural fit
- `telemetry.py` writes restored `Recommendation` rows and restored outcome rows, not active `SignalEnvelope` rows.
- It depends on restored `src.advisor.v2.cascade.Recommendation`.
- Restored audit already classifies that cascade stack as parallel to active `services/advise_v2`.
- Reusing this module directly would either:
  - pull active advise_v2 back toward restored cascade architecture, or
  - require a wrapper layer thick enough that a new minimal logger is simpler and cleaner.

## 3. Recommendation

### `parallel_minimal`

Rationale:
- `telemetry.py` solves a related but different problem: restored advisor recommendation telemetry plus delayed outcomes reconciliation.
- Its row schema is fixed around `Recommendation`, `play_id`, and `outcome` records, not around the active Pydantic `SignalEnvelope`.
- It does not provide the core reader contract required by `TZ-SIGNAL-LOGGER`: lazy `iter_signals()`, validated envelope parsing, null-signal stream, generic count, and `signals_by_pattern()`.
- The dependency on restored `cascade.py` is a boundary risk. The restored audit explicitly says that advisor v2 cascade should remain restored-only to avoid conflict with active `services/advise_v2`.
- Extending `telemetry.py` would create scope creep: two schemas, two runtime roots (`logs/` vs `state/`), and mixed active/restored ownership in one module.

Decision:
- Build a separate active-path `services/advise_v2/signal_logger.py`.
- Keep restored telemetry untouched for old `/advisor` workflows.
- Document the divergence explicitly: restored telemetry = recommendation/outcome journal; active `signal_logger` = `SignalEnvelope` / null-signal journal.

## 4. Implementation plan

### Recommended scope
1. Create `services/advise_v2/signal_logger.py` with active-schema-only helpers:
   - `DEFAULT_SIGNAL_LOG = Path("state/advise_signals.jsonl")`
   - `DEFAULT_NULL_LOG = Path("state/advise_null_signals.jsonl")`
   - `log_signal(envelope, log_path=None) -> Path`
   - `log_null_signal(market_context_dump, current_exposure_dump, reason, log_path=None) -> Path`
   - `iter_signals(log_path=None) -> Iterator[SignalEnvelope]`
   - `iter_null_signals(log_path=None) -> Iterator[dict]`
   - `count_signals(log_path=None, since=None) -> int`
   - `signals_by_pattern(log_path=None) -> dict[str, int]`
2. Reuse only the narrow proven pattern from restored telemetry / ingest:
   - parent dir creation
   - UTF-8 append
   - `ensure_ascii=False`
   - skip malformed JSON lines silently
3. Do not import anything from `_recovery/restored/src/advisor/v2/telemetry.py`.
4. Add focused tests under `tests/services/advise_v2/test_signal_logger.py`:
   - append behavior
   - lazy iteration
   - malformed line skip
   - null-signal format
   - `since` filter
   - `signals_by_pattern`
   - concurrent append smoke test
   - UTF-8/Cyrillic preservation
5. Update `.gitignore` if and only if `state/advise_signals.jsonl` and `state/advise_null_signals.jsonl` are still absent.

### Out of scope for signal_logger TZ
- Reconciliation horizons
- Outcome logging
- Any dependency on restored `Recommendation`
- Back-compat API for `/advisor log` and `/advisor stats`

## 5. Skills applied
- `state_first_protocol`
- `project_inventory_first`
- `encoding_safety`
- `regression_baseline_keeper`
- `operator_role_boundary`
