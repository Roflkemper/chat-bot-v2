# TZ-MORNING-BRIEF-MULTITRACK-ADAPT

**Track:** P6 (infrastructure debt / tooling)
**Priority:** P3 (low — обходной путь работает: paste roadmap + state directly в MAIN)
**Estimated:** 1.5–2h
**Opened:** 2026-05-05

## Pain
`scripts/main_morning_brief.py` ожидает на входе `WEEK_*.md` с per-day секциями ("Day 1 / Mon 2026-05-04 → ETAP X / TZ-list"). После перехода на `MULTI_TRACK_ROADMAP.md` (track-based, не day-based) скрипт генерирует пустой шаблон с `[No goal defined for this date]` и `_No TZs defined for this date in the week plan._`.

Текущий обходной путь: оператор пастит roadmap + STATE_CURRENT в MAIN напрямую, MAIN собирает MAIN_BRIEF без участия скрипта. Работает, но breaks weekly cycle automation.

## Hard deliverables
- [ ] D1: скрипт принимает `--roadmap` flag (alternative to `--week`) и парсит `MULTI_TRACK_ROADMAP.md`
- [ ] D2: dispatch logic — какие TZ из каких треков идут на конкретный день. Минимальная реализация: читать `STATE_CURRENT.md §4 OPEN TZs` (текущая priority queue) + `PENDING_TZ.md` (статусы) + брать N следующих OPEN TZ по dependency order
- [ ] D3: SPRINT output содержит non-empty `TODAY'S GOAL`, `TODAY'S TZs` table с est, `HARD DELIVERABLES` placeholder
- [ ] D4: тест на `tests/test_main_morning_brief.py` — fixture multi-track roadmap → non-empty sprint
- [ ] D5: backward compat — старый `--week WEEK_*.md` режим не сломан (если кому-то нужен)

## Anti-drift
- DO NOT перепридумывать roadmap structure под нужды скрипта (roadmap source of truth)
- DO NOT пихать ML-логику в dispatch (приоритеты явные в STATE_CURRENT §4 — следовать им)
- DO NOT добавлять CLI options "пока я тут" — только `--roadmap` flag

## Acceptance
Команда `python scripts/main_morning_brief.py --day 2026-05-XX --roadmap docs/PLANS/MULTI_TRACK_ROADMAP.md` пишет `SPRINT_2026-05-XX.md` с реальным goal+TZ list, и MAIN coordinator принимает его без ругани на пустоту.
