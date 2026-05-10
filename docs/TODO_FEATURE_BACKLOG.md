# Feature backlog (open TODOs)

Single source of truth for inline TODOs that should become tickets.
Audited 2026-05-11.

## TODO-1: Forward analysis — track price at projection time

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

## TODO-3: Regime red-green actual holdout metrics

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

## Closed TODOs (audited and dismissed)

- `advisor_v2.py:40 TODO(reuse): clustering reimplements DedupLayer` —
  examined; the reimplementation is intentional for advisor_v2's
  different bucketing semantics (per-side vs per-setup). Not actually
  duplicate. Leaving inline note.
