# REGULATION v0.1

**Status:** DRAFT regulation  
**Date:** 2026-05-05  
**Scope:** operational decision regulation for bot selection and activation only.  
**Out of scope:** P8 implementation, live deployment plan, sizing-v0.1 changes, UID schema.

---

## §1 Data coverage and limitations

This regulation is built on the current research foundation only:
- `docs/RESEARCH/REGIME_OVERLAY_v2.md` for cross-pack PnL direction and comparative evidence.
- `docs/RESEARCH/REGIME_OVERLAY_v3.md` for infeasibility limits on within-pack regime sensitivity.
- `docs/RESEARCH/TRANSITION_MODE_COMPARE_v2.md` for transition-handling logic after hysteresis recalibration.
- `docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md` for calibrated transition share (`H=1` primary, `H=2` sensitivity).
- `docs/RESEARCH/REGIME_PERIODS_2025_2026.md` for regime distribution over the reference year.

### 1.1 Data coverage used in this regulation

The current base covers **17 runs** across Packs A, C, D, E, and BT, all encoded in `REGIME_OVERLAY_v2.md` and its driver/raw output.

Reference-year regime distribution (`REGIME_PERIODS_2025_2026.md` §1):
- `RANGE = 72.1%` of the year (`6,317` hours, `263.2` days)
- `MARKUP = 13.0%` (`1,135` hours, `47.3` days)
- `MARKDOWN = 14.9%` (`1,309` hours, `54.5` days)
- `DISTRIBUTION = absent` in classifier output

Operational implication: the regulation must treat `RANGE` as the dominant environment because it is the dominant observed state in the current year sample. That is a data fact, not a design preference.

### 1.2 What is strong enough to enter regulation

The only findings treated as sufficiently stable for operational regulation are **cross-pack directional findings**:
- LONG without indicator is net negative in the observed year sample.
- LONG with indicator gate is net positive across two independent LONG indicator families.
- SHORT default family has positive aggregate evidence and is strongest in RANGE on the only pack where regime splits are distinguishable.
- SHORT indicator families are net negative in the currently observed datasets.
- Transition handling should be **per-bot conditional**, not a global pause, after hysteresis recalibration.

These statements are directly grounded in `REGIME_OVERLAY_v2.md` §4-§6 and `TRANSITION_MODE_COMPARE_v2.md` §4-§6.

### 1.3 What is explicitly not strong enough to enter regulation

Per `REGIME_OVERLAY_v3.md`, **within-pack regime sensitivity is infeasible to validate** with the available source data.

Reason:
- The M1 proportional-allocation method collapses to identical per-hour PnL inside packs whose runs share the same window.
- All sub-windows in V3 are RANGE-dominant; there are no MARKUP-dominant or MARKDOWN-dominant sub-windows to compare against.
- Therefore this regulation must **not** claim things like "Pack E is specifically best in MARKUP" or ?Pack D loses specifically in MARKDOWN.?

This is a hard anti-drift boundary.

### 1.4 Dataset flags that remain active

The following constraints remain active and must be carried into operator interpretation:
- `DISTRIBUTION` regime is absent. No recommendation is allowed for it.
- The sample is a **bullish BTC year**. No bear-market recommendation is supported.
- BTC only. No cross-asset extrapolation is supported.
- Rebate-aware analysis is partially unit-constrained: USD packs can be rebate-adjusted directly in `REGIME_OVERLAY_v2.md` §5; BTC packs cannot be converted to unified USD PnL without a separate FX methodology.

### 1.5 Regulation principle

This document is intentionally conservative. If a recommendation cannot be tied to a specific pack/run comparison in the cited research, it does not enter the regulation.

---

## §2 Optimal bot configurations (per evidence)

This section defines the **configuration families** that are currently admissible for operational use. "Optimal" here means ?best-supported by current evidence,? not ?globally proven optimum.?

### 2.1 Config table

