---
name: anti_drift_validator
description: Validates that a proposed TZ or in-progress work has not drifted from its original scope. Two drift types: drift+ (scope creep — built beyond plan) and drift- (incomplete — started but not finished). Run before each TZ start and at each checkpoint.
type: skill
---

# Skill: anti_drift_validator

## Trigger

Apply when ANY of these match:
- Starting a new TZ (pre-flight check)
- Mid-TZ checkpoint (every 3 deliverables)
- Operator says "check scope" / "validate drift" / "are we on track"
- Any deliverable takes >2x estimated time
- A new sub-task is proposed mid-TZ

---

## CHECK 1 — Pre-TZ inventory (drift prevention)

Before writing any code:

```
1. Read docs/STATE/PENDING_TZ.md → does this TZ already exist?
2. Read docs/CONTEXT/DEPRECATED_PATHS.md → does it repeat a deprecated approach?
3. Read docs/CONTEXT/DRIFT_HISTORY.md → does it match a known anti-pattern?
4. List all data dependencies → verify each exists:
   ls -la data/<expected_dir>/
5. List all TZ dependencies → verify each is ✅ DONE in STATE_CURRENT.md §2
```

**STOP criteria (do not start TZ if):**
- TZ already exists with overlapping scope
- Data dependency missing and operator has not confirmed it will be provided
- Depends on TZ that is IN_PROGRESS or BLOCKED

---

## CHECK 2 — Scope boundary (drift+ guard)

At every deliverable, ask:

> "Is this deliverable listed in the original TZ spec?"

If YES → continue.
If NO → STOP. Output:

```
DRIFT+ DETECTED
Proposed: <what I was about to do>
Not in scope: <original TZ spec says nothing about this>
Action: drop / defer to new TZ / get operator approval
```

**Do NOT:**
- Add error handling not in spec
- Add tests for behavior not being changed
- Refactor adjacent code "while I'm here"
- Create helper utilities not requested

---

## CHECK 3 — Completeness (drift- guard)

At TZ end, verify ALL hard deliverables from spec are done:

```
for each deliverable in TZ spec:
    [ ] file exists / test passes / metric met?
```

If ANY unchecked → TZ is NOT done. Do not mark as ✅ DONE.

Output:
```
DRIFT- DETECTED
Missing: <deliverable name>
Status: incomplete
Action: finish <deliverable> before commit
```

---

## CHECK 4 — Time drift

If a single TZ task takes >2x its estimate:

```
TIME DRIFT DETECTED
Estimated: Xh  Actual: Yh  (ratio: Y/X)
Root cause: <why it took longer>
Options:
  A) Continue if <2h remaining and on critical path
  B) Checkpoint commit + defer remainder to new TZ
  C) Notify operator if Y/X > 3x
```

---

## CHECK 5 — Replan triggers

Immediately notify operator and STOP work if:
- CP gate fails (Brier > threshold, tests red, metric regresses)
- A dependency was assumed to exist but does not
- 2+ hard deliverables are blocked simultaneously
- Work would touch files outside the stated scope boundary

Format:
```
REPLAN REQUIRED
Trigger: <which condition>
Current state: <what was done>
Blocked by: <what is missing>
Operator decision needed: <yes/no + what decision>
```

---

## Output format (pass case)

```
DRIFT CHECK PASSED ✅
TZ: <name>
Deliverables complete: N/M
Scope boundary: clean
Time: Xh (est Yh)
Next: <next deliverable>
```

## Why this skill exists

DRIFT-001 (playbook v3 reactive), DRIFT-003 (premature TZ), and DRIFT-005 (calibration ceiling chasing) all involved work continuing past the point where a scope check would have stopped it. See `docs/CONTEXT/DRIFT_HISTORY.md` for full incident records.
