# SESSION 2026-05-04 — FULL

## §1 Session overview

- **Date:** 2026-05-04
- **Window covered by this consolidation:** full project day from early model/calibration carry-over into end-of-day P8 and monitoring work
- **Closed checkpoints:** `CP18 -> CP30` = **13 CPs** closed in a single day
- **Test-count delta:** **199 -> 222**
- **Worker split note:** Git history for 2026-05-04 is recorded under one local author identity (`чат-бот-v2`), so a strict `Claude commits vs Codex commits` split is **not reconstructible from repo metadata alone**. This document preserves the day chronology and artifact trail; worker-attribution finer than that remained operator-side.

**Pivot moments in day flow**

1. **Morning:** P1/P4 operational work dominated — dashboard/state wiring, sizing v0.1, direction-aware workflow, brief tooling adaptation.
2. **Afternoon (~17:00-19:00):** audit/research pivot — discovery that calibration sim does not model live `instop` / `indicator` mechanics, which downgraded trust in several baseline numbers.
3. **Evening (~20:30-23:00):** P8 strategic shift — regime periods + backtest registry + regime overlay moved ensemble/coordinator design from optional idea to central architecture.

---

## §2 Closed TZs in chronological order

The table below consolidates the main TZs that closed during the day and directly shaped the project state referenced by end-of-day P8 work.

