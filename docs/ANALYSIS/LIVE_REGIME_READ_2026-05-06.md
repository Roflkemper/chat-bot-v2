# LIVE REGIME READ — 2026-05-06

**Type:** READ-ONLY ANALYTICAL (TZ-ANALYTICAL-A-LIVE-REGIME-READ)
**Read time:** 2026-05-06 11:09 UTC (state file mtime)
**Source paths:** [`state/regime_state.json`](../../state/regime_state.json) (live, Classifier A) + foundation files cited inline.

This document compiles facts only — no trade advice, no forecasts, no instructions.

---

## §1 Operator position context

Single SHORT position used as analytical anchor. Numbers from operator's BitMEX UI 2026-05-06 11:32 UTC+3:

| Field | Value |
|---|---|
| Symbol / direction | BTCUSDT linear, **SHORT** |
| Size | 1.416 BTC |
| Entry | ~79,036 |
| Mark | 81,610 |
| Unrealized PnL | −3,572 USD |
| Liquidation | 96,497 |
| Distance to liq | ~18.0% |
| Margin coefficient | 0.97 |
| Funding | −0.0082%/8h favoring SHORT (~$28/day to operator) |
| Operator stated target exit | 77–79k |

A small +6,300 USD inverse LONG (PnL ≈ 0) exists in parallel and is excluded from this analysis as a hedge/experiment.

---

## §2 What Classifier A reports right now

Read from [`state/regime_state.json`](../../state/regime_state.json) at 2026-05-06 11:09 UTC; symbol BTCUSDT.

**Live values (verbatim):**

| Field | Value |
|---|---|
| `current_primary` (6-state) | **RANGE** |
| `primary_since` | 2026-05-06T09:01:13Z |
| `regime_age_bars` | **5** (≈5 hours since RANGE began) |
| `pending_primary` | `null` |
| `hysteresis_counter` | 0 |
| `active_modifiers` | `POST_FUNDING_HOUR`, `WEEKEND_LOW_VOL`, `WEEKEND_GAP_DETECTED` |

**3-state projection** (per [`docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md`](../DESIGN/CLASSIFIER_AUTHORITY_v1.md) §1):

```
RANGE (Classifier A) → RANGE (3-state)
```

So in the foundation taxonomy used by `REGIME_PERIODS_2025_2026` and `REGULATION_v0_1_1` §3, the current regime is **RANGE**.

---

## §3 Where this episode sits in the 1y RANGE distribution

From [`docs/RESEARCH/REGIME_PERIODS_2025_2026.md`](../RESEARCH/REGIME_PERIODS_2025_2026.md) §2 (1y window, 2025-05-01 → 2026-05-01):

| Regime | Episodes | Mean (h) | Median (h) | p25 | p75 | p90 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| MARKUP | 147 | 7.7 | 3 | 1 | 13 | 23 | 38 |
| MARKDOWN | 175 | 7.5 | 3 | 1 | 10 | 23 | 43 |
| **RANGE** | **323** | **19.6** | **8** | **2** | **22** | **57** | **179** |

Current RANGE age = **5 hours**. Locating it in the RANGE column:

- Above p25 (2h), below median (8h) → roughly **35th–40th percentile** of the 1y RANGE-episode distribution.
- This is a *young* RANGE episode by historical standards: more than 60% of past RANGE runs lasted longer than this.
- For comparison: median RANGE episode runs 8h, p75 22h, p90 57h, max 179h (7.5 days). Long RANGE episodes are common.

**Plain reading:** the current RANGE has not yet outlived a typical RANGE episode. Statistically there is more historical mass at "RANGE continues for several more hours" than at "RANGE is about to flip" — but this is a frequency observation only, not a prediction.

---

## §4 Regulation matrix verdict for RANGE

From [`docs/REGULATION_v0_1_1.md`](../../docs/REGULATION_v0_1_1.md) §3 — activation matrix for RANGE:

| Config | Status in RANGE | Note |
|---|:---:|---|
| `CFG-L-RANGE` (LONG range) | **ON** | Pack E + E-NoStop both 4/4 profitable |
| `CFG-L-FAR` (LONG far) | **ON** | Pack BT 4/4 profitable |
| **`CFG-S-RANGE-DEFAULT` (SHORT default)** | **ON** | Pack A 1y +12,181 USD; RANGE dominates the year |
| `CFG-S-INDICATOR` (SHORT indicator-gated) | **OFF — SUSPENDED** | Pack A2/A4 + Pack D 4/4 losing |
| `CFG-L-DEFAULT` (LONG default) | **OFF — SUSPENDED** | Pack C 3/3 losing |

**SHORT-side reading** (relevant to the operator anchor):

- The operator's SHORT corresponds in spirit to `CFG-S-RANGE-DEFAULT` — the **only** non-suspended SHORT config under regulation.
- In RANGE, this config is **ON** per §3, on the rule "Pack A is profitable on a 1y window dominated by RANGE; RANGE is the modal regime to expect at runtime; therefore activate" ([`REGULATION_v0_1_1.md`](../../docs/REGULATION_v0_1_1.md):143).
- In MARKUP / MARKDOWN, the same config drops to **CONDITIONAL** ("deploy with bounded loss limits and pause if trend-regime live realization deviates negatively", line 145).

So the regulation framework treats current regime as the most permissive cell for SHORT-side activity. This is the structural backdrop, not a recommendation about the operator's specific position.

---

## §5 SHORT historically across regimes

From [`docs/RESEARCH/REGIME_OVERLAY_v2_1.md`](../RESEARCH/REGIME_OVERLAY_v2_1.md) and [`REGULATION_v0_1_1.md`](../../docs/REGULATION_v0_1_1.md) §1.3:

Aggregate SHORT findings (1y backtest):

| Pack | Description | 1y PnL | Verdict |
|---|---|---:|---|
| Pack A (A1, A3) | SHORT DEFAULT, no indicator | **+12,181 USD** | net positive over 1y |
| Pack A (A2, A4) | SHORT INDICATOR `>0.3%` (3M) | −478 USD | losing |
| Pack D | SHORT INDICATOR variant | −5,046 USD | losing |
| **Pack A2/A4 + D combined** | SHORT INDICATOR family | **−4,568 USD net** | 4/4 losing across two thresholds and two instop variants |

**Critical caveat — within-pack regime split is M1-uninformative.**

Per [`REGULATION_v0_1_1.md`](../../docs/REGULATION_v0_1_1.md):53 (sourced from `REGIME_OVERLAY_v3.md`):

> "The regulation must not say 'Pack X is best in regime Y' or 'the SHORT default bot is strongest in RANGE because the within-pack split shows it' — those claims are M1-infeasible."

What this means concretely:

- We **can** say: SHORT DEFAULT was net-profitable over a year that was 72% RANGE, 13% MARKUP, 15% MARKDOWN.
- We **cannot** say: "SHORT default makes more per hour in RANGE than in MARKUP/MARKDOWN" — the hours-proportional sub-window allocation is algebraically identical to the year-level allocation, so any per-regime PnL split is uninformative.
- The regulation's "ON in RANGE" decision is therefore an *exposure heuristic* (the dominant regime is the one we have the most evidence about), not a regime-conditional outperformance claim.

For the operator's current SHORT: historical aggregate evidence supports the structural class ("SHORT default 1y") being net-profitable. Whether that aggregate translates to the specific entry/exit setup the operator is running is a separate question that this 1y backtest cannot answer.

---

## §6 Hysteresis state — proximity to a regime change

From `state/regime_state.json` + [`docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md`](../RESEARCH/HYSTERESIS_CALIBRATION_v1.md):

| Field | Value | Interpretation |
|---|---|---|
| `pending_primary` | `null` | No challenger regime detected this cycle |
| `hysteresis_counter` | 0 | No bars accumulating toward a transition |
| Computed `regime_confidence` | **1.0** | (no pending → fully confirmed in current regime) |
| Computed `regime_stability` | 5/12 ≈ **0.42** | Age 5 bars vs saturation 12 bars |