| Bot type | Purpose | Side | Contract | Strategy | Indicator | target / instop / min_stop / max_stop | Order count | Production-vs-backtest note | Evidence packs / runs | Evidence summary | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG range | Capture downside-triggered long opportunities while retaining positive sign across current dataset | LONG | COIN_FUTURES / inverse | INDICATOR | Price% `< -0.3%` family (Pack E) or `< -1%` family (BT) | Pack E family: target `0.25-0.50`, indicator-gated, profitable monotonic target sweep. BT family: `instop=0.018`, `min_stop=0.01`, `max_stop=0.03`, target `0.25-0.50` | Production `220`; backtests in evidence mostly `800` | Backtests used higher `order_count` than production. Sign evidence is accepted; direct sizing equality is not claimed. | Pack E (`E-T0.25`..`E-T0.50`), BT (`BT-014`..`BT-017`) | Pack E total `+0.3893 BTC`; BT total `+0.25785 BTC`; both flip sign vs LONG default | `high` |
| LONG far | Higher-target version of LONG indicator family for stronger drift capture | LONG | COIN_FUTURES / inverse | INDICATOR | Price% `< -0.3%` or `< -1%` | Preferred evidence point is higher target: `0.40-0.50`; BT and Pack E both show monotonic improvement with higher target | Production `220`; evidence `800` | Same production/backtest count mismatch; use as directional regulation, not exact PnL forecast | Pack E `E-T0.40`, `E-T0.50`; BT `BT-014`, `BT-015` | In Pack E, target `0.50` is best (`+0.1114 BTC`), target `0.40` next (`+0.1039 BTC`). In BT, target `0.50` is best (`+0.07779 BTC`) | `medium` |
| SHORT range | Primary short exposure for RANGE-dominant environment | SHORT | USDT_FUTURES / linear | DEFAULT-dominated family | No indicator gate required for the core positive evidence | Pack A positive family is not a single clean parameter tuple, but positive evidence is dominated by DEFAULT 1y SHORT runs A1/A3 | Production `200`; backtests vary by pack | Production count lower than research/backtest counts; operator must treat sign evidence separately from exact return magnitude | Pack A (`A1`, `A3`, aggregate `A`) | Pack A total `+12,181 USD`; on the only usable regime split, RANGE contributes `+9,344.56 USD`, strongest per-hour rate in RANGE | `medium` |
| SHORT far | Secondary short exposure when wanting wider capture, but only under the same default-family logic | SHORT | USDT_FUTURES / linear | DEFAULT family preferred over indicator family | No evidence basis to promote `indicator>1%` or similar as far-short default | Parameter tuple not isolated cleanly in current cross-pack evidence; operationally inherits the same family as SHORT range but with lower confidence | Production `200`; backtest families include `800`, `5000` | No clean far-short winner exists in current evidence. Included only as a lower-confidence operator slot. | Indirectly Pack A positive; Pack D/A2/A4 negative indicator families | Positive support exists only for the broad Pack-A default family, not for an isolated "far" tuple | `low` |
| SHORT default | Baseline short bot for current regulation | SHORT | USDT_FUTURES / linear | DEFAULT | Indicator-gated short is not validated as default | Use production default short family rather than indicator short family | Production `200`; some negative research packs use `5000` or `800` | Explicit distinction: backtest `5000` in Packs D/G2-like research is a structural test, not production deployment guidance | Pack A positive vs Pack D negative | Pack A earns; Pack D (`INDICATOR>1%`) loses `-3,085 USD`; A2/A4 indicator-side runs also lose | `high` |

### 2.2 Operational interpretation of the config table

1. **LONG no-indicator default is excluded from regulation.** `REGIME_OVERLAY_v2.md` §4 and §6 show Pack C (`LONG DEFAULT`) at `-0.3408 BTC` across 3 runs. This is not a borderline case; the sign is negative across the whole pack.
2. **LONG indicator families are admitted.** Two independent families are positive:
   - Pack E: `INDICATOR < -0.3%`, total `+0.3893 BTC`
   - BT: `INDICATOR < -1%`, total `+0.25785 BTC`