| Order | TZ ID | Track | Status | Summary | Files changed / created | Commit | Estimate vs actual |
|---|---|---|---|---|---|---|---|
| 1 | `TZ-DASHBOARD-PHASE-1` | P4 | GREEN | Wired forecast, regime and virtual-trader state into dashboard so operator state became visible in one place. This opened the path for later freshness and content validation work. | Dashboard/state builder files; dashboard state outputs | `d801d2c` | Est not preserved in artifact; actual before `13:53` |
| 2 | `TZ-MORNING-BRIEF-MULTITRACK-ADAPT` | P6 | GREEN | Added roadmap-mode support to morning-brief generation and restored multi-track planning flow after roadmap migration. This became part of the day’s tooling hygiene theme. | `scripts/main_morning_brief.py`, tests, related brief artifacts | `3022ca7` | Queue/spec had it as a low-priority chore; actual closed by `17:53` |
| 3 | `TZ-SIZING-MULTIPLIER` | P1 | GREEN | Implemented rule-based sizing v0.1 and locked the operator-facing base multipliers / gating logic. This closed the sizing decision block for the day. | `docs/DESIGN/SIZING_MULTIPLIER_v0_1.md`, implementation/tests | `d15b901` | Brief-level estimate not preserved; actual landed by `17:20` |
| 4 | `TZ-DIRECTION-AWARE` | P1 | GREEN | Added direction-aware workflow behavior so trend regime could alter action flow rather than only annotation. This completed the paired P1 actionability work. | Workflow / orchestration logic, tests | `581bba9` | Brief-level estimate not preserved; actual landed by `17:30` |
| 5 | `TZ-TELEGRAM-INVENTORY` | P7 | GREEN | Produced the Telegram emitter inventory, identified dedup gaps and created the basis for later dedup-layer wiring. This is the first explicit P7 architecture anchor of the day. | `docs/STATE/TELEGRAM_EMITTERS_INVENTORY.md` | `c7bd9c4` | Artifact-only estimate not preserved; actual landed by `17:39` |
| 6 | `TZ-BOT-STATE-INVENTORY` | P2 | GREEN | Built the GinArea fleet map and P8 role-gap view, making deployed/manual/paper bot roles explicit. This fed directly into later coordinator design. | `docs/STATE/BOT_INVENTORY.md` and related inventory notes | `a1ba4a6` | Artifact-only estimate not preserved; actual landed by `17:40` |
| 7 | `TZ-RGE-RANGE-DETECTION` | P8 | GREEN | Produced the range-detection v0.1 design and selected the hybrid method direction for P8. This prepared the architectural frame before the evening findings wave. | `docs/DESIGN/P8_RANGE_DETECTION_v0_1.md` | `e3399cc` | Artifact-only estimate not preserved; actual landed by `17:43` |
| 8 | `TZ-BOT-ALIAS-HYGIENE` | P6 | GREEN | Stabilized bot UID / alias resolution and migrated the naming surface. This reduced ambiguity for dashboard, dedup and future coordinator actions. | Bot registry / resolver / migration files | `adb4962` | Artifact-only estimate not preserved; actual landed by `17:56` |
| 9 | `TZ-METRICS-RENDER-FIX` | P7 | GREEN | Fixed mobile-safe metrics rendering and canonicalized the metrics block. This improved operator-facing alert/monitoring readability ahead of dedup rollout. | Telegram/dashboard rendering files | `1f7853a` | Artifact-only estimate not preserved; actual landed by `18:01` |
| 10 | `TZ-ALERT-DEDUP-LAYER` | P7 | GREEN | Introduced the reusable dedup wrapper (`state-change + cooldown + cluster-collapse`) that later production wire-ups reuse. This was the core mechanism behind the rest of the P7 line. | `services/telegram/dedup_layer.py` and tests | `eaf03b4` | Artifact-only estimate not preserved; actual landed by `18:03` |
| 11 | `TZ-RGE-RESEARCH-EXPANSION` | P8 | GREEN | Expanded the P8 research variant matrix and documented the 5x3 expansion results. This extended the coordinator design search space before the regime-overlay pivot. | `docs/RESEARCH/P8_RGE_EXPANSION_RESULTS_v0_1.md`, raw JSON | `ba97f5f` | Artifact-only estimate not preserved; actual landed by `18:09` |
| 12 | `TZ-LONG-TP-SWEEP` | P8 | GREEN | Ran and documented the 5-TP x 4-window stress-test for LONG side research. This later became contextual support around LONG-side behavior and tradeoffs. | `docs/RESEARCH/LONG_TP_SWEEP_v1.md`, raw JSON | `f22ea60` | Artifact-only estimate not preserved; actual landed by `18:46` |
| 13 | `TZ-BACKTEST-AUDIT` | P8 | GREEN | Built the trust map for baseline calibration numbers and traced which metrics came from live-like vs synthetic/default assumptions. This is the key afternoon pivot away from blind trust in sim-derived K factors. | `docs/RESEARCH/BACKTEST_AUDIT.md` | `b3f019a` | Brief estimate `30-45m`; actual landed by `18:53` |
| 14 | `TZ-BACKTEST-DATA-CONSOLIDATION` | P8 | GREEN | Consolidated the operator’s 17 GinArea backtests into one registry with groups, flags and gaps. This became CP20’s structural source-of-truth. | `docs/RESEARCH/GINAREA_BACKTESTS_REGISTRY_v1.md` | `2502095` | Same grouped commit as below; actual by `22:10` |
| 15 | `TZ-REGIME-PERIODS-2025-2026` | P8 | GREEN | Measured regime time-distribution, transitions and episode structure on the 2025-05-01 -> 2026-05-01 year. This created CP21 and supplied the 72% RANGE finding plus the no-direct-transition finding. | `docs/RESEARCH/REGIME_PERIODS_2025_2026.md`, `_regime_periods_raw.json` | `2502095` | Same grouped commit as above; actual by `22:10` |
| 16 | `TZ-DEDUP-DRY-RUN` | P7 | GREEN | Produced the dry-run suppression baseline that later justified emitter-by-emitter wire-up sequencing. This set the tuned-vs-healthy-zone framework for P7 rollout. | `docs/RESEARCH/DEDUP_DRY_RUN_2026-05-04.md` | `2502095` | Same grouped commit as above; actual by `22:10` |
| 17 | `TZ-H` freshness finalize | P4 | GREEN | Finalized dashboard freshness handling so state visibility had a clearer validity signal. This closed the P4 freshness branch for the day. | Dashboard freshness-related files/docs | `a1fa27b` | Same grouped commit with TZ-G; actual by `22:23` |
| 18 | `TZ-G` POSITION_CHANGE dedup wire-up | P7 | GREEN | Production-wired the first dedup emitter and created the first 24h monitoring loop for real operator validation. This became the template for later `BOUNDARY_BREACH` work. | `services/telegram_runtime.py`, tests, monitoring doc | `a1fa27b` | Brief estimate not preserved; actual by `22:23` |
| 19 | `TZ-K` dual-mode coordinator design | P8 | GREEN | Produced the first full central-architecture design for P8 coordinator logic. This is the evening culmination of the ensemble shift. | `docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md` | `44a7dc9` | Brief estimate not preserved; actual by `22:36` |
| 20 | `TZ-Y` dashboard snapshot dedup fix | P4 | PARTIAL / YELLOW retroactive | Commit fixed legacy `.0` bot-id suffix handling in dashboard state building, but the operator later still reported a visible SHORT duplication issue in snapshot JSON. Treat this as partial recovery, not final closure. | Dashboard state-builder path | `5e9864f` | Same-day patch landed by `23:11`; operator follow-up remained open |

