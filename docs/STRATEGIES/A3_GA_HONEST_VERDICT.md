# A3 — GA on 1h with HONEST fees verdict

**Date:** 2026-05-10
**Engine:** existing GA (`tools/_genetic_detector_search.py`) with new `GA_HONEST_FEE=1` flag
**Old fees:** 2 × 0.05% taker = 0.10% round-trip
**New fees:** maker rebate -0.0125% IN + (taker 0.075% + slippage 0.02%) OUT = **0.165% round-trip** (65% more conservative)

## Quick A/B run (200 evals)

| Run | Best fitness | Best verdict | STABLE / MARGINAL / OVERFIT |
|---|---:|:---:|---:|
| Old fees (Stage E1, 819 evals) | 5.62 | STABLE × 28 | 28 / 264 / 527 |
| **Honest fees (this A3, 147 evals)** | **2.14** | MARGINAL | 0 / 1 / 146 |

## What this means

The "best" genome at honest fees is a single MARGINAL hit (PF≈1.5 on 2/4 folds).
**Zero STABLE genomes survive** the realistic cost model.

This is identical to the A1 finding (all 14 manually-coded detectors OVERFIT
on the honest engine). The library of 1h-resolution mean-revertion / fade
detectors does not have positive expectancy after realistic fees.

## Why only 147 evals reported but 200 expected?

GA caches identical genomes — duplicate hashes are skipped. 147 unique
genomes were evaluated; the remaining 53 evaluation slots hit cache.

## Recommendation

**Don't promote any honest-GA genome to paper/live.** Fitness 2.14 with PF on
2/4 folds is not enough signal to trust — could be one good fold + 3 break-even.

Path forward (consistent with A1 conclusion):
1. **Don't search 1h for fade-style detectors** — the universe is depleted.
2. **Look at intraday/tick-resolution patterns** (A2 in progress) — they are
   harder to overfit because the search space is huge but real microstructure
   constraints exist.
3. **Calibration approach** (grid_coordinator success) beats search: hand-built
   indicator with operator's domain knowledge + threshold tuning to current
   market regime. We got 9/12 operator-named extrema with 0 FALSE positives.

## Reproduction

```
GA_HONEST_FEE=1 python tools/_genetic_detector_search.py \
  --population 20 --generations 10 --output state/ga_honest_results.jsonl
```

For full GA (5000 evals × 4-fold) expect 6-12h compute.
