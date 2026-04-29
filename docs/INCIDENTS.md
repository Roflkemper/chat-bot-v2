# INCIDENTS

Accumulation of incidents, root causes, and prevention rules.

---

2026-04-29 — Skills system absent at project start

What happened: Claude Code repeatedly violated operator protocols this session — ran heavy backtests instead of only fixing bugs, triggered multiple permission prompts, skipped validation of ground truth timestamps, failed to send notifications until explicitly asked.

Root cause: No structured checklist enforcing pre-flight protocol per task type. Each ТЗ was executed from scratch with no memory of applicable constraints.

Fix: TZ-059 installed 9 skills in `.claude/skills/`, bidirectional enforcement in PROJECT_RULES.md, pre-commit hook protection for all skill files.

Prevention: Every ТЗ must declare "Skills applied" section. Code-side verifies triggers vs declared skills before execution. Missing skill = REJECT.

Related TZ: TZ-059