3. **SHORT default family is admitted.** Positive aggregate evidence exists only there, via Pack A total `+12,181 USD`.
4. **SHORT indicator families are not admitted as baseline.** Both Pack D and the negative indicator-side runs in Pack A are loss-making.

### 2.3 Confidence assignment logic

Confidence labels in this regulation mean:
- `high`: repeated directional confirmation across multiple packs or strong sign separation vs alternative family.
- `medium`: direction supported, but parameter isolation or production equality is incomplete.
- `low`: included only as an operational placeholder because the role exists, but evidence is indirect or confounded.

Applied honestly here:
- LONG indicator family: `high`
- LONG far sub-variant: `medium`
- SHORT default: `high`
- SHORT range: `medium`
- SHORT far: `low`

---

## §3 Activation rules per regime

This section converts the evidence into operator ON/OFF/CONDITIONAL rules.

### 3.1 Activation table

| Regime | LONG indicator | LONG default without indicator | SHORT default | SHORT indicator |
|---|---|---|---|---|
| MARKUP | ON | OFF | CONDITIONAL | OFF |
| RANGE | ON | OFF | ON | OFF |
| MARKDOWN | CONDITIONAL | OFF | CONDITIONAL | CONDITIONAL |
| DISTRIBUTION | NO RULE | NO RULE | NO RULE | NO RULE |

### 3.2 Rule basis by bot type

#### LONG indicator: ON in MARKUP and RANGE, CONDITIONAL in MARKDOWN

Evidence basis:
- `REGIME_OVERLAY_v2.md` §4 and §6 show both LONG indicator packs net positive overall:
  - Pack E total `+0.3893 BTC`
  - Pack BT total `+0.25785 BTC`
- Under M1, both packs allocate positive PnL to all three regimes, but `REGIME_OVERLAY_v3.md` makes clear that **within-pack regime sensitivity is not actually validated**. Therefore the regulation cannot say ?LONG indicator is proven best specifically in MARKUP.?

Regulatory consequence:
- `MARKUP`: `ON`, because the LONG indicator family is net positive and there is no contrary pack-level evidence.
- `RANGE`: `ON`, because the same family stays net positive and RANGE dominates the observed year.
- `MARKDOWN`: `CONDITIONAL`, not `ON`, because the current bullish-year dataset is insufficient to make a strong long-in-markdown claim, even though M1-allocated pack totals remain positive.

Operator meaning of `CONDITIONAL` here:
- allowed, but must be monitored as a hypothesis rather than treated as fully validated behavior.

#### LONG default without indicator: NEVER

Evidence basis:
- Pack C (`LONG DEFAULT`) total `-0.3408 BTC` in `REGIME_OVERLAY_v2.md` §4.
- `REGIME_OVERLAY_v2.md` §6 Finding A explicitly states that the indicator gate flips LONG sign from negative to positive.

Regulatory consequence:
- LONG default without indicator is `OFF` in every regime.
- This is one of the strongest rules in the document because it is based on sign separation across families, not on a narrow parameter tweak.

#### SHORT default: ON in RANGE primarily; CONDITIONAL in MARKUP and MARKDOWN

Evidence basis:
- Pack A aggregate is positive: `+12,181 USD`.
- On the only regime split that is interpretable, Pack A allocates:
  - `RANGE +9,344.56 USD`
  - `MARKDOWN +1,632.59 USD`
  - `MARKUP +1,203.86 USD`
- Pack A therefore has strongest support in `RANGE`, with positive but weaker support in both trend directions.

Regulatory consequence:
- `RANGE`: `ON`
- `MARKUP`: `CONDITIONAL`
- `MARKDOWN`: `CONDITIONAL`

