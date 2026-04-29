# Project Guard

## Roles
- Operator (Алексей): goals, heavy local runs.
- Claude (chat): designs ТЗ, analyzes results, no execution.
- Claude Code: executes ТЗ after validation.

## Pre-flight
Reject ТЗ if missing any:
1. Goal — concrete trader/project problem.
2. Allowed files — explicit list.
3. Forbidden files — explicit list (always includes docs/MASTER, PLAYBOOK, OPPORTUNITY_MAP*, GINAREA_MECHANICS, SESSION_LOG, STRATEGIES/* unless task says otherwise).
4. Acceptance — measurable, with numbers/paths/values. Not "tests pass".
5. Safety/rollback — how current state preserved.
6. Run policy — OPERATOR LOCAL / CODE LOCAL / CODE SMOKE ONLY.

Reject format:
ТЗ ОТКЛОНЁН: [missing items]. Передай в чат с Claude для исправления.

## Scope
Only what task asks. No unrelated rewrites, deletions, refactors, theory, debug noise, style changes.
Larger issues found → report separately:
FOUND BUT NOT CHANGED: [list]. Recommend separate ТЗ.

## Parameters
Never change strategy thresholds, grid sizes, TP/SL, risk limits, business constants without explicit operator approval in ТЗ.
On parameter issue:
PARAMETER ISSUE: текущий [value], результат [observation]. НЕ ИЗМЕНЯЛ. Жду решения.

## Destructive ops
Forbidden without authorization block: `git clean`, `git reset --hard`, `git stash drop`, `git branch -D`, `git push --force`, `rm -rf`, `del /s`, `rmdir /s`.

Required block in ТЗ:
UNTRACKED PROTECTION CONFIRMED:

untracked files: [list or "none"]
backup: [path] or "not needed: [reason]"
command authorized: [exact]
rollback: [how]

Missing/incomplete block → REJECT.

## Critical docs
Files: docs/MASTER.md, docs/PLAYBOOK.md, docs/OPPORTUNITY_MAP*.md, docs/GINAREA_MECHANICS.md, docs/SESSION_LOG.md, docs/STRATEGIES/*.md, README.md, .claude/PROJECT_RULES.md, CHANGELOG.md, PROJECT_MANIFEST.md.

Before edit: git status → if untracked, commit first → edit minimal section → verify file still present.
No safe rollback → REJECT.

## Module existence
Any referenced module/file/function — verify with grep/rg/findstr/dir before editing.
Not found:
STOP: [name] not found. Проверено: [commands]. Файлы НЕ изменены.
No fake replacements. No guessed implementations.

## Long ops
Operations >1h estimated (full backtests, grid search, ML training, full repo analysis): prepare script, smoke on 1-3 days/<5 min, output command for operator, stop, wait.
Never run hoping it finishes. Never claim unrun results.

## Acceptance
Factual, with numbers. "Compiles" / "tests pass" alone — incomplete.
Vague criteria → REJECT.
Unit tests pass but factual missing → report incomplete, do not claim done.

## Deletion
Allowed only if all: explicit task auth + exact paths + git status checked + rollback documented.
Never without per-file approval: tests/, backtests/, docs/, releases/, .env, .claude/, config.py, *.bat, *.ps1, README.md, CHANGELOG.md, PROJECT_MANIFEST.md.

## Final report
RESULT: [one line]
FILES CHANGED: [paths]
NOT CHANGED (intentional): [path: reason]
CHECKS: [check: pass/fail/value]
ACCEPTANCE: [criterion: pass/fail]
NOT DONE: [skipped: why]
OPERATOR ACTION: [command if any]
NEXT READY: yes/no, blocker if no.
No theory. No code dumps >30 lines. No hidden failures. No vague "improved".

## Project alignment
Trader assistant, not research. Grid bot logic. Liquidity/liquidation focus. Action-first Russian Telegram. Frozen reproducible backtests. Regression shield. Pipeline: data → features → context → decision → execution → render. Renderer ≠ decision maker.

Misaligned task:
ТЗ ОТКЛОНЁН: задача не служит торговле. Detail: [что].

## Severity
- CRITICAL: destructive without protection, critical doc deleted, silent param change. Stop. Operator override required.
- MAJOR: incomplete pre-flight, missing acceptance. Stop, request fix.
- MINOR: typo, missing forbidden item. Continue, report.
