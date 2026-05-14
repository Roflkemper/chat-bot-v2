# REGIME OVERLAY V3 — multi-window analysis

**Date:** 2026-05-05
**TZ:** TZ-REGIME-OVERLAY-V3-MULTI-WINDOW
**Goal:** Address F-E flag from `REGIME_OVERLAY_v2` (single-window M1 collapse) by splitting long-window runs into quarterly (1y) or monthly (3M) sub-windows.

**Driver:** [`scripts/_regime_overlay_v3.py`](../../scripts/_regime_overlay_v3.py)
**Raw output:** [`_regime_overlay_v3_raw.json`](_regime_overlay_v3_raw.json)
**Compute:** ~1.7 s.

---

## Feasibility verdict: **PARTIAL** — methodologically sound for sub-window regime composition, **infeasible** for true within-pack regime sensitivity validation. See §6 for what real M2 needs.

---

## §1 Methodology

### Split rule
- **1y runs (A1, A3, C1-clean, C2-clean, C3):** quarterly split, 90-day chunks.
- **3M runs (A2, A4, D-NoStop, D-WithStop, E-T0.25..0.50, BT-014..017):** monthly calendar split.

### Per sub-window
1. Intersect sub-window with hourly regime index → covered hours.
2. Count regime hours within → `(h_RANGE, h_MARKUP, h_MARKDOWN)`.
3. Classify dominant regime: any regime > 50 % of covered hours → `R_DOMINANT`; else `MIXED`.
4. **Hours-proportional sub-window PnL** (M1 at sub-window level):
   ```
   m1_subwindow_pnl = total_run_pnl × (sub_covered_hours / run_total_covered_hours)
   m1_per_hour      = m1_subwindow_pnl / sub_covered_hours = total_run_pnl / run_total_covered_hours
   ```

### Critical mathematical observation
Hours-proportional sub-window allocation is **algebraically identical** to direct year-level allocation. Splitting a run into sub-windows and re-aggregating returns the same numbers as the direct M1 calc in `REGIME_OVERLAY_v2`:

> `m1_per_hour` is the **same constant** in every sub-window of a given run.

This driver therefore cannot — by construction — produce different per-hour PnL across sub-windows of the same run. The only thing the split can reveal is **regime-mix variation** across sub-windows. The PnL allocation itself contains zero new information vs v2.

### Why volume-proportional was not used either
The brief proposed an alternative: assume PnL distributes proportionally to **volume in sub-window**. That would require **per-sub-window volume**, which is not in the source data — only **per-run total volume** is reported. So volume-proportional has the same single-number limitation.

### What this driver actually delivers
1. A regime-composition table per sub-window (RANGE / MARKUP / MARKDOWN hour fractions).
2. A dominance classification per sub-window.
3. M1-implied per-hour PnL per sub-window — included as numerical proof of the constant-per-hour artifact.
4. An aggregate "by regime-dominant class" view per Pack — which collapses to a single class in this dataset (see §3).

---

## §2 Per-run sub-window detail

### Sample 1y run (A1, quarterly split)
| Sub-window | Cov h | RANGE | MARKUP | MARKDOWN | Dominant | M1 sub-pnl (USD) | M1 per-hour |
|---|---:|---|---|---|---|---:|---:|
| 2025-05-05 → 2025-08-03 | 2 160 | 1 723 (80 %) | 263 (12 %) | 174 (8 %) | RANGE | +2 215.51 | +1.026 |
| 2025-08-03 → 2025-11-01 | 2 160 | 1 648 (76 %) | 228 (11 %) | 284 (13 %) | RANGE | +2 215.51 | +1.026 |
| 2025-11-01 → 2026-01-30 | 2 160 | 1 554 (72 %) | 218 (10 %) | 388 (18 %) | RANGE | +2 215.51 | +1.026 |
| 2026-01-30 → 2026-04-30 | 2 160 | 1 287 (60 %) | 410 (19 %) | 463 (21 %) | RANGE | +2 215.51 | +1.026 |
| 2026-04-30 → 2026-05-06 (tail) | 25 | 25 (100 %) | 0 | 0 | RANGE | +25.65 | +1.026 |

⚠ M1 per-hour is **identical across all sub-windows**, demonstrating the algebraic point in §1. The regime composition does vary meaningfully across quarters: RANGE drops from 80 % in 2025 Q3 to 60 % in 2026 Q1, while MARKDOWN rises from 8 % to 21 %.