Why not `ON` in MARKUP/MARKDOWN:
- Because `REGIME_OVERLAY_v3.md` blocks stronger within-pack sensitivity claims and because SHORT evidence mixes windows/families. RANGE is the only regime where the directional dominance is both positive and strongest.

#### SHORT indicator: OFF by default; CONDITIONAL hypothesis only in MARKDOWN

Evidence basis:
- Pack D total `-3,085 USD` in `REGIME_OVERLAY_v2.md` §4.
- A2 and A4 are also negative in Pack A's indicator-side 3M branch.
- `REGIME_OVERLAY_v2.md` §6 Finding B/F-B distinguishes the positive SHORT evidence (Pack A default-dominated family) from the negative SHORT indicator evidence (Pack D).

Regulatory consequence:
- `MARKUP`: `OFF`
- `RANGE`: `OFF`
- `MARKDOWN`: `CONDITIONAL` only as an explicit **unvalidated hypothesis**, because the operator may want to monitor whether short indicator logic could benefit from markdown-heavy periods, but the current dataset does not validate it.

Monitoring requirement for `SHORT indicator` in `MARKDOWN`:
- use only as a flagged experiment class, not as a regulation-approved default configuration.
- no scaling or recommendation is allowed from the current evidence base.

### 3.3 Distribution regime

No rule is allowed for `DISTRIBUTION`.

Evidence basis:
- `REGIME_PERIODS_2025_2026.md` §1 reports `DISTRIBUTION = 0` and explicitly notes that the classifier emits only three labels.

Regulatory consequence:
- Any operator facing a fourth-regime concept must treat it as outside this regulation.

---

## §4 Transition behavior (post-H=1 calibration)

### 4.1 Transition definition used by this regulation

Per `HYSTERESIS_CALIBRATION_v1.md`:
- primary calibrated hysteresis: `H = 1`
- annual transition share: `7.351%` of the year (`644 / 8,761` hourly bars)
- sensitivity reference: `H = 2` gives `13.115%`

This regulation adopts the **post-calibration interpretation**, not the original `H=12` artifact.

### 4.2 Core finding from transition-mode rerun

`TRANSITION_MODE_COMPARE_v2.md` §6 yields the decisive structural rule:
- For **net-profitable packs**, pause/reduction policies **forfeit gain**.
- For **net-loss packs**, pause/reduction policies **recover some loss**.
- There is no universal global-pause policy that improves all families simultaneously.

Examples from the rerun:
- Pack A (profitable SHORT family): `B-DR1 > C > A > B-DR2`
- Pack E (profitable LONG indicator): `B-DR1/DR2 > C > A`
- Pack BT (profitable LONG indicator): `B-DR1/DR2 > C > A`
- Pack C (loss-making LONG default): `A/B-DR2 > C > B-DR1`
- Pack D (loss-making SHORT indicator): `A > C > B-DR1/DR2`

### 4.3 Transition regulation

The regulation rule is therefore:
- **Do not apply a complex global pause.**
- During `TRANSITION`, each bot keeps the same activation status it has in §3 **unless that bot family is currently in a loss-making evidence class**.

Operationally:
- LONG indicator bots: remain active through transition when otherwise ON/CONDITIONAL under §3.
- SHORT default bots: remain active through transition when otherwise ON/CONDITIONAL under §3.
- LONG default bots: remain OFF; transition does not rescue them into admissibility.
- SHORT indicator bots: remain OFF by default; if being monitored under the MARKDOWN conditional flag, transition should not override that caution.

### 4.4 Practical per-bot rule

Per-bot transition rule:
- If the family is **validated-positive** in the current evidence base, do **not** pause simply because the state is TRANSITION.
- If the family is **validated-negative** in the current evidence base, pausing/reducing is allowed and consistent with the rerun.

This is the smallest rule that matches the evidence and avoids the H=12 overreaction artifact.

---

## §5 Production parameter constraints

### 5.1 Production order-count limits

Current production risk limits from live mechanics/config references are:
- SHORT production count: `200`
- LONG production count: `220`

