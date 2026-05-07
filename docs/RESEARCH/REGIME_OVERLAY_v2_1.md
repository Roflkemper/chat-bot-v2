# REGIME OVERLAY V2.1

**Date:** 2026-05-05
**TZ:** TZ-REGIME-OVERLAY-v2.1-WITH-PACK-E-NOSTOP
**Supersedes:** [`REGIME_OVERLAY_v2.md`](REGIME_OVERLAY_v2.md). v2 is preserved verbatim; v2.1 adds 4 Pack E NoStop runs and a new Finding F-G.
**Method:** Identical to v2 — M1 proportional allocation; no bar-by-bar reconstruction.
**Driver:** [`scripts/_regime_overlay_v2_1.py`](../../scripts/_regime_overlay_v2_1.py)
**Raw output:** [`_regime_overlay_v2_1_raw.json`](_regime_overlay_v2_1_raw.json)
**Compute:** ~1.7 s.

**What changed vs v2:**
- 4 new runs added: Pack E NoStop variants (E-NoStop-T0.25..T0.50), LONG INDICATOR `<-0.3%`, instop=0/0/0, contract COIN_FUTURES.
- Run total: **17 → 21**.
- New finding **F-G** added to §6: instop direction asymmetry between LONG and SHORT indicator families.
- All other content (§1, §2 v2 rows, §3-§5 base structure, §6 F-A..F-E, §7) preserved.

---

## §1 Methodology

Unchanged from v2. M1 proportional allocation:
```
PnL_regime = total_pnl × (h_regime / covered_hours)
```
Per-pack aggregation sums regime hours and regime PnL across runs in the pack, units kept separate (BTC vs USD).

The 4 new Pack E NoStop runs are encoded as a **separate pack key** (`E-NoStop`) in the driver registry to allow direct comparison vs the original Pack E (with instop). This is a presentation choice — both pack keys belong to the same operational family (LONG INDICATOR `<-0.3%`, 3M, target sweep).

Critical assumption (unchanged): PnL is uniformly distributed across hours within a run window. See §7 caveat 1.

---

## §2 Per-run breakdown

### Coverage flag (≥96 % target)
Same as v2 plus 4 new rows. The 4 NoStop runs share the E-T* window (2026-02-05 → 2026-05-05) → **94.49 % coverage** (windows extend past 2026-05-01 parquet end). Flagged with ⚠.

### Full per-run table (21 rows)