### Sample 3M run (BT-014, monthly split)
| Sub-window | Cov h | RANGE | MARKUP | MARKDOWN | Dominant |
|---|---:|---|---|---|---|
| 2026-02-05 → 2026-03-01 | 576 | 304 (53 %) | 105 (18 %) | 167 (29 %) | RANGE |
| 2026-03-01 → 2026-04-01 | 744 | 422 (57 %) | 163 (22 %) | 159 (21 %) | RANGE |
| 2026-04-01 → 2026-05-01 | 720 | 531 (74 %) | 133 (18 %) | 56 (8 %) | RANGE |
| 2026-05-01 → 2026-05-03 (tail) | 1 | 1 (100 %) | 0 | 0 | RANGE |

(All 17 runs are in `_regime_overlay_v3_raw.json` → `per_run[*].subwindows`.)

---

## §3 Pack-level synthesis

### Sub-window dominance counts
Across all 17 runs and all sub-windows:
- **RANGE_DOMINANT:** 70 sub-windows.
- **MARKUP_DOMINANT:** 0.
- **MARKDOWN_DOMINANT:** 0.
- **MIXED:** 0.

**Every single sub-window in the dataset is RANGE-dominant** (>50 % RANGE hours). RANGE share ranges from 53 % (BT-014 month 1) to 100 % (tiny tails) across sub-windows; the *minimum* RANGE share in any non-trivial sub-window is 53 %.

This means:
- The dominance-class aggregation collapses to a single class (`RANGE_DOMINANT`) for every Pack.
- The original goal — comparing PnL across regime-dominant quarters within a Pack — **cannot be operationalized** because there are no MARKUP- or MARKDOWN-dominant sub-windows to compare to.

### Per-Pack RANGE_DOMINANT aggregate
| Pack | Unit | n sub-windows | Σ hours | Σ M1 sub-pnl | M1 per-hour |
|---|---|---:|---:|---:|---:|
| A | USD | 17 | 21 506 | +12 180.99 | +0.5664 |
| BT | BTC | 16 | 8 164 | +0.25785 | +3.158e-5 |
| C | BTC | 15 | 25 992 | -0.34081 | -1.311e-5 |
| D | USD | 6 | 4 272 | -3 085.00 | -0.7221 |
| E | BTC | 16 | 8 164 | +0.38930 | +4.769e-5 |

These aggregates are identical to `REGIME_OVERLAY_v2` §3 totals (modulo rounding) — confirming the algebraic identity between sub-window split and direct allocation.

---

## §4 What this analysis does reveal

Although the M1-per-hour artifact prevents within-pack regime *sensitivity* extraction, the sub-window split does surface a **temporal** structural finding that REGIME_OVERLAY_v2 obscured:

### Regime composition varies across quarters but stays RANGE-heavy
The 1y window has structural seasonality:
- 2025 Q3: 80 % RANGE, 12 % MARKUP, 8 % MARKDOWN — most range-heavy.
- 2026 Q1: 60 % RANGE, 19 % MARKUP, 21 % MARKDOWN — most balanced.

Even the most-balanced quarter is still RANGE-dominant. **No pure-trend quarter exists in 2025-2026 BTC at hourly resolution**. This is consistent with the 645-episode stat in `_regime_periods_raw.json` (mean episode 13.6 h — most quarters are a mosaic, not a single regime).

### Implication
The original framing — "find regime-dominant quarters and compare PnL across them" — **does not match the underlying regime structure** of the year. Even with raw hourly trade logs (M2), the comparison would be RANGE-vs-RANGE quarters with slightly different MARKUP/MARKDOWN ratios; you would not get a clean "MARKUP quarter" vs "MARKDOWN quarter" signal.

For the regime-sensitivity question to be answerable in this dataset, the comparison axis would need to drop the >50 % dominance criterion (e.g. compare quarters by raw MARKDOWN-share, treating it as a continuous covariate) or use a different chunking that better separates regimes (e.g. select hours by regime label across the whole year, not by calendar window).

---

## §5 Cross-Pack regime distribution comparison

Different Packs cover different time slices. Here is how the time-slice regime mixes compare:

| Pack | Window covered | RANGE % | MARKUP % | MARKDOWN % |
|---|---|---:|---:|---:|
| A (mix) | 2025-05-05 → 2026-05-05 (1y) for A1; 2026-02..05 (3M) for A2/A4 | 69.85 | 14.17 | 15.98 |
| C | 2025-05-05 → 2026-04-30 (1y) | 71.98 | 12.92 | 15.10 |
| D | 2026-02-01 → 2026-04-30 (3M) | 60.44 | 19.10 | 20.46 |
| E | 2026-02-05 → 2026-05-05 (3M) | 61.64 | 19.65 | 18.72 |
| BT | 2026-02-05 → 2026-05-02 (3M) | 61.64 | 19.65 | 18.72 |

