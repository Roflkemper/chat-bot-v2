# Regime Overlay v3 — Final Decision

**Date:** 2026-05-10
**Status:** RESEARCH COMPLETE → DECISION: **BLOCKED on data availability**

## What was investigated

`REGIME_OVERLAY_v3.md` analysed whether splitting backtest runs into
quarterly/monthly sub-windows can reveal regime-conditional bot behavior
("does Bot X behave differently in MARKUP vs MARKDOWN vs RANGE within a
single window?").

## Verdict from §6 of v3 research

**Mathematically infeasible** with current data:

> Hours-proportional sub-window allocation is **algebraically identical** to
> direct year-level allocation. The sub-window split cannot — by
> construction — produce different per-hour PnL across sub-windows.

> M1 is the asymptotic ceiling — no amount of sub-window slicing can
> extract regime-conditional PnL signal that wasn't in the source.

## What unblocks this

True regime-conditional analysis (M2) requires one of:

1. **Bar-level trade logs from GinArea** with entry/exit timestamps + realized PnL per trade.
2. **Hourly equity curve dumps** per run: `(timestamp, cumulative_pnl)` series.
3. **Per-event metadata**: indicator activations, instop hits, grid fills with timestamps.

Without any of (1)/(2)/(3), no analytical method can extract per-regime PnL.

## Decision: WAIT

- **Operator action needed:** check if GinArea API exposes trade logs or
  equity curves. If yes — open new TZ to ingest into `state/`.
- **Until then:** treat regime classification as feature only (used in
  GC-confirmation, paper trader entry filters), not as PnL-attribution tool.

## When to revisit

When GinArea trade logs are accessible.

## Closed: 2026-05-10
