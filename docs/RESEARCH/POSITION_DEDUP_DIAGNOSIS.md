# Position Dedup Diagnosis

**Status:** FIXED (TZ-DASHBOARD-POSITION-DEDUP, Block CP32)
**Date:** 2026-05-05
**Operator-confirmed reality:** real BTC SHORT position = **−1.296 BTC**, dashboard showed **−2.241 BTC** (~73% inflation).

---

## §1 Root cause

`services/dashboard/state_builder.py::_read_csv_latest_by_bot` keyed snapshots by raw `bot_id` string with no normalization. The CSV `ginarea_live/snapshots.csv` historically wrote bot IDs as float strings (`5196832375.0`), and a later tracker fix switched to integer strings (`5196832375`) — but old rows are still in the file. Result: each affected bot appeared **twice** in the latest-per-bot map (one entry per format), and `_build_positions` summed both.

Concrete: 45 unique bot_id strings in the CSV mapped to ~22 actual bots. For SHORT positions specifically, 4 unique bots (`TEST_1`, `TEST_2`, `TEST_3`, `SHORT_1.1%`) appeared as 8 entries. Sum of "old format" entries (`-0.183, -0.181, -0.186, -0.395 = -0.945`) plus "new format" entries (`-0.22, -0.22, -0.22, -0.636 = -1.296`) = `-2.241`.

The `current_profit` and `position` values in old-format rows were **stale snapshots from 2026-04-28** that survived because their bot_id string never collided with the modern format.

## §2 Data-flow trace

| Layer | Behavior pre-fix | Verdict |
|-------|------------------|---------|
| GinArea API → tracker | Returns one record per bot per poll. ✅ no dups at source | clean |
| tracker → snapshots.csv | Append-only. Old `.0` rows from previous tracker version stayed. ⚠️ format-change boundary preserved both | format inconsistency, not duplication per-poll |
| snapshots.csv → `_read_csv_latest_by_bot` | Keyed by raw `bot_id` string. Two formats → two map entries → ❌ DUPLICATION HERE | **root cause** |
| `_build_positions` | Loops the deduplicated-by-string list, sums up. Faithful aggregator. | not a bug, just consumed bad input |
| `state_latest.json::exposure.shorts_btc` | Already correct (-1.296) — built by a separate path that didn't suffer from `.0` issue | reference value |

The fix lands at the earliest layer where we own the code: **`_read_csv_latest_by_bot`**, by adding a `_normalize_bot_id` helper that strips trailing `.0` from numeric IDs before keying.

## §3 Why not at ingestion?

The brief asks to prefer earliest layer (ingestion) over later (display). Considered options:

| Option | Pros | Cons |
|--------|------|------|
| Fix at GinArea API client | Earliest possible | The API itself is fine — the `.0` issue is a pure tracker formatting artifact from a Python `str(int_or_float)` call that no longer exists. Nothing to fix at the API layer. |
| Fix in `ginarea_tracker.py` | Cleans the file going forward | Doesn't fix existing rows; CSV would still have legacy `.0` rows for an indeterminate time. Display layer still needs to handle them. |
| Rewrite `snapshots.csv` to canonical form | One-time cleanup | Risk to live data; tracker is actively writing; race conditions; loss of audit trail. |
| **Fix in `_read_csv_latest_by_bot`** (chosen) | Defensive normalization at the consumer; works on existing legacy rows AND any future format glitch | Adds 7 LOC of normalization; downstream consumers (e.g. brief generator) reading the same CSV would need similar treatment |

The tracker code itself was not modified — its current writes are already in canonical form. The fix is one localized normalization at the dashboard's CSV consumer, with a clean docstring explaining the legacy reason.

If the brief generator or any other consumer ever reads `snapshots.csv` directly, it should import `_normalize_bot_id` (or duplicate the 5-line logic) — TODO surfaced in §6.

## §4 Validation

After applying the fix, ran `services.dashboard.state_builder.build_and_save_state()`:

| Metric | Pre-fix | Post-fix | Operator actual | Match |
|--------|---------|----------|------------------|-------|
| `shorts.total_btc` | −2.241 | **−1.296** | −1.296 | ✅ |
| `shorts.active_bots` count | 8 | **4** | 4 | ✅ |
| `net_btc` | −1.2935 | −1.2935 | (matches state_latest.exposure) | ✅ (was already from a separate path) |

The 4 unique SHORT bots post-fix:
- `TEST_1` (`5196832375`) → −0.22 BTC
- `TEST_2` (`5017849873`) → −0.22 BTC
- `4524162672` (`TEST_3`, no formal alias) → −0.22 BTC
- `6399265299` (`SHORT_1.1%`, no formal alias) → −0.636 BTC

Sum: **−1.296 BTC** — matches operator's confirmed reality.

The `net_btc` was already correct pre-fix because it comes from `state_latest.json::exposure`, which is built by a different code path (not `_build_positions`). This is why the dashboard had `shorts.total_btc = -2.241` AND `net_btc = -1.2935` simultaneously — internally inconsistent. Post-fix the two agree.

## §5 Tests added

`core/tests/test_position_dedup.py` — 13 tests:

| Category | Test count | Covers |
|----------|-----------|--------|
| `_normalize_bot_id` unit | 4 | dot-zero strip, clean passthrough, alphanumeric guard, empty/None |
| `_read_csv_latest_by_bot` dedup | 6 | legacy+modern merge, same-ts dedup, distinct ids preserved, empty/missing file, latest-by-ts wins |
| `_build_positions` invariants | 2 | net_btc consistency, empty input |
| **Regression** | 1 | Reproduces the production scenario exactly: 8 entries → 4 unique → -1.296 BTC |

Total project tests after this TZ: **235/235 green** (was 222, +13).

## §6 Follow-up TODOs (not this TZ, surfaced for backlog)

1. Audit other consumers of `snapshots.csv` for the same `.0` issue:
   - `services/decision_log/event_detector.py` (uses `bot_id` from snapshots indirectly via `state_latest`)
   - Any backtest harness or script that reads snapshots.csv directly
   - Search: `grep -rn "snapshots.csv\|bot_id" services/ scripts/`
2. Consider one-time CSV cleanup script that rewrites legacy `.0` rows to canonical form, with a backup. Low priority since the consumer-side fix is complete and idempotent.
3. Add a `_normalize_bot_id`-equivalent helper to `services/bot_registry/resolver.py` if it doesn't already handle this — the registry already does this via `gid.rstrip(".0")` in `migrate_bot_ids.py`, but worth checking the resolver's `resolve_to_uid` path explicitly.

## §7 Anti-drift held

- ✅ No GinArea API integration code touched
- ✅ No forecast / regime / sizing logic touched
- ✅ No new positions data sources added
- ✅ No "manual override" — fix is at the aggregation layer, addressing the root cause

---

## Appendix A — Reproducing

The regression test `test_regression_legacy_plus_modern_short_bots` in `core/tests/test_position_dedup.py` reproduces the exact production scenario in a controlled way: write 4 bots in legacy `.0` format with old ts + same 4 bots in modern format with new ts, run `_read_csv_latest_by_bot` + `_build_positions`, assert sum equals `-1.296`. Run:

```
python -m pytest core/tests/test_position_dedup.py::test_regression_legacy_plus_modern_short_bots -v
```