(Numbers from `REGIME_OVERLAY_v2` per-run aggregates.)

The 3M packs (D, E, BT) all sit at ~60 % RANGE / ~20 % MARKUP / ~20 % MARKDOWN. The 1y packs (A, C) sit at ~70 % RANGE / ~13-14 % MARKUP / ~15-16 % MARKDOWN. These differences are **time-slice-driven**, not bot-driven — comparing E and BT performance is comparing two runs of similar bots over an identical time slice, not comparing bots across different regime conditions.

---

## §6 What true M2 within-pack regime sensitivity would require

To actually answer F-E ("does Bot X behave differently in MARKUP vs MARKDOWN vs RANGE within a single window?"), the following data is needed (in approximate decreasing order of value):

1. **Bar-level (1h or finer) trade logs from GinArea**, including:
   - Entry timestamp + price for each trade.
   - Exit timestamp + price for each trade.
   - Realized PnL per trade.
   - Optional: open position size at any timestamp (for unrealized-PnL hourly equity curve reconstruction).
2. **Or: hourly equity curve dumps**: a time-series of `(timestamp, cumulative_pnl)` per run, exported from GinArea.
3. **Or (weaker but useful): per-event metadata**: indicator activations, instop hits, grid fills with timestamps. Even without full trade logs, knowing *when* trades happened relative to regime labels would let us separate "regime during entry" from "regime during exit" effects.

Once any of (1)/(2) is available, M2 implementation is straightforward:
- Tag each hour of equity curve with its regime label.
- Per-regime PnL = sum of `Δ_equity` over hours where regime label == R.
- **This is genuine regime-conditional PnL**, not a time-share allocation.

Failing all three, **M1 is the asymptotic ceiling** — no amount of sub-window slicing can extract regime-conditional PnL signal that wasn't in the source.

### Rebate methodology gap (BTC packs)
A separate but related data gap was raised in `REGIME_OVERLAY_v2` §5 — post-rebate analysis for BTC packs needs an FX conversion methodology. That is independent of the M2 trade-log gap and would need a separate sub-TZ.

---

## §7 Caveats

1. **Hours-proportional ≡ direct M1 allocation.** The sub-window split does not extract new PnL signal. Numerical results from this driver match `REGIME_OVERLAY_v2` totals exactly (verified in §3).
2. **Volume-proportional was rejected at design time** because per-sub-window volume is not in source data. Reported here so the operator knows that approach was considered and discarded with reason.
3. **All sub-windows are RANGE-dominant in this dataset.** The original "compare regime-dominant quarters within a Pack" framing collapses to a single class; the framing does not match the data.
4. **Bullish year bias inherited** from REGIME_OVERLAY_v2 — every analysis here is on 2025-2026 data; conclusions about regime mix variation are dataset-specific.
5. **No claim of validating regime sensitivity made.** The driver explicitly produces `feasibility_verdict: "PARTIAL"` in the raw JSON.
6. **Compute well under 1.5 h cap** (~1.7 s actual).

---

## CP report

- **Output paths:**
  - [docs/RESEARCH/REGIME_OVERLAY_v3.md](REGIME_OVERLAY_v3.md)
  - [docs/RESEARCH/_regime_overlay_v3_raw.json](_regime_overlay_v3_raw.json)
  - [scripts/_regime_overlay_v3.py](../../scripts/_regime_overlay_v3.py)
- **Feasibility verdict: PARTIAL.**
  - **Feasible:** quarter/month sub-window regime-composition tables; documenting that all 70 sub-windows are RANGE-dominant.
  - **Infeasible:** within-pack regime sensitivity validation, because (a) per-sub-window PnL is not in the source data, (b) per-sub-window volume is not in the source data, (c) hours-proportional sub-window allocation is mathematically identical to the direct M1 allocation already in REGIME_OVERLAY_v2.
- **What's needed for true M2:**
  1. Bar-level GinArea trade logs (entry/exit timestamp + PnL per trade), OR
  2. Hourly equity curve dumps (`timestamp, cumulative_pnl`) per run, OR
  3. Per-event metadata (indicator hits, grid fills) with timestamps.
- **Compute time:** ~1.7 s (well under 1.5 h cap).

---

## References
- F-E flag source: [`REGIME_OVERLAY_v2.md`](REGIME_OVERLAY_v2.md) §6 / §7
- Regime episode statistics: [`_regime_periods_raw.json`](_regime_periods_raw.json)
- Driver: [`scripts/_regime_overlay_v3.py`](../../scripts/_regime_overlay_v3.py)