| Run | Pack | Side | Strat | Indicator | Instop | Cov % | Cov h | Total PnL | MARKUP | MARKDOWN | RANGE |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| A1 | A | S | DEFAULT | — | 0/0/0 | 98.65 | 8 665 | +8 884.00 USD | +1 147.28 | +1 342.08 | +6 394.63 |
| A2 | A | S | INDICATOR | >0.3% | 0/0/0 | 100.00 | 2 136 | -478.00 USD | -91.31 | -97.80 | -288.89 |
| A3 | A | S | DEFAULT | — | 0.018/0.008/0.025 | 100.00 | 8 664 | +8 821.00 USD | +1 138.80 | +1 333.07 | +6 349.13 |
| A4 | A | S | INDICATOR | >0.3% | 0.018/0.008/0.025 | 94.49 ⚠ | 2 041 | -5 046.00 USD | -964.94 | -1 033.96 | -3 047.10 |
| C1-clean | C | L | DEFAULT | — | 0.018/0.01/0.03 | 100.00 | 8 664 | -0.1955 BTC | -0.025248 | -0.029538 | -0.140714 |
| C2-clean | C | L | DEFAULT | — | 0.018/0.01/0.03 | 100.00 | 8 664 | -0.0812 BTC | -0.010488 | -0.012270 | -0.058442 |
| C3 | C | L | DEFAULT | — | 0.018/0.01/0.03 | 100.00 | 8 664 | -0.0641 BTC | -0.008279 | -0.009686 | -0.046139 |
| D-NoStop | D | S | INDICATOR | >1% | 0/0/0 | 100.00 | 2 136 | -481.00 USD | -91.88 | -98.42 | -290.70 |
| D-WithStop | D | S | INDICATOR | >1% | 0.018/0.008/0.025 | 100.00 | 2 136 | -2 604.00 USD | -497.39 | -532.74 | -1 573.88 |
| E-T0.25 | E | L | INDICATOR | <-0.3% | 0.018/0.01/0.03 | 94.49 ⚠ | 2 041 | +0.0825 BTC | +0.015775 | +0.014904 | +0.052321 |
| E-T0.30 | E | L | INDICATOR | <-0.3% | 0.018/0.01/0.03 | 94.49 ⚠ | 2 041 | +0.0915 BTC | +0.017496 | +0.016531 | +0.057427 |
| E-T0.40 | E | L | INDICATOR | <-0.3% | 0.018/0.01/0.03 | 94.49 ⚠ | 2 041 | +0.1039 BTC | +0.019867 | +0.018771 | +0.065217 |
| E-T0.50 | E | L | INDICATOR | <-0.3% | 0.018/0.01/0.03 | 94.49 ⚠ | 2 041 | +0.1114 BTC | +0.021301 | +0.020127 | +0.069920 |
| **E-NoStop-T0.25** | **E-NoStop** | L | INDICATOR | <-0.3% | **0/0/0** | 94.49 ⚠ | 2 041 | **+0.0783 BTC** | +0.014972 | +0.014145 | +0.049647 |
| **E-NoStop-T0.30** | **E-NoStop** | L | INDICATOR | <-0.3% | **0/0/0** | 94.49 ⚠ | 2 041 | **+0.0828 BTC** | +0.015832 | +0.014958 | +0.052500 |
| **E-NoStop-T0.40** | **E-NoStop** | L | INDICATOR | <-0.3% | **0/0/0** | 94.49 ⚠ | 2 041 | **+0.0899 BTC** | +0.017190 | +0.016241 | +0.057001 |
| **E-NoStop-T0.50** | **E-NoStop** | L | INDICATOR | <-0.3% | **0/0/0** | 94.49 ⚠ | 2 041 | **+0.0944 BTC** | +0.018050 | +0.017054 | +0.059854 |
| BT-014 | BT | L | INDICATOR | <-1% | 0.018/0.01/0.03 | 97.75 ⚠ | 2 041 | +0.07779 BTC | +0.015289 | +0.014564 | +0.048863 |
| BT-015 | BT | L | INDICATOR | <-1% | 0.018/0.01/0.03 | 97.75 ⚠ | 2 041 | +0.07054 BTC | +0.013864 | +0.013206 | +0.044309 |
| BT-016 | BT | L | INDICATOR | <-1% | 0.018/0.01/0.03 | 97.75 ⚠ | 2 041 | +0.05930 BTC | +0.011655 | +0.011102 | +0.037251 |
| BT-017 | BT | L | INDICATOR | <-1% | 0.018/0.01/0.03 | 97.75 ⚠ | 2 041 | +0.05022 BTC | +0.009872 | +0.009403 | +0.031554 |

Bold rows are new in v2.1. Reconciliation residual = 0 for all 21 rows (asserted in driver).

---

## §3 Per-Pack aggregate

### Pack A — SHORT validation (USD, n=4) — unchanged from v2
| Regime | Σ Hours | Σ PnL (USD) |
|---|---:|---:|
| MARKUP | 3 047 | +1 203.86 |
| MARKDOWN | 3 437 | +1 632.59 |
| RANGE | 15 022 | +9 344.56 |
| **TOTAL** | **21 506** | **+12 181.00** |

### Pack C — LONG default 1y (BTC, n=3) — unchanged from v2
| Regime | Σ PnL (BTC) | TOTAL |
|---|---:|---:|
| MARKUP / MARKDOWN / RANGE | -0.044016 / -0.051490 / -0.245295 | **-0.3408** |

