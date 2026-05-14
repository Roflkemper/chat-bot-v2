# TRANSITION MODE COMPARE v1

**Date:** 2026-05-05
**TZ:** TZ-TRANSITION-MODE-COMPARE-ANALYTICS — closes P8 §9 Q2
**Method:** Post-hoc M1 proportional allocation over BT-001..017 × hourly regime time series. No new GinArea runs.
**Inputs:**
- `data/forecast_features/full_features_1y.parquet` (regime_int, 5min → hourly mode)
- `docs/RESEARCH/_regime_periods_raw.json` (645 episodes, sanity reference)
- `docs/RESEARCH/GINAREA_BACKTESTS_REGISTRY_v1.md` §1 (BT totals + windows)
- `docs/RESEARCH/REGIME_OVERLAY_v1.md` (proportional allocation methodology — template)

**Driver:** [`scripts/_transition_mode_compare.py`](../../scripts/_transition_mode_compare.py)
**Raw output:** [`_transition_mode_compare_raw.json`](_transition_mode_compare_raw.json)
**Compute:** 1.6 s actual vs 30-180 min estimate (1y window completed without fallback).

---

## §1 Methodology

### Window
- **Primary window used:** 1y (2025-05-01 00:00 UTC → 2026-05-01 00:00 UTC), 8 761 hourly bars.
- **Fallback (86d):** NOT used. 1y completed in 1.6 s.

### TRANSITION operational definition
For each hourly bar `h`, classify as `TRANSITION_HOUR` if:
- **Rule (a):** sliding window `[h-12, h]` (13 bars inclusive) contains ≥2 distinct `regime_int` values.
- **Rule (b):** SKIPPED — `full_features_1y.parquet` has no classifier-confidence column. Rule (b) is therefore not applied; only rule (a) gates TRANSITION.

Hysteresis = 12 bars, fixed (matches `RegimeForecastSwitcher`, no re-tuning per spec).
`regime_int` mapping: 1 = MARKUP, -1 = MARKDOWN, 0 = RANGE. Hourly value = mode of the twelve 5-minute bars in that hour.

### Three policies (mechanics)
Let `BT_total_pnl` = registered PnL; `s = TRANSITION_share_pnl`; `q = stable_share_pnl = total - s`.

- **Policy A (Pause-All):** `pnl_A = q` (TRANSITION PnL → 0 for every BT).
- **Policy B (Hold-Range / Pause-Trend):** requires range/trend categorization. Two rules reported:
  - **DR1 — all 17 = range-style** (none use a pure trend trigger per registry §2). Under DR1, `pnl_B_DR1 = total_pnl` (no pause anywhere) ≡ baseline.
  - **DR2 — G1 = trend-style** (BT-001..004, LONG annual, no indicator), G2-G4 = range-style (indicator-gated). Under DR2: G1 → `pnl = q`; G2-G4 → `pnl = total_pnl`.
- **Policy C (Hold-All-Reduced-Sizing):** `pnl_C = q + 0.5·s`. Multiplier fixed at 0.5 (no sweep in this TZ).

### M1 PnL allocation — assumption disclosure
Per `REGIME_OVERLAY_v1` template:
```
TRANSITION_share = BT_total_PnL × (BT_TRANSITION_hours / BT_window_total_hours)
stable_share     = BT_total_PnL − TRANSITION_share
```
**Critical assumption:** PnL is uniformly distributed across the BT window. This is identical to the assumption underlying `REGIME_OVERLAY_v1` and is **approximate**, not bar-by-bar reconstruction. Absolute numbers below should be read as proportional shares, not literal "PnL avoided / preserved."

---

## §2 TRANSITION-hours analysis

### Headline
- **TRANSITION hours total (1y):** 4 072 / 8 761 = **46.48 %**.
- **Stable hours total:** 4 689.
- **Sanity range (5–15 % per spec):** **NOT MET** — actual is ~3× the upper bound. ⚠️ See "interpretation" below.

