> ⚠️ Q2 REFRAME (2026-05-05): `TRANSITION_MODE` policy choice as originally framed is meaningless. `TRANSITION` is about `7%` of the year after `H=1` calibration, and the policy result is sign-conditional by pack rather than a single global pause rule. The real coordinator question is a regime-conditional activation matrix, not a global `TRANSITION` policy choice. See `docs/REGULATION_v0_1_1.md` §3-§4 for the current operational rules. Q2 is closed by reframing, not by policy selection.

# P8 Dual-Mode Coordinator — v0.1 design

**Status:** GREENFIELD DESIGN (TZ-K, Block 12 of week 2)
**Date:** 2026-05-05
**Track:** P8 — central architecture work
**Pre-reqs:** Block 7 (range detection), Block 6 (bot inventory), Blocks A/B (registry + regime periods), CP24/CP28 (regime overlay + joint findings).
**Output gate per brief:** v0.1 design only. No implementation, no backtest harness, no per-trade override logic.

---

## §1 Goal

**The coordinator decides, every minute, which bots from the catalog should be running, paused, or closed — given the current regime label, indicator events, and portfolio state — and issues GinArea API actions to make reality match.**

That single sentence is the whole job. Everything below is mechanics.

---

## §2 Architecture overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ INPUTS                                                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────┐   ┌─────────────────────────┐                  │
│  │ Regime classifier       │   │ Indicator gate signals  │                  │
│  │ (existing — services/   │   │ (existing — Price%      │                  │
│  │  market_forward_        │   │  threshold, ATR-based)  │                  │
│  │  analysis/regime_*)     │   │                         │                  │
│  │                         │   │ Emits: indicator_fired  │                  │
│  │ Emits: {label, conf,    │   │   {direction, threshold,│                  │
│  │  stable_bars,           │   │    ts, price}           │                  │
│  │  candidate_regime}      │   │                         │                  │
│  │                         │   │ One-shot per session    │                  │
│  │ Resolution: 5m → 1h →   │   │ (until reset by full    │                  │
│  │  4h-anchored decisions  │   │  bot-close).            │                  │
│  └────────────┬────────────┘   └────────────┬────────────┘                  │
│               │                              │                              │
└───────────────┼──────────────────────────────┼──────────────────────────────┘
                │                              │
                ▼                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ COORDINATOR (NEW — services/ensemble/coordinator.py)                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐                                                     │
│  │ State machine       │   reads bot_registry.json + GinArea status          │
│  │  (§3 — RANGE_MODE / │                                                     │
│  │   MARKUP_MODE /     │   reads bot_config_catalog (§4)                     │
│  │   MARKDOWN_MODE /   │                                                     │
│  │   TRANSITION_MODE / │   evaluates position-level guards (§5)              │
│  │   IDLE_MODE)        │                                                     │
│  └──────────┬──────────┘                                                     │
│             │                                                                │
│             │ desired bot lifecycle = {bot_uid: ACTIVE/PAUSED/CLOSED}        │
│             ▼                                                                │
│  ┌─────────────────────┐                                                     │
│  │ Action layer (§6)   │ — diff desired vs actual                            │
│  │                     │ — emit minimal set of API ops                       │
│  └──────────┬──────────┘                                                     │
│                                                                              │
└─────────────┼────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ EXECUTION LAYER                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  GinArea API (services/ginarea_api/) — start/pause/close/edit-params         │
│  Position state — read from ginarea_live/snapshots.csv                       │
│  Coordinator state — write to data/ensemble/coordinator_state.json           │
│  Audit log         — append data/ensemble/coordinator_log.jsonl              │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key separation of concerns:**

- **Inputs are read-only.** Coordinator never writes back to regime classifier or indicator gate.
- **Action layer is idempotent.** Re-running coordinator after a crash converges to the same desired state without duplicate actions.
- **Audit log is append-only.** Every state-machine transition + API call gets one line. Operator can replay.

---

## §3 State machine

### States

