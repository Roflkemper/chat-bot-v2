# TRANSITION MODE COMPARE V2 (H=1)

**Date:** 2026-05-05
**TZ:** TZ-BLOCK-2-RERUN-H1 — re-run of Block 2 with calibrated hysteresis.
**Replaces:** `TRANSITION_MODE_COMPARE_v1.md` (used H=12 → 46.48 % TRANSITION, artifact).
**Method:** M1 proportional allocation, identical to v1; only the TRANSITION definition is recalibrated per `HYSTERESIS_CALIBRATION_v1`.

**Driver:** [`scripts/_transition_mode_compare_v2.py`](../../scripts/_transition_mode_compare_v2.py)
**Raw output:** [`_transition_mode_compare_v2_raw.json`](_transition_mode_compare_v2_raw.json)
**Compute:** ~1.7 s.

**Window:** 1y, 2025-05-01 00:00 UTC → 2026-05-01 00:00 UTC, 8 761 hourly bars.
**Run set:** 17 runs from `REGIME_OVERLAY_v2` (Pack A=4, C=3, D=2, E=4, BT=4) — superset and replacement of v1's BT-001..017.

---

## §1 Methodology

### What changed vs v1
- **Hysteresis recalibrated**: `H = 1` (primary), `H = 2` (sensitivity). v1 used `H = 12`, which gave 46.48 % TRANSITION — a structural artifact of choppy regime data, not a property of any policy. See `HYSTERESIS_CALIBRATION_v1.md`.
- **Run set expanded**: now uses all 17 runs from `REGIME_OVERLAY_v2` (Pack A/C/D/E + BT-014..017), not just BT-001..017.
- **Policy B-DR2 categorization re-mapped**: in v1, "trend-style" = G1 (LONG annual DEFAULT no-indicator). In v2, the equivalent rule is **DEFAULT-strategy ∧ no-indicator**, which captures Pack A1/A3 (SHORT DEFAULT 1y) and Pack C1-clean/C2-clean/C3 (LONG DEFAULT 1y). All other runs are indicator-gated → range-style. Five runs flagged trend-style under DR2; twelve flagged range-style.

### TRANSITION operational definition
`h` is `TRANSITION_HOUR` ⇔ rolling window `[h-H, h]` (size `H+1` bars) contains ≥2 distinct `regime_int` values. No confidence rule (no confidence column in source data).

### Policies (unchanged from v1)
- **A — Pause-All:** `pnl_A = stable_pnl` (TRANSITION pnl → 0 for every run).
- **B — Hold-Range / Pause-Trend:**
  - **DR1:** all 17 runs = range-style. Under DR1, no run is paused → `pnl_B_DR1 = total_pnl ≡ baseline`.
  - **DR2:** DEFAULT/no-indicator = trend-style (zero on TRANSITION); INDICATOR-gated = range-style (preserve).
- **C — Hold-All-Reduced-Sizing:** `pnl_C = stable_pnl + 0.5 · transition_pnl`. Multiplier fixed at 0.5.

### M1 PnL allocation
```
TRANSITION_share_pnl = total_pnl × (TRANSITION_hours / covered_hours)
stable_share_pnl     = total_pnl − TRANSITION_share_pnl
```
Critical assumption: PnL is uniformly distributed across hours within a run window. Same caveat as `REGIME_OVERLAY_v1/v2`.

---

## §2 TRANSITION-hours analysis

### Headline (year-level)
| Hysteresis | TRANSITION hours | TRANSITION % | In [5,15] sanity? |
|---:|---:|---:|:---:|
| H=1 (primary) | 644 | **7.351 %** | ✓ |
| H=2 (sensitivity) | 1 149 | **13.115 %** | ✓ |

Both candidates land cleanly in the 5-15 % sanity range. Original v1 (H=12) was 46.48 % — clearly out of band.

### Per-run TRANSITION share at H=1
The within-window TRANSITION share varies slightly by run window:
| Run window | TRANSITION share at H=1 | TRANSITION share at H=2 |
|---|---:|---:|
| 2025-05-05 → 2026-05-05 (A1) | 7.41 % | 13.16 % |
| 2025-05-05 → 2026-04-30 (A3, C1-3) | 7.41 % | 13.13 % |
| 2026-02-01 → 2026-04-30 (A2, D-*) | 8.57 % | 14.94 % |
| 2026-02-05 → 2026-05-05 (A4, E-*) | 8.38 % | 14.79 % |
| 2026-02-05 → 2026-05-02 (BT-014..017) | 8.38 % | 14.79 % |