**Chronology note**

- Some commits before the morning P1/P4 line belong to carry-over forecast/model work (`TZ-TIER2-MARKUP`, `TZ-REGIME-MODEL-*`, `TZ-OOS-VALIDATION`, `TZ-REGIME-AUTO-SWITCH`, `TZ-FINAL`) and formed the starting state of 2026-05-04.
- The session narrative requested here focuses on the day’s operative P1 / P4 / P7 / P2 / P8 / P6 flow and the checkpoints that closed inside it.

---

## §3 Major findings of the day

Each finding below is already present in today’s artifacts. This section only consolidates them.

### Finding 1 — Sim does not model `instop` / `indicator`

- **When surfaced:** afternoon, around the audit pivot (`~17:00-19:00`)
- **Artifact anchor:** [docs/RESEARCH/BACKTEST_AUDIT.md](../RESEARCH/BACKTEST_AUDIT.md)
- **Meaning:** several core K/grid numbers were traced back to research-config sim runs that matched grid-step but did **not** reproduce live `instop` and `indicator` mechanics, and also differed in position size / order-count.
- **Impact on day narrative:** this is the audit revelation that shifted the project from “fix sim K-factors” toward “ground decisions in GinArea live ground truth.”

### Finding 2 — Indicator gate flips PnL sign

- **When surfaced:** evening, around regime-overlay conclusions (`~21:00`)
- **Artifact anchor:** [docs/RESEARCH/REGIME_OVERLAY_v1.md](../RESEARCH/REGIME_OVERLAY_v1.md)
- **Status:** **pending TZ-X cross-check verification** was the same-day caveat; later the separate cross-check artifact confirmed apples-to-apples sign-flip persistence in [docs/RESEARCH/REGIME_OVERLAY_v1_CROSSCHECK.md](../RESEARCH/REGIME_OVERLAY_v1_CROSSCHECK.md)
- **Consolidated statement:** on the first regime-overlay pass, LONG annual allocations were negative while LONG 02may allocations were positive across all three regimes.

### Finding 3 — SHORT in a bullish year does not recover even in MARKDOWN

- **When surfaced:** evening, around regime-overlay conclusions (`~21:00`)
- **Artifact anchor:** [docs/RESEARCH/REGIME_OVERLAY_v1.md](../RESEARCH/REGIME_OVERLAY_v1.md)
- **Status flag:** **requires non-bull-year validation**
- **Consolidated statement:** all SHORT backtests in the operator’s set remained negative across MARKUP, MARKDOWN and RANGE allocations, including the MARKDOWN bucket.

### Finding 4 — RANGE dominates 72% of the year

