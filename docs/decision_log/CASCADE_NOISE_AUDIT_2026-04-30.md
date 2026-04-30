# CASCADE NOISE AUDIT — 2026-04-30

**TZ:** TZ-DECISION-LOG-V2-CASCADE-NOISE-ROOT-CAUSE  
**Status:** INVESTIGATION COMPLETE — ready for fix

---

## Observed Behaviour

At **16:26 UTC** on 2026-04-30, `app_runner` was restarted.  
Within ~90 seconds, **~30 Telegram messages** were delivered to the operator channel in a burst, all referencing historical events (BOUNDARY_BREACH, PARAM_CHANGE, PNL_EXTREME) that had already occurred hours before the restart.

Restart command: `python -m bot7 restart app_runner tracker collectors`

---

## Inventory

| Source | Count |
|---|---|
| Total events in `state/events.jsonl` at restart | **161** |
| Events with severity WARNING | **115** |
| Events with severity CRITICAL | **10** |
| Total WARNING + CRITICAL | **125** |
| Events with severity INFO / NOTICE | 36 |

Breakdown by type (WARNING+CRITICAL only):

| event_type | count |
|---|---|
| BOUNDARY_BREACH | 90 |
| PARAM_CHANGE | 21 |
| PNL_EXTREME | 10 |
| POSITION_CHANGE | 2 |
| PNL_EVENT | 2 |

The detector itself (`event_detector.py`) generated **0 new events** at 16:26 — cold start protection and dedup mechanisms implemented in TZ-DECISION-LOG-V2-NOISE-REDUCTION worked correctly. The flood came entirely from the **separate Telegram alert worker thread**, not from the detector.

---

## Root Cause Hypotheses

### H1 — `_seen_event_ids` in-memory only [HIGH confidence — confirmed root cause]

**Location:** `services/telegram_runtime.py`, class `DecisionLogAlertWorker.__init__` (line 450)

```python
self._seen_event_ids: set[str] = set()  # ← empty on every startup
```

`_read_new_events()` iterates ALL events in the JSONL file on every call.  
Any event whose `event_id` is NOT in `_seen_event_ids` is treated as new.  
On restart, the set is empty → all 125 WARNING/CRITICAL events from history are "new" → sent to Telegram until Telegram rate-limit kicks in (~30 delivered).

**Confirmed:** The worker thread is separate from `decision_log_loop` (detector). The detector's cold start guard (`if not state: return []`) only protects against generating NEW events — it has no effect on the worker reading the JSONL that already exists.

### H2 — No startup silence period [MEDIUM confidence — contributing factor]

The worker thread starts `poll_interval_sec=15` — it fires its first `_read_new_events()` call within 15 seconds of startup, before any operator can intervene. If there were a configurable cold start delay (e.g., 60s), the JSONL could be seeded first.

This is a defence-in-depth issue rather than the primary cause. H1 is the direct cause.

### H3 — Severity gate applied after, not before, history scan [LOW confidence — not a root cause]

The severity filter `if event.severity in (WARNING, CRITICAL)` is applied inside `_read_new_events()` at the per-event level — it does suppress INFO events. However, 125 of the 161 events were WARNING/CRITICAL, so this gate only removed 36 events from the flood, not the flood itself.

This is correct behaviour for live detection. The bug is that historical events should never re-enter the gate after restart.

---

## Fix Plan

**Fix-C (primary):** Pre-seed `_seen_event_ids` from the existing JSONL on startup.

Add `_load_seen_ids()` to `DecisionLogAlertWorker`:
- Read all existing `event_id` values from JSONL
- Return as `set[str]`
- Call in `__init__`: `self._seen_event_ids = self._load_seen_ids()`

Effect: on restart, worker immediately knows about all 161 existing events → `_read_new_events()` returns only events added AFTER the restart.

**Regression tests required:**
- `test_cold_start_no_cascade`: worker initialised with pre-existing JSONL → `_read_new_events()` returns empty list
- `test_new_event_after_seed`: after seeding, a newly appended event IS returned by `_read_new_events()`
- `test_seed_handles_missing_file`: missing JSONL → returns empty set (no crash)

---

## Deploy Verification

After deploying the fix:

```
python -m bot7 restart app_runner
```

Expected: 0 Telegram messages in the first 60 seconds after restart (operator should monitor Telegram and the bot log for `decision_log_alert_worker.start` + `seed_seen_ids loaded N` log lines).

Acceptance: `seed_seen_ids loaded 161` (or current count) appears in log, zero historical events re-sent.
