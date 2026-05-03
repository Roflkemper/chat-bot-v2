# WEEK PLAN TEMPLATE
# Копировать как WEEK_YYYY-MM-DD_to_YYYY-MM-DD.md
# Заполнять каждое воскресенье вечером / понедельник утром

---

## WEEK HEADER

**Period:** YYYY-MM-DD (Mon) → YYYY-MM-DD (Sun)
**Primary goal:** [одна главная цель недели]
**Phase focus:** [Phase X — что именно продвигаем]
**Operator availability:** [full / partial / weekends only]

---

## CAPACITY

| Day | Slots | Notes |
|-----|-------|-------|
| Mon | 2 | — |
| Tue | 2 | — |
| Wed | 2 | — |
| Thu | 2 | — |
| Fri | 2 | — |
| Sat | 1 | buffer |
| Sun | 1 | review + next plan |

**Total slots:** 11 (adjust per operator availability)
**Buffer reserved:** 20% = ~2 slots for unplanned

---

## DAILY PLAN

### DAY 1 — Monday YYYY-MM-DD

**Goal:** [что должно быть сделано к концу дня]

| # | TZ_ID | Description | Est. | Dependency |
|---|-------|-------------|------|------------|
| 1 | TZ-XXXX | … | 2h | none |
| 2 | TZ-YYYY | … | 1.5h | TZ-XXXX |

**Hard deliverables:**
- [ ] D1: [конкретный artifact — файл, парсинг, commit]
- [ ] D2: [метрика — "Brier ≤0.22", "45 tests green", etc.]

**Verify commands:**
```
python -m pytest core/tests/test_XXX.py -v
python scripts/handoff_verify.py verify-pending
```

**Drift guard:** If [condition], stop and notify operator.

---

### DAY 2 — Tuesday YYYY-MM-DD

**Goal:** [цель дня]

| # | TZ_ID | Description | Est. | Dependency |
|---|-------|-------------|------|------------|
| 1 | TZ-ZZZZ | … | 3h | D1 from Day 1 |

**Hard deliverables:**
- [ ] D1: …

**Verify commands:**
```
python -m pytest …
```

**Gate:** [CP1 / CP2 / CP3 — если checkpoint день]

---

### DAY 3 — Wednesday YYYY-MM-DD

[same structure]

---

### DAY 4 — Thursday YYYY-MM-DD

[same structure]

---

### DAY 5 — Friday YYYY-MM-DD

**Goal:** Wrap week + prepare handoff

**Hard deliverables:**
- [ ] All open TZ committed
- [ ] PENDING_TZ.md updated
- [ ] Handoff snapshot generated
- [ ] Next week plan drafted (rough)

---

### DAY 6 — Saturday (buffer)

**Goal:** Catch overflow from week OR rest

**Rule:** Only work here if Friday hard deliverables not met.

---

### DAY 7 — Sunday (review)

**Goal:** Week retrospective + next week plan

**Review checklist:**
- [ ] All week deliverables achieved?
- [ ] Any drift detected?
- [ ] Calibration numbers changed?
- [ ] Operator decisions pending?

---

## DRIFT TRACKING

| Day | Planned | Actual | Drift? | Root cause |
|-----|---------|--------|--------|------------|
| Mon | … | … | — | — |
| Tue | … | … | — | — |
| Wed | … | … | — | — |
| Thu | … | … | — | — |
| Fri | … | … | — | — |

**Drift patterns this week:**
- [ ] Scope creep (extra work added mid-TZ)
- [ ] Incomplete (TZ started, not finished)
- [ ] Wrong direction (built something not in plan)
- [ ] Dependency miss (didn't check what was needed first)

---

## WEEKLY RETROSPECTIVE

**What worked:**
- …

**What didn't:**
- …

**Process change for next week:**
- …

**Metrics delta:**
| Metric | Week start | Week end | Change |
|--------|-----------|----------|--------|
| Tests passing | N | N+k | +k |
| PENDING_TZ open | N | N-k | -k |
| Paper journal day | N | N+5 | +5 |

---

## REPLAN TRIGGERS

Replanning required (mid-week) if ANY of:
- CP gate fails (Brier > 0.28, tests red, etc.)
- Operator decision reverses direction
- Critical blocker discovered (data missing, API down)
- 2+ days behind on hard deliverables

**Replan action:** Notify operator → generate revised plan → paste in worker chat.