The 2026-02 window is slightly choppier than the full year (8.4 % vs 7.4 % at H=1). At H=2, the 02may windows push to ~14.8 % — close to the upper sanity edge but still in band.

---

## §3 Per-run × policy PnL table (H=1 primary)

Coverage column from REGIME_OVERLAY_v2; ⚠ flag where <96 % (unchanged from v2).

| Run | Pack | Side | Strat | DR2 trend? | Cov % | TRANSITION % | Total PnL | Stable | Trans | A | B-DR1 | B-DR2 | C |
|---|---|---|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 | A | S | DEFAULT | **yes** | 98.65 | 7.41 | +8 884.00 USD | +8 225.77 | +658.23 | +8 225.77 | +8 884.00 | **+8 225.77** | +8 554.89 |
| A2 | A | S | INDICATOR | no | 100.00 | 8.57 | -478.00 USD | -437.05 | -40.95 | -437.05 | -478.00 | -478.00 | -457.52 |
| A3 | A | S | DEFAULT | **yes** | 100.00 | 7.41 | +8 821.00 USD | +8 167.37 | +653.63 | +8 167.37 | +8 821.00 | **+8 167.37** | +8 494.18 |
| A4 | A | S | INDICATOR | no | 94.49 ⚠ | 8.38 | -5 046.00 USD | -4 623.23 | -422.77 | -4 623.23 | -5 046.00 | -5 046.00 | -4 834.62 |
| C1-clean | C | L | DEFAULT | **yes** | 100.00 | 7.41 | -0.1955 BTC | -0.18102 | -0.01448 | -0.18102 | -0.1955 | **-0.18102** | -0.18826 |
| C2-clean | C | L | DEFAULT | **yes** | 100.00 | 7.41 | -0.0812 BTC | -0.07519 | -0.00601 | -0.07519 | -0.0812 | **-0.07519** | -0.07820 |
| C3 | C | L | DEFAULT | **yes** | 100.00 | 7.41 | -0.0641 BTC | -0.05935 | -0.00475 | -0.05935 | -0.0641 | **-0.05935** | -0.06173 |
| D-NoStop | D | S | INDICATOR | no | 100.00 | 8.57 | -481.00 USD | -439.79 | -41.21 | -439.79 | -481.00 | -481.00 | -460.40 |
| D-WithStop | D | S | INDICATOR | no | 100.00 | 8.57 | -2 604.00 USD | -2 380.90 | -223.10 | -2 380.90 | -2 604.00 | -2 604.00 | -2 492.45 |
| E-T0.25 | E | L | INDICATOR | no | 94.49 ⚠ | 8.38 | +0.0825 BTC | +0.07559 | +0.00691 | +0.07559 | +0.0825 | +0.0825 | +0.07905 |
| E-T0.30 | E | L | INDICATOR | no | 94.49 ⚠ | 8.38 | +0.0915 BTC | +0.08383 | +0.00767 | +0.08383 | +0.0915 | +0.0915 | +0.08766 |
| E-T0.40 | E | L | INDICATOR | no | 94.49 ⚠ | 8.38 | +0.1039 BTC | +0.09521 | +0.00871 | +0.09521 | +0.1039 | +0.1039 | +0.09955 |
| E-T0.50 | E | L | INDICATOR | no | 94.49 ⚠ | 8.38 | +0.1114 BTC | +0.10208 | +0.00934 | +0.10208 | +0.1114 | +0.1114 | +0.10674 |
| BT-014 | BT | L | INDICATOR | no | 97.75 ⚠ | 8.38 | +0.07779 BTC | +0.07127 | +0.00652 | +0.07127 | +0.07779 | +0.07779 | +0.07453 |
| BT-015 | BT | L | INDICATOR | no | 97.75 ⚠ | 8.38 | +0.07054 BTC | +0.06463 | +0.00591 | +0.06463 | +0.07054 | +0.07054 | +0.06759 |
| BT-016 | BT | L | INDICATOR | no | 97.75 ⚠ | 8.38 | +0.05930 BTC | +0.05433 | +0.00497 | +0.05433 | +0.05930 | +0.05930 | +0.05682 |
| BT-017 | BT | L | INDICATOR | no | 97.75 ⚠ | 8.38 | +0.05022 BTC | +0.04601 | +0.00421 | +0.04601 | +0.05022 | +0.05022 | +0.04812 |

