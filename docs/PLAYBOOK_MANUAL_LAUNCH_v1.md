# Manual Launch Playbook v1

**Status:** OPERATIONAL — pre-launch checklist for first bot activation per [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md).
**Date:** 2026-05-05
**Scope:** plan and pre-flight gates only — this document is **not** an activation. The actual `Start` click happens after every gate in §1 passes and every checkbox in §3 is verified.
**Owner action required:** operator + MAIN reviewer.

**Sources (read-only):**
- [`docs/REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §2 (configuration), §3 (activation rules), §5 (production constraints), §7 (limitations).
- [`docs/RESEARCH/REGIME_OVERLAY_v2_1.md`](RESEARCH/REGIME_OVERLAY_v2_1.md) §6 F-A and F-G (Pack E evidence basis).

---

## §1 Pre-launch gates (all must pass before any activation)

Each gate is a hard prerequisite. **Do not proceed to §3 pre-flight checks until every gate below is GREEN.**

| Gate ID | Gate | Pass criterion | Verifier |
|---|---|---|---|
| G1 | Position cleanup verified | Aggregate residual SHORT exposure ≤ planned tolerance (operator-declared number; default ≤ $5 000 USD-equivalent unless operator sets otherwise) | Operator inspects exchange UI + reconciles vs internal position log |
| G2 | Margin headroom | Margin coefficient < **60 %** on the live trading account (vs current ~95 % observed) | Operator reads margin coefficient from exchange UI; logs the reading with a timestamp |
| G3 | Live tracker pipeline operational | Trades capture into dedupe-protected logs (no duplicate trade IDs in the last hour of capture; tracker not in error state) | Operator runs the tracker health probe of choice; confirms last-trade-time is current |
| G4 | Current regime classification known | Operator has read the current regime label from the classifier output (RANGE / MARKUP / MARKDOWN) | Operator records the label + the timestamp of the read |
| G5 | Activation rules reviewed | Operator has read [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §3 once in the current session | Self-attested |

**Rule:** if any gate is RED or AMBER, fix the gate and re-verify. Do not start a bot with an open gate.

---

## §2 First bot recommendation (per evidence)

**Recommended first bot: `CFG-L-RANGE` @ target = 0.50.**

### Why this bot is first
1. **Highest evidence density.** Pack E (with instop) is 4/4 profitable across a 4-target sweep ([`REGIME_OVERLAY_v2_1.md`](RESEARCH/REGIME_OVERLAY_v2_1.md) §3, F-A). Pack E-NoStop is also 4/4 profitable, providing a clean A/B for the instop preference (F-G).
2. **Best-understood instop direction.** F-G validates `instop=0.018` over `instop=0` for this exact threshold (`<-0.3%`). No other approved configuration has this clean an A/B at the deployable parameter set.
3. **Activation coverage of the year.** Per [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §3, CFG-L-RANGE is **ON** in MARKUP and RANGE — that's 85 % of the reference year (RANGE 72.1 % + MARKUP 13.0 %). MARKDOWN remains CONDITIONAL.
4. **Independent of SHORT cleanup.** LONG side is orthogonal to the residual SHORT exposure being cleaned up — no interference with G1.

### Production parameters (FROZEN from REGULATION §2)

| Parameter | Production value | Source |
|---|---|---|
| Side | LONG | REG §2 cfg table, CFG-L-RANGE row |
| Contract | COIN_FUTURES (XBTUSD inverse) | REG §2 + §5 contract convention |
| Strategy | INDICATOR GRID | REG §2 |
| Indicator | PRICE % 1m-30 < −0.3 % | REG §2 (`<-0.3%`) + Pack E configuration |
| Target % | **0.50** | REG §2 cfg row "0.30 (or 0.40 for higher BTC capture)"; CFG-L-RANGE @ T=0.50 corresponds to E-T0.50, the highest-BTC variant in Pack E |
| Grid step (gs) | 0.03 | REG §2 |
| Instop % | **0.018** | REG §2 + FIX 4 + F-G (instop=0.018 dominates instop=0 for this config) |
| Min Stop % | 0.01 | REG §2 |
| Max Stop % | 0.03 | REG §2 |
| Order count | **220 (PRODUCTION — not 5 000)** | REG §5 production cap; Pack E backtest used 5 000, NOT transferable |
| Order size | $100 USD per order | Pack E configuration |
| Trailing | OFF | Pack E configuration; REG §5 ("all approved configs use Trail OFF") |
| Take-profit (extension) | OFF | Pack E baseline configuration |

**Per-order cap:** 220 × $100 = **$22 000 USD-equivalent maximum gross position**. This is the upper bound used in §1 G2 margin sizing and §5 hard stop.

### What this playbook does NOT promise
- This playbook does **not** project a specific PnL for the first bot. Pack E backtest used `order_count=5000` and the production cap is `220` — the order_count delta is unmodelled per [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §7 limitation 2 and open question O8. **Pack E PnL numbers are direction evidence, not a production yield prediction.**
- The instop preference (F-G, +0.0439 BTC across 4 targets in the 3M Pack E window) is the **direction signal**; the magnitude under production order_count is unverified.

---

## §3 Pre-flight checks (per bot, before clicking Start)

Run this checklist immediately before activation. Every box must be ticked. If any box fails, **do not start**.

```
[ ] Bot config UI displays parameters matching §2 EXACTLY:
    [ ] Side                         = LONG
    [ ] Contract                     = COIN_FUTURES (XBTUSD inverse)
    [ ] Strategy                     = INDICATOR GRID
    [ ] Indicator                    = PRICE % 1m-30 < -0.3 %
    [ ] Target %                     = 0.50
    [ ] Grid step (gs)               = 0.03
    [ ] Instop %                     = 0.018
    [ ] Min Stop %                   = 0.01
    [ ] Max Stop %                   = 0.03
    [ ] Order count                  = 220   (NOT 5 000)
    [ ] Order size                   = $100
[ ] Boundaries setup: NO boundaries (consistency with Pack E configuration)
[ ] Trailing: OFF
[ ] Take-profit extension: OFF
[ ] Percent (%) mode: ON
[ ] Account balance available ≥ $22 000 USD (room for full 220-order grid)
[ ] Account margin coefficient (post-bot-start projection) < 60 %
[ ] Live tracker logging configured to capture this bot's UID
[ ] Bot UID recorded in operator log with launch timestamp
[ ] §1 gates G1-G5 all GREEN as of within last 30 minutes
[ ] Current regime label (from G4) noted: ___RANGE / MARKUP / MARKDOWN___
```

**Note on regime label:** if current regime is MARKDOWN, CFG-L-RANGE is **CONDITIONAL** per [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §3 — proceed with bounded loss limits and an explicit MAIN review of the deviation in §4 thresholds. If RANGE or MARKUP, proceed at standard thresholds.

---

## §4 Validation criteria (when to make a decision)

The first bot is observation-mode for the first 50 closed grid cycles. Decisions made at three milestones:

### Milestone 1 — after 10 closed cycles (directional check)
- **Continue:** realized PnL is on a positive trend (cumulative > 0 OR clearly trending toward 0 from below). Direction matches Pack E (which earned across all 4 targets).
- **Continue with monitoring:** realized PnL is mixed/flat, no clear sign yet.
- **Stop and review:** cumulative PnL ≤ −1 BTC × Pack E per-cycle expectation (operator estimates from E-T0.50 BTC PnL / cycle count in source backtest), OR any unexpected behavior (orders not filling, indicator not triggering when expected).

### Milestone 2 — after 30 closed cycles (variance check)
- **Continue:** cumulative realized PnL is positive AND the per-cycle CV (coefficient of variation) is comparable to the Pack E expected range. Drawdown stays within 2× the average Pack E drawdown range.
- **Stop and review:** cumulative realized PnL is negative; OR drawdown exceeds 1.5× Pack E expected max; OR per-cycle CV is dramatically higher than Pack E (e.g. >3×), indicating the production environment is producing different behavior.

### Milestone 3 — after 50 closed cycles (full evaluation)
- **Validation PASSED:** cumulative realized PnL is positive AND aligned in direction with Pack E (positive BTC return); operator + MAIN agree the production behavior is consistent with the backtest within an explicitly documented order_count adjustment.
- **Validation FAILED:** any of (a) cumulative PnL negative, (b) drawdown beyond 1.5× expected max, (c) qualitative behavior anomalies that operator + MAIN judge as out-of-distribution vs Pack E.

### Threshold for "continue" (milestones 1 & 2)
- Realized PnL after 30 closed cycles **positive**.
- Drawdown not exceeding 2× the average Pack E drawdown range.

### Threshold for "stop and review" (milestones 1 & 2)
- Negative cumulative realized PnL after 30 closed cycles.
- Drawdown > 1.5× expected Pack E max.
- Any unexpected behavior (orders not filling, indicator not triggering, fills at unexpected prices).

### Caveat on validation
Pack E ran at `order_count=5000` over a 3M window. Production runs at `order_count=220`. **The order_count downscale is unmodelled** ([`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §7 limitation 2 + O8). Operator + MAIN must explicitly decide what "matches Pack E direction" means in production-realistic terms before milestone 1. A sub-task: derive a per-cycle expectation from Pack E that is order-count-comparable; until that derivation exists, "matches direction" = "positive cumulative PnL" only.

