# Feature backlog (open TODOs)

Single source of truth for inline TODOs that should become tickets.
Audited 2026-05-11.

## TODO-1: Forward analysis — track price at projection time [DONE 2026-05-11]

ForwardProjection now snapshots `price_at_projection` (commit pending).
Loop checks ±0.5% adverse move vs projected direction within 4h window;
emits `market_forward_analysis.forecast_invalidated` log line so daily
KPI can surface forecast degradation.

Tests added: `tests/services/market_forward_analysis/test_forward_projection.py`.

---

## TODO-1 (archived): Forward analysis — track price at projection time

**File:** [services/market_forward_analysis/loop.py:188](services/market_forward_analysis/loop.py#L188)

```python
pass  # TODO: track price at projection time for full invalidation check
```

**What's missing:** when a forward projection is made for a setup, we
don't snapshot the price at that moment. Without the snapshot, we can't
verify post-hoc whether the projection was invalidated (price moved
through key level) vs. simply elapsed.

**Effort:** ~2h. Add `price_at_projection` field to projection record;
on next tick compare current vs projection record's saved price.

**Priority:** medium — affects retrospective accuracy of forward
projections in the morning brief.

## TODO-2: Double-bottom breakout-confirmed entry

**File:** [services/setup_detector/double_top_bottom.py:323](services/setup_detector/double_top_bottom.py#L323)

```
# который входит ПОСЛЕ прорыва neckline (breakout-confirmed) — TODO
```

**What's missing:** current `detect_double_bottom_setup` enters at the
close BEFORE neckline breakout, which has WR 4.7% (TP touches but
slippage eats it). A breakout-confirmed variant would only emit after
price closes above neckline + holds for N bars.

**Effort:** ~1 day. Build new detect_double_bottom_breakout function,
backtest on 2y, wire into registry if PF >= 1.2.

**Priority:** low — current variant is already in HARD_BLOCK list
because of negative live precision; refactoring risks confusion.
Defer until live precision drops the existing variant entirely.

## TODO-3: Regime red-green actual holdout metrics [DONE 2026-05-11]

`_build_holdout_report(metrics, transition_acc, holdout_start, n_holdout)`
now renders real metrics — accuracy, per-class precision/recall,
confusion matrix, transition accuracy. `cmd_validate` predicts via
generated rules.py (loaded by importlib) or falls back to dominant-class
baseline when rules.py is absent.

---

## TODO-3 (archived): Regime red-green actual holdout metrics

**File:** [services/regime_red_green/runner.py:416](services/regime_red_green/runner.py#L416)

```python
report_content = _build_holdout_report()  # TODO: actual holdout metrics
```

**What's missing:** the red-green regime evaluation report renders a
stub instead of computing holdout-set classifier accuracy / precision
/ recall.

**Effort:** ~3h. Implement `_build_holdout_report()` that loads the
saved holdout split and computes confusion matrix + per-regime stats.

**Priority:** medium — regime classifier is critical input to many
downstream filters. Knowing if it drifts matters.

## TODO-4: test3_tpflat simulators — review or retire [DONE — RETIRED 2026-05-11]

**Decision:** retired. Both simulators removed from app_runner all_tasks.
Service code preserved on disk. See `docs/STRATEGIES/TEST3_TPFLAT_RETIRED.md`
for diagnosis + what-to-do-if-revisiting.

---

## TODO-4 (archived): test3_tpflat simulators — review or retire

**Files:**
- [services/test3_tpflat_simulator/loop.py](services/test3_tpflat_simulator/loop.py)
- [services/test3_tpflat_b_simulator/loop.py](services/test3_tpflat_b_simulator/loop.py)
- Output: `state/test3_tpflat_paper.jsonl` (last write 2026-05-09)
- Output: `state/test3_tpflat_b_paper.jsonl` (last write 2026-05-09)

**Status:** wired into app_runner as two parallel tasks. Last journal
writes >2 days ago — gate condition not firing. Each tick still does
poll work (60s loop), modest but non-zero cost.

**Decision needed:** either re-enable / re-validate, or retire if
experiment is concluded.

**Effort:** ~30 min to make a verdict — read both loops, check what
"flat TP" means in current data, compare against P-15. If retiring:
remove from app_runner all_tasks + delete service dirs + gitignore
state files (already gitignored).

**Priority:** low — costs 1 minute/tick of compute, nothing on fire.

## TODO-8: Watchdog 13 restarts/hour pattern — operator-induced, not bug

**Status:** investigated 2026-05-11. Not a bug.

**What looked suspicious:**
- 13 app_runner starts/hour in audit log
- check_restart_frequency.py flags >5/hour as anomaly
- App_runner / tracker / collectors die in lock-step (same count)

**Root cause:** every time the operator/Claude does
`python -c "p.terminate()"` to apply a code change, three things happen:
  1. app_runner + tracker + collectors all get terminated (children)
  2. Within 2min Task Scheduler runs watchdog
  3. Watchdog finds NOT RUNNING for all three → spawns each
  4. Audit records 3 `started` events

So each manual restart = 3 audit entries × ~5 restarts/day session
= ~15/day, matches the count.

**Not a problem because:**
- All starts succeed (no FAILED_TO_START events)
- No tracebacks in app.log
- Heartbeat continuous within each generation
- 5min crash interval matches the human-action cadence, not a periodic
  failure

**Action:** none. Pattern is by design.

**Future improvement (optional):** check_restart_frequency.py could
exclude restarts that happen within 30s of a watchdog tick (= operator-
triggered vs autonomous). Lowers false-positive alert noise.

---

## TODO-7: Watch short_mfi_multi_ga — DEGRADED candidate

**Live precision (2026-05-11):** N=9, exp=-0.32%, CI95 [-0.73, +0.13].
8/9 outcomes TIMEOUT, 1 SL. Direction wrong on uptrending market.

Status MARGINAL (not yet DEGRADED — CI straddles 0). At N=30 we'll
have decisive verdict. Until then leave enabled — accumulating sample
is the whole point.

Action: re-check on every `setup_precision_tracker` cron run.
If status flips to DEGRADED → add to `DISABLED_DETECTORS` like
short_pdh_rejection.

---

## TODO-6: Consolidate text-chunking helpers

**Duplicated:**
- `services/telegram_runtime.py` — `split_text_chunks()`, `_MAX_MESSAGE_LEN = 3800`
- `services/telegram_alert_service.py` — `_split_chunks()`, `_MAX_MESSAGE_LEN = 3800`

**Decision:** these split logic is non-trivial (handles \n\n blocks,
falls back to line-by-line, then char-by-char). Moving to a shared
module would be ~30 LOC + tests + risk of subtly different behavior.
Live in prod, both work — defer until next time someone touches
either.

**Effort:** ~1h with tests.
**Priority:** very low.

---

## TODO-5: ginarea_api tests missing pytest-httpx

**Files:** [tests/services/ginarea_api/test_client.py](tests/services/ginarea_api/test_client.py)

**Status:** 7 tests fail collection with `fixture 'httpx_mock' not found`.
Tests use `pytest-httpx` plugin which is not in requirements.txt.

**Effort:** ~5 min — add `pytest-httpx` to dev requirements, install,
re-run.

**Priority:** low — these are HTTP mock tests for ginarea retry logic.
Production code works; tests just can't run.

## Closed TODOs (audited and dismissed)

- `advisor_v2.py:40 TODO(reuse): clustering reimplements DedupLayer` —
  examined; the reimplementation is intentional for advisor_v2's
  different bucketing semantics (per-side vs per-setup). Not actually
  duplicate. Leaving inline note.
