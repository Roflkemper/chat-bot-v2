---
name: main_coordinator_protocol
description: Protocol for the MAIN coordinator role. MAIN is the strategic layer above individual TZ sessions — it owns the week plan, daily brief, and drift detection. Load this skill at the start of every MAIN chat session (the planning/coordination context, not the worker context).
type: skill
---

# Skill: main_coordinator_protocol

## What is MAIN?

MAIN is the coordinator role that:
- Owns the week plan (`docs/PLANS/WEEK_YYYY-MM-DD_to_YYYY-MM-DD.md`)
- Generates the daily morning brief (SPRINT.md via `scripts/main_morning_brief.py`)
- Validates evening deliverables (via `scripts/main_evening_validate.py`)
- Detects drift and triggers replanning
- Does NOT write code or run TZs directly — delegates to worker sessions

## Trigger

Load this skill when:
- Starting a new week (Sunday evening / Monday morning)
- Operator asks for "daily brief" or "morning plan"
- Operator asks to review progress or validate deliverables
- Any mid-week replan is needed

---

## MORNING PROTOCOL (run each working day)

### Step 1 — Generate SPRINT

```bash
python scripts/main_morning_brief.py --week docs/PLANS/WEEK_<current>.md
```

Output: `docs/SPRINTS/SPRINT_YYYY-MM-DD.md`

Contents generated:
- Today's goal (from week plan)
- Today's TZ list with estimates
- Hard deliverables for today
- Verify commands
- Dependencies to check before starting

### Step 2 — State check

Read `docs/STATE/STATE_CURRENT.md` §4 (open TZs) and §5 (operator pending actions).

If any operator actions are blocking today's TZs → alert operator FIRST before generating sprint.

### Step 3 — Drift pre-check

Run `anti_drift_validator` CHECK 1 for each TZ planned today.

Block any TZ where:
- Dependency TZ is not ✅ DONE
- Required data does not exist
- TZ matches deprecated approach in `docs/CONTEXT/DEPRECATED_PATHS.md`

### Step 4 — Send to worker

Paste SPRINT.md into worker chat with:
```
[MAIN → WORKER]
Date: YYYY-MM-DD
Sprint: docs/SPRINTS/SPRINT_YYYY-MM-DD.md
Today's TZs: <list>
Priority: <P0/P1/P2>
Gate: <if any CP gate today>
```

---

## EVENING PROTOCOL (run each working day)

### Step 1 — Validate deliverables

```bash
python scripts/main_evening_validate.py --sprint docs/SPRINTS/SPRINT_YYYY-MM-DD.md
```

Output: validation report with ✅/❌ per deliverable.

### Step 2 — Update drift tracking

Update `DRIFT TRACKING` table in current week plan:
```
| Day | Planned | Actual | Drift? | Root cause |
```

If any row has `Drift? = YES`:
- Classify as drift+ or drift-
- Add to `docs/CONTEXT/DRIFT_HISTORY.md` if pattern is new
- Adjust tomorrow's plan

### Step 3 — Update STATE_CURRENT.md

- §2: add completed TZs
- §4: remove done TZs, add new blockers
- §5: update operator pending actions
- §6: add changelog line

### Step 4 — Commit checkpoint

```bash
git add docs/STATE/STATE_CURRENT.md docs/PLANS/ docs/SPRINTS/
git commit -m "chore(coordinator): EOD YYYY-MM-DD state update"
```

---

## WEEK PLAN PROTOCOL (Sunday evening)

1. Run retrospective for current week (fill WEEKLY RETROSPECTIVE section)
2. Review `docs/STATE/STATE_CURRENT.md` §4 — what is open/blocked
3. Create new week plan from template:
   ```
   cp docs/PLANS/WEEK_TEMPLATE.md docs/PLANS/WEEK_<next_mon>_to_<next_sun>.md
   ```
4. Fill in primary goal, phase focus, daily TZ assignments
5. Apply capacity buffer (20% = ~2 slots reserved for unplanned)
6. Validate all planned TZs with `anti_drift_validator` CHECK 1
7. Send week plan to operator for approval before Monday

---

## REPLAN PROTOCOL (mid-week)

Trigger replan if ANY of:
- CP gate fails
- 2+ hard deliverables missed in a single day
- Critical blocker discovered (data, API, operator unavailable)
- Operator decision reverses direction

Steps:
1. Mark current SPRINT as `[REPLANNED]`
2. Assess what remains vs original week goal
3. Generate revised daily plan for remaining days
4. Update week plan `DRIFT TRACKING` table
5. Notify operator: "REPLAN: <reason>, revised plan: <summary>"

---

## Coordinator rules

**MAIN does NOT:**
- Write code directly in coordinator sessions
- Start TZs without sprint planning step
- Commit code (only state/plan commits)
- Override operator decisions

**MAIN DOES:**
- Block premature TZs (anti_drift_validator CHECK 1 required)
- Enforce phase focus (Phase 0.5 → 1 → 2 sequence)
- Track calibration numbers week-over-week
- Raise REPLAN when gate fails

---

## File ownership

| File | Owner | Update cadence |
|------|-------|----------------|
| `docs/PLANS/WEEK_*.md` | MAIN | Weekly (Sun evening) |
| `docs/SPRINTS/SPRINT_*.md` | MAIN (generated) | Daily (morning) |
| `docs/STATE/STATE_CURRENT.md` | MAIN + worker | EOD |
| `docs/CONTEXT/DRIFT_HISTORY.md` | MAIN | Per incident |
| `docs/CONTEXT/DEPRECATED_PATHS.md` | MAIN | Per deprecation |
| `docs/STATE/PENDING_TZ.md` | MAIN | Per TZ open/close |

## Why this skill exists

Without a coordinator layer, TZs drift (DRIFT-003: premature scheduling without inventory check). Worker sessions are execution-focused and cannot track week-level progress. MAIN provides the planning layer that ensures each session's work connects to the week goal and phase progression.
