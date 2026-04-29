# INCIDENTS

Accumulation of incidents, root causes, and prevention rules.

---

2026-04-29 — Skills system absent at project start

What happened: Claude Code repeatedly violated operator protocols this session — ran heavy backtests instead of only fixing bugs, triggered multiple permission prompts, skipped validation of ground truth timestamps, failed to send notifications until explicitly asked.

Root cause: No structured checklist enforcing pre-flight protocol per task type. Each ТЗ was executed from scratch with no memory of applicable constraints.

Fix: TZ-059 installed 9 skills in `.claude/skills/`, bidirectional enforcement in PROJECT_RULES.md, pre-commit hook protection for all skill files.

Prevention: Every ТЗ must declare "Skills applied" section. Code-side verifies triggers vs declared skills before execution. Missing skill = REJECT.

Related TZ: TZ-059

---

## INC-008: No main branch from project start (2026-04-29)

**Symptom:** При попытке branch consolidation (TZ-065) оказалось что `main` ветки не существует — весь проект работал на feature/tz-059-skills-system. Переезд в новый чат усложнился, нужна была ручная процедура создания main.

**Root cause:** `git init` создаёт ветку `master` (или `main` в зависимости от настроек), но первый feature/* был создан немедленно, и работа никогда не вернулась на trunk. Main-ветки не было с начала проекта.

**Impact:** Нет, работа не потеряна. Но git-граф нелинеен, переезд между чатами требует явного создания main.

**Fix:** TZ-065 создал `main` от HEAD 4c6fa28. Все старые feature/* удалены через safe `-d`.

**Prevention rule:** `git init` → немедленно `git commit --allow-empty -m "init"` на main, затем работа только через feature/* → merge → main. Никогда не работать месяцами на feature/* без trunk.

**Related TZ:** TZ-065

---

## INC-009: Encoding mojibake in done.py terminal output (2026-04-29)

**Symptom:** done.py вывел кириллицу как ? в терминале при печати статуса TZ-065. Первоначально интерпретировано как повреждённый файл.

**Root cause:** Windows terminal использует CP1251/CP866. Python stdout на Windows по умолчанию использует locale.getpreferredencoding() (CP1251 на RU-локали). UTF-8 строки в print() → mojibake в терминале.

**Note:** Сам файл docs/HANDOFF_2026-04-29_evening.md был в корректном UTF-8. Проблема была исключительно в терминальном выводе.

**Fix:** done.py: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace') на старте.

**Prevention:**
1. Mojibake в терминале ≠ поврежденный файл. Сначала проверить байты файла.
2. Skill encoding_safety — явный UTF-8 во всех write-операциях.
3. Никогда не перекодировать файл без диагностики байт первым шагом.

**Related TZ:** TZ-066

---

## INC-010: Acceptance leniency on partial TZ closure (2026-04-29)

**Symptom:** TZ-068 closed by architect Claude with 9/10 components done. Pre-commit hook (component 6) absent from FILES CHANGED. Architect suggested "don't block the rest of the acceptance for it" — partial TZ treated as closed.

**Root cause:** Soft acceptance creep. Architect applied informal "minor gap" judgement instead of binary pass/fail rule. Silent debt: missing component forgotten, next session starts with weaker invariants than declared.

**Failure mode:** Skill `state_first_protocol` works top-level (Claude doesn't analyze on stale state). But Claude can still soften acceptance one level down — allow Code to close TZ with gaps. Defense in depth fails at architect layer.

**Fix:** Added binary acceptance rule to PROJECT_RULES.md §acceptance: TZ is not closed until all components pass. No phrases like "minor gap", "fix later", "don't block for the rest". Exception only when operator explicitly descopes a component by name.

**Recovery:** Caught in chat. Addendum TZ-068+TZ-PORTFOLIO-PATH issued as single Code pass. Commit blocked until both pass acceptance.

**Prevention rule:** TZ acceptance is binary. Any missing component = TZ back to Code. Zero exceptions without explicit operator descope phrase.

**Related TZ:** TZ-068 addendum

---

## INC-011: Architect issued git/script commands to operator (2026-04-29)

**Symptom:** Across TZ-068 finalization, architect Claude repeatedly ended responses with operator-directed commands: `git commit -m "..."`, `git add ...`, `git reset HEAD ...`, `python scripts/state_snapshot.py`. Operator had stated that Code owns all C:\bot7\ operations.

**Root cause:** Role boundary not encoded as a skill. Under time pressure (22:00 deadline) and eager to close TZ, architect dropped the boundary and defaulted to imperative command style.

**Impact:** Operator had to manually execute staged git operations instead of issuing a mini-TZ to Code. Time lost; operator friction increased.

**Fix:** Skill `operator_role_boundary` created (.claude/skills/operator_role_boundary.md). Forbidden phrases and recovery rule now explicit.

**Prevention rule:** Any architect output containing `run ...`, `execute ...`, `git add ...` directed at operator = violation. Rewrite as mini-TZ for Code before sending.

**Related TZ:** TZ-SKILL-OPERATOR-BOUNDARY