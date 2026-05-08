# validate_tz — TZ Proposal Validator

Checks a proposed TZ against `ROADMAP.md` and `QUEUE.md` before adding it to the queue.

## Usage

```bash
# From inline text
python tools/validate_tz.py --text "TZ-MY-FEATURE: implement advise telegram push"

# From file
python tools/validate_tz.py --file path/to/tz_proposal.md

# From stdin
cat tz_proposal.md | python tools/validate_tz.py

# JSON output (for scripting)
python tools/validate_tz.py --text "..." --json

# Custom roadmap/queue paths
python tools/validate_tz.py --text "..." --roadmap docs/STATE/ROADMAP.md --queue docs/STATE/QUEUE.md
```

## Verdicts

| Verdict | Meaning |
|---|---|
| `APPROVED` | All checks pass. Safe to add to QUEUE. |
| `REVIEW_NEEDED` | Warnings found (phase not active, possible duplicate, missing file refs). Operator should review. |
| `REJECTED` | Blocking errors found (Phase 3 pre-requisites not met, hard dependency missing). Defer or mark as IDEA. |

## Checks performed

### 1. Phase alignment
Keywords in the TZ text are matched against phase-specific keyword lists:
- **Phase 0**: infra, collector, tracker, state, ohlcv, scheduler, test, debt…
- **Phase 0.5**: reconcile, engine, calibrat, sim, engine_fix, instop…
- **Phase 1**: paper journal, weekly report, advise signals…
- **Phase 2**: advise_v2, telegram, push notification, h10, optimize, widen…
- **Phase 3**: autonomous, full_auto, bot_management, тактический…

Currently active phases (in_progress): **0, 0.5, 1**
- TZ aligned with Phase 0/0.5/1 → APPROVED (phase check)
- TZ aligned with Phase 2 → REVIEW_NEEDED (planned, not active)
- TZ aligned with Phase 3 → REJECTED (pre-requisites unmet)

### 2. QUEUE overlap
- Checks if the TZ ID (e.g. `TZ-ENGINE-FIX-RESOLUTION`) already exists in QUEUE.md
- Checks if any distinctive title keyword (≥6 chars) appears in QUEUE.md
- Overlap → REVIEW_NEEDED warning

### 3. Dependency check
- Extracts file references from TZ text (backtick-quoted `.py/.json/.yaml` paths)
- Checks if referenced files exist in repo root
- Missing file → warning (not error, as TZ may reference files to be created)

### 4. Phase prerequisites
- Phase 2 TZ: warns if Phase 0/0.5/1 are not confirmed in_progress
- Phase 3 TZ: lists all pre-requisites from ROADMAP (Reconcile GREEN, 30+ days Phase 2, GinArea API automation)

## Exit codes

- `0` — APPROVED
- `1` — REVIEW_NEEDED or REJECTED
- `2` — usage error (no input provided)

## Tests

```bash
pytest tests/tools/test_validate_tz.py -v
```

## Examples

**APPROVED** (Phase 0 TZ):
```
$ python tools/validate_tz.py --text "TZ-OHLCV-RELOAD: reload ohlcv ingest collector state tracker"
VERDICT: APPROVED
Phase detected: Фаза 0 — Infrastructure & гигиена
INFO:
  • Phase phase0 is currently active (in_progress) — TZ is in scope
```

**REVIEW_NEEDED** (Phase 2 TZ, not yet active):
```
$ python tools/validate_tz.py --text "TZ-ADVISE-V3: /advise telegram push notification high-confidence"
VERDICT: REVIEW_NEEDED
Phase detected: Фаза 2 — Operator Augmentation
WARNINGS (review needed):
  ⚠ TZ appears to be Phase 2 (Operator Augmentation) work. Phase 2 is 'planned' — not yet active.
```

**REJECTED** (Phase 3 TZ):
```
$ python tools/validate_tz.py --text "TZ-BOT-AUTO: autonomous авто-торговля full_auto bot_management тактический"
VERDICT: REJECTED
Phase detected: Фаза 3 — Tactical Bot Management
ERRORS (blocking):
  ✗ TZ appears to be Phase 3 work. Phase 3 pre-requisites not met: Reconcile GREEN, 30+ days Phase 2, GinArea API automation.
```