**Reconciliation:** for every run and every policy, `(stable + mult × transition) == policy_pnl` to within 1e-9 (asserted in driver).

---

## §4 Per-pack and global aggregates

### Per-pack — H=1 (primary)
| Pack | Unit | n | Baseline | A (Pause) | Δ_A | B-DR1 | B-DR2 | Δ_B_DR2 | C (×0.5) | Δ_C |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | USD | 4 | +12 181.00 | +11 332.86 | -848.14 | +12 181.00 | +10 869.14 | -1 311.86 | +11 756.93 | -424.07 |
| BT | BTC | 4 | +0.25785 | +0.23625 | -0.02160 | +0.25785 | +0.25785 | 0.00000 | +0.24705 | -0.01080 |
| C | BTC | 3 | -0.34080 | -0.31555 | +0.02525 | -0.34080 | -0.31555 | +0.02525 | -0.32817 | +0.01263 |
| D | USD | 2 | -3 085.00 | -2 820.70 | +264.30 | -3 085.00 | -3 085.00 | 0.00000 | -2 952.85 | +132.15 |
| E | BTC | 4 | +0.38930 | +0.35668 | -0.03262 | +0.38930 | +0.38930 | 0.00000 | +0.37299 | -0.01631 |

### Per-pack — H=2 (sensitivity)
| Pack | Unit | n | Baseline | A (Pause) | Δ_A | B-DR1 | B-DR2 | Δ_B_DR2 | C (×0.5) | Δ_C |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | USD | 4 | +12 181.00 | +10 679.33 | -1 501.67 | +12 181.00 | +9 841.31 | -2 339.69 | +11 430.17 | -750.83 |
| BT | BTC | 4 | +0.25785 | +0.21881 | -0.03904 | +0.25785 | +0.25785 | 0.00000 | +0.23833 | -0.01952 |
| C | BTC | 3 | -0.34080 | -0.29576 | +0.04504 | -0.34080 | -0.29576 | +0.04504 | -0.31828 | +0.02252 |
| D | USD | 2 | -3 085.00 | -2 606.94 | +478.06 | -3 085.00 | -3 085.00 | 0.00000 | -2 845.97 | +239.03 |
| E | BTC | 4 | +0.38930 | +0.33036 | -0.05894 | +0.38930 | +0.38930 | 0.00000 | +0.35983 | -0.02947 |

### Global aggregate (across all packs, by unit)
**H=1:**
| Policy | BTC (n=11) | USD (n=6) |
|---|---:|---:|
| Baseline | +0.30635 | +9 096.00 |
| Policy A | +0.27738 (Δ -0.02897) | +8 512.16 (Δ -583.84) |
| Policy B-DR1 | +0.30635 (Δ 0) | +9 096.00 (Δ 0) |
| Policy B-DR2 | +0.33160 (Δ +0.02525) | +7 784.14 (Δ -1 311.86) |
| Policy C | +0.29187 (Δ -0.01448) | +8 804.08 (Δ -291.92) |

**H=2:**
| Policy | BTC (n=11) | USD (n=6) |
|---|---:|---:|
| Baseline | +0.30635 | +9 096.00 |
| Policy A | +0.25341 (Δ -0.05294) | +8 072.39 (Δ -1 023.61) |
| Policy B-DR1 | +0.30635 (Δ 0) | +9 096.00 (Δ 0) |
| Policy B-DR2 | +0.35139 (Δ +0.04504) | +6 756.31 (Δ -2 339.69) |
| Policy C | +0.27988 (Δ -0.02647) | +8 584.20 (Δ -511.80) |

### Critical contrast vs v1 (H=12)
At v1's H=12 the picture was dominated by ~50 % windows being silenced. At H=1 / H=2 (true TRANSITION rates), policy effects shrink **roughly proportionally to TRANSITION %**. The qualitative direction of effects, however, **changes for net-profitable packs** — see §6.

---

## §5 Drawdown / exposure ranking

Method unchanged from v1: M1 EXPOSURE proxy only (no raw trade logs in `backtests/raw/` → no M2). EXPOSURE = `Σ |TRANSITION_share_pnl × policy_mult|`.