| State | Meaning | Active bot classes |
|-------|---------|--------------------|
| `IDLE_MODE` | Coordinator just started or operator paused. No actions until next tick. | none |
| `RANGE_MODE` | regime classifier == RANGE for ≥ N hysteresis bars. Sideways market expected. | Range LONG + Range SHORT (paired hedge baseline) |
| `MARKUP_MODE` | regime classifier == MARKUP, regime_stability > threshold. | Trend LONG (Impulse if indicator fired) + Range bots PAUSED |
| `MARKDOWN_MODE` | regime classifier == MARKDOWN, regime_stability > threshold. | Trend SHORT (Impulse if indicator fired) + Range bots PAUSED + EXTRA GUARDS (§5) |
| `TRANSITION_MODE` | regime classifier reports candidate ≠ last_regime AND not yet stable for hysteresis bars. | All bots **paused not closed** (per Finding B — preserve grids); awaiting confirmation. |

### Transitions

Triggered by re-evaluation each tick (every 60s):

```
IDLE ──first regime read──► (corresponding mode)

RANGE ─────classifier flips─────► TRANSITION
                                       │
                  ┌────────────────────┤
                  │   stability        │   stability
                  │   confirms NEW     │   reverts to OLD
                  ▼                     ▼
        MARKUP_MODE / MARKDOWN_MODE   RANGE_MODE
        (hysteresis bars met)         (transient blip)

ANY_MODE ──operator /pause command──► IDLE_MODE
```

**Hysteresis** — borrowed from `RegimeForecastSwitcher` (12 bars confirmation, 0.65 confidence threshold). Coordinator does NOT re-implement; it consumes switcher's effective regime.

**TRANSITION_MODE pauses (does not close).** Per **Finding B** (operator+MAIN consensus): a SHORT grid that's accumulated 2 BTC of position over 8 hours should not be hard-closed when the classifier briefly flickers to MARKUP — that locks in losses. Pausing keeps the grid available for resume if the flicker reverts.

### Indicator events influence state but do not own it

Indicator gate signals (`Price% > 0.3%` threshold from §6 of GINAREA_MECHANICS) tell the coordinator **when** to *start* a trend-following bot (e.g. Impulse LONG / Far SHORT). They do NOT change the state machine label. Per **Finding A**:

> *Regime label says "we're in MARKUP." Indicator firing says "now is a good moment to deploy the Impulse LONG bot **within** that MARKUP regime." Without indicator firing, MARKUP_MODE keeps the trend LONG bot paused — regime alone isn't an entry signal.*

Concrete: in MARKUP_MODE with no indicator event, coordinator activates only Range bots (LONG-favored sizing). When indicator fires, coordinator additionally activates the Impulse LONG bot. Mirror logic in MARKDOWN_MODE.

### SHORT activation extra guards (Finding B)

In MARKDOWN_MODE, before activating any new SHORT bot:

1. Cumulative SHORT BTC across all already-running bots ≤ `MAX_CUMULATIVE_SHORT_BTC` (default 3.0 BTC; operator-tunable). If exceeded → coordinator **does not** activate a new SHORT, logs `guard:short_cap_exceeded`.
2. Free margin %  ≥ `MIN_FREE_MARGIN_PCT_FOR_SHORT_OPEN` (default 30%).
3. Last-hour 1h price change > −2% (don't open SHORT into a moving vertical drop — that's manual operator territory).

These guards reflect the operator's PARAM_CHANGE clusters morning-of (manual response to runaway accumulation) — coordinator codifies what operator already does manually.

---

## §4 Bot config catalog formalization

The catalog is a **data file** (`data/ensemble/bot_config_catalog.json`), not embedded constants. Each entry maps `(state, signal_qualifier)` → bot preset with explicit activation/deactivation conditions.

### Schema