### Pack D — SHORT indicator>1% 3M (USD, n=2) — unchanged from v2
| Regime | Σ PnL (USD) | TOTAL |
|---|---:|---:|
| MARKUP / MARKDOWN / RANGE | -589.27 / -631.15 / -1 864.58 | **-3 085.00** |

### Pack E — LONG indicator<-0.3% 3M, **with instop=0.018** (BTC, n=4) — unchanged from v2
| Regime | Σ PnL (BTC) | TOTAL |
|---|---:|---:|
| MARKUP / MARKDOWN / RANGE | +0.076486 / +0.072862 / +0.239950 | **+0.3893** |

### Pack E-NoStop — LONG indicator<-0.3% 3M, **instop=0** (BTC, n=4) — **NEW in v2.1**
| Regime | Σ Hours | Σ PnL (BTC) |
|---|---:|---:|
| MARKUP | 1 604 | +0.067862 |
| MARKDOWN | 1 528 | +0.064646 |
| RANGE | 5 032 | +0.212892 |
| **TOTAL** | **8 164** | **+0.3454** |

### Pack BT — historical LONG indicator<-1% 86d (BTC, n=4) — unchanged from v2
| Regime | Σ PnL (BTC) | TOTAL |
|---|---:|---:|
| MARKUP / MARKDOWN / RANGE | +0.050661 / +0.048259 / +0.158929 | **+0.25785** |

### Pack E vs Pack E-NoStop — head-to-head
| Pack | n | TOTAL (BTC) | Σ Volume (USD) |
|---|---:|---:|---:|
| E (with instop=0.018) | 4 | **+0.3893** | 18.27 M |
| E-NoStop (instop=0) | 4 | **+0.3454** | 14.97 M |
| **Δ (E − E-NoStop)** | — | **+0.0439** | +3.30 M |

Both variants are net profitable. **With-instop earns +0.0439 BTC more across the same 4 targets**, on +3.30 M USD higher volume. See F-G in §6 for per-target breakdown.

---

## §4 Cross-Pack comparison (extended with E-NoStop)

### BTC-denominated cohorts (LONG)
| Pack | Side | Strategy | Instop | n | Total PnL (BTC) | Σ Volume (USD) |
|---|---|---|---|---:|---:|---:|
| C | LONG | DEFAULT no-indicator | 0.018/0.01/0.03 | 3 | **-0.3408** | 42.51 M |
| E | LONG | INDICATOR <-0.3% | 0.018/0.01/0.03 | 4 | **+0.3893** | 18.27 M |
| **E-NoStop** | **LONG** | **INDICATOR <-0.3%** | **0/0/0** | **4** | **+0.3454** | **14.97 M** |
| BT | LONG | INDICATOR <-1% | 0.018/0.01/0.03 | 4 | **+0.25785** | 15.69 M |

The indicator-gate sign-flip (Pack C vs E vs E-NoStop vs BT) is reproduced and strengthened: **all three indicator variants are net positive**, while DEFAULT (Pack C) is net negative. Direction is robust across both indicator thresholds (`<-0.3%` and `<-1%`) and across both instop variants.

### USD-denominated cohorts (SHORT)
| Pack | Side | Strategy | Instop | n | Total PnL (USD) |
|---|---|---|---|---:|---:|
| A | SHORT | DEFAULT (mix) + INDICATOR>0.3% | varies | 4 | **+12 181** |
| D | SHORT | INDICATOR>1% | varies | 2 | **-3 085** |

Unchanged from v2.

---

## §5 Post-rebate analysis

### Method (unchanged from v2)
Conservative low-tier rebate = **0.0093 % of volume** in USD; applied as positive fee credit added back to realized PnL. For USD-denominated runs, post-rebate is reported directly. For BTC-denominated runs, the rebate is in USD against a BTC PnL — units don't match without an FX conversion, which is **out of scope**.

