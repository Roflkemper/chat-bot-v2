# Trading Regulation v0.1.1

**Status:** DRAFT — operational regulation, fresh rewrite.
**Date:** 2026-05-05
**Supersedes:** [`REGULATION_v0_1.md`](REGULATION_v0_1.md). v0.1 is preserved; v0.1.1 is a fresh-rewrite addressing 4 explicit fixes from CP review.
**Scope:** which bot configurations to deploy, when to activate them per market regime, with explicit evidence references and confidence levels.
**Out of scope:** P8 implementation code, live deployment plans, sizing v0.1 changes (locked elsewhere), bot UID schema decisions.

**Foundation evidence (read-only inputs):**
- [`docs/RESEARCH/REGIME_OVERLAY_v2_1.md`](RESEARCH/REGIME_OVERLAY_v2_1.md) — primary, 21 runs, F-G instop asymmetry finding.
- [`docs/RESEARCH/REGIME_OVERLAY_v3.md`](RESEARCH/REGIME_OVERLAY_v3.md) — sub-window infeasibility flag (within-pack regime sensitivity unverifiable under M1).
- [`docs/RESEARCH/TRANSITION_MODE_COMPARE_v2.md`](RESEARCH/TRANSITION_MODE_COMPARE_v2.md) — H=1 sign-conditional transition policy.
- [`docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md`](RESEARCH/HYSTERESIS_CALIBRATION_v1.md) — H=1 calibration (TRANSITION = 7.35 % of year).
- [`docs/RESEARCH/REGIME_PERIODS_2025_2026.md`](RESEARCH/REGIME_PERIODS_2025_2026.md) — regime distribution baseline.

**Fixes applied vs v0.1 (per CP review):**
- **FIX 1** — §2: LONG taxonomy split into "LONG range" (Pack E, `<-0.3%`) and "LONG far" (Pack BT, `<-1%`) as **distinct** configurations with separate evidence, **not** merged via "higher target" axis.
- **FIX 2** — §1.3 + §3: SHORT default activation rule rephrased to rest on overall pack positivity + RANGE-dominance-of-the-year, **not** on within-pack regime split (which `REGIME_OVERLAY_v3.md` blocks).
- **FIX 3** — §5: Pack E order_count corrected to **5 000** (not 800). 800 belongs to BT-014..017 only.
- **FIX 4** — §2 + §3 + §7: Pack E with-vs-without instop comparison (F-G finding from v2.1) integrated. LONG range configuration explicitly prefers `instop=0.018/0.01/0.03` over `instop=0`, with quantified per-target advantage. §7 acknowledges direction asymmetry vs SHORT INDICATOR (where instop hurts).

---

## §1 Data coverage and limitations

### What's in the dataset (v2.1 baseline)
**21 GinArea-realized runs** across 6 pack keys:
- Pack A (4): SHORT — DEFAULT 1y (A1, A3) + INDICATOR `>0.3%` 3M (A2, A4).
- Pack C (3): LONG DEFAULT 1y, no indicator.
- Pack D (2): SHORT INDICATOR `>1%` 3M.
- Pack E (4): LONG INDICATOR `<-0.3%` 3M, **with instop=0.018/0.01/0.03**.
- Pack E-NoStop (4, **new in v2.1**): LONG INDICATOR `<-0.3%` 3M, **instop=0/0/0**.
- Pack BT (4): historical LONG INDICATOR `<-1%` 86d, with instop=0.018/0.01/0.03.

### Year regime distribution
| Regime | Hours | % year | Episodes |
|---|---:|---:|---:|
| RANGE | 6 317 | **72.1 %** | 323 |
| MARKDOWN | 1 309 | 14.9 % | 175 |
| MARKUP | 1 135 | 13.0 % | 147 |
| **DISTRIBUTION** | 0 | 0.0 % | classifier emits 3 labels only |

Source: [`REGIME_PERIODS_2025_2026.md`](RESEARCH/REGIME_PERIODS_2025_2026.md) §1. Mean episode 13.6 h; median trending episode 3 h; zero direct MARKUP↔MARKDOWN transitions.

