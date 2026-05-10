# TRANSITION_MODE_COMPARE — Final Decision

**Date:** 2026-05-10
**Status:** RESEARCH COMPLETE → DECISION: adopt **Policy B-DR2 (G1=trend)** as the trial baseline; defer formal switch until live regime_shadow data accumulates 30 days.

## What was researched

`TRANSITION_MODE_COMPARE_v1.md` ranked 5 transition-mode policies on 17
historical backtests (G1+G2+G3+G4 cohorts, 1-year window):

| Policy | Mechanics | ΔPnL composite |
|---|---|---:|
| **B-DR2** | G1 = trend mode during transition | **#1** |
| **A** | Pause-all during transition | #2 |
| C | ×0.5 size during transition | #3 |
| B-DR1 | All-range, no carve-out | #4 (= baseline) |
| Baseline | No transition handling | ref |

## Caveats (from §6)

1. **TRANSITION share is 3× sanity range** — research-flag, may overstate effects.
2. **G4 is profitable cohort** — Policies A/C *reduce* G4 transitional gains.
3. **M1 hourly-uniform assumption** — real GinArea PnL is event-driven, not uniform.
4. **No M2 DD.** EXPOSURE proxy only.
5. **Bullish year bias** — 2025-2026 dataset; rankings may flip in bear year.

## Decision: ADOPT B-DR2 as TRIAL, MEASURE LIVE 30 DAYS

### Why B-DR2 (not A)
- B-DR2 wins composite ranking on BTC-denominated cohort.
- Policy A zeros all transitional PnL — too aggressive given G4's positive contribution.
- B-DR2 keeps G1 in trend mode (matches its actual behavior pattern), keeps others as-is.

### Why TRIAL not commit
- All quantitative caveats above.
- regime_shadow service (B3) is collecting parallel-classifier data starting
  2026-05-09. After 30 days we'll have direct empirical comparison instead
  of model-allocated PnL approximation.

### Implementation plan
- `services/decision_layer/regulation_v0_1_1.py` already has transition-mode
  support — confirm it routes G1 setups to trend-mode handler when
  `regime == TRANSITION`. If not, this is a small wire-up TZ.
- Track TRANSITION-window PnL separately in paper_trader audit.
- Re-evaluate after 30 days of regime_shadow data.

## Closed: 2026-05-10

This document supersedes the open-status of TRANSITION_MODE TZ. v1 research
remains as historical record.
