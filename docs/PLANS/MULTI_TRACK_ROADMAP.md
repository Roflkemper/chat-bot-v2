# MULTI-TRACK ROADMAP — bot7

**Created:** 2026-05-04
**Purpose:** Multi-track roadmap covering all directions of work in bot7. Replaces single-track week plans.
**Update cadence:** End of each week, or when a track's status changes materially.

---

## Tracks (P1–P6)

### P1 — Actionability layer (HIGHEST PRIORITY, week 2)
**Pain:** Operator "перебираю/недобираю" не закрыта. Forecast выдаёт probability, но не sizing decision.
**Goal:** Forecast probability → sizing multiplier → operator action.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-SETUP-DETECTION-WIRE | Connect setup_detector to RegimeForecastSwitcher | OPEN |
| TZ-SIZING-MULTIPLIER-ENGINE | 0–2× multiplier with reasoning (regime + forecast + setup confluence) | OPEN |
| TZ-DIRECTION-AWARE-WORKFLOW | Promote in MARKUP, normal flow elsewhere | OPEN |

**Success gate:** Operator gets "size 1.5× because MARKDOWN + 1h GREEN forecast + supply level proximity" instead of bare probability.

---

### P2 — Regime-aware bot management (week 2-3)
**Pain:** GinArea LONG broken (DP-001 confirmed today: K_LONG CV 43%). DCA/hedge bots не существуют. Bot state не inventoryован.
**Goal:** Map deployed bots, identify gaps, fix LONG sizing through target-conditional K.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-BOT-STATE-INVENTORY | What's deployed (GinArea), what's manual, what's paper | OPEN |
| TZ-K-TARGET-CONDITIONAL | Regression K = f(target_pct, side) on direct_k results | OPEN |
| TZ-RESEARCH-DIRS-AUDIT | countertrend/defensive/exhaustion: applicable or decommission | OPEN |

**Success gate:** Conservative K_LONG estimate per target band; explicit map of all bot deployments.

---

### P3 — MARKUP-1h numeric (week 3+)
**Pain:** MARKUP-1h CV mean 0.273 — refuses to go numeric on the only regime where price moves up reliably.
**Goal:** Find a signal architecture that brings MARKUP-1h into YELLOW band (≤0.265).

| TZ | Description | Status |
|----|-------------|--------|
| TZ-MARKUP-1H-IMPROVEMENT | Try regime-specific signal logic OR lightGBM | OPEN, lightGBM gated on operator approval |

**Success gate:** MARKUP-1h Brier ≤0.265 across 5 CV windows OR formal acceptance that 1h MARKUP ships qualitative permanently.

---

### P4 — Dashboard wire-in (week 2)
**Pain:** Dashboard alive but doesn't show anything from today's pipeline.
**Goal:** Operator sees current regime, forecast, virtual trader stats in browser.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-DASHBOARD-PHASE-1 | Wire forecast/regime/virtual_trader → state_builder.py | OPEN |
| TZ-DASHBOARD-PHASE-2 | Roadmap + drift surfaces (after MULTI_TRACK_ROADMAP exists) | DEFERRED |
| TZ-DASHBOARD-PHASE-3 | Live Brier aggregation (after data accumulates) | DEFERRED |

**Success gate:** Operator opens dashboard, sees current regime + 1h/4h/1d forecast + virtual trader 7d stats without leaving browser.

---

### P5 — Self-monitoring & long-running validation (continuous)
**Pain:** Forecast pipeline accuracy promises CV-validated, but no live evidence yet. Paper journal Day 4/14 — needs continuation.
**Goal:** Accumulate live evidence; alert on degradation.

| TZ | Description | Status |
|----|-------------|--------|
| Paper journal continuation | Day 4 → Day 14 | IN_PROGRESS |
| TZ-WEEKLY-COMPARISON-REPORT | Week 1 paper vs operator actions | PENDING (≥7 days) |
| TZ-VIRTUAL-TRADER-VALIDATE | Time-gated review after 2-4 weeks accumulation | DEFERRED |
| live_monitor.py rolling Brier alert | Already deployed, fires when live > 0.28 | ACTIVE |

**Success gate:** First weekly report (week 2 EOD) — paper journal entries vs operator decisions, agreement % computed.

---

### P6 — Infrastructure debt & remaining engine work (low priority, parallel)
**Pain:** 91 collection errors (DEBT-04). Tracker PID race. INSTOP semantics confirmation pending.
**Goal:** Phase 0 closure before Phase 2 expansion.

| TZ | Description | Status |
|----|-------------|--------|
| DEBT-04-A through E | Collection errors split | OPEN, P1-P3 |
| TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | LONG instop direction confirmation | BLOCKED on operator decision |
| Windows PID lock race | tracker.py at next restart | OPEN, P3 |
| H10 overnight backtest | scripts/run_backtest_h10_overnight.bat | PENDING operator |

**Success gate:** All P0/P1 debt closed. Phase 0 exits in_progress.

---

## Cross-track dependencies

```
P1 (actionability)          ─┐
                              ├─→ Phase 2 entry (operator augmentation production)
P2 (bot management)         ─┤
                              │
P4 (dashboard) ─────────────→ │
                              │
P5 (validation evidence) ───→ │ (gates Phase 2 promotion)
                              │
P3 (MARKUP-1h numeric) ─────→ Increases coverage of P1 sizing engine
P6 (infra debt) ────────────→ Phase 0 closure (parallel, not blocker for above)
```

---

## Track-status snapshot (week 2 start)

| Track | Status | This week's TZs | Next milestone |
|-------|--------|----------------|----------------|
| P1 | OPEN | 3 TZs | First end-to-end action recommendation |
| P2 | OPEN | 3 TZs | K-target-conditional regression + bot inventory |
| P3 | DEFERRED | 1 TZ (gated) | After P1 demand for MARKUP-1h numeric is real |
| P4 | OPEN | TZ-DASHBOARD-PHASE-1 | Operator dashboard shows live forecast |
| P5 | RUNNING | continuation | Day 14 paper journal review |
| P6 | OPEN | DEBT-04 split + tracker fix | Phase 0 close |

---

## Roadmap-evolution rules

1. Every track must have at least one **explicit operator pain** it closes. Track without operator pain → research, not production.
2. Cross-track dependencies must be stated explicitly. Don't add a track that silently blocks another.
3. Status update happens **every Friday EOD** or whenever a track's gate is reached.
4. New TZ in a track must declare which P1-P6 it serves.
