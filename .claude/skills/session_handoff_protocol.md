---
name: session_handoff_protocol
description: Protocol for preparing a complete handoff document at session end, so the next Claude session starts with full situational awareness. Prevents INC-012 (architectural amnesia — next session cannot know session-specific discoveries, decisions, or gotchas).
type: skill
---

# Skill: session_handoff_protocol

## Trigger

Apply when ANY of these match:
- Operator signals end of session ("закончим", "на сегодня всё", "следующий чат", "передай")
- Architect notices the session is long (>30 TZ exchanged or >2h) and has open threads
- Any TZ is left in status IN_PROGRESS at expected session close
- Operator asks Code to generate HANDOFF document

## Rule: TZ-HANDOFF-PREPARE

Architect issues `TZ-HANDOFF-PREPARE` to Code covering parts A through F:

### Part A — Living State
Code runs:
```
python scripts/state_snapshot.py --no-api
```
Links output `docs/STATE/CURRENT_STATE_latest.md` in HANDOFF §1 table.

### Part B — Active Threads
For each open TZ or ongoing investigation, document:
- TZ name / description
- Current status (done/blocked/in_progress/deferred)
- Key facts discovered (file paths, line numbers, error messages)
- Next action if not done

Format:
```
## Thread: <TZ-name>
Status: in_progress
Facts:
  - <path>: <observation>
  - <finding>
Next: <concrete action>
```

### Part C — Pending Decisions
List decisions that were DEFERRED to operator or next session:
- Decision topic
- Options considered
- Why deferred (blocker, needs data, operator choice)
- What the next Claude needs to know to resume

### Part D — Anti-patterns Discovered This Session
List behaviors, patterns, or assumptions that proved WRONG this session:
- What was assumed
- What was found instead
- Rule: don't do X, do Y instead

### Part E — Recent Commits
```
git log --oneline -20
```
Include full output in HANDOFF. Next Claude must know what was committed.

### Part F — Open TZs
Read `docs/STATE/QUEUE.md` and list:
- All TZs with status != done
- Their priority and blocking dependencies

## Architect Step: Final Snippet

After Code generates the HANDOFF, architect Claude reads it and produces a **"What to tell new Claude"** summary — a short paragraph (5-10 lines) for the operator to paste as first message in the new session.

Format:
```
Session handoff: <date>

Active work: <1-2 lines on what was being done>
Key discoveries: <critical facts new Claude must know, not obvious from code>
Do NOT: <anti-patterns discovered this session>
Open threads: <TZ names with one-line status>
First step: <exact first action new Claude should take>
```

## Output location

```
docs/HANDOFF_<YYYY-MM-DD>_<part>.md
```

## Integration with MAIN coordinator

After generating the handoff, also:
1. Update `docs/STATE/STATE_CURRENT.md` §2 and §6 (changelog)
2. If session ends mid-TZ: mark it IN_PROGRESS in `docs/STATE/PENDING_TZ.md`
3. Notify MAIN coordinator (paste handoff summary in MAIN chat)

MAIN coordinator uses `docs/CONTEXT/` layer for cross-session context:
- `docs/CONTEXT/STATE_CURRENT.md` — living state (updated EOD)
- `docs/CONTEXT/DEPRECATED_PATHS.md` — what not to rebuild
- `docs/CONTEXT/DRIFT_HISTORY.md` — known anti-patterns

See skill `main_coordinator_protocol` for full MAIN protocol.

## Why this skill exists

**INC-012** (2026-04-29): After context exhaustion, new chat session started with no knowledge of:
- `src/advisor/v2/cascade.py` being a known duplicate (not to reactivate)
- `src/features/calendar.py` being missing from active code
- 34 modules in `_recovery/restored/` needing inventory review
- Specific pagination behavior discovered for OKX liquidation API (`uly` parameter, not `instId`)
- Silence detection pattern discovered for Binance geo-restriction

All of these were session-specific discoveries that could not be inferred from code or git history alone. A handoff document would have preserved them.