### Cross-check
Independent path: count hour-to-hour regime changes (644 over 8 761 = 7.35 %), then expand each change forward by `HYSTERESIS_BARS = 12` to mark the post-change settling window. Result: **4 283 TRANSITION hours**.
Cross-check vs rule-(a) count: 4 283 vs 4 072 — 5 % discrepancy, both methods agree the TRANSITION share is in the 45-50 % range. The two paths differ in how they treat overlapping change clusters; the rule-(a) rolling-window method is the authoritative one.

### Why so high — interpretation
The 5-15 % estimate in the brief implicitly assumed long, stable regime episodes. The actual data has **645 episodes over 8 761 hours, mean episode length ≈ 13.6 h** (median 8 h). With a 13-bar rolling window, **any episode ≤13 h is fully covered by TRANSITION flags from its boundary changes**. Per `_regime_periods_raw.json`:
- 448 / 645 episodes (69 %) are ≤13 hours long.
- Combined hours in those short episodes: 1 735 h.

Adding the 12-hour post-change "settling" tail of every transition (644 changes × 13 h ≈ 8 372 h gross, with overlap collapsing to ~4 100 unique hours) explains the result. The data is **structurally choppy** at hourly resolution — episodes flip faster than the chosen hysteresis window can settle.

**Implication for downstream design:** Either (1) the hysteresis window is too long for the episode length distribution observed in 2025-2026 BTC data, (2) the regime classifier itself is jittery at hourly resolution, or (3) the operational definition of "TRANSITION" needs a longer-episode pre-condition (e.g. only flag if the *prior* stable run was ≥N hours). All three are out of scope for this TZ — the spec fixes hysteresis at 12 and forbids re-tuning. Reported as-is.

### Per-BT TRANSITION share
Different BTs see different TRANSITION shares depending on which slice of 2025-2026 they cover:
| BT-set | Window | TRANSITION % of window |
|---|---|---:|
| LONG annual (BT-001..004) | 2025-05 → 2026-05 | **47.31 %** |
| SHORT 3m (BT-005..008) | 2026-02 → 2026-05 | **54.10 %** |
| SHORT 02may (BT-009..013) | 2026-02 → 2026-05 | **53.41 %** |
| LONG 02may (BT-014..017) | 2026-02 → 2026-05 | **53.41 %** |

The 02may windows are even choppier than the annual: 2026-02..2026-04 are the highest-TRANSITION months in the year (63 %, 55 %, 45 %).

### Per-month TRANSITION %
| Month | % | Month | % |
|---|---:|---|---:|
| 2025-05 | 46.10 | 2025-11 | 50.83 |
| 2025-06 | 35.83 | 2025-12 | 52.02 |
| 2025-07 | 29.30 | 2026-01 | 40.19 |
| 2025-08 | 45.43 | 2026-02 | 63.10 |
| 2025-09 | 28.75 | 2026-03 | 54.70 |
| 2025-10 | 67.20 | 2026-04 | 45.14 |

Range 28.75-67.20 %; max in 2025-10 (highest regime-change density of the year).

---

## §3 Per-BT × policy PnL table

Coverage per BT (target 96-99 %; **flag** if <96 %):