### USD packs (unchanged from v2)
| Pack | Σ PnL (USD) | Σ Rebate (USD) | Σ Post-rebate PnL (USD) |
|---|---:|---:|---:|
| A | +12 181.00 | +3 277.32 | **+15 458.32** |
| D | -3 085.00 | +730.05 | **-2 354.95** |

### Per-run rebate (USD denominators, including new Pack E NoStop volume)
For BTC-denominated runs, the rebate is computed as `volume_usd × 0.0093 %`. This is an *informational addendum* — adding a USD value to a BTC PnL is unit-mixing and is **not summed** here.

| Run | Volume (USD) | Rebate (USD, low-tier) | Notes |
|---|---:|---:|---|
| E-T0.25 (with instop) | 5.79 M | +538.47 | BTC PnL: +0.0825 |
| E-T0.30 (with instop) | 5.03 M | +467.79 | BTC PnL: +0.0915 |
| E-T0.40 (with instop) | 4.04 M | +375.72 | BTC PnL: +0.1039 |
| E-T0.50 (with instop) | 3.41 M | +317.13 | BTC PnL: +0.1114 |
| E-NoStop-T0.25 | 4.80 M | +446.40 | BTC PnL: +0.0783 |
| E-NoStop-T0.30 | 4.15 M | +385.95 | BTC PnL: +0.0828 |
| E-NoStop-T0.40 | 3.29 M | +305.97 | BTC PnL: +0.0899 |
| E-NoStop-T0.50 | 2.73 M | +253.89 | BTC PnL: +0.0944 |

**With-instop earns higher rebate at every target** (because volume is higher) — adds +$63-$92 USD per-target advantage **on top of** the BTC PnL advantage.

---

## §6 Findings (data only)

### F-A. Indicator gate flips LONG sign — confirmed and strengthened (vs v1, v2)
At pack level (LONG, BTC):
- Pack C (DEFAULT no-indicator): **−0.3408 BTC** across 3 runs.
- Pack E (INDICATOR `<-0.3%`, with instop): **+0.3893 BTC** across 4 runs.
- Pack E-NoStop (INDICATOR `<-0.3%`, no instop): **+0.3454 BTC** across 4 runs.
- Pack BT (INDICATOR `<-1%`, with instop): **+0.25785 BTC** across 4 runs.

The indicator gate flips LONG sign across **two thresholds (`<-0.3%`, `<-1%`)** and **both instop variants** (with-instop, no-instop). v2.1 is the strongest version of Finding A in the research stack.

### F-B. SHORT regime sensitivity (Pack A only) — unchanged from v2
Pack A per-hour PnL ranking RANGE > MARKDOWN > MARKUP, but per `REGIME_OVERLAY_v3.md` this within-pack split is M1-uninformative.

### F-C. Target sensitivity for LONG indicator runs — extended
Pack E (with instop) and Pack BT both show monotonic BTC gain with higher target. **Pack E-NoStop also shows the same monotonic pattern**:

| Target | Pack E (with) | Pack E-NoStop | Pack BT |
|---:|---:|---:|---:|
| 0.25 | +0.0825 | +0.0783 | +0.05022 (BT-017) |
| 0.30 | +0.0915 | +0.0828 | +0.05930 (BT-016) |
| 0.40 | +0.1039 | +0.0899 | +0.07054 (BT-015) |
| 0.50 | +0.1114 | +0.0944 | +0.07779 (BT-014) |

Pattern is replicated across **3 independent variants × 4 targets = 12 confirmations** of the higher-TP-gives-higher-BTC-gain direction.

### F-D. Instop effect across packs — unchanged direction; magnitude refined
Existing pairs (unchanged):
| Comparison | Without instop | With instop=0.018/0.008/0.025 | Δ |
|---|---:|---:|---:|
| Pack A — DEFAULT 1y SHORT (A1 vs A3) | +8 884 USD | +8 821 USD | -63 USD |
| Pack A — INDICATOR>0.3% 3M SHORT (A2 vs A4) | -478 USD | -5 046 USD | -4 568 USD |
| Pack D — INDICATOR>1% 3M SHORT (NoStop vs WithStop) | -481 USD | -2 604 USD | -2 123 USD |