---

## §5 Stop conditions (immediate halt)

Any one of the following triggers an **immediate halt** of the bot — no debate, halt first then investigate.

| ID | Condition | Threshold |
|---|---|---|
| H1 | Margin coefficient (any account participating in this bot's margin pool) | **> 80 %** |
| H2 | Position size (gross USD-equivalent across all open grid orders) | **> $22 000** (cap = 220 orders × $100) |
| H3 | Liquidation distance | **< 5 %** of current price (≤ 5 % cushion to liquidation price) |
| H4 | Manual operator override | Any operator-initiated pause/stop signal |
| H5 | Live tracker pipeline failure | Tracker drops to error state OR last-trade-time stale > 10 minutes |
| H6 | Bot UI shows "error" / "rejected" state for ≥ 3 consecutive order placements | Any bot-side persistent failure |

**Halt sequence:** click `Pause` (do NOT click `Delete`), capture state, follow §6 rollback.

---

## §6 Rollback plan

If a stop condition fires OR validation thresholds in §4 trigger "stop and review":

1. **Pause bot.** Use the GinArea `Pause` action — **do not click `Delete`**. Pause preserves bot state (open orders, position, history) for analysis. Delete loses information.
2. **Capture state immediately.** Take screenshots of:
   - Bot config page (full parameter list).
   - Bot active page (open orders, current position, realized PnL, drawdown).
   - Account margin / balance state.
   - Live tracker dashboard for this bot UID.
3. **Capture log dumps:**
   - Live tracker logs for this bot UID since launch (or since the last 24 h, whichever is longer).
   - Exchange-side trade history filtered to this bot UID.
   - Exchange-side position history.
4. **Manual close active position if necessary.** If the paused bot still holds an open position and continued holding it presents margin risk per the §5 thresholds, manually flatten the position via market order. Document the close timestamp and price.
5. **Document incident in `incident_log.md`.** Required fields:
   - Bot UID + config (verbatim parameter list).
   - Launch timestamp + halt timestamp.
   - Stop condition that fired (H-ID from §5) OR validation threshold that triggered (M1/M2/M3 from §4).
   - Realized PnL at halt.
   - Drawdown reached.
   - Margin coefficient at halt.
   - Operator's qualitative observation (one paragraph).
6. **MAIN review before re-launch.** No re-launch of this bot or any new bot until MAIN has reviewed the incident log entry and explicitly cleared a re-launch plan. The clearance must reference the specific cause and the mitigation applied.

---

## §7 Decision tree for escalation

Bot performance vs Pack E expectation:

```
                  Bot result vs Pack E direction
                   |
     +-------------+--------------+--------------------+----------------------+
     |                            |                    |                      |
matches             slightly worse             significantly worse     catastrophically worse
direction           (within 1.5× Pack E DD)    (1.5×–2× Pack E DD)     (>2× Pack E DD or §5 fired)
     |                            |                    |                      |
continue;           continue with                stop;                   stop; full incident
plan second         monitoring;                  MAIN review              review per §6;
bot per §8          re-evaluate at              before continuation       full root-cause + mitigation
                    next milestone                                        before any re-launch
```

### Conditions to add a second bot
All must be true:
1. First bot validation **PASSED** at Milestone 3 (§4) — 50 closed cycles, positive cumulative realized PnL, drawdown within bounds.
2. Operator is comfortable with single-bot live data and signals readiness to expand.
3. Second bot is picked from §2 admissible list — likely **CFG-S-RANGE-DEFAULT** (high confidence, opposite side for portfolio balance).
4. The full §1 gates re-pass for the second bot's account/exchange context (some gates may carry over; G2/G3/G4 must be re-verified at the second-bot launch time).

### Conditions to delay a second bot
- First bot validation in "continue with monitoring" state (not yet PASSED).
- Operator wants more sample size before adding a second bot.
- Any §5 hard stop has fired on the first bot in the prior 7 days, even if the bot was successfully re-launched.

---

## §8 Activation sequence (after first bot success)

Once the first bot has validation PASSED at Milestone 3 and the §7 conditions for a second bot are met, the recommended order:

| Slot | Configuration | Rationale | Confidence |
|---:|---|---|:---:|
| 1 | **CFG-L-RANGE** | First — high confidence, F-G instop direction validated, MARKUP+RANGE coverage. | HIGH |
| 2 | **CFG-S-RANGE-DEFAULT** | Second — high confidence (Pack A), opposite side for balance vs slot 1. | HIGH |
| 3 | **CFG-L-FAR** | Third — high confidence at the threshold itself (Pack BT) but instop direction at `<-1%` is not A/B-validated (open question O3 in [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §8). Can wait. | HIGH (configuration), MEDIUM (instop choice) |
| 4 | (Optional) | If operator decides to use a second LONG slot or a SHORT variant beyond defaults — re-consult §2 of the regulation; do not invent slots not in the catalog. | — |

**Rule:** each slot must individually pass §1, §3, §4 before its activation. Do **not** activate two slots simultaneously on the assumption that "the first one already passed." Each slot is a separate launch event with its own pre-flight pass.

### What is explicitly NOT in this sequence
- Suspended configs (`CFG-S-INDICATOR`, `CFG-L-DEFAULT`) per [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §2 — DO NOT DEPLOY.
- Cross-asset slots (XRP, ETH) — out of scope per regulation §1 limitation 6.
- Bear-window-conditional slots — no validation evidence (open question O1).

---

## Appendix A — Source cross-reference

| This playbook | Sources from regulation / research |
|---|---|
| §1 G1-G5 gates | Operator-side prerequisites; not directly in regulation but consistent with §7 limitations 2 (order_count) and §3 activation matrix |
| §2 production parameters | [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §2 cfg table CFG-L-RANGE row + FIX 4 (instop preference) |
| §3 pre-flight checks | [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §2 + §5 (production constraints) |
| §4 validation thresholds | [`REGIME_OVERLAY_v2_1.md`](RESEARCH/REGIME_OVERLAY_v2_1.md) §3 Pack E aggregate (per-target PnL distribution), §6 F-A (sign expectation) |
| §5 hard stops | Operator risk policy; consistent with [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §7 limitation 2 (production order cap) |
| §6 rollback | Operator-side incident response; not in regulation directly |
| §7 escalation tree | [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §9 (revision triggers, including 30 % deviation rule) |
| §8 activation sequence | [`REGULATION_v0_1_1.md`](REGULATION_v0_1_1.md) §2 (admissible configs) + confidence ladder |

---

## Appendix B — What this playbook does and does not promise

**Does:**
- Specifies the exact production parameter tuple for the first bot, sourced from regulation §2.
- Defines pass/fail gates for launch.
- Defines stop conditions and rollback steps.
- Defines a sequenced expansion plan after first-bot success.

**Does not:**
- Predict a specific PnL or annualized return for the first bot. Pack E backtest at `order_count=5000` does not transfer 1:1 to production at `order_count=220`.
- Authorize cross-asset, suspended-config, or bear-window deployments.
- Replace operator judgement at any decision point — every threshold here is a **trigger for human review**, not an autonomous action.

---

## Document index
- [§1 Pre-launch gates](#1-pre-launch-gates-all-must-pass-before-any-activation)
- [§2 First bot recommendation](#2-first-bot-recommendation-per-evidence)
- [§3 Pre-flight checks](#3-pre-flight-checks-per-bot-before-clicking-start)
- [§4 Validation criteria](#4-validation-criteria-when-to-make-a-decision)
- [§5 Stop conditions](#5-stop-conditions-immediate-halt)
- [§6 Rollback plan](#6-rollback-plan)
- [§7 Decision tree for escalation](#7-decision-tree-for-escalation)
- [§8 Activation sequence](#8-activation-sequence-after-first-bot-success)
