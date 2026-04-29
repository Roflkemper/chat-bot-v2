# Incident Report — Missing Docs (TZ-055)

**Date:** 2026-04-29  
**Severity:** P0 — торговая документация  
**Resolved:** YES (восстановлено из stash@{2}^3)

---

## Что пропало

| Файл | Статус | Восстановлен |
|---|---|---|
| docs/PLAYBOOK.md | MISSING (untracked, wiped) | YES |
| docs/GINAREA_MECHANICS.md | MISSING (untracked, wiped) | YES |
| docs/HANDOFF_2026-04-29.md | MISSING (untracked, wiped) | YES |
| docs/NEXT_CHAT_PROMPT.md | MISSING (untracked, wiped) | YES |
| docs/CLEANUP_GUIDE.md | MISSING (untracked, wiped) | YES |

Всегда существовавшие и нетронутые:  
- docs/MASTER.md — was `??` at start, committed in TZ-053a  
- docs/SESSION_LOG.md — was `??` at start, committed in TZ-053a  
- docs/OPPORTUNITY_MAP_v1.md — was `??` at start, committed in TZ-053a  

---

## Root cause

Файлы были **НИКОГДА не закоммичены в git** — всегда untracked (`??`).

Wipe event: `git clean -fdx -e .venv` выполненный в рамках **TZ-044** (backtest state isolation,
`stash@{2}` датирован 2026-04-29 00:03:23 — это moment последнего stash ДО clean).

Подтверждение: `git show stash@{2}^3:docs/PLAYBOOK.md` → файл существовал в untracked snapshot
стеша, значит был на диске на 2026-04-29 00:03, потом уничтожен git clean.

**`git log --all --diff-filter=D`** не показал удалений — потому что файлы никогда не были в commits.
Dangling trees: 0 (gc.pruneExpire уже прогнан — объекты из TZ-049 восстановления были pruned).

---

## Recovery path

```
git show "stash@{2}^3:docs/PLAYBOOK.md" > docs/PLAYBOOK.md
git show "stash@{2}^3:docs/GINAREA_MECHANICS.md" > docs/GINAREA_MECHANICS.md
git show "stash@{2}^3:docs/HANDOFF_2026-04-29.md" > docs/HANDOFF_2026-04-29.md
git show "stash@{2}^3:docs/NEXT_CHAT_PROMPT.md" > docs/NEXT_CHAT_PROMPT.md
git show "stash@{2}^3:docs/CLEANUP_GUIDE.md" > docs/CLEANUP_GUIDE.md
```

---

## Protection applied

Все критические docs теперь **tracked в git** (TZ-055 commit).  
Pre-commit hook установлен: `.git/hooks/pre-commit` — блокирует commit если любой из 5 критических docs отсутствует.  
`.gitignore` содержит `!docs/PLAYBOOK.md` etc. (негативные паттерны) чтобы предотвратить исключение.

---

## Preventive rule (добавить в MASTER §0 anti-косяки)

К26: `git clean -fdx` УНИЧТОЖАЕТ все untracked файлы. Перед выполнением — обязательный `git stash --include-untracked`. Критические docs ДОЛЖНЫ быть tracked (не `??`).
