# Decision Layer — Design v1

**Status:** DESIGN. No code, no tests.
**Date:** 2026-05-05
**TZ:** TZ-DECISION-LAYER-DESIGN
**Companion design:** [`MTF_DISAGREEMENT_v1.md`](MTF_DISAGREEMENT_v1.md)

**Foundation evidence:**
- [`docs/REGULATION_v0_1_1.md`](../REGULATION_v0_1_1.md) §2 (admissible configs), §3 (activation matrix), §4 (transition behavior), §7 (limitations).
- [`docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md`](../RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md) Q4 (HITL), Q6 (alert fatigue tiering).
- [`docs/RESEARCH/FORECAST_CALIBRATION_DIAGNOSTIC_v1.md`](../RESEARCH/FORECAST_CALIBRATION_DIAGNOSTIC_v1.md) (forecast decommission verdict).
- [`docs/CONTEXT/DRIFT_HISTORY.md`](../CONTEXT/DRIFT_HISTORY.md) META-PATTERN-003 (decommission rationale).
- [`docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md`](../RESEARCH/HYSTERESIS_CALIBRATION_v1.md) (H=1 calibration).
- [`docs/RESEARCH/REGIME_PERIODS_2025_2026.md`](../RESEARCH/REGIME_PERIODS_2025_2026.md) (episode statistics, regime distribution).
- [`docs/RESEARCH/POSITION_CLEANUP_SIMULATION_v1.md`](../RESEARCH/POSITION_CLEANUP_SIMULATION_v1.md) (frozen-state inputs incl margin/funding).
- [`services/dashboard/state_builder.py`](../../services/dashboard/state_builder.py) (regulation card already wired).
- [`services/telegram/alert_router.py`](../../services/telegram/alert_router.py) (PRIMARY/VERBOSE channel).

---

## §1 Architecture overview

### Principle

The decision layer is a **rule-based** translator that converts upstream signal state into operator-actionable output. It is **not an ML model**. It is the layer that sits between the data + regulation + position state and the dashboard / Telegram surfaces.

It exists because the previous attempt at this surface (raw forecast probabilities) was decommissioned for being not-actionable (per `META-PATTERN-003`). The design replaces that surface with **explicit rules grounded in `REGULATION_v0_1_1`**.