**Hysteresis context** (from `HYSTERESIS_CALIBRATION_v1` §2):
- Classifier A's `apply_hysteresis` uses `hysteresis_counter >= 2` for non-cascade transitions — a regime change requires 2 consecutive bars of agreement on a new candidate.
- The 1y-calibrated TRANSITION rate at H=1 is **7.35%** of hours, mean transition segment **1.3h**. The regime spends ~93% of time stable.

**Plain reading:** there is no challenger regime accumulating right now. A TREND or COMPRESSION reading on the next bar would set `pending_primary`; a second consecutive bar of the same candidate would flip the regime. Until then, the classifier's read of "RANGE" is locked.

The 0.42 stability score reflects "this regime is young — only 5/12 bars of the saturation window have elapsed." This is how the Decision Layer's R-3 (`regime_instability`) rule reads it: stability < 0.60 wouldn't trigger R-3 here because R-3 fires only when the underlying classifier explicitly weakens (no challenger present), but the saturation-fraction value itself sits below the 0.60 R-3 floor by construction of "young episode."

---

## §7 Active modifiers — what the classifier is currently flagging

From `state/regime_state.json["symbols"]["BTCUSDT"]["active_modifiers"]` + definitions in [`core/orchestrator/regime_classifier.py`](../../core/orchestrator/regime_classifier.py):

| Modifier | Meaning | Activated | Live trigger context |
|---|---|---|---|
| `POST_FUNDING_HOUR` | Bar within an hour after a funding event (lines 22, 31 modifier list) | 2026-04-29 08:13 UTC | hour=8, minute=9 |
| `WEEKEND_LOW_VOL` | Saturday/Sunday UTC; reduced expected volatility (`detect_weekend_low_vol` line 426) | 2026-05-02 00:00 UTC | weekday=6 |
| `WEEKEND_GAP_DETECTED` | Friday-close → Sunday-reopen gap > 0.5% (`detect_weekend_gap` line 431) | 2026-05-03 23:09 UTC | gap=+0.53%, dir=UP, fri=78,153 → sun=78,569; expires 2026-05-07 05:40 UTC |

Modifier priority order (lines 26–34): `NEWS_BLACKOUT > HUGE_DOWN_GAP > TREND_UP_SUSPECTED > TREND_DOWN_SUSPECTED > POST_FUNDING_HOUR > WEEKEND_LOW_VOL > WEEKEND_GAP_DETECTED`. Higher-priority modifiers (blackout / huge gap / trend-suspected) are **not** active.

Modifiers do not change the primary regime label — they annotate the bar's market context for downstream consumers. The current set reads as: weekend-tail conditions dominate, no news event, no fast-move detection. The +0.53% Sunday-reopen gap remains tagged through 2026-05-07 05:40 UTC (~42h from now).

---

## §8 Observations for the current setup

Compiled facts (no recommendations):

1. **Regime taxonomy alignment.** Live Classifier A says RANGE; 3-state projection is RANGE; this is the modal regime of the year (72.1% of hours per `REGIME_PERIODS` §1).
2. **Episode age in distribution.** Current RANGE is 5h old, sits ≈ p35–p40 of the 1y RANGE-episode distribution. More past RANGE episodes have lasted longer than this than have ended sooner.
3. **Regulation alignment with operator direction.** `CFG-S-RANGE-DEFAULT` is the only non-suspended SHORT config and is **ON** in RANGE per §3. The operator's SHORT direction is in the regulation's permissive cell.
4. **Distance to liquidation.** 18% sits well above any Decision Layer alert tier — M-4 emergency is `<5%`, M-3 critical applies via `margin_coefficient ≥ 0.85`, not via distance. The operator is in M-3 territory by margin-coefficient (0.97 ≥ 0.85) and in M-4 territory by margin-coefficient too (0.97 ≥ 0.95) — but **not** by distance branch. (Live Decision Layer reading per the wire landed earlier today: M-3 + M-4 fire on coefficient, with `trigger="margin"`, not `distance_to_liq`.)
5. **Funding tailwind.** Negative funding favors SHORT. ~$28/day is a small but non-zero carry for holding the position through this regime.
6. **Modifier context.** Weekend-tail conditions (LOW_VOL + GAP_DETECTED) — these are descriptive of the structural background, not predictive. The +0.53% Sunday reopen gap is still tagged as recent context.
7. **Hysteresis is calm.** No pending regime, no counter accumulation. The regime is locked at the per-bar level until a new candidate appears.