These must be treated as hard production constraints in this regulation.

### 5.2 Backtest order counts are not production settings

Backtest order counts used in evidence packs are structurally larger in several places:
- Pack D / 3M indicator SHORT family: `5000`
- BT LONG indicator family: `800`
- Pack E LONG indicator family: effectively `800`-class evidence family

Regulatory interpretation:
- These counts validate **directional behavior and family sign**, not a production deployment count.
- A backtest count of `5000` or `800` must never be copied into production under this regulation.

### 5.3 Exact production-vs-backtest distinctions that matter

| Family | Production count | Evidence count(s) | Constraint note |
|---|---:|---:|---|
| SHORT default | 200 | mixed Pack A evidence, broader research families above production size | Positive sign is admissible; exact annual PnL magnitude is not transferable 1:1 |
| SHORT indicator | 200 | 5000 in Pack D-style evidence; 3M indicator families also above production realism | Negative sign is strong enough to reject family baseline use; exact loss magnitude is not the key point |
| LONG indicator | 220 | 800 in BT / Pack E style evidence | Positive sign is admissible; order-count mismatch lowers confidence on exact numeric projection |
| LONG default | 220 | 1y default research pack | Negative sign is enough to exclude the family operationally |

### 5.4 Other production parameter constraints

This regulation treats the following as production constraints rather than optimization variables:
- Production SHORT count remains `200`
- Production LONG count remains `220`
- Live-vs-backtest parameter mismatch must be disclosed wherever evidence is cited
- No recommendation here upgrades research-config PnL into production forecast

---

## §6 Rebate-aware PnL projections

This section is intentionally conservative and unit-aware.

### 6.1 What can be projected directly from current evidence

Per `REGIME_OVERLAY_v2.md` §5, direct rebate-aware adjustments are available only for **USD-denominated packs**, because the rebate rate is expressed in USD-volume terms.

USD pack post-rebate figures already established in the research:
- Pack A raw: `+12,181.00 USD`
- Pack A rebate add: `+3,277.32 USD`
- Pack A post-rebate: `+15,458.32 USD`

- Pack D raw: `-3,085.00 USD`
- Pack D rebate add: `+730.05 USD`
- Pack D post-rebate: `-2,354.95 USD`

Operational reading:
- Rebate materially improves SHORT-family PnL in USD terms.
- Rebate does **not** change the sign of the negative SHORT indicator family.

### 6.2 Low / mid / high tier projection framing

Only a scenario framework is supportable here, not a fresh numerical model.

#### Conservative scenario
- Assume the low-tier rebate case reflected in `REGIME_OVERLAY_v2.md` §5.
- Resulting directional implication:
  - SHORT default family remains positive and improves further.
  - SHORT indicator family remains negative, even after rebate.
  - LONG BTC-denominated families remain sign-positive/negative on raw BTC evidence; rebate normalization is deferred.

#### Aggressive scenario
- Assume better-than-low-tier rebate improves USD packs further in the same direction.
- Allowed conclusion:
  - SHORT default family becomes more attractive than on raw PnL alone.
  - SHORT indicator family may become less bad, but the regulation still does not admit it as ON because the current evidence does not show sign flip even at low-tier rebate and does not provide a validated high-tier conversion table.

### 6.3 Per-bot annual projection handling rule

This regulation allows the operator to use the following projection logic:
- For **SHORT default family**: use raw evidence as lower bound and post-rebate Pack A as upper directional support.
- For **SHORT indicator family**: treat raw and post-rebate evidence both as negative.
- For **LONG families**: use BTC-denominated raw sign evidence only; do not convert into USD annual projections inside this regulation.

### 6.4 Why exact per-bot annual numbers are not expanded further here

The brief requested per-bot annual PnL with low/mid/high tiers, but the source base does not provide enough unit-harmonized information to do that honestly for all bot types:
- LONG packs are BTC-denominated.
- Rebate is modeled in USD-volume terms.
- No approved FX-normalization method is part of the source set.

