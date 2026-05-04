# MULTI-TRACK ROADMAP — bot7

**Created:** 2026-05-04
**Purpose:** Multi-track roadmap covering all directions of work in bot7. Replaces single-track week plans.
**Update cadence:** End of each week, or when a track's status changes materially.

---

## Tracks (P1–P6)

### P1 — Actionability layer ✅ CLOSED (week 2)
**Pain:** Operator "перебираю/недобираю" не закрыта. Forecast выдаёт probability, но не sizing decision.
**Goal:** Forecast probability → sizing multiplier → operator action.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-SETUP-DETECTION-WIRE | Connect setup_detector to RegimeForecastSwitcher | ✅ CLOSED 2026-05-05 (services/market_forward_analysis/setup_bridge.py) |
| TZ-SIZING-MULTIPLIER-ENGINE | 0–2× multiplier with reasoning (regime + forecast + setup confluence) | ✅ CLOSED 2026-05-05 (services/sizing/* v0.1, 31 tests) |
| TZ-DIRECTION-AWARE-WORKFLOW | Promote in MARKUP, normal flow elsewhere | ✅ CLOSED 2026-05-05 (apply_direction_workflow post-clamp layer, 12 tests) |

**Success gate:** ✅ structurally met — sizing engine emits multiplier with Russian reasoning. Promotion to *production deployment* still gated on paper journal evidence (P5).

---

### P2 — Regime-aware bot management (week 2-3, partially closed)
**Pain:** GinArea LONG broken (DP-001 confirmed today: K_LONG CV 43%). DCA/hedge bots не существуют. Bot state не inventoryован.
**Goal:** Map deployed bots, identify gaps, fix LONG sizing through target-conditional K.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-BOT-STATE-INVENTORY | What's deployed (GinArea), what's manual, what's paper | ✅ CLOSED 2026-05-05 (docs/STATE/BOT_INVENTORY.md, 22 bots, P8 role gaps) |
| TZ-K-TARGET-CONDITIONAL | Regression K = f(target_pct, side) on direct_k results | DEFERRED (superseded by TZ-K-RECALIBRATE-PRODUCTION-CONFIGS in week 3) |
| TZ-RESEARCH-DIRS-AUDIT | countertrend/defensive/exhaustion: applicable or decommission | DEFERRED (revisit after P8 implementation) |

**Success gate:** ✅ inventory done; target-conditional K supplanted by full production-config recalibration in week 3.

---

### P3 — MARKUP-1h numeric (week 3+)
**Pain:** MARKUP-1h CV mean 0.273 — refuses to go numeric on the only regime where price moves up reliably.
**Goal:** Find a signal architecture that brings MARKUP-1h into YELLOW band (≤0.265).

| TZ | Description | Status |
|----|-------------|--------|
| TZ-MARKUP-1H-IMPROVEMENT | Try regime-specific signal logic OR lightGBM | OPEN, lightGBM gated on operator approval |

**Success gate:** MARKUP-1h Brier ≤0.265 across 5 CV windows OR formal acceptance that 1h MARKUP ships qualitative permanently.

---

### P4 — Dashboard wire-in ✅ CLOSED (PHASE-1 + PHASE-1.5)
**Pain:** Dashboard alive but doesn't show anything from today's pipeline.
**Goal:** Operator sees current regime, forecast, virtual trader stats in browser.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-DASHBOARD-PHASE-1 | Wire forecast/regime/virtual_trader → state_builder.py | ✅ CLOSED 2026-05-05 (16 tests) |
| TZ-DASHBOARD-LIVE-FRESHNESS (PHASE-1.5) | 60s loop + 3-tier ok/yellow/red freshness layer + corruption regression | ✅ CLOSED 2026-05-05 (8 tests) |
| TZ-DASHBOARD-POSITION-DEDUP | Bot_id `.0` legacy suffix dedup; shorts.total_btc fixed | ✅ CLOSED 2026-05-05 (13 tests) |
| TZ-DASHBOARD-PHASE-2 | Roadmap + drift surfaces (after MULTI_TRACK_ROADMAP exists) | DEFERRED |
| TZ-DASHBOARD-PHASE-3 | Live Brier aggregation (after data accumulates) | DEFERRED |

**Success gate:** ✅ operator opens dashboard, sees regime + 1h/4h/1d forecast + virtual trader stats + freshness banner; positions match BitMEX UI exactly post-dedup.

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

### P6 — Infrastructure debt & remaining engine work (partial)
**Pain:** Collection errors. Tracker PID race. INSTOP semantics confirmation pending. Sprint generator broken after roadmap migration. Bot aliases not stable.
**Goal:** Phase 0 closure before Phase 2 expansion.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-MORNING-BRIEF-MULTITRACK-ADAPT | --roadmap mode for sprint generator | ✅ CLOSED 2026-05-05 (14 tests) |
| TZ-BOT-ALIAS-HYGIENE | Stable bot UIDs + migration script | ✅ CLOSED 2026-05-05 (20 tests) |
| TZ-FIX-COLLECTION-ERRORS | 4 broken test files + brittle datetime test | OPEN, week 3 priority 7 |
| DEBT-04-A through E | Collection errors split | OPEN, P1-P3 |
| TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | LONG instop direction confirmation | BLOCKED on operator decision |
| Windows PID lock race | tracker.py at next restart | OPEN, P3 |
| H10 overnight backtest | scripts/run_backtest_h10_overnight.bat | PENDING operator |

**Success gate:** All P0/P1 debt closed. Phase 0 exits in_progress.

---

### P7 — Operator output channel quality (partial)
**Pain:** Telegram channel 20+ raw alerts/day; duplicates of unchanged conditions; broken ASCII metrics block.
**Goal:** Two-channel collapse — primary synthesizer + verbose for raw alerts; dedup wrappers for noisy emitters.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-TELEGRAM-INVENTORY | Map all 18 emitters with dedup gaps | ✅ CLOSED 2026-05-05 |
| TZ-METRICS-RENDER-FIX | Mobile-safe visuals + canonical metrics_block helper | ✅ CLOSED 2026-05-05 (14 tests) |
| TZ-ALERT-DEDUP-LAYER | services/telegram/dedup_layer.py library | ✅ CLOSED 2026-05-05 (17 tests) |
| TZ-DEDUP-WIRE-PRODUCTION (POSITION_CHANGE) | Wired in DecisionLogAlertWorker | ✅ CLOSED 2026-05-05 (12 tests) |
| TZ-DEDUP-WIRE-BOUNDARY_BREACH | Wired with cluster collapse | ✅ CLOSED 2026-05-05 (10 tests) |
| TZ-DEDUP-WIRE-PNL_EVENT | Wired after threshold tune | OPEN, week 3 priority 4 |
| TZ-DEDUP-WIRE-PNL_EXTREME | Wired after PNL_EVENT validated | OPEN, week 3 priority 5 |

**Success gate:** ✅ wrapper library built, 2 emitters wired & ready for 24h monitoring. PNL types pending threshold tune.

---

### P8 — Multi-bot ensemble coordinator (design done, impl pending)
**Pain:** Operator manually pauses/resumes bots at regime changes; no automation; SHORT cumulative exposure runs unattended; no bot config catalog.
**Goal:** Coordinator state machine consumes regime + indicator events, automates bot lifecycle within guards.

| TZ | Description | Status |
|----|-------------|--------|
| TZ-RGE-RANGE-DETECTION | Method recommendation for range boundaries | ✅ CLOSED 2026-05-05 (Method D Hybrid) |
| TZ-K-DUAL-MODE-COORDINATOR-DESIGN | docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md | ✅ CLOSED 2026-05-05 (12 sections) |
| TZ-CROSS-CHECK-FINDING-A | Period-correction validation of indicator-gate finding | ✅ CLOSED 2026-05-05 (Outcome A) |
| TZ-TRANSITION-MODE-COMPARE-BACKTEST | Operator GinArea backtest closing P8 §9 Q2 | OPEN, week 3 priority 1 |
| TZ-PURE-INDICATOR-AB-ISOLATION | BT-014..017 without indicator on 86-day window — closes Finding A confounds | OPEN, week 3 priority 2 |
| P8 implementation skeleton | services/ensemble/ package + state machine + tests | OPEN, contingent on Q2 backtest decision |

**Success gate:** Q2 backtest results inform whether to implement P8 v0.1 as designed or refactor before implementation.

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
