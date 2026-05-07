# Multi-Timeframe Disagreement Detection — Design v1

**Status:** DESIGN. No code, no tests.
**Date:** 2026-05-05
**TZ:** TZ-MTF-DISAGREEMENT-DETECTION-DESIGN
**Companion design:** [`DECISION_LAYER_v1.md`](DECISION_LAYER_v1.md)

**Foundation evidence:**
- [`docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md`](../RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md) §1 Q2 (MTF synthesis), Q6 alert fatigue tiering.
- [`docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md`](../RESEARCH/HYSTERESIS_CALIBRATION_v1.md) — H=1 calibration; TRANSITION = 7.35 % of year at hourly resolution.
- [`docs/RESEARCH/REGIME_PERIODS_2025_2026.md`](../RESEARCH/REGIME_PERIODS_2025_2026.md) — episode statistics: median trending episode 3 h, mean 7.5-7.7 h.
- [`docs/REGULATION_v0_1_1.md`](../REGULATION_v0_1_1.md) §3 (activation matrix, regime taxonomy).
- [`services/market_forward_analysis/phase_classifier.py`](../../services/market_forward_analysis/phase_classifier.py) (`PhaseClassifier` logic; current MARKUP / MARKDOWN / RANGE source for the MTF-aligned taxonomy). Source verified in `TZ-MTF-FEASIBILITY-CHECK` (2026-05-05).
- [`core/orchestrator/regime_classifier.py`](../../core/orchestrator/regime_classifier.py) (parallel taxonomy: RANGE / TREND_UP / TREND_DOWN / COMPRESSION / CASCADE_*).

---

## §1 Architecture

### Block diagram

```
            ┌──────────────────────────────────────────────────────────────┐
            │  OHLCV multi-TF feeds (already collected via market_collector)│
            │     5m, 15m, 1h, 4h, 1d                                       │
            └──────────────┬───────────────────────────────────────────────┘
                           │
                           ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Per-TF signal computation                                          │
   │    (each TF independent, zero cross-TF data leakage)                │
   │                                                                      │
   │   ┌─15m ──┐  ┌── 1h ──┐  ┌── 4h ──┐  ┌── 1d ──┐                     │
   │   │       │  │        │  │        │  │        │                     │
   │   │ A.regime_label                                                  │
   │   │ B.trend_dir   (up/down/flat)                                    │
   │   │ C.vol_regime  (low/normal/high)                                 │
   │   │       │  │        │  │        │  │        │                     │
   │   └───┬───┘  └────┬───┘  └────┬───┘  └────┬───┘                     │
   └───────┼───────────┼───────────┼───────────┼─────────────────────────┘
           │           │           │           │
           └───────────┴─────┬─────┴───────────┘
                             ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Cross-TF disagreement detector                                     │
   │    Inputs: 4×3 = 12 signal cells                                    │
   │    Compute: pairwise comparisons HTF↔LTF                            │
   │    Apply: confidence gate, persistence gate, TRANSITION exemption   │
   │    Output: disagreement state {NONE | MINOR | MAJOR}                │
   │            + descriptor (which TFs, which signal type, magnitude)    │
   └──────────────────────────────────┬───────────────────────────────────┘
                                      ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Decision layer (DECISION_LAYER_v1)                                 │
   │    Consumes disagreement state alongside regulation matrix +        │
   │    position state to emit operator-actionable output.               │
   └──────────────────────────────────┬───────────────────────────────────┘
                                      ▼
                       Telegram PRIMARY / dashboard
```

### Operating principle (top-down MTF gating with disagreement-as-veto)

- **Agreement is silent.** When all four TFs agree on regime label and trend direction, no alert fires. The regulation card simply renders the active regime; no Telegram event.
- **Minor disagreement is informational only.** When one adjacent-TF pair (e.g. 15m vs 1h) disagrees but HTFs (4h, 1d) still agree, the system logs the disagreement to the audit log and updates a `mtf_state` block in `dashboard_state.json`, but does not emit a Telegram event.
- **Major disagreement is a PRIMARY-channel alert.** When HTFs (4h or 1d) disagree with each other, OR when HTF and LTF give opposite directional readings *and* the disagreement persists past a threshold, the system emits a Telegram PRIMARY-channel alert with explicit action context.