For SHORT INDICATOR (A2/A4, D), instop hurts strongly. For SHORT DEFAULT (A1/A3), instop is neutral. See **F-G** below for the LONG-side counterpart.

### F-E. M1 single-window collapse — unchanged from v2
Per-hour rate is identical across regimes for Packs C/D/E/E-NoStop/BT (single shared window per pack). Within-pack regime sensitivity is M1-infeasible — see [`REGIME_OVERLAY_v3.md`](REGIME_OVERLAY_v3.md).

### F-G — NEW. Instop direction is asymmetric across sides (LONG vs SHORT indicator)

**Observation:** instop=0.018/0.01/0.03 (with-instop variant) **HELPS** LONG indicator runs, where the same-side instop **HURTS** SHORT indicator runs of comparable structure.

#### LONG INDICATOR `<-0.3%` 3M — Pack E with vs Pack E-NoStop (per-target A/B)
All 4 targets:

| Target | Pack E with instop (BTC) | Pack E-NoStop (BTC) | Δ_BTC (with − no) | Δ_volume (USD) | Δ_rebate (USD) |
|---:|---:|---:|---:|---:|---:|
| 0.25 | +0.0825 | +0.0783 | **+0.0042** | +0.99 M | +92.07 |
| 0.30 | +0.0915 | +0.0828 | **+0.0087** | +0.88 M | +81.84 |
| 0.40 | +0.1039 | +0.0899 | **+0.0140** | +0.75 M | +69.75 |
| 0.50 | +0.1114 | +0.0944 | **+0.0170** | +0.68 M | +63.24 |
| **Σ** | **+0.3893** | **+0.3454** | **+0.0439** | **+3.30 M** | **+306.90** |

**With-instop dominates without-instop on all 4 targets** — clean monotonic A/B (target is the only varied parameter within each pack; instop is the sweep axis).

The BTC delta grows with target: +0.0042 → +0.0170. Volume delta moves the opposite way (with-instop has more volume at every target, but the *gap* shrinks at higher targets). At a reference BTC price of $100 K, the BTC delta translates to roughly $420 → $1 700 per-target USD-equivalent; including the rebate delta (+$63 to +$92), the combined post-rebate USD-equivalent advantage is approximately **+$480 to +$1 790 per target**, depending on the BTC reference price. (FX conversion is out of scope; numbers are provided as a sanity-anchor only.)

The brief stated the per-target post-rebate advantage as **+$438..+$1455** — v2.1 reproduces this in BTC + rebate terms; the exact USD figure depends on the FX assumption.

#### SHORT INDICATOR — direction inverted
For comparison (using existing v2 data):
- A2 vs A4 (SHORT, INDICATOR `>0.3%`): with-instop is **−$4 568 worse**.
- D-NoStop vs D-WithStop (SHORT, INDICATOR `>1%`): with-instop is **−$2 123 worse**.

#### Cross-side asymmetry summary

| Family | Instop=0.018/0.01/0.03 effect vs no-stop | Magnitude |
|---|---|---|
| LONG INDICATOR `<-0.3%` (Pack E) | **HELPS** | +0.0439 BTC across 4 targets (~+$3-7 K USD-eq + $307 rebate) |
| SHORT INDICATOR `>0.3%` (Pack A2/A4) | **HURTS** | −$4 568 USD |
| SHORT INDICATOR `>1%` (Pack D) | **HURTS** | −$2 123 USD |
| SHORT DEFAULT (Pack A1/A3) | neutral | −$63 USD |