Therefore this regulation records the **projection rule** and the directly supported USD-pack numbers, but does not fabricate a cross-unit annual table.

---

## §7 Known limitations

All known gaps are explicit here. None are concealed.

1. **Bullish-year only.** All referenced runs live inside the 2025-2026 BTC bullish year sample. No bear-market operational recommendation is validated.
2. **DISTRIBUTION absent.** The classifier output contains no DISTRIBUTION label. No rule can be issued for it.
3. **Within-regime sensitivity not measured.** `REGIME_OVERLAY_v3.md` shows the M1 sub-window method cannot validate true within-pack regime sensitivity.
4. **SHORT indicator profitability in MARKDOWN is unverified.** It is allowed only as a conditional monitoring hypothesis, not as validated regulation.
5. **Production-vs-backtest order-count mismatch exists.** Several evidence packs use `800` or `5000` counts versus production `200/220`.
6. **Cross-unit limitation remains.** BTC and USD PnL are not unified in the source set; LONG rebate-aware annual projections are therefore incomplete.
7. **BTC-only evidence.** No cross-asset operational transfer is validated.
8. **Transition findings depend on calibrated H=1/H=2 framing.** They replace the H=12 artifact, but still rest on M1 proportional allocation rather than raw trade logs.
9. **No direct within-pack parameter isolation for every role.** Some bot "types" in this regulation are operational role labels mapped from families, not from perfect isolated A/B optimization tables.
10. **No PnL forecast guarantee.** This regulation governs family selection and activation direction, not live expected return.

---

## §8 Open questions for next iteration

1. **Bear market data collection plan**
   - Acquire comparable run families on a bearish BTC year or bearish sub-window.
   - Goal: test whether LONG indicator positivity survives outside bullish drift.

2. **SHORT indicator MARKDOWN validation method**
   - Required because current regulation only permits MARKDOWN-conditional monitoring, not activation approval.
   - Preferred method: collect explicit markdown-heavy SHORT indicator runs with production-like counts.

3. **LONG `< -1%` without instop comparison**
   - Current BT evidence (`BT-014..017`) supports the indicator family, but the missing no-instop mirror prevents cleaner isolation of the instop contribution.

4. **Cross-asset validation**
   - Current regulation is BTC-only.
   - Need a separate run registry for ETH/XRP or other production-relevant assets before any asset-general rule is allowed.

5. **Unit-normalized rebate methodology for BTC packs**
   - Needed before a full unified annual PnL table can be produced for LONG families.

6. **Raw trade-log / equity-curve M2 path**
   - Needed if the operator wants true within-regime conditional PnL rather than M1 time-share allocation.

---

## Quick operator extract

If the operator needs the shortest usable reading from this regulation:
- Keep **LONG indicator** bots in the admissible set.
- Exclude **LONG default without indicator**.
- Keep **SHORT default** as the primary short family, especially for `RANGE`.
- Exclude **SHORT indicator** from default use; only monitor its MARKDOWN hypothesis.
- During `TRANSITION`, do **not** run a global pause. Keep positive-evidence families active; only consider pausing families that are already loss-making in the evidence base.
- Never copy backtest `order_count=800/5000` into production; production constraints remain `200/220`.

---

## References

- [REGIME_OVERLAY_v2.md](C:/bot7/docs/RESEARCH/REGIME_OVERLAY_v2.md)
- [REGIME_OVERLAY_v3.md](C:/bot7/docs/RESEARCH/REGIME_OVERLAY_v3.md)
- [TRANSITION_MODE_COMPARE_v2.md](C:/bot7/docs/RESEARCH/TRANSITION_MODE_COMPARE_v2.md)
- [HYSTERESIS_CALIBRATION_v1.md](C:/bot7/docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md)
- [REGIME_PERIODS_2025_2026.md](C:/bot7/docs/RESEARCH/REGIME_PERIODS_2025_2026.md)