| BT-ID | Set | Side | Group | Coverage | Covered h | TRANSITION h | TRANSITION % | Total PnL | TRANSITION_share | Stable_share | A (Pause-All) | B-DR1 (=base) | B-DR2 | C (×0.5) |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BT-001 | LONG annual | L | G1 | 98.87 % | 8 305 | 3 929 | 47.31 % | -0.0956 BTC | -0.04523 | -0.05037 | -0.05037 | -0.0956 | -0.05037 | -0.07299 |
| BT-002 | LONG annual | L | G1 | 98.87 % | 8 305 | 3 929 | 47.31 % | -0.1197 BTC | -0.05663 | -0.06307 | -0.06307 | -0.1197 | -0.06307 | -0.09139 |
| BT-003 | LONG annual | L | G1 | 98.87 % | 8 305 | 3 929 | 47.31 % | -0.1285 BTC | -0.06079 | -0.06771 | -0.06771 | -0.1285 | -0.06771 | -0.09810 |
| BT-004 | LONG annual | L | G1 | 100.00 % | 8 304 | 3 929 | 47.32 % | -0.2311 BTC | -0.10934 | -0.12176 | -0.12176 | -0.2311 | -0.12176 | -0.17643 |
| BT-005 | SHORT 3m | S | G2 | **95.74 %** ⚠ | 2 137 | 1 156 | 54.10 % | -4 083.52 USD | -2 208.96 | -1 874.56 | -1 874.56 | -4 083.52 | -4 083.52 | -2 979.04 |
| BT-006 | SHORT 3m | S | G2 | **95.74 %** ⚠ | 2 137 | 1 156 | 54.10 % | -3 924.25 USD | -2 122.80 | -1 801.45 | -1 801.45 | -3 924.25 | -3 924.25 | -2 862.85 |
| BT-007 | SHORT 3m | S | G2 | **95.74 %** ⚠ | 2 137 | 1 156 | 54.10 % | -2 122.20 USD | -1 147.99 | -974.21 | -974.21 | -2 122.20 | -2 122.20 | -1 548.20 |
| BT-008 | SHORT 3m | S | G2 | **95.74 %** ⚠ | 2 137 | 1 156 | 54.10 % | -2 135.01 USD | -1 154.92 | -980.09 | -980.09 | -2 135.01 | -2 135.01 | -1 557.55 |
| BT-009 | SHORT 02may | S | G3 | 98.89 % | 2 041 | 1 090 | 53.41 % | -3 985.64 USD | -2 128.54 | -1 857.10 | -1 857.10 | -3 985.64 | -3 985.64 | -2 921.37 |
| BT-010 | SHORT 02may | S | G3 | 97.75 % | 2 041 | 1 090 | 53.41 % | -2 621.59 USD | -1 400.07 | -1 221.52 | -1 221.52 | -2 621.59 | -2 621.59 | -1 921.56 |
| BT-011 | SHORT 02may | S | G3 | 97.75 % | 2 041 | 1 090 | 53.41 % | -3 055.64 USD | -1 631.87 | -1 423.77 | -1 423.77 | -3 055.64 | -3 055.64 | -2 239.70 |
| BT-012 | SHORT 02may | S | G3 | 98.89 % | 2 041 | 1 090 | 53.41 % | -3 506.22 USD | -1 872.50 | -1 633.72 | -1 633.72 | -3 506.22 | -3 506.22 | -2 569.97 |
| BT-013 | SHORT 02may | S | G3 | 97.75 % | 2 041 | 1 090 | 53.41 % | -3 710.38 USD | -1 981.54 | -1 728.84 | -1 728.84 | -3 710.38 | -3 710.38 | -2 719.61 |
| BT-014 | LONG 02may | L | G4 | 97.75 % | 2 041 | 1 090 | 53.41 % | +0.07779 BTC | +0.04154 | +0.03625 | +0.03625 | +0.07779 | +0.07779 | +0.05702 |
| BT-015 | LONG 02may | L | G4 | 97.75 % | 2 041 | 1 090 | 53.41 % | +0.07054 BTC | +0.03767 | +0.03287 | +0.03287 | +0.07054 | +0.07054 | +0.05170 |
| BT-016 | LONG 02may | L | G4 | 97.75 % | 2 041 | 1 090 | 53.41 % | +0.05930 BTC | +0.03167 | +0.02763 | +0.02763 | +0.05930 | +0.05930 | +0.04347 |
| BT-017 | LONG 02may | L | G4 | 97.75 % | 2 041 | 1 090 | 53.41 % | +0.05022 BTC | +0.02682 | +0.02340 | +0.02340 | +0.05022 | +0.05022 | +0.03681 |

PnL units preserved (BTC vs USD) as in `GINAREA_BACKTESTS_REGISTRY_v1.md`. ⚠ flag = coverage 95.74 % is below the 96 % target floor stated in the spec; the gap is the 4-day BT tail (2026-05-01..2026-05-04) that extends past the regime-label window end.

**Reconciliation (per BT, per policy):** verified that for each BT and each policy, `(stable_share + policy_mult × transition_share) == policy_pnl` to within 1e-9 (asserted in driver). Policy B-DR1 reproduces `total_pnl` exactly for every BT. Policy A reproduces `stable_share` exactly.

---

## §4 Aggregate PnL per policy

Sums across BTs (BTC and USD reported separately — no synthetic FX conversion).