### Existing infrastructure dependencies

- The current `PhaseClassifier` logic in [`services/market_forward_analysis/phase_classifier.py`](../../services/market_forward_analysis/phase_classifier.py) is the verified source of per-TF `MARKUP / MARKDOWN / RANGE`-aligned labels for the MTF design. Source verified in `TZ-MTF-FEASIBILITY-CHECK` (2026-05-05).
- `core/orchestrator/regime_classifier.py` consumes multi-TF *features* (15m, 1h, 4h) inside its computation but emits a **single regime label**. It does not produce per-TF labels.
- **Per-TF independent classification is therefore a prerequisite for this design** and is flagged in §9. See the implementation TZ sequence in §8 for the staged rollout.

---

## §2 TF coverage

### Supported TFs and per-TF signals

The design covers four timeframes. Three signal types are computed per TF (independently).

| TF | Bar interval | Role | Signal A: regime label | Signal B: trend direction | Signal C: volatility regime |
|---|---|---|:---:|:---:|:---:|
| **15m** | 15 minutes | LTF — entry/timing context | yes | yes | yes |
| **1h** | 1 hour | LTF/HTF transition — primary working frame | yes | yes | yes |
| **4h** | 4 hours | HTF — strategic context | yes | yes | yes |
| **1d** | 1 day | HTF — top-of-stack context | yes | yes | yes |

### Signal A — regime label (per TF)

Adopt the `PhaseClassifier` taxonomy subset already aligned with `REGULATION_v0_1_1.md` §1: **`MARKUP / MARKDOWN / RANGE`**. DISTRIBUTION is reserved at the design surface.

The design **does not** introduce new regime states. Each TF runs the same classifier independently, fed only its own bars.

### Signal B — trend direction (per TF)

Three-state output: **`up / down / flat`**. Computed via simple price-action rule, not a model:

- `up` if EMA-20 of TF > EMA-50 of TF AND `last_close > EMA-20`.
- `down` if EMA-20 of TF < EMA-50 of TF AND `last_close < EMA-20`.
- `flat` otherwise.

Justification for this choice over a heavier indicator: trend direction is a *coarse* dimension here (we already have regime label A); we want a fast, deterministic, cheap-to-compute signal that can disagree with regime label A in informative ways (regime says RANGE but trend says up = drift; regime says MARKUP but trend says down = potential exhaustion).

### Signal C — volatility regime (per TF)

Three-state output: **`low / normal / high`**, derived from ATR percentile within the TF's own rolling window.

- `low` if ATR-14 percentile (rolling 30 days at this TF) ≤ 25.
- `high` if ≥ 75.
- `normal` otherwise.

Per `REGIME_OVERLAY_v2_1.md` and `MARKET_DECISION_SUPPORT_RESEARCH` Q3-B, volatility regime as a second axis to the activation matrix is a research-supported extension. This signal is the data input for that.

### Cell summary

The MTF state at any moment is a 4 × 3 grid (4 TFs × 3 signal types) = **12 cells**, each holding a discrete value.

```
                15m         1h          4h          1d
A regime    : MARKUP      RANGE       RANGE       RANGE
B trend     : up          flat        flat        up
C vol       : high        normal      normal      low
```

This 12-cell state is the input to §3.

---

## §3 Disagreement metrics

The detector emits one of three states: **`NONE`**, **`MINOR`**, **`MAJOR`**. The state is derived from per-cell pair comparisons with explicit thresholds.

### 3.1 Categorical disagreement (Signal A — regime label)

Pairwise comparison among `{15m, 1h, 4h, 1d}` regime labels:

- **A-major:** any HTF (4h or 1d) holds a different regime label from another HTF, OR the 1d HTF holds a regime opposite to the 1h LTF (`MARKUP` vs `MARKDOWN` only — `RANGE` paired with either is *not* opposite).
- **A-minor:** at least one TF differs from the modal label across all four TFs, but HTFs (4h, 1d) agree with each other AND no opposite-direction conflict exists.
- **A-none:** all four TFs hold the same regime label.