### Block diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Inputs                                                                      │
├──────────────┬─────────────┬──────────────┬─────────────┬─────────────────┤
│ regime label │ MTF state   │ position    │ price       │ regulation       │
│ + confidence │ + dim+TFs   │ state       │ levels      │ activation matrix│
│ (regime_     │ (mtf_state) │ (state_     │ (operator-  │ (REG §3 mirror)  │
│  classifier) │             │  latest)    │  config'd)  │                  │
└──────┬───────┴──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────────┘
       │              │             │             │             │
       └──────────────┴─────────────┴─────────────┴─────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────┐
       │  Decision layer (this design)                   │
       │    Rule engine over {input combinations}        │
       │    State machine: emit only on state changes    │
       │    Rate-limited per channel                      │
       └────────────┬─────────────────┬──────────────────┘
                    │                 │
                    ▼                 ▼
        ┌─────────────────────┐  ┌───────────────────┐
        │ Dashboard           │  │ Telegram          │
        │ regulation_action_  │  │ PRIMARY: state-   │
        │ card (live render)  │  │  change events    │
        │ +decision_log       │  │ VERBOSE: context  │
        │ (audit trail)       │  │  per filter        │
        └─────────────────────┘  └───────────────────┘
```

### Where it sits

The decision layer is implemented as a single Python module `services/decision_layer/decision_layer.py` (new) that runs inside the dashboard's state-builder cycle:

- `state_builder.build_state()` produces a draft state dict.
- The decision layer reads this draft + auxiliary inputs (MTF state, position state, price levels) and produces:
  1. An augmentation block in `dashboard_state.json["decision_layer"]` for the dashboard.
  2. A list of state-change events for PRIMARY/VERBOSE Telegram routing.
  3. An append to `state/decision_log/decisions.jsonl` for audit.
- Outputs are deterministic given inputs; the layer is stateless except for its rate-limiting cooldown registry (reused from `dedup_layer.py`).

---

## §2 Internal logic specification (exhaustive for core paths)

The decision layer's output is a *list of events*, each one a dict with `{type, severity, payload, recommendation}`. The dashboard renders them; Telegram routes them per their type.

This section enumerates the rules. Each rule has a deterministic trigger and an explicit recommendation.

### 2.1 Regime activation rules (R-* family)

| Rule ID | Trigger | Output type | Severity | Recommendation |
|---|---|---|:---:|---|
| **R-1** | regime_label is unchanged AND confidence ≥ 0.80 AND stability ≥ 0.80 AND no active config conflict per regulation §3 | `regulation_status` | INFO (dashboard only) | "Activation matrix stable; admissible configs unchanged." |
| **R-2** | regime_label changes (new label persisted ≥ 12 hourly bars per H=1 calibration; alternatively confidence ≥ 0.80 immediately upgrades to `CONFIRMED` from `CANDIDATE`) | `regime_change` | PRIMARY | "Regime moved {old}→{new}. Affected configs: {list}. Review activation status." |
| **R-3** | regime stability drops below 0.60 (hysteresis-weakening) | `regime_instability` | PRIMARY | "Regime stability dropped to {value}. Hysteresis weakening; expect potential transition." |
| **R-4** | candidate_regime is non-null AND candidate_bars ≥ 6 (6 hourly = 50% of 12-bar hysteresis = 50% to regime change) | `transition_pending` | VERBOSE | "Pending regime change to {candidate}; {bars}/12 hysteresis bars accumulated." |

### 2.2 Margin / position-stress rules (M-* family)

Anchored in `POSITION_CLEANUP_SIMULATION_v1` thresholds (margin coefficient ranges).

| Rule ID | Trigger | Output type | Severity | Recommendation |
|---|---|---|:---:|---|
| **M-1** | margin_coefficient < 0.60 | `margin_safe` | INFO (dashboard only) | "Margin headroom safe; activation gate G2 met." |
| **M-2** | margin_coefficient ∈ [0.60, 0.85) | `margin_elevated` | PRIMARY | "Margin coefficient elevated ({value:.2f}). Reduce new-position activation; review existing exposure." |
| **M-3** | margin_coefficient ≥ 0.85 | `margin_critical` | PRIMARY | "Margin coefficient CRITICAL ({value:.2f}). HALT new activations. Review position cleanup options." |
| **M-4** | margin_coefficient ≥ 0.95 OR distance_to_liquidation_pct < 5 % | `margin_emergency` | PRIMARY | "🚨 Margin EMERGENCY ({value:.2f}, dist_to_liq {dist:.1f}%). Consider immediate position reduction. Reference: PLAYBOOK_MANUAL_LAUNCH_v1 §5 hard stops." |
| **M-5** | net_btc moves ≥ 0.10 BTC vs last decision-layer record AND |delta_unrealized| > $500 | `position_change` | PRIMARY | "Position changed by {delta_btc:+.4f} BTC (Δ unrealized {delta_unrealized:+.0f} USD). Review whether this matches your manual cleanup plan." |

### 2.3 Critical price-level rules (P-* family)

Operator-configurable list of `critical_levels_usd` (default: 78 779, 80 000, 82 400 — the operator's view zones from `POSITION_CLEANUP_SIMULATION_v1` §1). Proximity threshold default $300 (matches `TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD` already in `regulation_relevance.py`).

| Rule ID | Trigger | Output type | Severity | Recommendation |
|---|---|---|:---:|---|
| **P-1** | abs(current_price − level) ≤ proximity AND state_change vs last evaluation | `price_near_level` | PRIMARY | "Price approaching critical level {level} ({distance} USD away). Review position-cleanup or activation plan." |
| **P-2** | price crosses a critical level (sign of `current_price − level` flips since last evaluation) | `price_crossed_level` | PRIMARY | "Price crossed level {level} (now {current_price:,.0f}). Recheck position state and active bot configs." |

### 2.4 MTF disagreement rules (T-* family) — wired to `MTF_DISAGREEMENT_v1`

| Rule ID | Trigger | Output type | Severity | Recommendation |
|---|---|---|:---:|---|
| **T-1** | mtf_state.mtf_state == "MAJOR" first-detected | `mtf_disagreement` | PRIMARY | "MTF disagreement: {dim} {htf}↔{ltf}; affected configs {list}. {action}" |
| **T-2** | mtf_state escalation (sustained 24+ bars) | `mtf_escalation` | PRIMARY | "Persistent MTF disagreement: {dim} {htf}↔{ltf} sustained 24+ bars. Operator decision needed." |
| **T-3** | mtf_state.mtf_state == "MINOR" | `mtf_minor` | INFO (dashboard only) | "Minor MTF disagreement noted; no admissibility change." |

### 2.5 Activation eligibility rules (E-* family)

These rules surface when a config becomes *eligible* to activate that wasn't before, OR loses eligibility. They synthesize regulation matrix + MTF + position state.

| Rule ID | Trigger | Output type | Severity | Recommendation |
|---|---|---|:---:|---|
| **E-1** | A config that was OFF or CONDITIONAL becomes ON (in regulation card) AND M-1 met AND no MTF MAJOR affecting it | `cfg_eligible` | PRIMARY | "{cfg_id} now eligible for activation under current regime ({regime_label}, conf {conf:.2f}). See `PLAYBOOK_MANUAL_LAUNCH_v1` for activation procedure." |
| **E-2** | A previously-ON config moves to CONDITIONAL or OFF | `cfg_demoted` | PRIMARY | "{cfg_id} demoted to {new_status} due to {reason}. Review whether to pause active instances." |
| **E-3** | Suspended configs (CFG-S-INDICATOR, CFG-L-DEFAULT) attempted activation by user input — never actually changes status | (none — display-only) | n/a | "Reminder: {cfg_id} is permanently suspended per REG §2." |

### 2.6 Engine / data-pipeline rules (D-* family)

| Rule ID | Trigger | Output type | Severity | Recommendation |
|---|---|---|:---:|---|
| **D-1** | snapshots.csv age > 10 min | `tracker_stale` | PRIMARY | "Live tracker stale ({age} min). Trades may be missed." |
| **D-2** | regime_state age > 2 h | `regime_stale` | PRIMARY | "Regime classifier output stale ({age} min). Activation decisions may be based on outdated label." |
| **D-3** | engine_status.bugs_detected > bugs_fixed | `engine_bugs` | INFO (dashboard) | "Engine has {n} unresolved bugs. {fix_eta}." |

### 2.7 Aggregation and de-duplication

Each rule emits *at most one event* per evaluation cycle. State-change semantics are enforced via the existing `services/telegram/dedup_layer.py`:

- Events keyed by `{rule_id, payload_signature}`.
- Cooldown: 30 minutes for PRIMARY, 60 minutes for INFO.
- An event re-emits only if `(severity, payload_signature)` differs from the last cached event.

### 2.8 What is explicitly NOT in scope

These categories are **not** in §2 because they would require evidence we don't have or grounding in a regulation we haven't yet revised:

- Forecast-driven activation decisions (forecast decommissioned).
- ML-based eligibility scoring (the layer is rule-based by design).
- Sentiment-driven recommendations (anti-recommended in research).
- Cross-asset rules (BTC-only per regulation §1).
- Bear-market-specific rules (no bear-market data validated).

If a rule is wanted that doesn't fit these constraints, it requires regulation revision first.

---

## §3 Trigger conditions and thresholds

| Threshold | Default value | Source |
|---|:---:|---|
| Regime confidence — confirmed | **≥ 0.80** | `RegimeForecastSwitcher` cached state historically holds ~0.85; 0.80 is a stable floor |
| Regime confidence — transition warning | **0.65** | matches `_REGIME_CONF_THRESHOLD` in `RegimeForecastSwitcher` |
| Regime stability — instability flag | **< 0.60** | empirically below where hysteresis is at risk |
| Hysteresis bars — confirmed transition | **12 hourly bars** | `HYSTERESIS_CALIBRATION_v1` H=1 calibration; 12 bars = 12h hysteresis at 1h scale |
| Hysteresis bars — half-warning | **6 hourly bars** | mid-point of 12 |
| Margin coefficient — safe | **< 0.60** | `POSITION_CLEANUP_SIMULATION_v1` §1 frozen state + `PLAYBOOK_MANUAL_LAUNCH_v1` §1 G2 |
| Margin coefficient — elevated | **0.60 to 0.85** | `PLAYBOOK_MANUAL_LAUNCH_v1` §5 hard-stop threshold is 0.80 |
| Margin coefficient — critical | **≥ 0.85** | half-way to playbook hard stop |
| Margin coefficient — emergency | **≥ 0.95** | `POSITION_CLEANUP_SIMULATION_v1` worst-case stress |
| Distance to liquidation — emergency | **< 5 %** | `PLAYBOOK_MANUAL_LAUNCH_v1` §5 hard stop H3 |
| Critical price levels (USD) | **{78 779, 80 000, 82 400}** | `POSITION_CLEANUP_SIMULATION_v1` §1 view target zones — operator-configurable |
| Price proximity | **$300** | matches `TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD` |
| Position delta (M-5) | **0.10 BTC** | small enough to catch operator manual ops, large enough to ignore micro-changes |
| Unrealized PnL delta (M-5) | **$500** | small enough to catch a single grid fill, large enough to ignore noise |
| Cooldown — PRIMARY | **1 800 sec (30 min)** | matches `MTF_DISAGREEMENT_DEDUP_CONFIG` proposed |
| Cooldown — INFO/dashboard | **3 600 sec (60 min)** | dashboard-only events tolerate longer cooldown |

Every threshold is **operator-configurable** via a settings YAML (specified in §8 step 2).

---

## §4 Output channels

Each event from §2 carries a `severity` field that maps directly to channels.

| Severity | Dashboard | Telegram channel | Audit log |
|---|:---:|:---:|:---:|
| `INFO` | always rendered in regulation card / decision panel | none | append |
| `VERBOSE` | rendered in decision panel | VERBOSE only (per `alert_router.py`) | append |
| `PRIMARY` | rendered in decision panel + flag visible from main view | PRIMARY (always-on for allowed chats) | append |

### 4.1 Dashboard rendering

The dashboard's `regulation_action_card` (already implemented in TZ-DASHBOARD-USABILITY-FIX-PHASE-1) is **augmented** with a new sub-section `decision_layer_recent_events` showing the last 5 events in chronological order, color-coded by severity.

A new top-level field `dashboard_state.json["decision_layer"]` is added containing:
```json
{
  "last_evaluated_at": "2026-05-05T12:34:56Z",
  "active_severity": "PRIMARY | VERBOSE | INFO | NONE",
  "events_recent": [ { ... } ],
  "events_24h_count": 12,
  "events_24h_by_rule": {"R-2": 1, "M-2": 3, ...},
  "rate_limit_status": { ... }
}
```

### 4.2 Telegram routing

PRIMARY events route per `services/telegram/alert_router.py` PRIMARY channel. VERBOSE events route per the existing VERBOSE channel (opt-in via `/verbose` command).

### 4.3 Audit log

`state/decision_log/decisions.jsonl` accumulates every event with full payload. Append-only; rotation policy:
- Hot (current month): kept in primary path.
- Archive: monthly tarball to `state/decision_log/archive/YYYY-MM.jsonl.gz`.

This log is what enables operator + MAIN to do post-hoc review of decision quality (per the `events_log` pattern from `MARKET_DECISION_SUPPORT_RESEARCH` Q4-A on HITL accountability).

---

## §5 Alert volume target

Per operator constraint: **5-15 PRIMARY alerts per day max.** Validation methodology:

| Channel | Target volume | Hard limit (rate-shaped) |
|---|:---:|:---:|
| Dashboard | live, no rate limit | n/a |
| VERBOSE | bounded by `regulation_relevance.py` filter (already implemented) | ~30/day soft cap |
| **PRIMARY** | **5-15/day** | **20/day hard cap** |
| Audit log | every evaluation; no rate limit | n/a |

**State-change definition.** A PRIMARY event fires only on:
1. **First-time entry into a state** (e.g. M-2 fires when margin first crosses into elevated band).
2. **Severity escalation** (e.g. M-2 → M-3 fires; M-3 → M-2 does not re-fire).
3. **Payload signature change** (e.g. R-2 fires on `RANGE→MARKUP`, then again on `MARKUP→RANGE`, but not on each bar within `RANGE`).

The `alert_router.py` cooldown layer enforces the hard cap. If 20 PRIMARY events fire in a 24-hour window, the 21st is suppressed and an "alert volume exceeded" diagnostic INFO is added to the audit log (visible to operator on dashboard but not pushed to Telegram).

**Anchor for 5-15/day target.** Per `REGIME_PERIODS_2025_2026` §1: 645 episodes / 365 days ≈ 1.77 regime changes/day. At our 12-bar hysteresis → ~0.5 confirmed regime transitions/day. Add margin events (typically 0-2/day during cleanup), MTF disagreements (~0.5/day estimated), critical price-level crossings (~1-3/day during active price exploration). Total expected: 2-6/day in calm conditions, 8-15/day during transitions. The 20/day cap protects against pathological days.

---

## §6 Multi-timeframe context integration

The decision layer consumes the structured `mtf_state` block from `MTF_DISAGREEMENT_v1` §6 directly. Two integration points:

### 6.1 HTF defines admissibility (read-only)

The regulation card mirror (`_REGULATION_ACTIVATION_V0_1_1` in `state_builder.py`) is keyed by **the regime label currently in `regime_state.json`** — which is by convention the bot-level master TF (1h). The decision layer treats this as the **HTF anchor** for admissibility computation.

### 6.2 LTF defines timing alerts

When MTF state is MAJOR and the LTF (15m or 1h) signal contradicts the HTF anchor, the decision layer emits T-1. The recommendation copy uses `affected_configs` from the MTF descriptor.

### 6.3 Decision-layer demotion semantics

When a config is `ON` per regulation §3 BUT MTF MAJOR affects it (per §6.3 of MTF design), the decision layer emits E-2 (`cfg_demoted`) and visually demotes the config in the dashboard regulation card to `CONDITIONAL — MTF disagreement`. This is annotated explicitly (per `MTF_DISAGREEMENT_v1` open question #8): the demotion is labeled "demoted by MTF disagreement" so the operator distinguishes regulation-driven from MTF-driven demotions.

### 6.4 TF-by-TF logic summary

| Source | Role | What decision layer reads | What it does |
|---|---|---|---|
| 1d regime label | strategic context | mtf_state cell A.1d | informs E-1 / E-2 transition |
| 4h regime label | strategic context | mtf_state cell A.4h | informs T-1 / T-2 escalation |
| 1h regime label | **HTF anchor** for admissibility | regime_state.json (existing) | drives the whole §3 activation matrix |
| 15m regime label | LTF timing | mtf_state cell A.15m | feeds T-1 LTF readings |
| 15m / 1h trend | LTF timing dim | mtf_state cell B.* | feeds T-1 / T-2 |
| All TFs vol regime | second-axis context | mtf_state cell C.* | feeds future "vol-regime activation rule" extension (see §9 #4) |

---

## §7 Test plan

### 7.1 Replay-based validation

Replay the 1-year historical state through the decision layer with simulated input streams:

- `regime_state` — derived from `data/forecast_features/full_features_1y.parquet` `regime_int`.
- `position_state` — bootstrap from `state/state_latest.json` snapshots historical (where available) or simulated.
- `price_levels` — operator-default (78 779, 80 000, 82 400).
- `mtf_state` — placeholder (zeros if MTF not yet implemented).

**Acceptance metrics:**
- **PRIMARY events/day distribution:** mean 4-8, p90 ≤ 15, max ≤ 20 (hard cap effective).
- **No alert storms:** no 1-hour window with > 5 PRIMARY events.
- **Cooldown compliance:** no two PRIMARY events of the same `rule_id` within their cooldown window.
- **Coverage:** every regime change in the 1y data produces an R-2 event (assuming hysteresis confirmed).

### 7.2 Comparison against operator manual decisions

If `state/operator_decisions_log.jsonl` exists with operator-tagged actions:
- Decision layer should emit a corresponding event ≤ 5 minutes before / after each manual decision.
- Coverage rate target: ≥ 70 % of operator decisions had a corresponding decision-layer alert.

### 7.3 Edge cases

- **Stale data:** when any input is stale (D-1 / D-2 trigger), decision layer continues to emit but flags `stale: true` on each event.
- **Classifier disagreement:** when regime_state.regime_confidence < 0.60, R-3 fires; no E-1 / E-2 should fire while confidence is low.
- **Liquidation imminent:** M-4 must always emit immediately (no cooldown). Tested via simulated price spike.
- **Multiple simultaneous events:** if 3 events fire on the same evaluation, all 3 emit (no internal-batching), but `alert_router` cooldown still applies per-rule.

### 7.4 Production wire-up acceptance gate

Before live deployment:
1. Pass replay validation §7.1.
2. Run in shadow mode for 7 calendar days with logging enabled but no Telegram emission.
3. Operator review of shadow-mode log: subjective acceptance rate ≥ 80 % on PRIMARY events ("would I have wanted this alert?").
4. After sign-off, enable Telegram emission with hard cap monitoring for 14 calendar days.
5. If hard cap exceeded > 1 day in the 14-day period, halt and recalibrate.

---

## §8 Implementation TZ sequence

Each row is a separately-scoped TZ. All TZs are Claude-tier deliverables with explicit acceptance criteria.

| Step | TZ name | Scope | Prereq | Output |
|---:|---|---|---|---|
| 1 | `TZ-DECISION-LAYER-CORE-WIRE` | Implement `services/decision_layer/decision_layer.py`. Rules R-* + M-* + P-* + D-* (no MTF, no E- yet). Adds `dashboard_state.json["decision_layer"]` block. Adds `state/decision_log/decisions.jsonl` audit log. | none | basic decision layer running on dashboard cycle |
| 2 | `TZ-DECISION-LAYER-CONFIG` | Add `config/decision_layer.yaml` for operator-configurable thresholds (§3). Wire into core. | step 1 | thresholds editable without code change |
| 3 | `TZ-DECISION-LAYER-MTF` | Add T-* rules. Consumes `mtf_state` from companion design. Adds E-* rules (eligibility transitions). | step 1 + `MTF_DISAGREEMENT_v1` step 3 | MTF integration live |
| 4 | `TZ-DECISION-LAYER-TELEGRAM` | Wire PRIMARY / VERBOSE routing via existing `services/telegram/alert_router.py`. Register cooldown configs. | step 1 + `MTF_DISAGREEMENT_v1` step 5 (so cooldown infra ready) | Telegram emission live (after shadow-mode gate) |
| 5 | `TZ-DECISION-LAYER-AUDIT-LOG-ROTATION` | Implement monthly rotation policy for `decisions.jsonl`. Adds operator-side query helper script. | step 1 | audit log sustainable |
| 6 | `TZ-DECISION-LAYER-DASHBOARD-PANEL` | Render the new `decision_layer_recent_events` panel in `docs/dashboard.js` and `docs/dashboard.html`. | step 1 | operator sees events on dashboard |
| 7 | `TZ-DECISION-LAYER-OPERATOR-CALIBRATION` | After 7-day shadow mode (gate per §7.4), operator review and threshold adjustment. | step 4 | operator sign-off |

Steps 1-2 are the structural foundation; an MVP runs after just those two.
Steps 3 onward are progressive feature additions that don't block the MVP.

---

## §9 Open questions

1. **Operator-specific critical price levels.** Default uses `POSITION_CLEANUP_SIMULATION_v1` view zones (78 779, 80 000, 82 400). These may be stale — the position state has evolved since that simulation. Operator should re-confirm before step 1.

2. **Confidence thresholds (0.65 / 0.80).** Both anchors are defensible (`_REGIME_CONF_THRESHOLD` / RegimeForecastSwitcher cached state) but neither has been operator-validated for *decision-layer use*. Replay results in §7.1 will inform; final sign-off in step 7.

3. **Hysteresis bars (12).** From `HYSTERESIS_CALIBRATION_v1` H=1 calibration. Was selected for TRANSITION-rate band; *not* validated for "operator wants confirmation before regime change re-emits". May be too conservative (operator may want ~6 bars) or too aggressive (may want ~24). Empirical question.

4. **Volatility-regime axis activation.** `MARKET_DECISION_SUPPORT_RESEARCH` Q3-B recommends ATR%-based vol regime as a second axis to the activation matrix. If adopted, the decision layer's R-* rules expand to handle (regime × vol_regime) cells. This is **not** in §2 v1; flagged as v2 extension. Decision needed: is vol-regime-aware admissibility worth the matrix expansion now, or wait for live validation of v1?

5. **Position-delta thresholds (M-5).** 0.10 BTC / $500 are reasonable defaults but completely operator-preference. Solo-operator workflow may prefer finer (catch every grid fill) or coarser (only major manual ops). Step 7 calibration.

6. **Audit log retention policy.** Proposed: hot (current month), archived (monthly gzip). Alternative: hot 7 days, archived weekly. Storage budget consideration.

7. **Decision-layer evaluation cadence.** Currently aligns with dashboard build cadence (every dashboard refresh). If that's too slow for margin alerts (M-4 emergency), a separate fast-cycle just for M-* rules may be needed. Decision: keep it simple v1, fast-path later if needed?

8. **Interaction with `regulation_relevance.py` filter.** The decision layer emits structured events; the existing relevance filter would normally suppress non-regulation events. The decision layer's events are *all* regulation-relevant by construction (rules anchored in regulation), so the filter should pass them through. Confirm: should the filter become a no-op for decision-layer events, or run as a sanity gate?

9. **Suspended-config display.** When the operator queries about a suspended config (CFG-S-INDICATOR / CFG-L-DEFAULT), how does the decision layer respond? Proposal: E-3 emits to dashboard as INFO with explicit "permanently suspended per REG §2 — not deployable". Confirm this is desired vs simply not surfacing them at all.

10. **Liquidation-imminent emergency cooldown (M-4).** Proposed: zero cooldown. Counter-argument: even emergency events shouldn't spam more than once per minute. Choose: zero cooldown OR 60-second floor.

11. **Rate-limit hard cap (20 PRIMARY/day) recovery.** When the cap is hit, the layer suppresses further events. How does it recover the next day — full reset at midnight UTC, rolling 24h window, or operator-acknowledge-to-clear? Proposed: rolling 24h window. Confirm.

12. **Forecast re-introduction hook.** If a future `TZ-FORECAST-MODEL-REPLACEMENT` produces a model with positive resolution, where does its output enter the decision layer? Proposed: as a new severity-tier (BLEND-VERBOSE) with severity-mapping rules; do not introduce as a primary input. Future-design question.

---

## CP report

- **Output path:** [`docs/DESIGN/DECISION_LAYER_v1.md`](DECISION_LAYER_v1.md)
- **Sections complete:** 9/9
- **Open questions:** 12
- **Implementation TZ sequence:** 7 staged TZs in §8
- **Compute time:** ~1 minute (synthesis-only; no driver runs)
- **Anti-drift compliance:**
  - ✅ No code changes (pure design).
  - ✅ No regulation modification (the layer reads regulation; does not revise it).
  - ✅ No regime classifier changes.
  - ✅ No new ML models specified — the decision layer is rule-based by design.
  - ✅ Numbers grounded in `HYSTERESIS_CALIBRATION_v1` (H=1, hysteresis=12), `RegimeForecastSwitcher._REGIME_CONF_THRESHOLD = 0.65`, `POSITION_CLEANUP_SIMULATION_v1` margin tiers, `PLAYBOOK_MANUAL_LAUNCH_v1` §5 hard stops, `REGIME_PERIODS_2025_2026` episode statistics.
  - ✅ Phased rollout: step 1+2 give a functional MVP without MTF / Telegram; steps 3-7 layer on incrementally.
  - ✅ Open questions explicit where data or operator preference is needed before commit.