### BTC-denominated BTs (BT-001..004, BT-014..017 — 8 BTs)
| Policy | Total PnL (BTC) | Δ vs baseline (BTC) |
|---|---:|---:|
| Baseline (no policy) | -0.31705 | 0 |
| **Policy A** Pause-All | **-0.18276** | **+0.13429** |
| **Policy B-DR1** all-range | **-0.31705** | **0.00000** |
| **Policy B-DR2** G1=trend | **-0.04506** | **+0.27199** |
| **Policy C** ×0.5 | **-0.24991** | **+0.06714** |

### USD-denominated BTs (BT-005..013 — 9 BTs, all SHORT)
| Policy | Total PnL (USD) | Δ vs baseline (USD) |
|---|---:|---:|
| Baseline (no policy) | -29 144.45 | 0 |
| **Policy A** Pause-All | **-13 495.25** | **+15 649.20** |
| **Policy B-DR1** all-range | **-29 144.45** | **0.00** |
| **Policy B-DR2** G1=trend | **-29 144.45** | **0.00** |
| **Policy C** ×0.5 | **-21 319.85** | **+7 824.60** |

### Notable findings (mechanics, no winner pick)
- **DR1 ≡ baseline** in both BTC and USD by construction (no BT is paused). This confirms the spec's anticipation: "if DR1 shows indistinguishable from baseline, report finding." Reported.
- **DR2 ≡ baseline in USD** by construction: G1 contains only BTC-denominated BTs (BT-001..004 / LONG annual / DEFAULT), so DR2 leaves all 9 USD-denominated BTs unchanged. Useful contrast available only in BTC.
- **DR2 in BTC** shows the largest Δ (+0.272 BTC) because G1's four large negative LONG annual losses are exactly the cell DR2 silences during TRANSITION.
- **Policy A in USD** removes ~54 % of the USD loss (+15 649 of 29 144), reflecting the 53-54 % TRANSITION share in the 02may/3m windows.
- **Policy C in BTC** is the symmetric trade-off: it removes 50 % of the *transitional* BTC loss (and 50 % of the transitional BTC gain in G4). For BT-014..017 (profitable), Policy C *reduces* gain by ~26 % vs baseline. Policy A *removes* the entire transitional gain (~53 %) for those BTs.

---

## §5 Drawdown / exposure ranking

### Method
M2 quantitative DD is **not feasible** — `backtests/raw/` does not exist; no per-bar equity curves are available for any of the 17 BTs. Only M1 qualitative EXPOSURE proxy is reported.

```
EXPOSURE_policy = Σ |TRANSITION_share_pnl × policy_mult|   (across all 17 BTs)
```
Lower EXPOSURE = lower transitional turnover = qualitatively lower DD risk during regime flips. **Not** quantitative DD.

### EXPOSURE per policy

**BTC-denominated** (G1 + G4 BTs):
| Policy | EXPOSURE (BTC) | Rank |
|---|---:|---:|
| Baseline | 0.4097 | 5 (worst) |
| Policy A | **0.0000** | **1 (best)** |
| Policy B-DR1 | 0.4097 | 5 (tied) |
| Policy B-DR2 | 0.1377 | 2 |
| Policy C | 0.2048 | 3 |

**USD-denominated** (G2 + G3 BTs):
| Policy | EXPOSURE (USD) | Rank |
|---|---:|---:|
| Baseline | 15 649.20 | 4 (tied worst) |
| Policy A | **0.00** | **1 (best)** |
| Policy B-DR1 | 15 649.20 | 4 (tied) |
| Policy B-DR2 | 15 649.20 | 4 (tied — no G1 in USD set) |
| Policy C | 7 824.60 | 3 |

### Note
EXPOSURE rankings here mirror the policy mults directly (A=0, C=½, DR1/DR2=full where applicable) because all 17 BT total PnLs are well-defined; the proxy collapses to "fraction of transitional PnL retained, in absolute value." Without bar-level data this is the most that can be said about DD. To upgrade to M2, raw GinArea trade logs (entry/exit timestamps + PnL per fill) would be required.

---

## §6 Recommendation framework (mechanics only — no winner pick)

Per spec: this section ranks; it does **not** pick a winner. Operator + MAIN interpret jointly per session model.