- **When surfaced:** evening, around regime-periods conclusions (`~20:30`)
- **Artifact anchor:** [docs/RESEARCH/REGIME_PERIODS_2025_2026.md](../RESEARCH/REGIME_PERIODS_2025_2026.md)
- **Consolidated statement:** on the 2025-05-01 -> 2026-05-01 year, `RANGE` occupied 72% of time, making range behavior the primary structural mode rather than a side case.

### Finding 5 — `snapshot.json` duplicates SHORT positions by roughly 1.6x

- **When surfaced:** operator report late in the day (`~22:55`)
- **Artifact anchors:** dashboard/snapshot line of work around `TZ-H` / `TZ-Y`; operator report remained the authoritative signal
- **Status flag:** **pending TZ-Y fix / follow-up**
- **Consolidated statement:** operator screenshot vs JSON indicated that the dashboard content layer still over-reported SHORT exposure despite same-day bot-id dedup work.

### Finding 6 — Zero direct `MARKUP <-> MARKDOWN` transitions

- **When surfaced:** evening, around regime-periods conclusions (`~20:30`)
- **Artifact anchor:** [docs/RESEARCH/REGIME_PERIODS_2025_2026.md](../RESEARCH/REGIME_PERIODS_2025_2026.md)
- **Consolidated statement:** all yearly transitions passed through `RANGE`; there were no direct trend-to-trend flips, creating explicit buffer time for coordinator transitions.

---

## §4 Strategic shifts during the day

### Shift 1 — From “1 TZ per day” to operator-presence weekly-session model

- **Evidence anchors:** [docs/SPRINTS/SPRINT_2026-05-04.md](../SPRINTS/SPRINT_2026-05-04.md), [docs/STATE/PENDING_TZ.md](../STATE/PENDING_TZ.md)
- **What changed:** the project moved further away from isolated single-task cadence toward a dense operator-present weekly work model with multiple parallel tracks and CP-based governance.

### Shift 2 — From “fix sim K-factors” to “use GinArea live ground truth”

- **Evidence anchor:** [docs/RESEARCH/BACKTEST_AUDIT.md](../RESEARCH/BACKTEST_AUDIT.md)
- **What changed:** afternoon audit work exposed that several baseline figures were only partially aligned with live mechanics. That changed the trust hierarchy for subsequent reasoning.

### Shift 3 — From “P8 ensemble is nice to have” to “P8 ensemble is central architecture”

- **Evidence anchors:** [docs/RESEARCH/REGIME_PERIODS_2025_2026.md](../RESEARCH/REGIME_PERIODS_2025_2026.md), [docs/RESEARCH/REGIME_OVERLAY_v1.md](../RESEARCH/REGIME_OVERLAY_v1.md), [docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md](../DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md)
- **What changed:** by evening, the coordinator / ensemble line was no longer optional research. The regime and overlay outputs made it the core architecture direction.

### Logged side-idea

- **Operator side-idea recorded:** `TZ-SELF-REGULATING-BOT-RESEARCH`
- **Status in this consolidation:** logged to backlog only; no new analysis added here

---

## §5 Backlog generated today

This backlog consolidates scattered follow-up TZ references from the day. Priorities are preserved as planning labels, not recommendations.

