# DRIFT HISTORY
# Назначение: anti-patterns и drift incidents. Читать перед новой TZ.
# Формат: каждый incident — ID, дата, тип, симптомы, root cause, fix.
# Обновлять при каждом обнаруженном дрейфе.

---

## DRIFT-001 — Playbook v3 reactive anti-pattern

**Date:** 2026-05-01 → 2026-05-03
**Type:** drift+ (scope creep — built something not in plan)
**Detected by:** TZ-COUNTERTREND-VALIDATE-VS-OPERATOR (commit 1ffdc12)

**Symptoms:**
- Bot generating 6 "advise" signals/day that operator ignored
- Playbook rules said "act on signal" but operator acted on market feel instead
- Growing gap between playbook-recommended actions and actual operator decisions

**Root cause:**
- Playbook built as per-alert reactive tree (DP-003)
- Did not account for operator's phase-level state awareness
- Each alert treated as independent without MTF context

**Fix:**
- Playbook v3 with early-intervention branch (db8f064)
- Phase classifier feeds branch selection upstream
- Operator brief generated once/day, not per-alert

**Prevention rule:**
> Before adding any new operator-facing signal: verify operator will actually use it.
> If no operator action in 3+ consecutive signals of a type → deprecate the signal type.

---

## DRIFT-002 — INERT-BOTS confusion

**Date:** 2026-04-28 → 2026-04-30
**Type:** drift- (incomplete — work started, wrong direction)
**Detected by:** TZ-PROJECT-STATE-AUDIT (2026-05-02)

**Symptoms:**
- Bot started, tracker showed RUNNING, but no actual trades executed
- Operator assumed bots were active; they were "inert" (running but not trading)
- Counter-long, boundary-expand, adaptive-grid all showed RUNNING with 0 actions

**Root cause:**
- Services launched but no live positions existed to act on
- Tracker RUNNING = process alive, not "doing something meaningful"
- No distinction between "service running" and "service actively managing positions"

**Fix:**
- Added `cmdline_must_contain` fallback check in tracker (TZ-DIAGNOSE-TRACKER-FALSE-NEGATIVE)
- Paper journal started (Day 1) as Phase 1 to generate observable signal record

**Prevention rule:**
> RUNNING in tracker = process alive only. Always check last_action timestamp.
> If last_action > 6h ago for an active service → investigate before assuming OK.

---

## DRIFT-003 — Premature TZ without prerequisite inventory

**Date:** 2026-04-26 → 2026-04-29
**Type:** drift+ (wrong direction — built without checking what existed)
**Detected by:** TZ-PROJECT-STATE-AUDIT

**Symptoms:**
- TZ-057/065/066 queued before H10 backtest data existed
- TZ-ENGINE-FIX-RESOLUTION started before operator confirmed 1s OHLCV availability
- Multiple TZs blocked immediately after start (no data, no baseline)

**Root cause:**
- TZs written without checking PENDING_TZ.md for existing blockers
- Dependency graph not validated before scheduling
- "Optimistic planning" — assumed data/infrastructure would be ready

**Fix:**
- TZ validator CLI: `tools/validate_tz.py` (TZ-CLAUDE-TZ-VALIDATOR, 20 tests)
- Mandatory pre-TZ check: validate_tz before starting any TZ
- Operator action items listed explicitly in §5 of STATE_CURRENT.md

**Prevention rule:**
> Before scheduling any TZ that depends on data: verify data exists with `ls -la data/`.
> Before scheduling any TZ that depends on another TZ: confirm that TZ is ✅ DONE in STATE_CURRENT.

---

## DRIFT-004 — Context window exhaustion mid-TZ

**Date:** 2026-05-03 (this session)
**Type:** drift- (incomplete — TZ interrupted by context limits)
**Detected by:** Session summary trigger

**Symptoms:**
- TZ-MAIN-COORDINATOR-INFRASTRUCTURE started (12 deliverables)
- Context hit limit after deliverable 1 (WEEK_TEMPLATE.md)
- Work state scattered across session summary

**Root cause:**
- 12-deliverable TZ is too large for single session without handoff checkpoints
- No mid-TZ checkpoints defined (only end-of-TZ commit planned)
- WEEK_TEMPLATE was first deliverable but commit deferred to end

**Fix:**
- Resumed from session summary (context preserved across compaction)
- Deliverables being written sequentially, committed at end

**Prevention rule:**
> For TZs with >6 deliverables: commit after every 3rd deliverable as intermediate checkpoint.
> Mid-TZ commit message: "wip(TZ-ID): deliverables N-M done, N+1 to N+6 remaining"

---

## DRIFT-005 — Calibration ceiling mistaken for fixable bug

**Date:** 2026-05-03
**Type:** drift+ (scope creep — kept trying to improve past fundamental ceiling)
**Detected by:** CP3 GO/NO-GO gate

**Symptoms:**
- Brier target: ≤0.22. Actual: ~0.257 across all trials
- Spent ~2h on threshold tuning (1% → 0.3%), feature additions, weight perturbations
- Each attempt improved Brier marginally but never crossed 0.22

**Root cause:**
- Rule-based signals (positioning extreme, structural context) are systematically contrarian
- In strong bull year (2025-2026), contrarian signals fire bearish during markup
- No amount of weight tuning fixes systematic signal inversion

**Fix:**
- CP3 gate triggered (0.22-0.28 → report operator, wait)
- Sent to operator as GO/NO-GO decision (not treated as a bug to fix)
- WHATIF-V3 full rebuild killed (DP-002)

**Prevention rule:**
> If Brier does not improve after 3 different approaches → it is a ceiling, not a bug.
> At ceiling: document the root cause, trigger operator gate, do not continue tuning.

---

## DRIFT-PATTERN SUMMARY

| Pattern | Count | Typical trigger |
|---------|-------|----------------|
| Premature TZ (no inventory check) | 3 | Optimistic scheduling |
| Reactive builds (no operator validation) | 2 | Alert-first design |
| Context exhaustion mid-TZ | 1 | >6 deliverable TZs |
| Calibration ceiling chasing | 1 | Missing explicit stop criterion |
| Service confusion (RUNNING ≠ active) | 1 | Tracker status misread |

**Most common:** Premature TZ without checking prerequisites.
**Highest impact:** INERT-BOTS confusion (2+ days of false confidence).
