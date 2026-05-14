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

## HANDOFF generation protocol (TZ-068)

Before creating any HANDOFF document (docs/HANDOFF_<date>_<part>.md):
1. Run `python scripts/state_snapshot.py` → generates docs/STATE/CURRENT_STATE_<ts>.md
2. Link the fresh state report in HANDOFF §1 table: "| Текущий стейт | [CURRENT_STATE_latest.md](STATE/CURRENT_STATE_latest.md) |"
3. HANDOFF without state link → incomplete, do not mark done.

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

## TZ Template — Inventory Check

Before any ТЗ for new functionality, new module, or new feature:

**Code-side mandatory before execution:**
1. Confirm `project_inventory_first` skill was applied by architect.
2. If "Skills applied" section is missing or does not list `project_inventory_first` for applicable TZ → REJECT with:
   ```
   ТЗ ОТКЛОНЁН: inventory check missing. Apply project_inventory_first skill in chat.
   ```

**Architect-side mandatory before issuing TZ:**
1. Walk `src/`, `services/`, `_recovery/restored/` for relevant keywords.
2. Read `docs/STATE/PROJECT_MAP.md` (sections: active modules, conflicts, missing deps).
3. Read latest `docs/STATE/RESTORED_FEATURES_AUDIT_*.json` for any module with `status == "restored_only"` relevant to the task.
4. If parallel implementation found → replace TZ with `TZ-INVENTORY-<feature>` that decides reactivate/integrate/leave.

**Session end mandatory:**
Apply `session_handoff_protocol` skill whenever session closes with open threads or context near limit. Generate `docs/HANDOFF_<date>_<part>.md` covering all active threads, pending decisions, anti-patterns discovered, and "what to tell new Claude" snippet.

## Skills triggers index

When ТЗ contains keywords or task involves these operations, listed skills are MANDATORY:

| Triggers | Required skill |
|---|---|
| backtest, ohlcv, market_collector, real validation, frozen, historical data | data_freshness_check |
| live, rollout, deploy, kill PID, restart daemon, taskkill | live_position_safety |
| after backtest/validation/detector — before final report | result_sanity_check |
| recovery, restoration, rollback, file loss, root cause | incident_log_writer |
| strategy parameter change (C1, C2, threshold, target, gs, TP, SL, risk) | param_provenance_tracker |
| long backtest, grid search, ML, full repo scan | cost_aware_executor |
| Telegram output, advise, signal rendering | telegram_signal_validator |
| any code change, ТЗ closing, before commit | regression_baseline_keeper |
| live bots, GinArea API, Bitmex positions, market_collector | state_drift_detector |
| writing .md/.txt/.csv/.json files via PowerShell or Python on Windows | encoding_safety |
| new chat session start; positions/bots/AGM/liq/trading decisions | state_first_protocol |
| architect ТЗ contains git/script/file commands directed at operator | operator_role_boundary |
| new module, add feature, new service, write X, implement Y, before нарезать TZ | project_inventory_first |
| end of session, session handoff, new chat, context limit, open threads | session_handoff_protocol |
| architect отправляет TZ для new module, new feature, new service | architect_inventory_first |

Skills live in `.claude/skills/<name>.md`. Code reads relevant skill when trigger matches.

## Skills applied — bidirectional enforcement

**Chat-side (Claude in chat) responsibility:**
Every ТЗ must include section:
Skills applied

skill_name_1 (because: [trigger])
skill_name_2 (because: [trigger])

ТЗ without this section or with skills not matching triggers detected by Code → REJECT.

**Code-side responsibility:**
1. On receiving ТЗ — parse triggers in goal/steps, derive expected skills.
2. Compare to "Skills applied" section.
3. If mismatch:
SKILLS MISMATCH:

ТЗ declared: [list]
Triggers detected: [list]
Missing: [list]
Передай Claude в чате для исправления.

4. Final report must include:
SKILLS APPLIED:

skill_name_1: [confirmation/result]
skill_name_2: [confirmation/result]

5. If skill detected applicable but not applied — final report flags it as INCOMPLETE regardless of other criteria.

This double-check prevents skill amnesia on either end.