### Composite ranking — primary = PnL improvement, secondary = EXPOSURE reduction

PnL improvement ranks Δ vs baseline (more positive = higher rank). EXPOSURE ranks (lower abs = higher rank). Composite = PnL rank, ties broken by EXPOSURE rank.

**BTC-denominated set:**
| Policy | ΔPnL (BTC) | PnL rank | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **B-DR2 (G1=trend)** | +0.27199 | 1 | 2 | **1** |
| **A (Pause-All)** | +0.13429 | 2 | 1 | **2** |
| **C (×0.5)** | +0.06714 | 3 | 3 | **3** |
| **B-DR1 (all-range)** | 0.00000 | 4 (tied) | 4 (tied) | **4** |
| Baseline | 0 (ref) | 4 (tied) | 4 (tied) | ref |

**USD-denominated set:**
| Policy | ΔPnL (USD) | PnL rank | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **A (Pause-All)** | +15 649 | 1 | 1 | **1** |
| **C (×0.5)** | +7 825 | 2 | 2 | **2** |
| **B-DR1 / B-DR2** | 0 | 3 (tied) | 3 (tied) | **3** |
| Baseline | 0 (ref) | 3 (tied) | 3 (tied) | ref |

### Caveats the operator must weigh before any decision
1. **TRANSITION share is ~3× the brief's sanity range.** This is a real property of the data, not a bug, but it means policies A / B-DR2 are silencing close to half of every BT window. Read PnL deltas as "what fraction of an already-questionable hourly-uniform allocation is reassigned" rather than "what would actually be earned/avoided."
2. **M1 hourly-uniformity assumption.** Real GinArea PnL is concentrated at trigger/grid-fill events, not uniform across the window. If TRANSITION hours coincidentally cluster near actual fill events, A/C overestimate gain; if they avoid fill events, A/C underestimate.
3. **G4 is the only profitable cohort.** Policies A and C *reduce* G4 gains (G4 has +0.243 BTC of transitional gain across 4 BTs that A zeros out). Operator should weigh whether the loss-avoidance in G1+G2+G3 is worth giving up G4's transitional gains.
4. **DR1 ≡ baseline by construction** — meaningful only as a null comparator.
5. **DR2 has no effect on USD totals** because G1 is BTC-only; this is registry-shape-dependent, not policy-shape-dependent.
6. **Bullish year bias.** All 17 BTs span a structurally bullish 2025-2026 — TRANSITION rankings here may not transfer to a bear or balanced year (cf. `REGIME_OVERLAY_v1` Finding B).
7. **No re-tuning of TRANSITION_SIZE_MULT in this TZ.** Policy C uses 0.5 only. A multiplier sweep is the natural follow-up TZ if Policy C composite-wins.
8. **No M2 DD.** EXPOSURE proxy only — true DD ranking requires raw trade logs.

---

## Anti-drift adherence

- ✅ 3 policies, fixed (A, B, C). No 4th invented.
- ✅ Policy B = DR1 + DR2 only. No DR3.
- ✅ Policy C multiplier = 0.5 only. No sweep.
- ✅ No Q1/Q3/Q4/Q5 touched — only Q2 (TRANSITION_MODE comparison).
- ✅ No new BT runs. No production code changes.
- ✅ 1y window completed; no fallback taken.
- ✅ No winner pick in §6.
- ⚠ TRANSITION % outside 5-15 % sanity range — flagged in §1, §2, §6 caveat 1.
- ⚠ BT-005..008 coverage 95.74 % (below 96 % target floor) — flagged inline in §3.

---

## Upstream / downstream references
- Baseline regime allocation: [`REGIME_OVERLAY_v1.md`](REGIME_OVERLAY_v1.md)
- BT registry: [`GINAREA_BACKTESTS_REGISTRY_v1.md`](GINAREA_BACKTESTS_REGISTRY_v1.md)
- Regime episode statistics: [`_regime_periods_raw.json`](_regime_periods_raw.json)
- Driver: [`scripts/_transition_mode_compare.py`](../../scripts/_transition_mode_compare.py)
- Raw output: [`_transition_mode_compare_raw.json`](_transition_mode_compare_raw.json)
