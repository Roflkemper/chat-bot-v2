# Forecast Model Replacement — Final Decision

**Date:** 2026-05-10
**Status:** RESEARCH COMPLETE → DECISION: do NOT replace forecast model

## Background

Two parallel research efforts (2026-05-05) investigated whether a new forecast
model could achieve operator's target Brier score < 0.22 with positive
resolution component. The decommissioned model had Brier 0.2569.

- Claude worker: `FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md` §5
- Codex worker: `FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md`

## Verdict (from §5 "Realistic assessment")

| Outcome | Probability under best path |
|---|:---:|
| Brier < 0.22 (target) | **5-20%** |
| Brier 0.220-0.244 (useful slight skill) | **30-55%** |
| Brier 0.245-0.249 (near baseline) | **30-50%** |
| Brier ≥ 0.250 (no improvement) | **10-30%** |

**Key insight:** rigorous walk-forward research on BTC direction prediction
ceiling at 52-58% accuracy out-of-sample after costs, equivalent to Brier
0.245-0.249. Operator's target of < 0.22 puts us in the **top decile** of
peer-reviewed crypto-direction literature. Not impossible, but
disproportionate effort vs payoff.

## Decision: DO NOT BUILD

Reasons:

1. **Regulation works without forecast.** `REGULATION_v0_1_1` regime-conditional
   activation is independent of forecast input. Removing the forecast
   doesn't break decision layer.
2. **3-month calendar investment** for likely slight-skill improvement (PF
   bump similar in magnitude to one threshold tweak in `grid_coordinator`).
3. **Higher-leverage alternatives exist:**
   - GC-confirmation gating (already done, +137 boosted / 63 blocked per 90d)
   - Calibration of existing detectors (short_rally_fade: PF 0.54 → 1.53)
   - confluence triple analysis (C2)
4. **Position cleanup, live deployment, ginarea integration** consume
   calendar capacity better.

## When to revisit

Reopen this decision IF:

- A clearly-validated reproducible architecture appears in literature
  (independent replication of >70% directional accuracy with rigorous
  walk-forward).
- Order-flow imbalance / LOB data becomes available locally with sufficient
  history for training.
- The operator explicitly wants to allocate 1-3 months calendar time to
  forecast work specifically.

## Closed: 2026-05-10

This document supersedes the open status of the forecast TZ. Both research
docs remain as historical record.
