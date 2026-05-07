# REGIME OVERLAY V2

**Date:** 2026-05-05
**TZ:** TZ-REGIME-OVERLAY-V2
**Method:** M1 proportional allocation (per `REGIME_OVERLAY_v1` template) — no bar-by-bar reconstruction.
**Driver:** [`scripts/_regime_overlay_v2.py`](../../scripts/_regime_overlay_v2.py)
**Raw output:** [`_regime_overlay_v2_raw.json`](_regime_overlay_v2_raw.json)
**Compute:** 1.7 s.

**Input regime labels:** `data/forecast_features/full_features_1y.parquet` (`regime_int`, 5min bars resampled to hourly mode). Index: 2025-05-01 00:00 UTC → 2026-05-01 00:00 UTC, 8 761 hours.
**Source PnL data:** Pack A/C/D/E + BT-014..017 (encoded inline in driver per brief).

---

## §1 Methodology

### Per-run allocation
For each registered run with window `[w_start, w_end+1d)`:
1. Intersect run window with hourly regime index → `covered_hours`.
2. Count regime hours inside the intersection: `h_RANGE`, `h_MARKUP`, `h_MARKDOWN`.
3. Allocate run's `total_pnl` proportionally:
   ```
   PnL_regime = total_pnl × (h_regime / covered_hours)
   ```
4. Coverage % = `covered_hours / nominal_hours`. Target ≥ 96 % per CP24 baseline.

This is **identical** to `REGIME_OVERLAY_v1` §1 — no methodological innovation in v2 beyond the wider source set and the post-rebate column (§5).

### Per-Pack aggregation
Within a Pack, sum per-regime PnL and per-regime hours across runs (units kept separate — BTC and USD never mixed). Hours-weighted PnL-per-hour-per-regime = `sum_regime_pnl[r] / sum_regime_hours[r]`.

### Critical assumption
M1 assumes **PnL is uniformly distributed across hours within each run window**. Real GinArea PnL is concentrated at trigger/grid-fill events, so the per-regime split is **proportional to time exposure**, not actual realized regime conditional PnL. This is the same caveat that gates `REGIME_OVERLAY_v1`.

---

## §2 Per-run breakdown

### Coverage flag
Target ≥ 96 %. Six runs fall below the floor — all because their nominal windows extend past 2026-05-01 (regime parquet end). Specifically:
- A1, A4, E-T*: windows reach to 2026-05-05 → ~4 days uncovered.
- BT-014..017: windows reach to 2026-05-02 → ~2 days uncovered (97.75 %, just below target).
- A2, C1-clean, C2-clean, C3, A3, D-NoStop, D-WithStop: 100 % coverage (windows fit fully inside the parquet).

