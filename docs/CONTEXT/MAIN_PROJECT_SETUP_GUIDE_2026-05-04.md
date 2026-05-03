# MAIN PROJECT SETUP GUIDE — 2026-05-04
# Operator: read this tomorrow morning before opening any chat.
# Time required: ~10 min one-time setup, then ~10 min/day.

---

## WHAT YOU'RE SETTING UP

A Claude Project called "bot7 Coordinator" that acts as the strategic brain (MAIN).
MAIN lives in Claude.ai (not Claude Code). It reads what you paste, thinks, and outputs
decisions. It does NOT run scripts or access files — you run scripts, paste results.

**Total daily operator effort: ~10-15 min copy/paste + script runs.**

---

## PART 1 — ONE-TIME SETUP (~10 min, do this tomorrow morning)

### Step 1.1 — Create Claude Project

1. Open claude.ai in browser
2. Left sidebar → **Projects** → **Create New Project**
3. Name: `bot7 Coordinator`
4. Description: `Strategic coordinator for bot7 trading system. Validates daily sprints, detects drift, issues CP verdicts. NOT a worker — operator pastes everything in.`
5. Click **Create**

### Step 1.2 — Upload Project Knowledge (10 files)

In the Project settings → **Knowledge** → **Add content** → upload each file:

```
c:\bot7\docs\PLANS\WEEK_2026-05-04_to_2026-05-10.md
c:\bot7\docs\STATE\PENDING_TZ.md
c:\bot7\docs\CONTEXT\DEPRECATED_PATHS.md
c:\bot7\docs\CONTEXT\DRIFT_HISTORY.md
c:\bot7\docs\STATE\STATE_CURRENT.md
c:\bot7\docs\CONTEXT\HANDOFF_2026-05-03.md
c:\bot7\docs\SPRINTS\SPRINT_TEMPLATE.md
c:\bot7\reports\MAIN_COORDINATOR_USAGE_GUIDE.md
```

Upload them one by one. Wait for each to confirm "processed".

### Step 1.3 — Set Custom Instructions

In Project settings → **Instructions** (or "Custom instructions"):

Copy-paste the ENTIRE contents of:
```
c:\bot7\docs\CONTEXT\MAIN_CHAT_OPENING_PROMPT_2026-05-04.md
```

Click **Save**.

### Step 1.4 — Test the Project

Open a new chat in "bot7 Coordinator" project.
Type: `Confirm you've loaded your instructions. What is this week's mission in 2 sentences?`

Expected response: MAIN confirms regime-conditional calibration, 4 regime models, Brier ≤0.22 target.
If wrong → re-check that custom instructions were saved.

---

## PART 2 — DAILY MORNING ROUTINE (~2-3 min)

### Step 2.1 — Run morning brief script (PowerShell)

```powershell
cd c:\bot7
python scripts/main_morning_brief.py --day 2026-05-04 --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md
```

Output file: `docs\SPRINTS\SPRINT_2026-05-04.md`

### Step 2.2 — Open MAIN chat

Go to claude.ai → Projects → "bot7 Coordinator" → **New chat** (one per day, keep it open all day)

### Step 2.3 — Paste morning brief

Copy the template below, fill in the 2 blanks, paste:

```
--- MORNING BRIEF REQUEST ---
Date: 2026-05-04 (Day 1/7)
SPRINT draft below. Blockers since yesterday: none
New operator decisions: none
---
[paste full contents of docs\SPRINTS\SPRINT_2026-05-04.md here]
```

### Step 2.4 — Get MAIN_BRIEF

MAIN outputs a `=== MAIN BRIEF ===` block.

### Step 2.5 — Open worker session

Open Claude Code (c:\bot7 workspace).
Paste the MAIN_BRIEF as your first message.
Worker starts executing.

---

## PART 3 — CHECKPOINT ROUTINE (~30-60 sec each, 2-3× per day)

Worker will say "CP1 triggered" or similar. It will output a `=== CP SNAPSHOT ===` block.

### Step 3.1

Copy the snapshot from worker chat.

### Step 3.2

Paste into the MAIN chat (same one from morning):
```
--- CP SNAPSHOT ---
[paste snapshot here]
```

### Step 3.3

MAIN outputs `CP[N] VERDICT: GREEN/YELLOW/RED`.

### Step 3.4

Copy verdict. Paste into worker chat.
Worker continues (GREEN/YELLOW) or stops (RED).

---

## PART 4 — EVENING ROUTINE (~5 min)

Worker generates a `=== EOD REPORT ===` block.

### Step 4.1 — Run validation script

```powershell
cd c:\bot7
python scripts/main_evening_validate.py --sprint docs\SPRINTS\SPRINT_2026-05-04.md --no-verify
```

### Step 4.2 — Paste to MAIN

```
--- EVENING REVIEW REQUEST ---
Worker EOD report:
[paste EOD REPORT block from worker]

Script validation output:
[paste output from main_evening_validate.py]
---
```

### Step 4.3 — Get acceptance review

MAIN outputs `=== EOD ACCEPTANCE ===` with PASS/PARTIAL/FAIL and Day N+1 seed.

### Step 4.4 — Optional: apply updates

If MAIN flags week plan changes → edit `docs\PLANS\WEEK_2026-05-04_to_2026-05-10.md` directly.
If simple script actions → run them.

---

## PART 5 — WEEKLY REFRESH (Sunday evening, ~5 min)

Update Project knowledge with fresh files:
- Re-upload `STATE_CURRENT.md` (updated §2, §4)
- Re-upload `PENDING_TZ.md`
- Upload new `WEEK_2026-05-11_to_2026-05-17.md`

MAIN reads fresh knowledge automatically next morning.

---

## PART 6 — TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| MAIN doesn't know about a file | Paste the relevant section directly into chat |
| MAIN lost context mid-week | Continue in same chat — knowledge persists |
| MAIN chat hit context limit | Open new chat in project; knowledge reloads automatically |
| Worker drifted without MAIN noticing | Trigger CP manually: copy worker's last message → paste as CP snapshot |
| Script output is garbled (encoding) | Check PowerShell output; use `> out.txt` redirect and open in editor |
| MAIN gives wrong advice | Paste the specific file it's missing context from |

---

## DAILY TIME BUDGET

| Activity | Time |
|----------|------|
| Run morning script | 30 sec |
| Paste to MAIN, get brief | 1-2 min |
| Open worker, paste brief | 30 sec |
| Per checkpoint (×2-3/day) | 30 sec each |
| Evening: run script + paste | 2-3 min |
| Evening: read acceptance | 1 min |
| **TOTAL** | **~10-15 min/day** |

---

## DAY 1 SHORTCUT (tomorrow morning only)

Day 1 SPRINT is already pre-generated:
```
c:\bot7\docs\SPRINTS\SPRINT_2026-05-04_DRAFT.md
```

Skip Step 2.1 tomorrow — just paste the DRAFT directly.
Still do Steps 2.2-2.5.

---

*Generated by TZ-SESSION-CLOSE-PROPER-HANDOFF-2026-05-03 on 2026-05-03 EOD.*