```json
{
  "version": "v0.1",
  "presets": {
    "<preset_id>": {
      "display_name": "...",
      "side": "long|short|both",
      "params": {
        "grid_step_pct": 0.03,
        "target_pct": 0.25,
        "order_size_btc": 0.001,        // or order_size_usd for inverse
        "order_count": 200,
        "instop_pct": 0.018,
        "min_stop_pct": 0.008,
        "max_stop_pct": 0.025,
        "boundaries": [68000, 78600],   // optional; inherits from operator config
        "indicator": {                   // optional
          "type": "Price%",
          "tf_minutes": 1,
          "period": 30,
          "threshold_pct": 0.3
        }
      },
      "activation": {
        "states": ["RANGE_MODE", "MARKUP_MODE"],
        "requires_indicator_fired": false,
        "extra_conditions": ["regime_stability > 0.7"]
      },
      "deactivation": {
        "states": ["IDLE_MODE", "MARKDOWN_MODE"],
        "action_on_state_exit": "pause"   // pause | close
      },
      "limits": {
        "max_position_btc": 1.0,
        "hard_close_drawdown_pct": null    // null = no hard-close trigger
      },
      "evidence": ["BT-014", "BT-015"]    // links to BT-XXX from registry
    }
  }
}
```

### Initial catalog (v0.1, BTC only)

| Preset ID | Display | Side | Active states | Requires indicator | Source/evidence |
|-----------|---------|------|---------------|--------------------|------------------|
| `range_long_d_volume` | LONG-D-volume | long inverse | RANGE_MODE, MARKUP_MODE | no | MASTER §6 catalog row "LONG-D-volume", evidence: live BTC-LONG-C/D running production |
| `range_long_02may` | Range LONG (02may preset) | long inverse | RANGE_MODE | yes (indicator fired = "buy dip") | BT-014 / BT-015 / BT-016 / BT-017 (G4 from registry) — all profitable +0.05 to +0.08 BTC over 86d |
| `range_short_test` | TEST_1/2/3 SHORT | short linear | RANGE_MODE, MARKDOWN_MODE | yes | live TEST_1/2/3, MASTER §6 |
| `trend_short_far_hyp` | Far Short [HYP] | short linear | MARKDOWN_MODE | yes (Price% > 1% threshold + hard guards §5) | MASTER §6 catalog row "Far Short [HYP]"; no BT evidence yet — flagged "needs backtest" |
| `impulse_long_rej` | Impulse Long [REJ] | long inverse | MARKUP_MODE | yes (rejection-of-N1 trigger) | MASTER §6 row "Impulse Long [REJ]"; KLOD_IMPULSE in production currently has 0 firings — trigger TOO STRICT, flagged for re-tune |
| `counter_long_hedge` | Counter-LONG hedge | long inverse | TRANSITION_MODE only (cascade rescue) | yes (cascade-detection signal) | MASTER §6 row "Counter-LONG hedge"; TTL 15-45min |

**Three explicit gaps** the catalog flags but doesn't close:

1. **No "Trend SHORT MARKDOWN-anchored" preset matches BT evidence.** G3 (SHORT 02may with INDICATOR + P&L Trail) all losing across TPs. Coordinator treats trend SHORT as **research/paper** until a profitable SHORT MARKDOWN preset is identified.
2. **No "Range SHORT" with Indicator OFF.** All current SHORT presets require indicator. If RANGE_MODE wants pure-mean-reversion SHORT (no indicator), the catalog has no row → coordinator does not start a SHORT in RANGE without indicator.
3. **`impulse_long_rej` is currently inert** in production (KLOD_IMPULSE 0 firings/week per operator note in MASTER §6). Coordinator includes it but operator should expect 0 activations until trigger is re-tuned.

### Registry-evidence cross-reference

Every preset that has BT evidence cites the BT IDs. Presets without evidence (`trend_short_far_hyp`) carry an explicit "no evidence yet, paper-only" flag. v0.1 coordinator **only activates evidence-backed presets in production mode**; non-evidence presets stay in paper mode.

---

## §5 Position-level guards

### Per-bot

| Guard | Threshold | Action |
|-------|-----------|--------|
| Position notional | ≥ `preset.limits.max_position_btc` | Pause that bot, no new IN orders |
| Bot drawdown vs entry | ≥ `preset.limits.hard_close_drawdown_pct` (if set) | Close bot at market, log `guard:bot_dd_hard_close` |

### Cumulative (across all bots)

| Guard | Threshold | Action |
|-------|-----------|--------|
| Cumulative SHORT BTC | ≥ `MAX_CUMULATIVE_SHORT_BTC` (default 3.0) | Block any new SHORT activation. Log + Telegram operator notice. |
| Cumulative LONG USD notional | ≥ `MAX_CUMULATIVE_LONG_USD` (default $50,000) | Same, blocks new LONG. |
| Cumulative net BTC delta | abs(net_btc) ≥ `MAX_NET_BTC_DELTA` (default 4.0) | Pause LEAST-recently-active bot on the over-side. (Not close — preserves grid.) |