| Run | Pack | Side | Window | Cov % | Cov h | Total PnL | MARKUP | MARKDOWN | RANGE |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| A1 | A | S | 2025-05-05 → 2026-05-05 | 98.65 | 8 665 | +8 884.00 USD | +1 147.28 | +1 342.08 | +6 394.63 |
| A2 | A | S | 2026-02-01 → 2026-04-30 | 100.00 | 2 136 | -478.00 USD | -91.31 | -97.80 | -288.89 |
| A3 | A | S | 2025-05-05 → 2026-04-30 | 100.00 | 8 664 | +8 821.00 USD | +1 138.80 | +1 333.07 | +6 349.13 |
| A4 | A | S | 2026-02-05 → 2026-05-05 | **94.49** ⚠ | 2 041 | -5 046.00 USD | -964.94 | -1 033.96 | -3 047.10 |
| C1-clean | C | L | 2025-05-05 → 2026-04-30 | 100.00 | 8 664 | -0.1955 BTC | -0.025248 | -0.029538 | -0.140714 |
| C2-clean | C | L | 2025-05-05 → 2026-04-30 | 100.00 | 8 664 | -0.0812 BTC | -0.010488 | -0.012270 | -0.058442 |
| C3 | C | L | 2025-05-05 → 2026-04-30 | 100.00 | 8 664 | -0.0641 BTC | -0.008279 | -0.009686 | -0.046139 |
| D-NoStop | D | S | 2026-02-01 → 2026-04-30 | 100.00 | 2 136 | -481.00 USD | -91.88 | -98.42 | -290.70 |
| D-WithStop | D | S | 2026-02-01 → 2026-04-30 | 100.00 | 2 136 | -2 604.00 USD | -497.39 | -532.74 | -1 573.88 |
| E-T0.25 | E | L | 2026-02-05 → 2026-05-05 | **94.49** ⚠ | 2 041 | +0.0825 BTC | +0.015775 | +0.014904 | +0.052321 |
| E-T0.30 | E | L | 2026-02-05 → 2026-05-05 | **94.49** ⚠ | 2 041 | +0.0915 BTC | +0.017496 | +0.016531 | +0.057427 |
| E-T0.40 | E | L | 2026-02-05 → 2026-05-05 | **94.49** ⚠ | 2 041 | +0.1039 BTC | +0.019867 | +0.018771 | +0.065217 |
| E-T0.50 | E | L | 2026-02-05 → 2026-05-05 | **94.49** ⚠ | 2 041 | +0.1114 BTC | +0.021301 | +0.020127 | +0.069920 |
| BT-014 | BT | L | 2026-02-05 → 2026-05-02 | 97.75 ⚠ | 2 041 | +0.07779 BTC | +0.015289 | +0.014564 | +0.048863 |
| BT-015 | BT | L | 2026-02-05 → 2026-05-02 | 97.75 ⚠ | 2 041 | +0.07054 BTC | +0.013864 | +0.013206 | +0.044309 |
| BT-016 | BT | L | 2026-02-05 → 2026-05-02 | 97.75 ⚠ | 2 041 | +0.05930 BTC | +0.011655 | +0.011102 | +0.037251 |
| BT-017 | BT | L | 2026-02-05 → 2026-05-02 | 97.75 ⚠ | 2 041 | +0.05022 BTC | +0.009872 | +0.009403 | +0.031554 |

⚠ = coverage below 96 % target. PnL units (BTC vs USD) preserved without conversion.

**Reconciliation:** for every run, `regime_pnl[MARKUP] + regime_pnl[MARKDOWN] + regime_pnl[RANGE] == total_pnl` to within 1e-9. Verified in driver (residual = 0 for all rows).

---

## §3 Per-Pack aggregate

### Pack A — SHORT validation (USD, n=4)
| Regime | Σ Hours | Σ PnL (USD) | PnL/h (USD) |
|---|---:|---:|---:|
| MARKUP | 3 047 | +1 203.86 | +0.395 |
| MARKDOWN | 3 437 | +1 632.59 | +0.475 |
| RANGE | 15 022 | +9 344.56 | +0.622 |
| **TOTAL** | **21 506** | **+12 181.00** | — |

Pack A is **net profitable** in all three regimes (USD-denominated, hours-weighted). Highest per-hour rate in RANGE.

### Pack C — LONG default 1y, no indicator (BTC, n=3)
| Regime | Σ Hours | Σ PnL (BTC) | PnL/h (BTC) |
|---|---:|---:|---:|
| MARKUP | 3 357 | -0.044016 | -1.31e-5 |
| MARKDOWN | 3 927 | -0.051490 | -1.31e-5 |
| RANGE | 18 708 | -0.245295 | -1.31e-5 |
| **TOTAL** | **25 992** | **-0.3408** | — |

⚠ The per-hour rate is **identical across regimes** (~-1.3×10⁻⁵ BTC/h). This is an M1 artifact: all 3 Pack-C runs share the same window (2025-05-05 → 2026-04-30), so the regime-share distribution is identical for each run; aggregating preserves uniform per-hour PnL. The split is informative about *time exposure*, not about *regime conditional performance*. See §7 caveat.

### Pack D — SHORT indicator>1% 3M (USD, n=2)
| Regime | Σ Hours | Σ PnL (USD) | PnL/h (USD) |
|---|---:|---:|---:|
| MARKUP | 816 | -589.27 | -0.722 |
| MARKDOWN | 874 | -631.15 | -0.722 |
| RANGE | 2 582 | -1 864.58 | -0.722 |
| **TOTAL** | **4 272** | **-3 085.00** | — |

Same M1 artifact (single shared window 2026-02-01 → 2026-04-30). Per-hour rate identical across regimes.

