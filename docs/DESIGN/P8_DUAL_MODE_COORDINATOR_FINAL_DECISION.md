# P8 Dual-Mode Coordinator — Final Decision

**Date:** 2026-05-10
**Status:** DESIGN COMPLETE → DECISION: **decompose into 4 mini-TZs, schedule one per session**

## What is P8

Greenfield design (`P8_DUAL_MODE_COORDINATOR_v0_1.md`, ~400 lines) for a
central coordinator that:
- Decides every minute which bots run/pause/close based on regime + indicator
  events + portfolio state.
- Issues GinArea API actions to make reality match the decision.
- Tracks Stage A/B/C ensemble plan: 1 bot → 3 → full ensemble.

## Why not one-shot

§8 "Validation plan" requires:
- Bot config catalog with 12+ bot variants
- State machine with 5 states + 11 transitions
- Position-level guards (per-bot + cumulative + margin)
- Lifecycle operations (startup/pause/restart/coordinator-restart)
- 7 days dry-run before real deployment

Too large for one session. Risk of incomplete pieces being half-merged.

## Decomposition: 4 mini-TZs

### Mini-TZ P8.1 — Bot config catalog (1 session)

- Implement `BotConfig` dataclass per §4 schema
- Load catalog from `config/p8_bots.yaml`
- Tests: catalog loads, validates fields, missing fields = error

### Mini-TZ P8.2 — State machine (1 session)

- Implement `BotState` enum (DESIRED_ACTIVE / DESIRED_PAUSED / etc.)
- Per §3 transitions table: 11 transitions, each pure function
- Tests: each transition works, invalid transitions raise

### Mini-TZ P8.3 — Position guards (1 session)

- Per-bot guards (entry size, max position)
- Cumulative guards (total exposure, margin floor)
- Tests: guards trigger when expected

### Mini-TZ P8.4 — Lifecycle + coordinator main loop (1-2 sessions)

- Startup/pause/restart procedures
- Coordinator restart safety (resume from state file)
- 7-day dry-run mode (logs decisions, doesn't call API)
- Tests: full cycle simulation

## Decision: SCHEDULE P8.1 NEXT

Start with **Mini-TZ P8.1 — Bot config catalog** as foundation.

The other parts of P8 (state machine, guards) consume the catalog and can
be built only after it exists.

## Status of dependencies

- ✅ Block 7 (range detection): exists in `services/regime_classifier.py`
- ✅ Block 6 (bot inventory): exists as `BOTS` dict in
      `tools/_backtest_combined_all_bots_v2.py` — can be lifted to YAML
- ✅ Blocks A/B (registry + regime periods): research done
- ✅ CP24/CP28 (regime overlay): research done

All prerequisites are satisfied. Implementation can start anytime.

## Closed: 2026-05-10 (decomposed; not closed in implementation sense)

When P8.1 starts, this document remains as the index. Each mini-TZ gets
its own implementation doc when complete.