### Margin / liquidation risk

| Guard | Threshold | Action |
|-------|-----------|--------|
| Free margin % | ≤ `MIN_FREE_MARGIN_FORCE_DELEV_PCT` (default 15%) | Force-deleverage: pause newest 50% of bots (by activation time). Log + critical Telegram alert. |
| Free margin % | ≤ `KILLSWITCH_FREE_MARGIN_PCT` (default 5%) | Hard-close the most recently-opened bot on the losing side. Last-resort. Log + critical alert. |
| Liquidation distance | < `MIN_LIQ_DISTANCE_PCT` (default 1.5%) | Critical alert. Coordinator does NOT auto-close in v0.1 — operator must intervene. |

### Why pause beats close (Finding B applied to guards)

Operator P0 principle (MASTER §7): *"никогда не закрывать в минус (без крайней необходимости)"*. Coordinator preserves this principle: pause is preferred for everything except the killswitch case. A paused grid retains all open IN orders and resumes work when conditions change. A closed grid forces realization of intermediate losses and starts from scratch.

The PARAM_CHANGE clusters from operator activity that morning (cumulative SHORT exposure manual response) become **automatic guards** rather than emergencies — operator stops being a real-time risk monitor.

---

## §6 Lifecycle operations

### Bot startup procedure

```
1. Coordinator decides: bot_uid X should be ACTIVE.
2. Read current bot status from GinArea API (cache 60s).
3. If status == running → no-op (idempotent).
4. If status == paused → POST /bots/{id}/resume.
5. If status == off → POST /bots/{id}/start (with validated params from catalog).
6. Append to coordinator_log.jsonl: {ts, action, bot_uid, before_status, after_status}.
```

### Bot pause vs close decision tree

```
Reason for deactivation:
├─ State exit (regime change) → action_on_state_exit from preset (default: pause)
├─ Position guard tripped     → pause (preserve grid)
├─ Free margin guard tripped  → pause (force-deleverage)
├─ Killswitch fires           → close (last-resort, hard)
└─ Operator manual command    → operator chooses pause/close
```

### Bot restart with new params

If regime change requires **same bot side but different TP** (e.g. RANGE → MARKUP, range LONG with TP=0.25 → trend LONG with TP=0.21):

1. Pause the existing bot.
2. Activate the new preset (different bot_uid). Old bot stays paused, holding its position.
3. Coordinator does NOT edit params on the old running bot — that introduces semantic ambiguity (whose TP applies to existing IN orders?). Always-new-bot policy.
4. Old bot eligible for resume only if regime returns. If it never does, operator manually closes after some operator-defined cool-off.

### Coordinator restart safety

State on disk (`data/ensemble/coordinator_state.json`) holds:

```json
{
  "current_state": "RANGE_MODE",
  "since_ts": "2026-05-05T12:00:00Z",
  "active_bots": ["binance:long:btcusdt:003", "binance:short:btcusdt:001"],
  "paused_bots": [],
  "guards_tripped": [],
  "last_indicator_event": null,
  "version": "v0.1"
}
```

On startup:
1. Load state file.
2. Read GinArea actual status for each bot in `active_bots` / `paused_bots`.
3. Diff: emit minimal action set to converge real to desired.
4. If state file missing/corrupted → enter `IDLE_MODE`, alert operator, await manual confirm.

### Failure modes

| Scenario | Coordinator behavior |
|----------|---------------------|
| GinArea API timeouts on tick | Retry next tick (60s). If >5 min consecutive failures, enter `IDLE_MODE`, Telegram alert. |
| Regime classifier returns stale state (no update >5 min) | Treat as `regime_stability=0`, force `TRANSITION_MODE`, no bot activations. |
| Partial action: started bot A but failed bot B | Action layer logs partial; next tick retries B. No rollback of A. |
| GinArea reports bot status that doesn't match catalog params | Log discrepancy, do not auto-edit. Operator manual review. |
| Snapshots.csv stale (>2 min) per freshness layer | Coordinator treats position numbers as estimates; cumulative guards use last-known + recent fills upper-bound. |