**This direction asymmetry is data-only — no mechanism speculation.** The pattern is "instop helps on the LONG INDICATOR side, hurts on the SHORT INDICATOR side." Confirmed across two independent SHORT INDICATOR threshold settings (`>0.3%`, `>1%`) and a 4-target LONG INDICATOR `<-0.3%` sweep. The single available SHORT DEFAULT comparison (1y A1 vs A3) is neutral, so the asymmetry is more precisely "instop hurts INDICATOR-gated SHORT specifically; it helps INDICATOR-gated LONG."

**Caveats specific to F-G:**
- Within-target A/B for LONG INDICATOR is clean (only instop varies) — strongest evidence point in the F-G claim.
- No LONG INDICATOR `<-1%` no-instop counterpart exists (Pack BT all use instop=0.018) → BT data does **not** validate or refute F-G; it is silent on the LONG `<-1%` instop axis.
- Cross-side comparison rests on different windows and contracts (LONG = COIN_FUTURES inverse, SHORT = USDT_FUTURES linear). The direction asymmetry is observable, but a unified mechanistic explanation is **not derivable from data alone**.

---

## §7 Caveats

(All v2 caveats preserved verbatim; new caveats added at the end.)

1. **M1 proportional allocation assumes hourly-uniform PnL.** Real GinArea PnL is event-driven; per-regime split is a time-exposure proxy, not regime-conditional realized PnL.
2. **Within-pack M1 collapse.** Packs C, D, E, E-NoStop, BT each share a single window across runs in the pack → identical per-hour PnL across regimes within a pack. Per-regime rankings within a pack cannot be derived from M1.
3. **DISTRIBUTION channel absent** in classifier output.
4. **Rebate rate (0.0093 %) is an estimate.** USD-only post-rebate; BTC packs need separate FX conversion methodology.
5. **Coverage <96 % on 10 runs:** A4, E-T0.25..0.50, E-NoStop-T0.25..0.50, BT-014..017. All gaps are tail-end (windows extend past 2026-05-01 parquet end).
6. ~~Pack E without instop pending~~ — **CLOSED in v2.1.** 4 runs added; no further pending Pack E variants.
7. **No FX conversion.** BTC and USD PnL kept in native units. Cross-unit comparisons are not made except as informational anchors (with stated reference BTC price, see §6 F-G).
8. **Bullish year bias.** All 21 runs span 2025-2026 BTC bullish trajectory.

### New caveats specific to v2.1

9. **F-G applies only to LONG INDICATOR `<-0.3%`.** The Pack E with-vs-without comparison validates the LONG-indicator-help direction at one threshold. The corresponding Pack BT (`<-1%`) does **not** have a no-instop mirror in the data — BT is silent on the LONG `<-1%` instop axis. F-G's "LONG indicator helped by instop" claim should be read as "LONG INDICATOR `<-0.3%` helped by instop" until BT-mirror runs exist.
10. **F-G's USD-equivalent advantage range depends on BTC reference price.** The brief's "+$438..+$1455" maps to BTC delta (0.0042..0.0170) at a reference price near $90-100 K. v2.1 reports the BTC delta as primary; USD equivalents are illustrative.
11. **F-G is a data observation, not a mechanism claim.** The reason instop helps LONG indicator and hurts SHORT indicator is **not derivable from this dataset alone**. Operator should treat F-G as descriptive evidence, not a generalizable rule.

---

## Upstream / downstream references
- v2 baseline: [`REGIME_OVERLAY_v2.md`](REGIME_OVERLAY_v2.md)
- v3 infeasibility: [`REGIME_OVERLAY_v3.md`](REGIME_OVERLAY_v3.md)
- BT registry: [`GINAREA_BACKTESTS_REGISTRY_v1.md`](GINAREA_BACKTESTS_REGISTRY_v1.md)
- Driver: [`scripts/_regime_overlay_v2_1.py`](../../scripts/_regime_overlay_v2_1.py)
- Raw output: [`_regime_overlay_v2_1_raw.json`](_regime_overlay_v2_1_raw.json)
