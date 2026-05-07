# BACKLOG_TRIGGERS

Items deferred с explicit trigger criteria для revisit. Not active TZ — 
activated when trigger condition met. New items добавляются только с 
observable trigger criteria.

---

## TZ-PERSISTENCE-ADAPTIVE-DESIGN

**Trigger:** Operator reports regime detection delays >15% during high-vol periods (ATR% >2× baseline).

**Reason:** Constant 12-bars hysteresis может быть unsuitable в high vol periods. Adaptive persistence based на ATR% may improve regime change detection latency.

**Effort estimate:** 1-2 days design + 3-5 days implementation.

**Priority when triggered:** medium.

**Anchor:** ChatGPT review identified concern, MAIN acknowledged as known limitation.

---

## TZ-FORECAST-REBUILD-AS-REDUNDANCY

**Trigger:** 3+ months live experience с Decision Layer accumulated, AND operator desires second independent signal source for robustness.

**Reason:** Slight-skill forecast (~Brier 0.245) as redundancy может add value beyond stand-alone forecast utility. Per FORECAST_MODEL_REPLACEMENT_RESEARCH cross-validated finding: 80%+ probability of slight skill achievable, even if Brier <0.22 unlikely.

**Effort estimate:** 4-12 weeks (per research §3 implementation paths).

**Priority when triggered:** medium.

**Anchor:** Cross-validated research v1 (Claude + Codex independent investigations).

---

## TZ-CROSS-ASSET-VALIDATION

**Trigger:** Operator wants to extend bot operations to ETH or other assets.

**Reason:** REGULATION_v0_1_1 validated only on BTC. Other assets may have different regime distributions, indicator behavior, instop direction effects.

**Effort estimate:** 2-4 weeks (data acquisition + sim runs across multiple Pack types).

**Priority when triggered:** depends on operator timeline.

**Anchor:** REGULATION_v0_1_1 §7 limitation 7.

---

## TZ-BEAR-MARKET-DATA-ACQUISITION

**Trigger:** Macroeconomic shift indicates bear regime likely OR operator wants robustness validation before scaling capital meaningfully.

**Reason:** REGULATION validated only on bullish year (2025-2026, RANGE 72%). Bear market regime distribution radically different, может invalidate current activation matrix.

**Effort estimate:** 1-3 weeks (historical data acquisition) + 2-4 weeks (sim runs + analysis + regulation update).

**Priority when triggered:** high if operator scaling capital.

**Anchor:** REGULATION_v0_1_1 §7 limitation 1, §8 open question 1.

---

## TZ-MTF-INTEGRATION

**Trigger:** TZ-MTF-FEASIBILITY-CHECK returns viable option (A/B/C, не D) AND TZ-MTF-AB-SHADOW-TESTING completes 2-3 weeks.

**Reason:** MTF integration depends on feasibility outcome + winner from A/B shadow comparison. Implementation effort varies per feasibility option.

**Effort estimate:** 2-4 weeks per feasibility option.

**Priority when triggered:** high (закрывает T-* rules в Decision Layer).

**Anchor:** docs/DESIGN/MTF_DISAGREEMENT_v1.md §8 implementation sequence.

---

## TZ-VALIDATION-FRAMEWORK

**Trigger:** TZ-DECISION-LAYER-CORE-WIRE deployed AND running 7+ days в production.

**Reason:** Need structured framework для operator review of Decision Layer behavior. Without framework, operator review будет ad-hoc — "что-то не так" без specific metrics.

**Effort estimate:** 2-3 days.

**Priority when triggered:** high.

**Anchor:** Coordinator self-review identified validation framework gap.

---

## TZ-DECISION-LAYER-CALIBRATION

**Trigger:** TZ-VALIDATION-FRAMEWORK completed AND operator identifies tuning needs based on real-world data.

**Reason:** Default thresholds (0.65/0.80 confidence, 12 bars hysteresis, etc.) могут не быть optimal в practice. Real data может show miscalibration.

**Effort estimate:** 1 week.

**Priority when triggered:** medium.

**Anchor:** Decision Layer design §9 open question — calibration cadence.

---

## TZ-PROJECT-MAP-CLEANUP

**Trigger:** Worker references docs/PROJECT_MAP.md и file отсутствует.

**Reason:** Multiple TZ briefs reference PROJECT_MAP.md as input, но file missing on disk. Either restore (если deprecated removal was unintentional) или remove all references.

**Effort estimate:** 30 min (decision + cleanup).

**Priority when triggered:** low.

**Anchor:** TZ-MTF-FEASIBILITY-CHECK CP flagged this missing file.

---

## TZ-INVENTORY-EMITTERS-DEPRECATION-VERIFY

**Trigger:** Operator decides to clean up Telegram emitters list.

**Reason:** TELEGRAM_EMITTERS_INVENTORY identified 4 suspect orphans (#14 state_snapshot, #15 watchdog, #17 integration_decision, #18 btc_elite_plus_fast) requiring trace verification before deprecation.

**Effort estimate:** ~20 min total (5 min per emitter trace).

**Priority when triggered:** low.

**Anchor:** TELEGRAM_EMITTERS_INVENTORY §6 trace-verification next steps.

---

## TZ-METRICS-RENDER-FIX

**Trigger:** Operator decides to clean up dashboard/Telegram rendering issues.

**Reason:** Broken ASCII rendering в metrics output identified в TELEGRAM_EMITTERS_INVENTORY.

**Effort estimate:** depends on which renderer affected; likely 1-3 hours after screenshot localization.

**Priority when triggered:** low.

**Anchor:** TELEGRAM_EMITTERS_INVENTORY §5 fix flag.

---

## TZ-SYNTH-PROMOTE

**Trigger:** Operator wants enhanced synthesizer alerts (orchestrator-style alerts с richer context).

**Reason:** TELEGRAM_EMITTERS_INVENTORY §5 long-term direction recommended promoting synthesizer alerts above raw triggers. Partially implemented (PRIMARY/VERBOSE channels). Full promotion = next phase.

**Effort estimate:** 1-2 weeks.

**Priority when triggered:** medium.

**Anchor:** TELEGRAM_EMITTERS_INVENTORY §5.

---

## Rules for backlog management

1. Items НЕ активируются автоматически — operator + MAIN coordinator решают когда trigger met.

2. Trigger criteria должны быть OBSERVABLE (не subjective). "Operator wants X" allowed, но needs explicit operator decision не assumed change.

3. Effort estimates обновляются когда runtime context changes (e.g. codebase grows, dependencies change).

4. Items могут быть удалены если становятся obsolete (technology change, requirement removed).

5. New items добавляются только с explicit trigger criteria — нельзя добавить vague "будет хорошо иметь" item.

6. Items reference anchor — где идея originated (research doc, design doc, ChatGPT review, operator discussion). Anchor preserves context.