| TZ ID | Priority | Dependencies | Est. worker time | Why it exists in backlog |
|---|---|---|---:|---|
| `TZ-X` | P1 | `REGIME_OVERLAY_v1.md`, `GINAREA_BACKTESTS_REGISTRY_v1.md`, `REGIME_PERIODS_2025_2026.md` | 20-30m | Apples-to-apples cross-check of Finding A |
| `TZ-Y` | P1 | dashboard snapshot path, operator screenshot reproduction | 30-60m | Snapshot SHORT duplication remained visible after same-day patch |
| `TZ-K-RECALIBRATE-PRODUCTION-CONFIGS` | P1 | `BACKTEST_AUDIT.md` | 2-4h | Audit recommendation to rebuild calibration numbers on production-aligned parameters |
| `TZ-TRANSITION-MODE-COMPARE-BACKTEST` | P2 | P8 coordinator open questions | 1-2h | Q2 in coordinator line remained unresolved |
| `TZ-SELF-REGULATING-BOT-RESEARCH` | P3 | none | 1-2h | Operator side-idea logged for later research |
| `TZ-FIX-COLLECTION-ERRORS` | P1 | current broken test surface, `DEBT-04` context | 2-4h | Same-day suite still had broken collection files plus brittle datetime test |
| `TZ-DASHBOARD-CONTENT-VALIDATION` | P3 | dashboard freshness/content branch | 30-60m | Low-priority validation pass after dashboard state fixes |
| `TZ-DEDUP-WIRE-PNL_EVENT` | P2 | 24h confirmed `POSITION_CHANGE` and later `BOUNDARY_BREACH` behavior; tuning artifact | 30-45m | Next emitter in dedup rollout sequence |
| `TZ-DEDUP-WIRE-PNL_EXTREME` | P2 | `TZ-DEDUP-WIRE-PNL_EVENT`, tuning artifact | 30-45m | Follows `PNL_EVENT` in rollout sequence |
| `TZ-IMPULSE-RECALIBRATE` | P3 | operator decision to activate `impulse_long_rej` | 30-60m | Conditional follow-up only if operator chooses that activation path |
| `TZ-MORNING-BRIEF-MULTITRACK-ADAPT` cleanup | P3 | roadmap / sprint tooling | 30-60m | Same tool family remained a maintenance surface even after same-day fix |

---

## §6 Operator decisions made today

### Sizing v0.1

- **Q1-Q5 from sizing v0.1:** treated as closed for the day’s design/output line
- **Artifact anchor:** [docs/DESIGN/SIZING_MULTIPLIER_v0_1.md](../DESIGN/SIZING_MULTIPLIER_v0_1.md)

### P8 coordinator

- **Q1:** deferred
- **Q2:** deferred
- **Q3:** reserved
- **Q4:** enhanced alerts added
- **Q5:** `5 min`
- **Artifact anchor:** [docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md](../DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md)

### Dual-worker preference

- **Recorded operator preference:** `Codex` for monotonous / compile / structuring work; `Claude` for critical / interpretive / argumentative passes
- **Status in this consolidation:** recorded as working preference for future sessions; not expanded beyond today’s observed split model

---

## §7 Anti-drift incidents during the day

These incidents were already part of the day’s operator/MMAIN governance context. They are consolidated here as process memory, not re-litigated.

| Incident | What went wrong | How detected | Prevention rule added / reinforced |
|---|---|---|---|
| Block 12 brief lacked production parameters | MAIN prepared a brief without the concrete live-parameter anchor needed for reliable comparison | Operator noticed mismatch against production-mechanics expectations | Any audit/recalibration brief touching bot PnL must anchor to `GINAREA_MECHANICS §6` or explicitly mark params unknown |
| Block 13 repeated the same pattern | Production-parameter omission repeated in the next brief family | Operator caught the recurrence | Reuse the same gold-standard parameter reference across neighboring calibration TZs |
| “Declared CP2 GREEN without visual check” | A checkpoint was treated as green before direct output validation | Operator intervened and status was rolled back | No visual/UI-facing checkpoint is `GREEN` without an explicit visual verification step |
| “Did not read earlier finding about live bots on different instop” | Previous already-known finding was not carried into later reasoning | Operator caught inconsistency in reasoning chain | Before claiming novelty, re-check same-day findings and active audit docs |
| “Did not read Codex audit correctly” | MAIN reasoning diverged from what the audit actually said | Operator caught misread of the artifact | Artifact-driven claims must quote or paraphrase the actual doc conclusions, not memory of them |

---

## §8 Reference cross-links

This is the compact index of the main artifacts created or actively used today.

### Research

