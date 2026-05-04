# Operator Monitoring — POSITION_CHANGE dedup wrapper (24h period)

**Status:** PRODUCTION WIRE-UP (TZ-G, 2026-05-05)
**Scope:** ONE event type (POSITION_CHANGE) wrapped with `services.telegram.dedup_layer.DedupLayer`. All other Telegram emitters unaffected.

## What's running now

Inside `DecisionLogAlertWorker` (the worker that emits Telegram messages from `state/decision_log/events.jsonl`):

1. Existing signature-based dedup (`_is_duplicate_recent`) runs first — unchanged.
2. NEW: For events of type `POSITION_CHANGE`, a `DedupLayer` second-stage check runs.
3. Layer config (frozen for v1):
   - `cooldown_sec = 300` — 5 minutes between emits per (event_type, bot_id) key
   - `value_delta_min = 0.05` — net BTC position must change by ≥0.05 BTC since last emit to re-emit
   - `cluster_enabled = False`
4. Other event types (PNL_EVENT, BOUNDARY_BREACH, PNL_EXTREME, etc.) **bypass the new layer** and only go through the original signature check.

## Feature flag

Environment variable: `DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE`
- `1` (default) → layer ON
- `0` → layer disabled, behavior reverts to pre-TZ-G state

To disable without restarting: set the env var to `0` and restart the worker process. State accumulates in `data/telegram/dedup_state.json`.

## Counters surfaced

The worker tracks per-emitter:
- `emitted` — sent to Telegram successfully
- `suppressed_layer` — blocked by the new layer (cooldown or state-Δ)
- `suppressed_signature` — blocked by the existing signature dedup (existed pre-TZ-G)

Read via `worker.dedup_metrics()` — returns `{"POSITION_CHANGE": {emitted, suppressed_layer, suppressed_signature}, "layer_enabled_position_change": bool}`.

## 24h monitoring checklist (operator)

Confirm during the next 24h:

- [ ] **POSITION_CHANGE alerts still arrive in Telegram.** They should not stop completely; the layer's job is to thin the stream, not silence it. Expect 1-2 per active trading hour with significant position movement.
- [ ] **No duplicates within 5 min** for the same bot at same position size. (Pre-TZ-G this could happen if the signature changed but state was effectively the same.)
- [ ] **Position changes ≥0.05 BTC always emit** (after cooldown expires). 0.05 BTC = ~$4k notional at $80k BTC — material enough to inform.
- [ ] **Per-bot independence** — TEST_1 and TEST_2 emit independently (no cross-suppression between bots).

## Rollback procedure

If POSITION_CHANGE alerts behave wrong (silent, duplicate, or operator wants the previous behavior back):

1. Set `DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE=0` in env.
2. Restart the worker process.
3. Layer state file `data/telegram/dedup_state.json` can be safely deleted — it'll regenerate when the layer is re-enabled.
4. No data loss — events.jsonl is the source of truth and is unaffected.

## Why only POSITION_CHANGE in v1

Per `docs/RESEARCH/DEDUP_DRY_RUN_2026-05-04.md`:
- POSITION_CHANGE: 10.6% suppression on 4-day production sample = HEALTHY band
- BOUNDARY_BREACH: 95.0% TOO AGGRESSIVE — needs cluster collapse first
- PNL_EVENT: 88.6% HIGH — needs threshold tuning ($200 → $400-500)
- PNL_EXTREME: 99.2% TOO AGGRESSIVE — operator decides scope first

POSITION_CHANGE is the only event type whose default config the dry-run validated. The other types are deferred to future TZs after threshold-tuning iterations.

## Next-block prerequisite

After 24h of operator-confirmed correct behavior, the next dedup wire-up TZ can move on to BOUNDARY_BREACH (with cluster collapse enabled per `services/telegram/dedup_layer.py:DedupConfig.cluster_enabled=True`). Until then, only POSITION_CHANGE is wrapped.