---

## §9 What to monitor (risk indicators, not directional calls)

Items the operator can watch in `state/regime_state.json` and the Decision Layer dashboard:

1. **`pending_primary` becomes non-null with `TREND_UP` or `CASCADE_UP`.** These project to MARKUP under CLASSIFIER_AUTHORITY_v1 §1. MARKUP is the regime in which `CFG-S-RANGE-DEFAULT` drops from ON to CONDITIONAL ([`REGULATION_v0_1_1.md`](../../docs/REGULATION_v0_1_1.md):122). Pending → counter=1 → counter=2 → flip; one extra bar of warning.
2. **`pending_primary = COMPRESSION`.** Projects to RANGE (still permissive cell), but COMPRESSION specifically encodes "low-vol consolidation" and historically often *precedes* trend bursts (no claim from this dataset, just a structural observation). Worth noting if it appears.
3. **Time-of-day clustering.** Per `REGIME_PERIODS` §4, transitions cluster around **15:00 UTC (52 transitions, ~2× mean)** — NY session open. Lesser peaks at 14:00, 16:00, 23:00 UTC. Current Warsaw time UTC+2 → 15:00 UTC ≈ 17:00 local. No causal claim, just a frequency observation: if a regime change is coming today, the 14–17 UTC window is historically denser.
4. **R-3 (`regime_instability`).** Decision Layer fires R-3 when `regime_stability < 0.60` (computed from `hysteresis_counter` saturation). It would surface in the dashboard if a challenger emerged. Not currently firing.
5. **Active modifiers gaining priority entries.** If `TREND_UP_SUSPECTED` or `HUGE_DOWN_GAP` appear in `active_modifiers`, the classifier has detected fast-move conditions — these have higher priority than the current weekend-tail set.
6. **Per-month context.** [`REGIME_PERIODS`](../RESEARCH/REGIME_PERIODS_2025_2026.md) §5: April 2026 was MARKUP-heavy (18.5% MARKUP, 73.8% RANGE). The 2026-05 row in the table shows 100% RANGE on a single-day window — too small to extrapolate to the full month. May has no historical baseline in this dataset.
7. **Margin data freshness.** D-4 rule (added in TZ-MARGIN-COEFFICIENT-INPUT-WIRE) fires INFO at 6h, PRIMARY at 12h since the last `/margin` update. The operator-supplied snapshot becomes the source of truth; if it ages beyond 6h, M-* reads risk drifting from reality.

---

## §10 What this document does not do

- **No price forecast.** Forecast pipeline is decommissioned ([`FORECAST_CALIBRATION_DIAGNOSTIC_v1.md`](../RESEARCH/FORECAST_CALIBRATION_DIAGNOSTIC_v1.md)); no claim is made about whether 77–79k retest will or will not happen.
- **No close / hold / scale recommendation** for the SHORT.
- **No bias from the M-3 / M-4 alerts** to "act now." Decision Layer alerts surface that margin is in critical/emergency tiers per the regulation's *thresholds* — they do not rank that against the operator's thesis or risk tolerance.
- **No within-regime per-hour PnL claim.** Per `REGULATION_v0_1_1.md`:53, this is M1-infeasible from the existing data.
- **No within-day directional read.** The Decision Layer is rule-based and reports state; it is not a market opinion.
- **§B (strategy review on the specific entry/exit structure) and §C (live view with mark/funding/derivative context) are out of scope** — separate TZs.

---

**End of analytical document.** All facts cited inline reference the linked foundation files.
