---
name: context_handoff
description: Generates and maintains structured handoff documents so the next Claude session starts with full project context. Prevents session-boundary knowledge loss (INC-012, INC-013, INC-014).
type: skill
---

# Skill: context_handoff

## Trigger

Apply ALWAYS when ANY of:
- End of session (≥3 TZs closed, or operator signals "на сегодня всё")
- Operator asks "сгенерируй handoff" / "обнови контекст" / "/handoff"
- New chat session starts — read docs/CONTEXT/ FIRST
- Phase transition (Phase N → Phase N+1)
- Critical finding that invalidates prior research

## Three-layer document structure

| Layer | File | Update frequency | Purpose |
|---|---|---|---|
| 1 (Static) | `docs/CONTEXT/PROJECT_CONTEXT.md` | Rare — when fundamental understanding changes | GinArea mechanics, strategy, project goals, phase map |
| 2 (Dynamic) | `docs/CONTEXT/STATE_CURRENT.md` | End of each session | Current phases, calibration numbers, open TZs, blockers |
| 3 (Transient) | `docs/CONTEXT/SESSION_DELTA_YYYY-MM-DD.md` | Once per session | TZs closed today, key findings, decisions made |

## When starting a new session — DO THIS FIRST

```
Read docs/CONTEXT/PROJECT_CONTEXT.md
Read docs/CONTEXT/STATE_CURRENT.md
Read docs/CONTEXT/ latest SESSION_DELTA_*.md
```

Then confirm in ≤5 lines:
1. Main project goal
2. Current phase status + top blocker
3. Top-3 open TZs
4. Latest calibration K numbers
5. First action you'll take

## When ending a session — DO THIS

### Step 1: Update STATE_CURRENT.md

In `docs/CONTEXT/STATE_CURRENT.md`:
- §1: update phase progress
- §2: add completed TZs at top of list
- §3: update calibration numbers if changed
- §4: update open TZ list
- §5: update operator pending actions
- §6 Changelog: add one line `YYYY-MM-DD | what changed`

### Step 2: Create SESSION_DELTA

Create `docs/CONTEXT/SESSION_DELTA_YYYY-MM-DD.md` with:
- TZs closed this session (table: TZ, finding, files)
- Key findings (numbered list, ≤10 items)
- Decisions made (what we will / will not do)
- Not changed (intentional)
- Next session priorities (≤5 items)

### Step 3: Update dashboard data

After updating STATE_CURRENT.md and QUEUE.md, update `state/engine_status.json` with:
- `bugs_fixed` / `bugs_detected` — реальные числа из текущих TZ
- `k_short`, `k_long` — если перекалибровка была
- `last_updated` — сегодняшняя дата ISO

Then rebuild dashboard state:
```bash
python -c "from services.dashboard.state_builder import build_and_save_state; build_and_save_state()"
```

Output: `docs/STATE/dashboard_state.json` (читается браузером через HTTP server).

### Step 4: Generate HANDOFF

```bash
python tools/handoff.py generate --preview
```

Output: `docs/CONTEXT/HANDOFF_YYYY-MM-DD.md`

### Step 5: Validate (optional but recommended)

```bash
python tools/handoff.py validate
```

### Step 6: Commit

```bash
git add docs/CONTEXT/ docs/STATE/ state/engine_status.json
git commit -m "docs: handoff YYYY-MM-DD + state update"
```

## CLI reference

```bash
python tools/handoff.py generate               # generate today's HANDOFF
python tools/handoff.py generate --preview     # generate + print first 50 lines
python tools/handoff.py validate               # consistency checks
python tools/handoff.py update-state           # print instructions for manual update
```

## Telegram command

`/handoff` — generates HANDOFF and sends as file to operator chat.

## What NOT to do

- Do NOT replace MASTER.md, PLAYBOOK.md, QUEUE.md — они source of truth
- Do NOT auto-update STATE_CURRENT without reviewing changes first
- Do NOT paste PROJECT_CONTEXT.md unchanged if it's stale (check against STATE_CURRENT dates)
- Do NOT skip SESSION_DELTA — it's the most valuable layer for the next session

## Key project facts (always true, don't need STATE_CURRENT to verify)

- **HARD BAN:** P-5, P-8, P-10 — никогда не предлагать
- **Phase awareness:** TZ для Phase 2/3 не нарезаются пока Phase 1 не closed
- **K_LONG TD-dependent** — structural, не баг
- **Indicator gate = разовая проверка** — один раз на цикл, сброс при full-close
- **Два контракта:** SHORT = Linear USDT-M, LONG = Inverse COIN-M
- **Trader-first filter:** каждый TZ должен (а)/(б)/(в)

## Why this skill exists

INC-012 (2026-04-29): После context exhaustion новый чат не знал:
- cascade.py = известный дубликат (не реактивировать)
- 34 модуля в _recovery/restored/ ждут review
- Специфическое поведение OKX liquidation API

INC-013, INC-014 (2026-04-30): architectural amnesia — создание дублей существующих модулей
из-за отсутствия project_inventory_first проверки.

Этот skill + docs/CONTEXT/ layer = системное решение проблемы.
