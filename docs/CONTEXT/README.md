# docs/CONTEXT — Context Handoff System

Three-layer document structure for passing full project context between Claude sessions without knowledge loss.

## Files

| File | Layer | Update frequency |
|---|---|---|
| `PROJECT_CONTEXT.md` | 1 — Static | Only when fundamental understanding changes |
| `STATE_CURRENT.md` | 2 — Dynamic | End of each session |
| `SESSION_DELTA_YYYY-MM-DD.md` | 3 — Transient | Once per session |
| `HANDOFF_YYYY-MM-DD.md` | Generated | On demand via CLI |

## CLI usage

```bash
# Generate today's HANDOFF (combines all 3 layers)
python tools/handoff.py generate

# Generate with preview (first 50 lines)
python tools/handoff.py generate --preview

# Generate for a specific date / path
python tools/handoff.py generate --date 2026-05-03
python tools/handoff.py generate --output /tmp/test_handoff.md

# Check consistency of context docs
python tools/handoff.py validate

# Print instructions for updating STATE_CURRENT.md manually
python tools/handoff.py update-state
```

## Telegram

```
/handoff
```

Generates HANDOFF and sends it as a file to the operator chat.

## Starting a new session

1. Paste `docs/CONTEXT/HANDOFF_YYYY-MM-DD.md` into a new Claude chat.
2. Claude responds in ≤5 lines: goal / phase status / top-3 TZs / K numbers / first action.

## Ending a session

```bash
# 1. Update STATE_CURRENT.md (run for instructions)
python tools/handoff.py update-state

# 2. Create SESSION_DELTA (use latest as template)
cp docs/CONTEXT/SESSION_DELTA_2026-05-02.md docs/CONTEXT/SESSION_DELTA_$(date +%F).md
# Edit it with today's TZs, findings, decisions

# 3. Generate HANDOFF
python tools/handoff.py generate --preview

# 4. Validate
python tools/handoff.py validate

# 5. Commit
git add docs/CONTEXT/
git commit -m "docs: handoff $(date +%F) + state update"
```

## Consistency checks

`validate` checks:
- PROJECT_CONTEXT.md exists and contains `indicator`, `HARD BAN`, `Phase roadmap`
- STATE_CURRENT.md exists and contains `Paper Journal`, `K_SHORT`
- STATE_CURRENT.md last modified ≤ 7 days ago
- SESSION_DELTA for today exists
- QUEUE.md and ROADMAP.md exist