### Pack E — LONG indicator<-0.3% 3M (BTC, n=4)
| Regime | Σ Hours | Σ PnL (BTC) | PnL/h (BTC) |
|---|---:|---:|---:|
| MARKUP | 1 604 | +0.076486 | +4.77e-5 |
| MARKDOWN | 1 528 | +0.072862 | +4.77e-5 |
| RANGE | 5 032 | +0.239950 | +4.77e-5 |
| **TOTAL** | **8 164** | **+0.3893** | — |

Same M1 artifact. Pack E is **net profitable in all regimes**.

### Pack BT — historical LONG indicator<-1% 86d (BTC, n=4)
| Regime | Σ Hours | Σ PnL (BTC) | PnL/h (BTC) |
|---|---:|---:|---:|
| MARKUP | 1 604 | +0.050661 | +3.16e-5 |
| MARKDOWN | 1 528 | +0.048259 | +3.16e-5 |
| RANGE | 5 032 | +0.158929 | +3.16e-5 |
| **TOTAL** | **8 164** | **+0.25785** | — |

Same M1 artifact (BT-014..017 share 2026-02-05 → 2026-05-02 window).

---

## §4 Cross-Pack comparison

### Per-hour PnL across packs (within-unit comparison)
**USD-denominated (Pack A vs Pack D):**
| Pack | Side | Strategy | n | PnL/h MARKUP | PnL/h MARKDOWN | PnL/h RANGE |
|---|---|---|---:|---:|---:|---:|
| A | SHORT | DEFAULT + INDICATOR>0.3% mix | 4 | +0.395 | +0.475 | +0.622 |
| D | SHORT | INDICATOR>1% only | 2 | -0.722 | -0.722 | -0.722 |

Pack A (mix dominated by 1y DEFAULT-strategy SHORT) earns; Pack D (indicator>1% threshold, narrow 3M window) loses. Within Pack A, regime sensitivity is real (RANGE > MARKDOWN > MARKUP per-hour rate). Within Pack D, M1 artifact prevents per-regime distinction.

**BTC-denominated (Pack C vs Pack E vs Pack BT):**
| Pack | Side | Strategy | n | PnL/h all-regimes (×10⁻⁵) | Total PnL (BTC) |
|---|---|---|---:|---:|---:|
| C | LONG | DEFAULT (no indicator) | 3 | -1.31 | -0.3408 |
| E | LONG | INDICATOR <-0.3% | 4 | +4.77 | +0.3893 |
| BT | LONG | INDICATOR <-1% (86d historical) | 4 | +3.16 | +0.25785 |

The indicator gate flips LONG sign from net negative (Pack C) to net positive (Pack E and BT). This **strongly confirms `REGIME_OVERLAY_v1` Finding A** — see §6.

### Total PnL per Pack
| Pack | Unit | Σ Total PnL |
|---|---|---:|
| A | USD | +12 181.00 |
| C | BTC | -0.3408 |
| D | USD | -3 085.00 |
| E | BTC | +0.3893 |
| BT | BTC | +0.25785 |

---

## §5 Post-rebate analysis

### Method
Conservative low-tier rebate rate = **0.0093 % of volume**, applied as a *positive* fee credit added back to realized PnL:
```
post_rebate_pnl = total_pnl + (volume_usd × 0.0093%)
post_rebate_per_regime = regime_pnl + rebate_total × (h_regime / cov_h)
```
Rebate is fee-side, not regime-conditional, so it is allocated proportionally to hours (same fraction as PnL allocation).

**Important constraint:** rebate is computed in USD (volume is USD-denominated). For **USD-denominated runs (Packs A, D)** post-rebate is reported. For **BTC-denominated runs (Packs C, E, BT)** the rebate would be a USD credit added to a BTC-denominated PnL — units don't match without an FX conversion, which is **out of scope** per the brief. Post-rebate for BTC packs is therefore **not reported** here; that requires a separate TZ with explicit BTC/USD conversion methodology.

### Pack-level post-rebate sums (USD only)
| Pack | Σ PnL (USD) | Σ Rebate (USD) | Σ Post-rebate PnL (USD) | Δ vs raw |
|---|---:|---:|---:|---:|
| A | +12 181.00 | +3 277.32 | **+15 458.32** | +3 277.32 |
| D | -3 085.00 | +730.05 | **-2 354.95** | +730.05 |