**Confidence weighting.** Each TF's regime classifier output ships with a `regime_confidence` field (0..1). A cell is **eligible** for disagreement contribution only if `regime_confidence ≥ 0.65` (matches `_REGIME_CONF_THRESHOLD` already used in `RegimeForecastSwitcher` hysteresis logic). Cells below 0.65 are tagged **`uncertain`** and contribute neither agreement nor disagreement; they are reported separately.

### 3.2 Direction conflict (Signal B — trend direction)

- **B-major:** 1d trend and 15m trend are *opposite* (`up` vs `down`); persistent ≥ B-persistence threshold (see 3.4).
- **B-minor:** any non-adjacent pair has opposite direction (e.g. 1h `up` vs 4h `down`) but 1d and 15m do not contradict.
- **B-none:** no opposite-direction pair, or the only conflicts are with `flat` (flat does not contradict up/down).

### 3.3 Volatility-regime conflict (Signal C)

- **C-major:** any HTF reports `low` while any LTF reports `high` (volatility expansion at LTF inside a calm HTF — characteristic of regime transition).
- **C-minor:** any single-step adjacent disagreement (e.g. 1h `normal` vs 4h `low`).
- **C-none:** all four TFs agree.

### 3.4 Persistence requirement (anti-flicker)

To avoid alerts on transient single-bar disagreements:

- **Major disagreement persistence threshold:** 12 LTF bars (= 3 hours when LTF=15m, since 15m × 12 = 3h, matching the median trending-episode length per `REGIME_PERIODS_2025_2026` §2).
- **Minor disagreement persistence threshold:** **n/a** (minor never alerts; it's logged but no Telegram event).
- **B-persistence:** 6 LTF bars (1.5 h at 15m); shorter than A because trend conflicts resolve faster than regime conflicts in our data.
- **C-persistence:** 12 LTF bars.

The choices are anchored in `REGIME_PERIODS_2025_2026` median episode = 3 h. A disagreement that does not persist past the median episode is more likely a regime micro-flip than an actionable signal.

### 3.5 TRANSITION exemption

Per `HYSTERESIS_CALIBRATION_v1` H=1 calibration: TRANSITION hours are 7.35 % of the year. During a TRANSITION-flagged hour (rolling 1-bar window contains ≥2 distinct regime labels at the 1h TF), the disagreement detector **suppresses MAJOR alerts** but still records to the audit log. This prevents the detector from re-firing on every regime micro-flip.

### 3.6 Combined state machine

```
Inputs every bar:
  A_state_per_TF, B_state_per_TF, C_state_per_TF, conf_per_TF

Compute:
  disagreement_per_dim = {A, B, C} → {NONE, MINOR, MAJOR}

Aggregate:
  if any_dim is MAJOR AND persistence_threshold met
    AND TRANSITION flag is FALSE:
      state := MAJOR
      descriptor := which dim, which TFs, magnitude
  elif any_dim is MAJOR AND TRANSITION is TRUE:
      state := MAJOR_SUPPRESSED  (logged only)
  elif any_dim is MINOR:
      state := MINOR  (logged + dashboard, no Telegram)
  else:
      state := NONE
```

### 3.7 Threshold summary table

| Threshold | Value | Source |
|---|:---:|---|
| Confidence eligibility floor | 0.65 | Source verified in `TZ-MTF-FEASIBILITY-CHECK` (2026-05-05); calibrated against the MTF-aligned classifier output |
| A-major persistence (LTF bars) | 12 | median trending episode = 3h ≈ 12×15m |
| B-major persistence (LTF bars) | 6 | trend conflicts resolve faster |
| C-major persistence (LTF bars) | 12 | matches A |
| TRANSITION exemption hysteresis | H=1 | `HYSTERESIS_CALIBRATION_v1` calibration |

---

## §4 Alert generation

### 4.1 When to alert

Only `state = MAJOR` (and not `MAJOR_SUPPRESSED`) emits a Telegram event. `MINOR` updates `dashboard_state.json mtf_state` only.

### 4.2 Channel

PRIMARY only. Per `MARKET_DECISION_SUPPORT_RESEARCH` Q6-A (tiered alert classification, AHRQ healthcare CDS literature), MTF disagreement is a *state-change-of-admissibility* event — the regulation activation matrix may need re-evaluation. That makes it inherently a PRIMARY-channel concern, not a VERBOSE one. Existing `services/telegram/alert_router.py` channel mapping should add `MTF_DISAGREEMENT` as PRIMARY.

### 4.3 Alert template (text, Russian)

```
⚠️ MTF disagreement: {dim_label} — {magnitude} ({htf} ↔ {ltf})

  • {htf}: {htf_signal}    confidence {htf_conf:.2f}
  • {ltf}: {ltf_signal}    confidence {ltf_conf:.2f}
  • persistence: {persistence_bars}/{threshold_bars} bars

📋 Регламент: {affected_configs}
   {action_recommendation}
```

Fields:
- `{dim_label}` — `regime` / `trend` / `volatility`
- `{magnitude}` — `MAJOR`
- `{htf}`, `{ltf}` — TF labels (e.g. `4h`, `15m`)
- `{affected_configs}` — list of `cfg_id` from `_REGULATION_ACTIVATION_V0_1_1` whose status would change if the HTF or LTF reading flips
- `{action_recommendation}` — one of: `"Watch for confirmation"` / `"Review {cfg_id} status"` / `"Pause activation pending resolution"`

### 4.4 Cooldown

To prevent oscillating-disagreement spam (the operator's core pain), apply a **30-minute cooldown** per `(dim, htf, ltf)` triple. Cooldown is enforced by the existing `services/telegram/dedup_layer.py` infrastructure — register `MTF_DISAGREEMENT` as a new emitter in `services/telegram/dedup_configs.py`:

```python
MTF_DISAGREEMENT_DEDUP_CONFIG = DedupConfig(
    cooldown_sec=1800,        # 30 min
    value_delta_min=0.0,      # state change is the trigger; no value delta needed
    cluster_enabled=False,
)
```

State-change semantics already implemented in `DedupLayer` give us "only emit when MTF state changes from NONE/MINOR → MAJOR or when descriptor changes" without further work.

### 4.5 Action recommendations from REGULATION

The detector reads `_REGULATION_ACTIVATION_V0_1_1` from `services/dashboard/state_builder.py` (already available). For each MAJOR disagreement, compute which configs change status if either side of the disagreement wins. Map:

- HTF says `MARKUP`, LTF says `MARKDOWN` → CFG-L-RANGE / CFG-L-FAR move from ON to CONDITIONAL if MARKDOWN wins; CFG-S-RANGE-DEFAULT moves from CONDITIONAL to CONDITIONAL (no change).
- HTF says `RANGE`, LTF says `MARKUP` → all approved configs stay ON (RANGE and MARKUP both have ON for L configs); only message says "watch for confirmation".
- Major HTF↔HTF conflict (4h `MARKUP` vs 1d `MARKDOWN`) → action = `"Pause activation pending resolution"` because both choices flip the matrix in opposite directions.

---

## §5 Examples (worked)

### Example 1 — All TFs agree RANGE
| TF | A regime | B trend | C vol | conf |
|---|---|---|---|---|
| 15m | RANGE | flat | normal | 0.82 |
| 1h | RANGE | flat | normal | 0.85 |
| 4h | RANGE | flat | normal | 0.88 |
| 1d | RANGE | flat | low | 0.90 |

**Detector state:** `NONE`. (One C-cell differs but it's `low` vs `normal` — adjacent-step minor only; B and A both agree.)
**Alert:** silent. Dashboard shows agreement state.

### Example 2 — 4h MARKUP, 1h RANGE, 15m RANGE, 1d MARKUP
| TF | A regime | conf |
|---|---|---|
| 15m | RANGE | 0.80 |
| 1h | RANGE | 0.82 |
| 4h | MARKUP | 0.85 |
| 1d | MARKUP | 0.90 |

**Detector state:** `MINOR` (HTFs agree with each other; LTFs lag the trend; no opposite-direction conflict because RANGE is not opposite of MARKUP).
**Alert:** silent on Telegram. Dashboard `mtf_state` block shows: `MINOR — LTFs lag MARKUP HTFs`.

### Example 3 — 4h MARKUP, 1h MARKDOWN (opposite)
| TF | A regime | conf |
|---|---|---|
| 15m | MARKDOWN | 0.75 |
| 1h | MARKDOWN | 0.78 |
| 4h | MARKUP | 0.85 |
| 1d | MARKUP | 0.90 |

**Detector state (after persistence):** `MAJOR` if persists ≥ 12 × 15m = 3 h.
**Alert (PRIMARY):**
```
⚠️ MTF disagreement: regime — MAJOR (4h ↔ 1h)

  • 4h: MARKUP    confidence 0.85
  • 1h: MARKDOWN  confidence 0.78
  • persistence: 12/12 bars

📋 Регламент: CFG-L-RANGE, CFG-L-FAR
   Pause activation pending resolution
```

### Example 4 — 1d MARKUP, 15m brief MARKDOWN spike (5 bars)
| TF | A regime | conf |
|---|---|---|
| 15m | MARKDOWN | 0.71 (5 bars old) |
| 1h | RANGE | 0.80 |
| 4h | MARKUP | 0.85 |
| 1d | MARKUP | 0.90 |

**Detector state:** would be major if persistent, but persistence = 5 < 12 threshold.
**Alert:** silent. Logged as `disagreement_pending` for transparency. Dashboard `mtf_state` block shows: `pending major (5/12)`.

### Example 5 — Persistent 1h ↔ 4h regime conflict, 12+ hours
| TF | A regime | conf |
|---|---|---|
| 15m | RANGE | 0.80 |
| 1h | MARKUP | 0.78 (held 48 bars = 12 h) |
| 4h | RANGE | 0.85 |
| 1d | RANGE | 0.90 |

**Detector state:** `MAJOR` after first 12 bars; **escalation flag** set after 24 bars (= 6 h sustained at 1h TF).

After 12 bars: PRIMARY alert with normal template.
After 24 bars: escalation alert emitted, includes
```
🔁 Persistent MTF disagreement: 1h ↔ 4h, 24 bars sustained.
   This conflict has not resolved in 6 hours of LTF time.
   Operator decision needed: which TF dominates the activation read?
```
Escalation cooldown is independent of the initial-alert cooldown (separate dedup key suffixed `_escalation`).

---

## §6 Integration with decision layer

The MTF detector emits **state + descriptor** as structured output (not text-only). The decision layer (`DECISION_LAYER_v1.md`) consumes this output as one of its inputs.

### Output contract

```json
{
  "mtf_state": "NONE | MINOR | MAJOR | MAJOR_SUPPRESSED",
  "dim": "regime | trend | volatility",
  "htf": "4h" | "1d" | "1h",
  "ltf": "15m" | "1h" | "4h",
  "htf_value": "MARKUP",
  "ltf_value": "MARKDOWN",
  "htf_confidence": 0.85,
  "ltf_confidence": 0.78,
  "persistence_bars_observed": 12,
  "persistence_threshold_bars": 12,
  "transition_flag": false,
  "affected_configs": ["CFG-L-RANGE", "CFG-L-FAR"],
  "recommendation": "Pause activation pending resolution",
  "first_observed_at": "2026-05-05T12:00:00Z",
  "last_updated_at": "2026-05-05T15:00:00Z"
}
```

This block lives at `dashboard_state.json["mtf_state"]` (top-level field, alongside `regulation_action_card`).

### Decision-layer reads

The decision layer's logic in `DECISION_LAYER_v1.md` §2 uses `mtf_state` to:
- Demote any `ON` config in the regulation card to `CONDITIONAL` if `mtf_state.mtf_state == "MAJOR"` AND the affected_configs list includes that config.
- Emit an explanatory note to the dashboard regulation card when MTF disagreement affects at least one config status.
- Pass the structured block to `services/telegram/alert_router.py` for PRIMARY-channel emission per §4 above.

---

## §7 Test plan

### 7.1 Replay-based validation

Replay the 1-year feature parquet (`data/forecast_features/full_features_1y.parquet`, 105 117 5-min bars) through the MTF detector with simulated per-TF classifiers driven by the same `regime_int` stream resampled to each TF.

#### Acceptance metrics

- **Alert frequency target:** ≤ 15 PRIMARY MTF alerts per 24 h on average across the year. Per-day distribution should not skew (no day with > 30 alerts).
- **TRANSITION coverage:** when the H=1 TRANSITION flag is true, no `MAJOR` alerts should fire (only `MAJOR_SUPPRESSED`).
- **MINOR/MAJOR ratio:** approximately 5-15 % of bars in `MINOR` state; ≤ 1 % in `MAJOR` state. (Anchor: TRANSITION rate ~7 %; major disagreement should be a subset of transition periods.)
- **Persistence-filter effect:** without persistence filter, raw alerts ~5-10× more frequent. Persistence filter should suppress at least 80 % of raw spikes.

### 7.2 Operator-fit calibration

After replay produces alert frequency estimates, the operator reviews a sample 7-day window:
- Are the MAJOR alerts informative? (operator subjective judgment)
- Are any silenced MINOR cases something the operator wishes had been alerted?
- Are any MAJOR alerts redundant given existing regulation card view?

Calibration loop: adjust persistence thresholds (per-dim) until subjective acceptance.

### 7.3 Adversarial cases

- Stale per-TF data: detector should output `degraded` state when any TF's last-bar age exceeds 2× the TF's bar interval.
- Confidence-floor violations: if all TFs report confidence < 0.65, output state should be `unverifiable` (not NONE — explicitly distinguishable).
- Per-TF classifier disagreement during TRANSITION: ensure suppression works.

### 7.4 Production wire-up gate

Before the detector is wired to Telegram (PRIMARY emission), it must:
1. Pass replay validation (alert frequency target met).
2. Run in shadow mode for 7 calendar days (logs only, no Telegram emission).
3. Operator review of shadow-mode alert log; sign-off required before live.

---

## §8 Implementation TZ sequence

Each row is a separately-scoped TZ. Implementation order matters because §8.1 is a hard prerequisite for everything else.

| Step | TZ name | Scope | Prereq | Output |
|---:|---|---|---|---|
| 1 | `TZ-MTF-CLASSIFIER-PER-TF` | Adopt and harden the verified per-TF classifier path for independent labels (15m, 1h, 4h, 1d). | OHLCV multi-TF feed (already collected) | `services/market_forward_analysis/phase_classifier.py` + downstream per-TF state output |
| 2 | `TZ-MTF-PRICE-ACTION-SIGNALS` | Compute Signal B (trend) + Signal C (volatility) per TF using EMA / ATR rules from §2. | step 1 not strictly required (this is independent but complementary) | `services/mtf/price_action.py` (new) |
| 3 | `TZ-MTF-DISAGREEMENT-CORE` | Implement detector logic from §3: confidence gating, persistence tracker, TRANSITION exemption, state machine. | steps 1-2 | `services/mtf/disagreement.py` (new) emitting structured state per §6 |
| 4 | `TZ-MTF-STATE-BUILDER-WIRE` | Add `mtf_state` block to `dashboard_state.json`; render block in `docs/dashboard.js`. | step 3 | dashboard panel + state block live |
| 5 | `TZ-MTF-ALERT-WIRE` | Register `MTF_DISAGREEMENT` emitter in `dedup_configs.py`; wire alert template to `services/telegram/alert_router.py` PRIMARY channel. | step 3 + step 4 | Telegram PRIMARY emission live (after shadow-mode gate per §7) |
| 6 | `TZ-MTF-OPERATOR-CALIBRATION` | After 7-day shadow mode, operator review + threshold adjustment per §7.2. | step 5 | operator-signed-off thresholds |

Steps 1-3 are the design's structural foundation. Steps 4-6 are the operational rollout.

---

## §9 Open questions

1. **Per-TF independent classification requires adoption of the verified classifier source.** `core/orchestrator/regime_classifier.py` consumes multi-TF features but emits a single label. `TZ-MTF-FEASIBILITY-CHECK` (2026-05-05) verified that the MTF-aligned per-TF path is [`services/market_forward_analysis/phase_classifier.py`](../../services/market_forward_analysis/phase_classifier.py), not `regime_switcher.py`. **Step 1 of §8 remains a hard prerequisite** because the per-TF output still needs hardening/wiring for disagreement use.

2. **Two coexisting regime taxonomies.** `PhaseClassifier` provides the regulation-aligned `MARKUP/MARKDOWN/RANGE` surface used here. `core/orchestrator/regime_classifier.py` uses `RANGE/TREND_UP/TREND_DOWN/COMPRESSION/CASCADE_*`. The MTF design adopts the former. Operator should confirm this remains the right choice before step 1.

3. **Persistence thresholds may need empirical adjustment.** The 12-bar threshold is anchored in median trending episode (3 h) but the operator's actual tolerance for "this disagreement is meaningful" may differ. Replay results in §7.1 will inform; final values are operator-signed-off.

4. **B-major (1d ↔ 15m direction conflict) might be too aggressive.** A common pattern is a 1d uptrend with a 15m pullback; treating the 15m `down` as opposite to 1d `up` could produce false positives. Mitigation in design: B-major requires 6-bar persistence. Empirical question: is 6 bars enough, or should it be 12?

5. **Per-TF data freshness requirements.** What's the maximum acceptable lag for each TF's last bar before the detector outputs `degraded`? Proposed: 2× bar interval (e.g. 2h for the 1h TF, 8h for 4h, 2d for 1d). Operator confirmation needed.

6. **Cooldown granularity.** Should MTF_DISAGREEMENT cooldown be per-`(dim, htf, ltf)` triple (proposed in §4.4) or coarser (per-pair, regardless of dim)? The finer split allows separate alerts when, e.g., regime conflict resolves but trend conflict starts; coarser would consolidate. Choice depends on operator preference.

7. **Audit-log retention.** MINOR disagreements log every bar; even at 1-bar cadence on 5-min the LTF this is ~288 entries/day. Storage/retention policy needed (proposed: 30 days hot, archive monthly).

8. **Interaction with regulation_action_card demotion.** When MTF MAJOR demotes a config from `ON` to `CONDITIONAL` (§6 hook), should the dashboard render that demotion *as if* it were the regulation's own state, or with explicit "demoted by MTF disagreement" annotation? Latter is more honest; former is cleaner UI. Operator preference.

9. **Confidence threshold (0.65) for cell eligibility may need revisiting.** Source verified in `TZ-MTF-FEASIBILITY-CHECK` (2026-05-05); if per-TF classifier confidence calibration differs in practice, this floor may need per-TF adjustment. Empirical.

10. **Signal C (volatility regime) lacks operator-validated thresholds.** ATR percentile cuts at 25/75 are a defensible default; operator may want different (e.g. 20/80, or distribution-aware quantiles per TF).

---

## CP report

- **Output path:** [`docs/DESIGN/MTF_DISAGREEMENT_v1.md`](MTF_DISAGREEMENT_v1.md)
- **Sections complete:** 9/9
- **Open questions:** 10
- **Implementation TZ sequence:** 6 staged TZs in §8
- **Compute time:** ~1 minute (synthesis-only; no driver runs)
- **Anti-drift compliance:**
  - ✅ No code changes (pure design).
  - ✅ No new ML models.
  - ✅ Reuses existing regime classifier; per-TF extension explicitly flagged as prereq in §9 #1.
  - ✅ Numbers grounded in `HYSTERESIS_CALIBRATION_v1` (H=1, TRANSITION=7.35 %), `REGIME_PERIODS_2025_2026` (median episode 3 h), and the confidence-floor note verified in `TZ-MTF-FEASIBILITY-CHECK` (2026-05-05).
  - ✅ Adopts existing taxonomy (MARKUP/MARKDOWN/RANGE) — does not invent new states.
  - ⚠ Per-TF classification is a real prerequisite (open question #1); design does not paper over it.