### What this regulation may claim
**Cross-pack directional findings only.** Specifically:
1. Indicator gate flips LONG sign (Pack C −0.34 BTC vs Pack E +0.39 BTC vs Pack E-NoStop +0.35 BTC vs Pack BT +0.26 BTC).
2. SHORT DEFAULT 1y is overall positive (Pack A +12 181 USD).
3. SHORT INDICATOR is overall negative (Pack A2/A4 + Pack D, all 4 losing).
4. F-G — instop direction is asymmetric across sides: helps LONG INDICATOR `<-0.3%`, hurts SHORT INDICATOR.

### What this regulation must NOT claim
1. **No within-pack regime sensitivity claims.** Per [`REGIME_OVERLAY_v3.md`](RESEARCH/REGIME_OVERLAY_v3.md): hours-proportional sub-window allocation is algebraically identical to direct M1 year-level allocation. All 70 sub-windows in the v3 dataset are RANGE-dominant (>50 % RANGE) — no MARKUP- or MARKDOWN-dominant sub-window exists. **The regulation must not say "Pack X is best in regime Y" or "the SHORT default bot is strongest in RANGE because the within-pack split shows it" — those claims are M1-infeasible.** SHORT default's RANGE activation in §3 below rests on **a different argument**: overall pack positivity + RANGE-dominance-of-the-year, not within-pack split.
2. **No DISTRIBUTION rules** (classifier doesn't emit it).
3. **No bear-market rules** (dataset is bullish-only).
4. **No cross-asset rules** (BTC only).

### Coverage flag
10 of 21 runs have coverage <96 % (A4, E-T*, E-NoStop-T*, BT-014..017). All gaps are tail-end (windows extend past 2026-05-01 parquet end). Magnitude: 4 days for E/A4, 2 days for BT. PnL impact small but non-zero.

---

## §2 Optimal bot configurations (per evidence)

### Production parameter convention
- **Order count column shows production target.** Production caps at `200/220` per side (locked elsewhere).
- **Backtest order_count varied** — Pack A used 5 000, Pack C used 5 000, Pack D used 5 000, **Pack E used 5 000**, Pack BT used 800. The order_count delta is acknowledged in §5.
- **Contract:** LONG = COIN_FUTURES (inverse, BTC-denominated); SHORT = USDT_FUTURES (linear, USD-denominated).

### Configuration table

| Cfg-ID | Purpose | Side | Strategy | Indicator | Target | gs | Instop / Min / Max | Order count (prod) | Evidence | Confidence |
|---|---|---|---|---|:---:|:---:|---|:---:|---|:---:|
| **CFG-L-RANGE** | LONG range (indicator-gated, balanced TP) | LONG | INDICATOR | **< −0.3 %** | 0.30 (or 0.40 for higher BTC capture) | 0.03 | **0.018 / 0.01 / 0.03 (preferred)** | 220 | Pack E (n=4, +0.0825 → +0.1114 BTC); Pack E-NoStop (n=4, +0.0783 → +0.0944 BTC) — **F-G: with-instop dominates no-instop on all 4 targets** | **HIGH** |
| **CFG-L-FAR** | LONG far (deeper-trigger indicator, longer hold) | LONG | INDICATOR | **< −1.0 %** | 0.50 (or 0.40) | 0.03 | 0.018 / 0.01 / 0.03 | 220 | Pack BT (BT-014..017, n=4, +0.05022 → +0.07779 BTC over 86 d) | **HIGH** |
| **CFG-S-RANGE-DEFAULT** | SHORT range/default (no indicator, 1y validated) | SHORT | DEFAULT | n/a | n/a (TP=0.25 in BT mirror) | 0.03 | 0/0/0 OR 0.018/0.008/0.025 (instop neutral) | 200 | Pack A1 (+8 884 USD, no instop) and A3 (+8 821 USD, with instop) — instop neutral | **HIGH** |
| ~~CFG-S-INDICATOR~~ (suspended) | SHORT indicator-gated | SHORT | INDICATOR | `>0.3%` or `>1%` | n/a | 0.03 | varies | — | Pack A2/A4 (loss); Pack D (loss). 4/4 losing across two thresholds | **DO NOT DEPLOY** |
| ~~CFG-L-DEFAULT~~ (suspended) | LONG no-indicator | LONG | DEFAULT | n/a | 0.25/0.30/0.40 | 0.03 | 0.018/0.01/0.03 | — | Pack C (n=3, all losses −0.0641 → −0.1955 BTC) | **DO NOT DEPLOY** |

### Instop preference for CFG-L-RANGE (FIX 4)
Per F-G in [`REGIME_OVERLAY_v2_1.md`](RESEARCH/REGIME_OVERLAY_v2_1.md) §6: with-instop dominates no-instop on all 4 targets:
| Target | with-instop (BTC) | no-instop (BTC) | Δ_BTC | Δ_volume (USD) | Δ_rebate (USD low-tier) |
|---:|---:|---:|---:|---:|---:|
| 0.25 | +0.0825 | +0.0783 | +0.0042 | +0.99 M | +92.07 |
| 0.30 | +0.0915 | +0.0828 | +0.0087 | +0.88 M | +81.84 |
| 0.40 | +0.1039 | +0.0899 | +0.0140 | +0.75 M | +69.75 |
| 0.50 | +0.1114 | +0.0944 | +0.0170 | +0.68 M | +63.24 |
| **Σ** | **+0.3893** | **+0.3454** | **+0.0439** | **+3.30 M** | **+306.90** |

**Rule:** CFG-L-RANGE deploys with `instop=0.018 / min_stop=0.01 / max_stop=0.03`, NOT with `instop=0`.

### Why CFG-L-RANGE and CFG-L-FAR are kept distinct (FIX 1)
The two LONG configurations differ on the **indicator threshold axis**, not the target axis:
- **CFG-L-RANGE** → indicator `<-0.3%` (Pack E). Triggers more frequently; higher volume, higher BTC PnL across the 3M window.
- **CFG-L-FAR** → indicator `<-1.0%` (Pack BT). Triggers less frequently (deeper drawdown required); lower volume per same time window, but earns positive BTC over 86 days.

These are two different operational bots — operator may run them in parallel or pick one. They are **not collapsed** under a "higher-target" axis. Within each, the target sweep (0.25..0.50) is a separate tuning dimension.

### Confidence ladder
- **HIGH:** ≥3 clean runs in pack confirming sign and direction; or cross-pack replication.
- **DO NOT DEPLOY:** ≥2 independent losing runs with no profitable counter-evidence.

### Pack-level evidence summary
| Pack | n | Total PnL | Σ Volume | Sign | Use in regulation |
|---|---:|---:|---:|---|---|
| A | 4 | +12 181 USD | 35.24 M | mixed | ✅ CFG-S-RANGE-DEFAULT |
| BT | 4 | +0.25785 BTC | 15.69 M | + (4/4) | ✅ CFG-L-FAR |
| C | 3 | −0.3408 BTC | 42.51 M | − (3/3) | ❌ CFG-L-DEFAULT suspended |
| D | 2 | −3 085 USD | 7.85 M | − (2/2) | ❌ CFG-S-INDICATOR suspended |
| E | 4 | +0.3893 BTC | 18.27 M | + (4/4) | ✅ CFG-L-RANGE (with instop) |
| E-NoStop | 4 | +0.3454 BTC | 14.97 M | + (4/4) | comparator for F-G; CFG-L-RANGE prefers instop variant |

---

## §3 Activation rules per regime

### Activation matrix
| Configuration | RANGE | MARKUP | MARKDOWN |
|---|:---:|:---:|:---:|
| **CFG-L-RANGE** (LONG, INDICATOR `<-0.3%`, instop=0.018) | **ON** | **ON** | **CONDITIONAL** |
| **CFG-L-FAR** (LONG, INDICATOR `<-1%`, instop=0.018) | **ON** | **ON** | **CONDITIONAL** |
| **CFG-S-RANGE-DEFAULT** (SHORT, DEFAULT, no indicator) | **ON** | **CONDITIONAL** | **CONDITIONAL** |
| ~~CFG-S-INDICATOR~~ | OFF | OFF | OFF (CONDITIONAL hypothesis-flag for monitoring only) |
| ~~CFG-L-DEFAULT~~ | OFF | OFF | OFF |

### Rule basis (FIX 2 — internal consistency with §1.3)

#### CFG-L-RANGE / CFG-L-FAR — ON in MARKUP and RANGE, CONDITIONAL in MARKDOWN
**Evidence:** Pack E (4/4 profitable, +0.3893 BTC), Pack E-NoStop (4/4 profitable, +0.3454 BTC), and Pack BT (4/4 profitable, +0.25785 BTC) span entire 3M / 86d windows that include all three regime labels. The bots were **on through all three regimes** in the validation runs and the packs are net positive overall.

**Why MARKUP and RANGE are ON:** the packs are net positive and there is no contrary pack-level evidence. Activation in these regimes is licensed by overall-pack positivity, not by within-pack split.

**Why MARKDOWN is CONDITIONAL:** the bullish-year dataset over-weights MARKUP-favorable conditions; no pure-MARKDOWN window exists for clean validation. Per [`REGIME_OVERLAY_v3.md`](RESEARCH/REGIME_OVERLAY_v3.md), within-pack regime sensitivity is M1-infeasible — we cannot specifically validate "LONG INDICATOR is profitable in MARKDOWN" within Pack E. CONDITIONAL means: deploy with monitoring; pause if MARKDOWN-share live realization deviates negatively from the pack baseline.

**Sub-rule (FIX 4):** CFG-L-RANGE deploys with `instop=0.018/0.01/0.03`, not `instop=0`. CFG-L-FAR likewise (Pack BT all use instop=0.018; no no-instop mirror exists for Pack BT).

#### CFG-S-RANGE-DEFAULT — ON in RANGE, CONDITIONAL in MARKUP/MARKDOWN

**FIX 2 — rephrased to be consistent with §1.3.**

**Evidence basis (corrected):** Pack A1 (+8 884 USD) and A3 (+8 821 USD) are the only profitable SHORT runs in the dataset. Pack A1+A3 covers a 1y window in which 72.1 % of hours are RANGE.

**Rule:** RANGE is ON because (a) Pack A is overall net-profitable (+12 181 USD aggregate), (b) RANGE is the dominant regime of the year (72.1 %), and (c) most of the 1y validation window was spent in RANGE. **The argument is "Pack A is profitable on a 1y window dominated by RANGE; RANGE is the modal regime to expect at runtime; therefore activate."** The argument is **not** "the within-pack regime split shows RANGE per-hour outperforms" — that within-pack claim is M1-infeasible per §1.3.

MARKUP and MARKDOWN are CONDITIONAL because Pack A1+A3 evidence does not specifically validate trend-regime performance for SHORT DEFAULT, and the M1 split that would otherwise rank regimes is unreliable. CONDITIONAL = deploy with bounded loss limits and pause if trend-regime live realization deviates negatively.

#### CFG-S-INDICATOR / CFG-L-DEFAULT — OFF
Pack D + Pack A2/A4: 4/4 losing across two thresholds and two instop variants → CFG-S-INDICATOR suspended.
Pack C: 3/3 losing across a 1y window → CFG-L-DEFAULT suspended; the indicator gate (Pack E vs Pack C) is what flips LONG sign.

The MARKDOWN-conditional flag for CFG-S-INDICATOR is retained as a **monitoring hypothesis only**, not a deployable rule. Predicted MARKDOWN profitability is not validated; Pack A2/A4/D windows include MARKDOWN hours and the bots still lost overall.

### Cross-rule constraint
Per [`REGIME_PERIODS_2025_2026.md`](RESEARCH/REGIME_PERIODS_2025_2026.md) §3, MARKUP↔MARKDOWN direct transitions are **zero in the dataset**. Every trend-to-trend flip routes through RANGE. The regulation does not need a direct MARKUP→MARKDOWN handler.

---

## §4 Transition behavior (post-H=1 calibration) — preserved from v0.1

### Calibrated TRANSITION rate
Per [`HYSTERESIS_CALIBRATION_v1.md`](RESEARCH/HYSTERESIS_CALIBRATION_v1.md): hysteresis `H = 1` → **TRANSITION = 7.35 %** of year (644 / 8 761 hours), mean segment 1.3 h. The original H=12 result (46.5 %) was a definitional artifact.

### Sign-conditional transition policy
Per [`TRANSITION_MODE_COMPARE_v2.md`](RESEARCH/TRANSITION_MODE_COMPARE_v2.md) §6, at calibrated H=1:
- For **net-profitable packs**, pause/reduce policies forfeit gain.
- For **net-loss packs**, pause/reduce recovers some loss.
- No universal global-pause policy improves all families.

### Operational rule — preserved verbatim
**Each bot stays at its §3 activation rule during TRANSITION.** No global "pause everything during transitions."

Reasoning chain:
1. TRANSITION is rare (7 % of year, mean 1.3 h).
2. Suspended configs are off everywhere — TRANSITION rule is moot for them.
3. Approved configs (CFG-L-RANGE, CFG-L-FAR, CFG-S-RANGE-DEFAULT) are net-profitable; their TRANSITION-allocated PnL is positive under M1; pausing forfeits gain.
4. Therefore: per-bot conditional behavior, no global pause.

### Caveats on the no-pause rule
- Rests on M1 hourly-uniformity (see §7).
- If a bot's realized performance turns net-negative for any reason, the sign flips and pause/reduce becomes applicable. Performance-state-conditional, not just configuration-conditional.

---

## §5 Production parameter constraints (FIX 3 applied)

### Order count (production vs backtest)
| Pack | Backtest order count | Production order count |
|---|---:|---:|
| Pack A (1y SHORT DEFAULT + 3M INDICATOR) | 5 000 | **200** |
| Pack C (1y LONG DEFAULT) — *suspended* | 5 000 | n/a |
| Pack D (3M SHORT INDICATOR) — *suspended* | 5 000 | n/a |
| **Pack E (3M LONG INDICATOR)** | **5 000** | **220** |
| **Pack E-NoStop (3M LONG INDICATOR no-instop)** | **5 000** | **220** |
| Pack BT (86d LONG INDICATOR `<-1%`) | **800** | **220** |

**FIX 3 confirmation:** Pack E and E-NoStop ran with `order_count = 5000` in backtest, NOT 800. The 800 figure applies only to Pack BT (BT-014..017). Earlier v0.1 noted Pack E "evidence `800`" — that was incorrect; v0.1.1 corrects it.

### Risk note
The order count delta (5 000 → 200/220) is significant for **all approved configurations**. Backtests with 5 000 orders may have benefited from never hitting a max-orders bind during heavy grid activity. Production order_count caps at 200/220 may bind during prolonged drawdown phases. **This is an unmodelled risk** — open question in §8.

### Other parameters
- TP, gs, indicator threshold, instop / min_stop / max_stop are production-equivalent to backtest.
- order_size: BTC for USDT_FUTURES (linear) = 0.001 BTC in backtests; production setting must be confirmed by operator.
- P&L Trail: all approved configs use Trail OFF.

---

## §6 Rebate-aware PnL projections — preserved methodology

### Rate ladder
- **Conservative low-tier:** 0.0093 % of volume (binding for decisions).
- **Mid-tier estimate:** 0.015 % (operator-supplied estimate, not validated in source).
- **High-tier estimate:** 0.020 % (operator-supplied estimate, not validated in source).

### USD-pack projections
**CFG-S-RANGE-DEFAULT (Pack A1+A3, 1y avg):**
| Tier | Annual rebate (USD) | Annual PnL pre-rebate | Annual PnL post-rebate |
|---|---:|---:|---:|
| Low (0.0093 %) | +1 298 | +8 853 | **+10 150** |
| Mid (0.015 %)* | +2 092 | +8 853 | +10 945 |
| High (0.020 %)* | +2 790 | +8 853 | +11 643 |

*Mid/High are unvalidated estimates; bind decisions to low-tier only.*

### BTC-pack projections (FX gap)
The rebate is paid in USD against a BTC-denominated PnL — **mixing units requires FX conversion methodology that is out of scope for v0.1.1.** Raw BTC projections (no rebate, simple annualization where applicable):

| Config | Pack basis | Window basis | Annualized BTC PnL projection |
|---|---|---|---|
| CFG-L-RANGE @ T=0.30 | E-T0.30 | 3M (90d) | +0.0915 × (365/90) ≈ **+0.371 BTC/yr** |
| CFG-L-RANGE @ T=0.50 | E-T0.50 | 3M | +0.1114 × (365/90) ≈ **+0.452 BTC/yr** |
| CFG-L-FAR @ T=0.40 | BT-015 | 86d | +0.07054 × (365/86) ≈ **+0.299 BTC/yr** |
| CFG-L-FAR @ T=0.50 | BT-014 | 86d | +0.07779 × (365/86) ≈ **+0.330 BTC/yr** |

Per-target BTC differential between with-instop and no-instop (CFG-L-RANGE only):
| Target | Δ_BTC (with − no) | Annualized Δ from 3M | Δ Rebate (USD low-tier) |
|---:|---:|---:|---:|
| 0.25 | +0.0042 | +0.017 BTC/yr | +92 USD |
| 0.30 | +0.0087 | +0.035 BTC/yr | +82 USD |
| 0.40 | +0.0140 | +0.057 BTC/yr | +70 USD |
| 0.50 | +0.0170 | +0.069 BTC/yr | +63 USD |

⚠ Annualization assumes the 3M / 86d window's per-time PnL repeats over a full year. Strong assumption.

### Conservative vs aggressive scenarios
**Conservative** (CFG-S-RANGE-DEFAULT only, low-tier rebate, no annualization-of-3M-results):
- Expected USD: ~+10 150 / yr.
- Expected BTC: 0.

**Aggressive** (CFG-S-RANGE-DEFAULT + CFG-L-RANGE @ T=0.30 + CFG-L-FAR @ T=0.50, low-tier rebate where applicable, 3M results annualized):
- Expected USD: ~+10 150 / yr.
- Expected BTC: ~+0.371 + 0.330 = ~+0.701 BTC/yr.

⚠ Aggressive scenario stacks two indicator-gated LONG configs with different thresholds (`<-0.3%`, `<-1%`) — they may exhibit positively-correlated activations on the same price events. **Portfolio-level interaction is unmodelled.**

---

## §7 Known limitations

1. **M1 hourly-uniform PnL assumption.** All allocations assume PnL distributes uniformly across hours within a run window. Real GinArea PnL is event-driven. No bar-level trade logs available → no M2 upgrade.
2. **Order_count downscale (5 000 → 200/220) is unmodelled.** Affects all approved configurations. If 200/220 binds during drawdown, production may underperform backtest.
3. **DISTRIBUTION absent from classifier.** Re-evaluate regulation if classifier is later expanded.
4. **SHORT INDICATOR profitability in MARKDOWN unverified** — predicted but contradicted by Pack A2/A4 + Pack D (4/4 losing including their MARKDOWN time-share).
5. **Bullish year only (2025-05 → 2026-05).** Pure-bear-market behavior not validated for any configuration.
6. **Single asset (BTC).** XRP / ETH / other-pair behavior not tested.
7. **Within-pack regime sensitivity is M1-infeasible** per [`REGIME_OVERLAY_v3.md`](RESEARCH/REGIME_OVERLAY_v3.md). The "best regime for Bot X within Pack Y" question is unanswerable from this evidence.
8. **Coverage <96 % on 10 runs** (A4, E-T*, E-NoStop-T*, BT-014..017). All gaps tail-end.
9. **Mid/High rebate tiers are estimates, not data.** Bind decisions to low-tier 0.0093 % only.
10. **TRANSITION-mode policy depends on M1 sign assumption** (see §4).
11. **No portfolio-level interaction modelled** (§6 aggressive scenario disclaimer).

### New limitations specific to v0.1.1

12. **F-G instop direction asymmetry is observed but not mechanistically explained.** Per [`REGIME_OVERLAY_v2_1.md`](RESEARCH/REGIME_OVERLAY_v2_1.md) §6 F-G:
    - **LONG INDICATOR `<-0.3%` (Pack E):** instop=0.018 **HELPS** (+0.0439 BTC across 4 targets, ~+$3-7 K USD-equivalent + $307 rebate).
    - **SHORT INDICATOR `>0.3%` (A2/A4):** instop=0.018 **HURTS** (−$4 568).
    - **SHORT INDICATOR `>1%` (D):** instop=0.018 **HURTS** (−$2 123).
    - **SHORT DEFAULT (A1/A3):** instop=0.018 neutral (−$63).
    The cross-side direction asymmetry is **data-only**, not derived from a mechanism. Any extension of the instop-helps rule to a new family (e.g. LONG INDICATOR `<-1%`, or any cross-asset variant) requires new evidence; F-G must not be generalized blindly.
13. **F-G's LONG-helps direction is validated only for the `<-0.3%` threshold.** Pack BT (`<-1%`) has no no-instop mirror in the dataset → BT is silent on whether instop helps or hurts CFG-L-FAR. The CFG-L-FAR instop choice in §2 (instop=0.018) is taken from BT's actual configuration, **not** from a comparative A/B. This means CFG-L-FAR uses the same instop as BT but the direction is unverified relative to `instop=0`.
14. **Forecast block decommissioned (TZ-FORECAST-DECOMMISSION, 2026-05-05).** This regulation is independent of any forecast input. The activation matrix in §3 depends only on the regime classifier, not on forecast probabilities. Any future regulation revision that wants to admit forecast-driven rules must first establish positive Brier-decomposition evidence (resolution > 0; calibrated test Brier < 0.22). See [`FORECAST_CALIBRATION_DIAGNOSTIC_v1.md`](RESEARCH/FORECAST_CALIBRATION_DIAGNOSTIC_v1.md) for the diagnostic that retired the previous model.

---

## §8 Open questions for next iteration

These are evidence gaps the regulation cannot currently answer.

### O1 — Bear-market validation
Do CFG-L-RANGE, CFG-L-FAR, and CFG-S-RANGE-DEFAULT survive a sustained downtrend? Method: identify a clean bear window in BTC history and re-run.

### O2 — SHORT INDICATOR MARKDOWN validation
Is `SHORT INDICATOR > X%` profitable in pure MARKDOWN, or is the prediction false? Method: bear/MARKDOWN-restricted backtest, OR M2 with bar-level trade logs.

### O3 — LONG INDICATOR `<-1%` no-instop comparison (open in v0.1.1)
Pack BT (BT-014..017) all use `instop=0.018/0.01/0.03`. **There is no no-instop mirror for the `<-1%` threshold.** F-G validates the LONG-helps direction at `<-0.3%` only. Open question: does instop also help for `<-1%`? Method: 4 new GinArea backtests mirroring BT-014..017 with `instop=0/0/0`.

### O4 — Cross-asset transferability
Do CFG-L-RANGE and CFG-S-RANGE-DEFAULT work on XRP, ETH, or other liquid pairs? Method: replicate Pack E and Pack A on at least one other pair.

### O5 — Mid/High-tier rebate validation
Are 0.015 % and 0.020 % correct for the operator's actual fee tier? Operator-side question to GinArea/exchange.

### O6 — M2 within-pack regime sensitivity
The deep question. Requires bar-level GinArea trade logs OR hourly equity curve dumps. Per [`REGIME_OVERLAY_v3.md`](RESEARCH/REGIME_OVERLAY_v3.md) §6, this is what blocks all within-pack claims.

### O7 — TRANSITION-aware sizing sweep
If sizing reduction is adopted (Policy C in `TRANSITION_MODE_COMPARE_v2`), is 0.5 the right multiplier? Sweep `TRANSITION_SIZE_MULT ∈ {0.25, 0.5, 0.75, 1.0}`.

### O8 — Order_count = 200 vs 5 000 effect
Re-run Pack A1 (or any approved config) with `order_count = 200` in backtest, compare to the 5 000-order baseline. Critical for converting backtest PnL projections to production-realistic numbers.

### O9 — Portfolio-level interaction
When CFG-L-RANGE + CFG-L-FAR + CFG-S-RANGE-DEFAULT run simultaneously, what is the correlation structure of activations? Beyond v0.1.1 scope.

### O10 — F-G mechanism / generalization (new in v0.1.1)
What causes the LONG-helps / SHORT-hurts asymmetry? Method: bar-level analysis to identify whether instop activation timing differs by side, or whether the asymmetry is contract-side artifact (COIN_FUTURES vs USDT_FUTURES). Until answered, F-G remains a **data observation**, not a generalizable rule.

---

## §9 Versioning and revision policy

**v0.1.1** — fresh rewrite addressing 4 CP-review fixes. Differences from v0.1:
- §2: LONG split into CFG-L-RANGE and CFG-L-FAR (FIX 1).
- §3: SHORT default activation argued from overall pack positivity + RANGE-dominance, not within-pack split (FIX 2).
- §5: Pack E order_count corrected to 5 000 (FIX 3).
- §2/§3/§7: Pack E with-vs-without instop integration; instop=0.018 preferred for CFG-L-RANGE (FIX 4).

**Revision triggers (unchanged from v0.1):**
1. Any open question (O1-O10) closed with new evidence.
2. Classifier expanded to include DISTRIBUTION.
3. New GinArea runs that materially change confidence levels.
4. Live-realized PnL deviates from evidence-projected PnL by more than 30 % over a 30-day rolling window.

---

## Appendix: evidence-to-configuration cross-reference

| Configuration | Primary evidence | Cross-pack validation | Suspended? |
|---|---|---|:---:|
| CFG-L-RANGE | Pack E with-instop (4 runs) | Pack E-NoStop (no-stop comparator); F-G validates instop preference | — |
| CFG-L-FAR | Pack BT (BT-014..017, 4 runs) | Pack E replicates LONG-INDICATOR sign at `<-0.3%`; instop direction at `<-1%` is unverified (O3) | — |
| CFG-S-RANGE-DEFAULT | Pack A1, A3 | None in dataset (1y SHORT DEFAULT is unique) | — |
| CFG-S-INDICATOR | Pack A2, A4 + Pack D | All 4 runs negative; no positive counter-evidence | **YES** |
| CFG-L-DEFAULT | Pack C (3 runs) | Replicates v1 Finding A | **YES** |

---

## Document index
- [§1 Data coverage and limitations](#1-data-coverage-and-limitations)
- [§2 Optimal bot configurations (per evidence)](#2-optimal-bot-configurations-per-evidence)
- [§3 Activation rules per regime](#3-activation-rules-per-regime)
- [§4 Transition behavior (post-H=1 calibration)](#4-transition-behavior-post-h1-calibration--preserved-from-v01)
- [§5 Production parameter constraints (FIX 3 applied)](#5-production-parameter-constraints-fix-3-applied)
- [§6 Rebate-aware PnL projections](#6-rebate-aware-pnl-projections--preserved-methodology)
- [§7 Known limitations](#7-known-limitations)
- [§8 Open questions for next iteration](#8-open-questions-for-next-iteration)
- [§9 Versioning and revision policy](#9-versioning-and-revision-policy)