---

## §7 Rebate awareness (placeholder for future enhancement)

**Acknowledged in design, not implemented in v0.1.**

Operator has not provided the specific BitMEX/Binance rebate tier currently active, so the rule "keep bot alive even at low gross PnL if rebate > cost" cannot be parameterized today. The coordinator architecture supports this via:

- A future `rebate_config.json` with: `tier_name`, `volume_target_per_period_usd`, `rebate_pct_per_volume`, `current_period_volume_usd`.
- A future guard layer that adjusts deactivation thresholds: if cumulative period volume is below tier-upgrade threshold, the deactivation action gets a softer trigger (pause instead of close, hold longer).
- An optional `volume_minimum_per_period` constraint in preset definitions: bot is kept active until volume target is hit, even if it would otherwise be deactivated.

**TODO for v0.2+:**
- Operator provides current rebate tier and volume target.
- Implement `rebate_aware_deactivate()` policy on top of base lifecycle.
- Re-evaluate after one full rebate period to validate the rule is producing intended behavior.

This is **not a v0.1 blocker** — coordinator works without rebate awareness; rebate optimization is a layer that gets added later without restructuring.

---

## §8 Validation plan

Three phases, each gating the next.

### Phase 1 — Paper mode (no API calls)

Coordinator runs against live regime classifier + indicator events but **does not call GinArea API**. Instead:

- All decisions logged to `data/ensemble/coordinator_log.jsonl` as if they would have been executed.
- Operator reviews 24h log, confirms decisions match what they would have done manually.
- **Gate to Phase 2:** at least 24 hours of paper logs with operator approval of ≥80% of decisions.

### Phase 2 — Backtest replay

Feed historical regime classifier outputs (`data/forecast_features/full_features_1y.parquet`) + synthetic indicator events into the coordinator, watch which bot-state sequence it would have produced over the 1y window.

- Compare resulting (bot, regime, hours) buckets to `REGIME_OVERLAY_v1.md` actual results.
- Validate that for evidence-backed presets (G4 LONG 02may), the coordinator's chosen activation periods cover the periods where those bots were actually profitable.
- Identify cases where coordinator would have intervened differently than what the operator did manually.
- **Gate to Phase 3:** no catastrophic-disagreement cases (coordinator chose aggressive SHORT when operator chose pause-everything, or similar).

### Phase 3 — Phased live rollout

| Stage | Bots under coordinator control | Operator role |
|-------|-------------------------------|---------------|
| Stage A (1 bot) | One non-critical bot (e.g. paused TEST_3 first reactivated under coordinator) | Watches every action, can override at any tick |
| Stage B (3 bots) | Add a Range LONG + a Range SHORT after Stage A is stable for 7 days | Daily review, approve weekly continuation |
| Stage C (full ensemble) | All evidence-backed presets | Weekly review only; coordinator is primary controller |

**Rollback:** at any stage, operator can disable coordinator via env var (`P8_COORDINATOR_ENABLED=0`) and resume manual control. State file persists; resuming is one env var flip.

---

## §9 Open questions for operator (capped at 5)

Each question has a MAIN-default. Operator confirms or overrides.

### Q1. SHORT cumulative cap value

**Default proposal:** `MAX_CUMULATIVE_SHORT_BTC = 3.0 BTC` based on operator's morning PARAM_CHANGE response point (cumulative shorts hit ~2.2 BTC before manual intervention).

**Question:** Is 3.0 BTC the right cap, or should it be tied to free margin % rather than absolute BTC?

### Q2. TRANSITION_MODE policy: pause or hold?

**Default proposal:** **pause all bots** during TRANSITION_MODE (between regime confidence breakdown and new regime confirmation). This sacrifices some grid yield for risk reduction.

**Question:** Is this too cautious? Alternative: keep RANGE bots running, only pause trend bots during transitions.

### Q3. Should `impulse_long_rej` (currently inert, 0 firings/week) be in the catalog?

**Default proposal:** Yes, kept as-is. Coordinator inactive on it doesn't cost anything; if trigger gets re-tuned, no catalog update needed.

