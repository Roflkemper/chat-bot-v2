# TEST_3 TP-flat simulators — RETIRED (2026-05-11)

## Status

Both simulators removed from `app_runner.py` all_tasks. Service code
preserved at:
- `services/test3_tpflat_simulator/`
- `services/test3_tpflat_b_simulator/`

State files (gitignored, keep last):
- `state/test3_tpflat_paper.jsonl` — last write 2026-05-09T11:08 OPEN, never closed
- `state/test3_tpflat_b_paper.jsonl` — last write 2026-05-09T16:00 OPEN, never closed

## Why retired

Designed 2026-05-09 as a 7-day paper run to test "SHORT-fade-the-trend"
with flat TP ($10 / $5 USD) and 3% dd cap.

Gate: `EMA50>EMA200 AND close>EMA50` on 1h (uptrend) → open SHORT.
Idea: small TP catches micro-pullbacks within trend.

**Outcome after 2 days:** zero CLOSE events. Each simulator opened
once on 2026-05-09 and kept the position open through 2 days of
continued uptrend — TP never hit, DD cap not reached.

## Diagnosis

- TP_USD = $10 on $1000 size = 1% downside needed. In trending up
  market with low pullback amplitude, even 1m candles don't hit it
  frequently — and over hours/days the TP target drifts further away
  as `entry` was set early.
- No timeout / hold cap. Position can live indefinitely.
- DD cap of 3% would have rescued it, but trend hasn't been strong
  enough to trigger that either.

## What to do if revisiting

Don't fix this implementation. Build a fresh prototype with:
1. **Anchored TP relative to current price**, not entry — moving target
   so position respects current level.
2. **Time cap** (e.g. 4h max hold) to free up the slot for next fade.
3. **Re-entry gate** that requires the price to have moved up from
   prev entry before opening another short.
4. Multi-asset (BTC/ETH/XRP) per `P15_PAIR_SIZE_FACTOR` pattern.

Or simply: P-15 SHORT (already validated 6/6 CONFIRMED at PF 3+) is
the working SHORT-fade strategy. TEST_3 TP-flat duplicates intent at
lower edge. Probably no reason to revive.

## Code references

- `app_runner.py` line ~617 — removed `_run_test3_tpflat_simulator`
  and `_run_test3_tpflat_b_simulator` async helpers (kept retirement
  comment).
- `app_runner.py` line ~725 — removed both task creations from
  all_tasks tuple.
- Original wire-in: TZ-D ADVISOR night batch 2026-05-09.

## Backlog reference

This closes TODO-4 in `docs/TODO_FEATURE_BACKLOG.md`.