### Per-run rebate breakdown (USD only)
| Run | Volume (USD) | Rebate (USD) | Raw PnL (USD) | Post-rebate PnL (USD) |
|---|---:|---:|---:|---:|
| A1 | 13.02 M | +1 210.86 | +8 884.00 | +10 094.86 |
| A2 | 3.57 M | +332.01 | -478.00 | -145.99 |
| A3 | 14.89 M | +1 384.77 | +8 821.00 | +10 205.77 |
| A4 | 3.76 M | +349.68 | -5 046.00 | -4 696.32 |
| D-NoStop | 3.56 M | +331.08 | -481.00 | -149.92 |
| D-WithStop | 4.29 M | +398.97 | -2 604.00 | -2 205.03 |

**Observation:** rebate is meaningful but does not flip signs in Pack D (still net loss); it does push A2 and D-NoStop very close to break-even (within ~$150 of zero).

---

## §6 Findings (data only — no recommendations)

### F-A. Confirms `REGIME_OVERLAY_v1` Finding A: indicator gate flips LONG sign
Side-by-side at the LONG/BTC pack level:
- **Pack C** (LONG, DEFAULT, no indicator, 1y): **−0.3408 BTC** total across 3 runs.
- **Pack E** (LONG, INDICATOR<-0.3%, 3M): **+0.3893 BTC** total across 4 runs.
- **Pack BT** (LONG, INDICATOR<-1%, 86d): **+0.25785 BTC** total across 4 runs.

Pack E and Pack BT both **flip the sign vs Pack C**, despite shorter windows and different indicator thresholds. This reproduces the `REGIME_OVERLAY_v1` Finding A on a strictly larger dataset (Pack C is the v1 G1 mirror; Pack E is new evidence in the same direction as G4). The interpretation in v1 — "indicator gate is a temporal opportunity filter, not a regime filter" — is consistent with the v2 data: per-hour PnL is positive in all three regimes for Pack E, not just in trending ones.

### F-B. SHORT regime sensitivity (Pack A only)
Pack A (4 runs, 21 506 covered hours total, mix of DEFAULT 1y and INDICATOR>0.3% 3M) shows **per-hour PnL ranking RANGE (+0.622) > MARKDOWN (+0.475) > MARKUP (+0.395)**. This is the *only* pack with enough heterogeneity in run windows to give a per-hour split that differs across regimes; all other packs collapse to a single per-hour rate due to shared-window M1 artifact (see §7 caveat). Pack A is also the *only* SHORT pack with a positive aggregate.

Pack D (SHORT, INDICATOR>1%, 3M, n=2) is uniformly negative across regimes and loses ~$0.72 per hour every regime. Cannot distinguish regimes inside D under M1.

This contrasts with `REGIME_OVERLAY_v1` Finding B (all SHORT BT-005..013 negative across all regimes). The Pack-A DEFAULT-strategy 1y SHORT runs (A1: +$8 884, A3: +$8 821) are the new positive-SHORT data points. The difference vs v1 G2/G3 SHORT runs is the **strategy axis** (DEFAULT vs INDICATOR>1%) and the **window length** (1y vs 3M), not the side itself.

### F-C. Target sensitivity for LONG indicator runs
Pack E (4 runs differ only in target ∈ {0.25, 0.30, 0.40, 0.50}) shows **monotonic gain in BTC PnL with higher target**:
| Target | PnL (BTC) | Volume (USD) |
|---|---:|---:|
| 0.25 | +0.0825 | 5.79 M |
| 0.30 | +0.0915 | 5.03 M |
| 0.40 | +0.1039 | 4.04 M |
| 0.50 | +0.1114 | 3.41 M |

Higher target → fewer fills, lower volume, but higher BTC gain. Sign matches BT-014..017 (Pack BT) where higher target also produced higher BTC gain (BT-014 TP=0.50 → +0.07779, BT-017 TP=0.25 → +0.05022). Replicates across two independent indicator thresholds (-0.3% and -1%) and two windows.