**Question:** Or remove until trigger is fixed (cleaner state machine, no dead-code presets)?

### Q4. Hard-killswitch threshold for free margin

**Default proposal:** `KILLSWITCH_FREE_MARGIN_PCT = 5%` triggers a hard-close of the most recently opened bot on the losing side.

**Question:** Is 5% the right line (operator P0 principle says avoid closing in minus)? Alternative: do NOT auto-close even at 5%, only Telegram alert and let operator decide.

### Q5. Coordinator tick interval

**Default proposal:** 60s (matches dashboard refresh, GinArea API limits comfortable).

**Question:** Is 60s too slow for a vertical-drop scenario where guards need to fire faster, or appropriate?

---

## §10 Anti-drift safeguards — what v0.1 does NOT do

Explicit non-scope for v0.1:

| Excluded | Reason |
|----------|--------|
| **No ML / regression / learned thresholds** | Per anti-drift rule — rule-based v0.1 strict |
| **No per-trade override** | Coordinator manages bot lifecycle, NOT individual orders within a bot |
| **No manual mode switching from operator side via Telegram** | Operator pause/resume is a future TZ; v0.1 operator changes via env var + restart |
| **No cross-asset coordination** | BTC only. XRP/ETH presets exist in catalog for future, but v0.1 coordinator hard-skips non-BTC |
| **No self-regulating bot research** | Operator's separate side-idea — separate track |
| **No backtest harness** | Phase 2 validation harness is a separate TZ |
| **No GinArea API auth retry / re-login flow** | v0.1 assumes stable session; reauth is operator-managed |
| **No multi-region failover** | Single deployment |
| **No A/B testing of presets in production** | Phase rollout is sequential, not parallel |

### v0.2+ backlog (informal, for next design iteration)

- Rebate-aware deactivation (§7)
- Operator pause/resume Telegram commands
- Multi-asset (XRP first)
- Online preset performance tracking → automatic preset retirement when sustained losses
- Real-time preset re-tuning (e.g. adjust TP based on rolling Sortino)
- ML layer for regime classifier confidence boost
- Cross-bot anti-correlation guard (don't activate bots whose strategies would close orders against each other)

---

## §11 Files this design implies (not built in this TZ)

| File | Purpose |
|------|---------|
| `services/ensemble/__init__.py` | New package |
| `services/ensemble/coordinator.py` | State machine + tick loop |
| `services/ensemble/state_machine.py` | Pure state-transition logic (testable in isolation) |
| `services/ensemble/action_layer.py` | Idempotent diff + GinArea API calls |
| `services/ensemble/guards.py` | Position + margin + cumulative checks |
| `data/ensemble/bot_config_catalog.json` | Catalog (operator-editable) |
| `data/ensemble/coordinator_state.json` | Persistent state, written each tick |
| `data/ensemble/coordinator_log.jsonl` | Append-only audit log |
| `core/tests/test_coordinator_state_machine.py` | State transition tests |
| `core/tests/test_coordinator_guards.py` | Guard logic tests |
| `core/tests/test_coordinator_lifecycle.py` | Action layer tests with mocked GinArea client |

Implementation is the next TZ once design is operator-approved. Estimate: ~3-4h wall-clock for skeleton + state machine + guards + tests; phase 2/3 rollout is calendar weeks.

---

## §12 Summary

The coordinator is **a thin state machine that reads two existing inputs (regime classifier + indicator gate), writes one decision per minute (which bots active), and codifies operator-already-manual risk behaviors as automatic guards**. It does not invent new strategies, learn from data, or override human judgment — it removes the need for the operator to be a real-time risk monitor while preserving the option to intervene at any tick.

Three principles sit underneath every choice:

1. **Pause beats close** (operator P0): preserve grids when conditions are uncertain.
2. **Indicator firing gates trend bot activation, regime alone gates range bots** (Finding A): without an indicator event, MARKUP_MODE keeps trend bots paused.
3. **SHORT requires explicit cumulative + margin guards** (Finding B): asymmetric risk demands asymmetric protection.

Five operator questions in §9, four phased validation gates in §8, ten files implied in §11, twelve excluded from scope in §10. Implementation is the next TZ.