- [docs/RESEARCH/BACKTEST_AUDIT.md](../RESEARCH/BACKTEST_AUDIT.md)
- [docs/RESEARCH/GINAREA_BACKTESTS_REGISTRY_v1.md](../RESEARCH/GINAREA_BACKTESTS_REGISTRY_v1.md)
- [docs/RESEARCH/REGIME_PERIODS_2025_2026.md](../RESEARCH/REGIME_PERIODS_2025_2026.md)
- [docs/RESEARCH/REGIME_OVERLAY_v1.md](../RESEARCH/REGIME_OVERLAY_v1.md)
- [docs/RESEARCH/REGIME_OVERLAY_v1_CROSSCHECK.md](../RESEARCH/REGIME_OVERLAY_v1_CROSSCHECK.md)
- [docs/RESEARCH/P8_RGE_EXPANSION_RESULTS_v0_1.md](../RESEARCH/P8_RGE_EXPANSION_RESULTS_v0_1.md)
- [docs/RESEARCH/LONG_TP_SWEEP_v1.md](../RESEARCH/LONG_TP_SWEEP_v1.md)
- [docs/RESEARCH/DEDUP_DRY_RUN_2026-05-04.md](../RESEARCH/DEDUP_DRY_RUN_2026-05-04.md)
- [docs/RESEARCH/DEDUP_THRESHOLD_TUNING_v1.md](../RESEARCH/DEDUP_THRESHOLD_TUNING_v1.md)
- [docs/RESEARCH/_regime_periods_raw.json](../RESEARCH/_regime_periods_raw.json)
- [docs/RESEARCH/_p8_raw_results.json](../RESEARCH/_p8_raw_results.json)
- [docs/RESEARCH/_long_tp_sweep_raw.json](../RESEARCH/_long_tp_sweep_raw.json)
- [docs/RESEARCH/_dedup_dry_run_raw.json](../RESEARCH/_dedup_dry_run_raw.json)

### Design

- [docs/DESIGN/SIZING_MULTIPLIER_v0_1.md](../DESIGN/SIZING_MULTIPLIER_v0_1.md)
- [docs/DESIGN/P8_RANGE_DETECTION_v0_1.md](../DESIGN/P8_RANGE_DETECTION_v0_1.md)
- [docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md](../DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md)
- [docs/DESIGN/BOT_ID_SCHEMA_v0_1.md](../DESIGN/BOT_ID_SCHEMA_v0_1.md)

### State / operator-facing control docs

- [docs/STATE/BOT_INVENTORY.md](../STATE/BOT_INVENTORY.md)
- [docs/STATE/TELEGRAM_EMITTERS_INVENTORY.md](../STATE/TELEGRAM_EMITTERS_INVENTORY.md)
- [docs/STATE/PENDING_TZ.md](../STATE/PENDING_TZ.md)
- [docs/STATE/QUEUE.md](../STATE/QUEUE.md)
- [docs/STATE/CURRENT_STATE_latest.md](../STATE/CURRENT_STATE_latest.md)
- [docs/CONTEXT/STATE_CURRENT.md](../CONTEXT/STATE_CURRENT.md)
- Hourly 2026-05-04 state snapshots: `docs/STATE/CURRENT_STATE_2026-05-04_*.md`
- Dashboard state outputs and logs under `docs/STATE/` used by the P4 line

### Sprint / session scaffolding

- [docs/SPRINTS/SPRINT_2026-05-04.md](../SPRINTS/SPRINT_2026-05-04.md)
- [docs/SPRINTS/SPRINT_2026-05-04_DRAFT.md](../SPRINTS/SPRINT_2026-05-04_DRAFT.md)

---

## Closing snapshot

By end of day 2026-05-04, the project state had shifted from local tactical improvements to a research-backed architectural pivot:

- P1 actionability primitives were advanced
- P4 dashboard visibility materially improved but still had unresolved content correctness
- P7 dedup moved from diagnosis to first production wiring
- P8 moved onto live-ground-truth and regime-structure foundations

This file is the one-document operator handoff for that session.