### F-D. Instop effect across packs
Pairs of runs that vary instop while holding other params constant:
| Comparison | Without instop | With instop=0.018/0.008/0.025 | Δ |
|---|---:|---:|---:|
| Pack A — DEFAULT 1y (A1 vs A3) | +8 884 USD | +8 821 USD | -63 USD |
| Pack A — INDICATOR>0.3% 3M (A2 vs A4) | -478 USD | -5 046 USD | -4 568 USD |
| Pack D — INDICATOR>1% 3M (D-NoStop vs D-WithStop) | -481 USD | -2 604 USD | -2 123 USD |

For DEFAULT 1y SHORT, instop has near-zero effect (−63 USD over $8 800 base). For both INDICATOR-strategy SHORT 3M comparisons, adding instop hurts by ~$2-5 K. Direction consistent. **Caveat:** instop comparisons within Pack A pair A2-vs-A4 also span different starts (A2: 2026-02-01, A4: 2026-02-05) — strictly a 4-day window mismatch on top of the instop change.

### F-E. M1 single-window collapse limits per-regime resolution within most packs
Packs C, D, E, BT each contain runs that share a single window. Under M1, this yields identical regime-share splits across runs in the pack, and aggregating preserves a single per-hour rate that doesn't differ across regimes. Per-regime rankings within these packs cannot be derived from M1 — they are valid only when comparing across packs with different windows (cross-pack comparison §4) or within Pack A (whose runs span two distinct window lengths).

---

## §7 Caveats

1. **M1 proportional allocation assumes hourly-uniform PnL.** Real GinArea PnL is event-driven (grid fills, trigger events, indicator activations). The per-regime split is a time-exposure proxy, not regime-conditional realized PnL. Same caveat as `REGIME_OVERLAY_v1` §7.

2. **Within-pack M1 collapse.** When all runs in a pack share a single window (Packs C, D, E, BT), per-run regime shares are identical, so aggregated per-hour PnL is identical across regimes. This is a property of M1 + shared-window — not a property of the bots. To break the collapse, either (a) include runs with different windows in the same pack, or (b) reconstruct hourly equity curves (M2, requires GinArea raw trade logs which are not available).

3. **DISTRIBUTION channel absent.** The regime classifier emits {MARKUP, MARKDOWN, RANGE}; there is no fourth "DISTRIBUTION" label in the data. Any framework expecting four-regime resolution should treat that gap explicitly.

4. **Rebate rate is an estimate.** 0.0093 % is a conservative low-tier number and is reported as USD-only. BTC-denominated packs (C, E, BT) have no post-rebate column because applying a USD-denominated rebate to a BTC-denominated PnL requires an explicit FX conversion methodology that is out of scope here.

5. **Coverage <96% on 6 runs.** A4, E-T0.25, E-T0.30, E-T0.40, E-T0.50, BT-014..017. All gaps are at the **tail end** (windows extend past 2026-05-01 parquet end). The unscored hours are ≤4 days each and do not bias one regime over another systematically — but it is a real coverage shortfall vs the brief's ≥96 % target. Flagged inline in §2 with ⚠.

6. **Pack E without instop pending.** The brief noted that Pack E runs without instop may be added later by the operator. The driver has a `RUNS_PENDING_PLACEHOLDER` list ready — operator can append tuples with the same shape and re-run `python scripts/_regime_overlay_v2.py` to regenerate without code changes. As of this report: **no Pack E without-instop runs are present** in the input data.

7. **No FX conversion.** BTC and USD PnL are kept in their native units. Any cross-unit comparison (e.g. "is Pack A USD profit > Pack E BTC profit at current price?") is **not made** here.

8. **Bullish year bias.** All runs span 2025-2026 BTC bullish trajectory. Findings about LONG profitability (Pack E, BT) and SHORT marginal performance (Pack A, D) are window-specific. Cross-period validation would require adding a bear-window run set, which is not present in the registry.

---

## Upstream / downstream references
- Methodology template: [`REGIME_OVERLAY_v1.md`](REGIME_OVERLAY_v1.md)
- Episode statistics: [`_regime_periods_raw.json`](_regime_periods_raw.json)
- BT-001..017 baseline: [`GINAREA_BACKTESTS_REGISTRY_v1.md`](GINAREA_BACKTESTS_REGISTRY_v1.md)
- Driver: [`scripts/_regime_overlay_v2.py`](../../scripts/_regime_overlay_v2.py)
- Raw output: [`_regime_overlay_v2_raw.json`](_regime_overlay_v2_raw.json)