### EXPOSURE per policy at H=1
| Pack | Unit | Baseline | A | B-DR1 | B-DR2 | C |
|---|---|---:|---:|---:|---:|---:|
| A | USD | 1 775.79 | 0 | 1 775.79 | 1 311.86 | 887.89 |
| BT | BTC | 0.02160 | 0 | 0.02160 | 0.02160 | 0.01080 |
| C | BTC | 0.02525 | 0 | 0.02525 | 0 | 0.01263 |
| D | USD | 264.30 | 0 | 264.30 | 264.30 | 132.15 |
| E | BTC | 0.03262 | 0 | 0.03262 | 0.03262 | 0.01631 |

Policy A has zero EXPOSURE by definition. Policy C halves it. B-DR2 only zeroes EXPOSURE on the trend-style runs (Packs A's DEFAULT subset and Pack C); for indicator-gated packs (D, E, BT) B-DR2 = full baseline EXPOSURE.

### Note on EXPOSURE interpretation at H=1/H=2
At low TRANSITION %, raw EXPOSURE numbers are smaller in absolute terms — but the *ratio* between policies is the same as v1 (mults are unchanged). The key change vs v1 is that EXPOSURE rankings now act on the **right denominator** (~7-13 % of windows, not ~50 %).

---

## §6 Recommendation framework (mechanics only — no winner pick)

Per spec: rank, do not pick.

### Composite ranking — primary = ΔPnL (more positive = better), secondary = ΔEXPOSURE (more negative = better)

#### Pack A (USD, SHORT) — net profitable baseline (+12 181 USD)
| Policy | ΔPnL (H=1) | ΔPnL (H=2) | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **B-DR1** | 0.00 | 0.00 | tied 4 | **1 (no-op)** |
| **C (×0.5)** | -424.07 | -750.83 | 3 | **2** |
| **A (Pause-All)** | -848.14 | -1 501.67 | 1 | **3** |
| **B-DR2** | -1 311.86 | -2 339.69 | 2 | **4** |

⚠ **Sign reversal vs v1:** at v1's H=12, A and B-DR2 both improved Pack A's USD outcome because TRANSITION pnl was net negative there (a different run set + a different definition). At H=1, Pack A's TRANSITION pnl is **net positive** (the DEFAULT-strategy 1y SHORT runs A1+A3 contribute +1 311.86 USD of transitional gain), so silencing TRANSITION *forfeits* gain. **For net-profitable runs, all "pause" policies hurt.**

#### Pack BT (BTC, LONG indicator<-1%) — net profitable (+0.25785)
| Policy | ΔPnL (H=1) | ΔPnL (H=2) | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **B-DR1, B-DR2** | 0 | 0 | tied (B-DR2: 4 in pack) | **1 (no-op)** |
| **C** | -0.01080 | -0.01952 | 3 | **2** |
| **A** | -0.02160 | -0.03904 | 1 | **3** |

Same pattern as Pack A: profitable pack → pausing hurts.

#### Pack C (BTC, LONG DEFAULT) — net loss (-0.34080)
| Policy | ΔPnL (H=1) | ΔPnL (H=2) | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **A, B-DR2** (tied) | +0.02525 | +0.04504 | tied 1 | **1** |
| **C** | +0.01263 | +0.02252 | 3 | **2** |
| **B-DR1** | 0 | 0 | tied 4 | **3 (no-op)** |

Pack C is loss-making. Pausing TRANSITION recovers a small fraction (~7 % of the loss at H=1, ~13 % at H=2). A and B-DR2 are equivalent here because all Pack C runs are DEFAULT/no-indicator → DR2 already silences them.

#### Pack D (USD, SHORT INDICATOR>1%) — net loss (-3 085)
| Policy | ΔPnL (H=1) | ΔPnL (H=2) | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **A** | +264.30 | +478.06 | 1 | **1** |
| **C** | +132.15 | +239.03 | 3 | **2** |
| **B-DR1, B-DR2** | 0 | 0 | tied 4 | **3 (no-op)** |

Loss-making, but all runs are indicator-gated → DR2 has no effect. Only A and C help.

#### Pack E (BTC, LONG INDICATOR<-0.3%) — net profitable (+0.38930)
| Policy | ΔPnL (H=1) | ΔPnL (H=2) | EXPOSURE rank | Composite |
|---|---:|---:|---:|---:|
| **B-DR1, B-DR2** | 0 | 0 | tied (B-DR2: 4 in pack) | **1 (no-op)** |
| **C** | -0.01631 | -0.02947 | 3 | **2** |
| **A** | -0.03262 | -0.05894 | 1 | **3** |

Same as Pack A and BT — profitable, pausing hurts.

### Cross-pack synthesis (mechanics, no policy decision)
At calibrated hysteresis (H=1 or H=2):
1. **Net-profitable packs (A, BT, E):** every "pause" or "reduce" policy *forfeits* gain. The best policy on the PnL axis is **B-DR1 (no-op)**.
2. **Net-loss packs (C, D):** "pause" policies recover ~7-13 % of the loss. Best policy is **A** (and B-DR2 where applicable).
3. There is **no single policy** that improves all packs simultaneously. The choice depends on which packs the operator deploys.

This is in stark contrast to v1's H=12 conclusion (where many composite rankings put A or B-DR2 first across the board), which was driven by the artifact of silencing half the year. At true TRANSITION rates, **TRANSITION_MODE policy choice depends entirely on whether a given run has positive or negative transitional PnL**, and M1's hourly-uniformity assumption maps that directly to the run's overall sign.

### Caveats the operator must weigh (unchanged from v1 in spirit, refreshed)
1. **M1 hourly-uniform assumption.** Real GinArea PnL is event-driven — at low TRANSITION %, the assumption matters even more, because misallocation of just a few high-impact hours could flip a small Δ.
2. **At H=1, mean TRANSITION segment is 1.3 hour.** A 1-bar settling window may be too aggressive for a real coordinator (any truly transient regime jitter would still trigger a pause). Operator may prefer H=2 (mean 2.7 h) or some other operational definition out of scope here.
3. **No M2 DD.** EXPOSURE proxy only.
4. **Bullish year bias.** All 17 runs span 2025-2026; conclusions about "B-DR1 wins for net-profitable packs" are window-specific.
5. **B-DR1 ≡ baseline by construction.** Reported as no-op for clarity — its "win" on profitable packs really means "do nothing and keep the gain."
6. **B-DR2 has zero effect on indicator-gated packs (BT, D, E).** Categorization-by-construction; not informative there.
7. **Pack A's positive TRANSITION pnl is concentrated in two large 1y DEFAULT runs (A1+A3, ~$1 312 each).** That dominates the +1 312 USD positive Δ_B_DR2. If those runs are excluded, Pack A's pattern flips to match D's loss-recovery shape.

---

## Anti-drift adherence
- ✅ Hysteresis values not re-derived (taken from `HYSTERESIS_CALIBRATION_v1`).
- ✅ No new policies introduced.
- ✅ Same 3 policies (A, B-DR1, B-DR2, C) and same multipliers as v1.
- ✅ Same window (1y 2025-05-01 → 2026-05-01).
- ✅ All 17 runs from REGIME_OVERLAY_v2 used.
- ✅ TRANSITION % per H reported; both in [5,15] band.
- ✅ §6 ranks, no winner pick.
- ⚠ Six runs <96 % coverage — same flag as REGIME_OVERLAY_v2 §2.

---

## CP report

- **Output paths:**
  - [docs/RESEARCH/TRANSITION_MODE_COMPARE_v2.md](TRANSITION_MODE_COMPARE_v2.md)
  - [docs/RESEARCH/_transition_mode_compare_v2_raw.json](_transition_mode_compare_v2_raw.json)
  - [scripts/_transition_mode_compare_v2.py](../../scripts/_transition_mode_compare_v2.py)
- **TRANSITION % at H=1:** 7.351 % (644 / 8 761 hours)
- **TRANSITION % at H=2:** 13.115 % (1 149 / 8 761 hours)
- **Per-pack composite ranking:**
  - Pack A (USD, profitable): B-DR1 > C > A > B-DR2
  - Pack BT (BTC, profitable): B-DR1/DR2 > C > A
  - Pack C (BTC, loss): A/B-DR2 > C > B-DR1
  - Pack D (USD, loss): A > C > B-DR1/DR2
  - Pack E (BTC, profitable): B-DR1/DR2 > C > A
- **Compute time:** ~1.7 s.

## References
- Hysteresis calibration source: [`HYSTERESIS_CALIBRATION_v1.md`](HYSTERESIS_CALIBRATION_v1.md)
- Run data source: [`REGIME_OVERLAY_v2.md`](REGIME_OVERLAY_v2.md)
- Original v1 (H=12): [`TRANSITION_MODE_COMPARE_v1.md`](TRANSITION_MODE_COMPARE_v1.md)
