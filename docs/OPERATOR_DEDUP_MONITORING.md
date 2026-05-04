# Operator Monitoring — Telegram dedup wrappers (24h period)

**Status:** PRODUCTION WIRE-UP (`POSITION_CHANGE` from TZ-G, `BOUNDARY_BREACH` from TZ-J)
**Scope:** Two event types are wrapped with `services.telegram.dedup_layer.DedupLayer`: `POSITION_CHANGE` and `BOUNDARY_BREACH`. Other Telegram emitters remain on signature dedup only.

## What's running now

Inside `DecisionLogAlertWorker` (the worker that emits Telegram messages from `state/decision_log/events.jsonl`):

1. Existing signature-based dedup (`_is_duplicate_recent`) runs first — unchanged.
2. For events of type `POSITION_CHANGE`, a `DedupLayer` second-stage check runs.
3. For events of type `BOUNDARY_BREACH`, a separate `DedupLayer` second-stage check runs after signature dedup.
4. Other event types (`PNL_EVENT`, `PNL_EXTREME`, etc.) bypass the new layer and only go through the original signature check.

## Feature flags

Environment variable: `DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE`
- `1` (default) → layer ON
- `0` → layer disabled, behavior reverts to pre-TZ-G state

Environment variable: `DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH`
- `1` (default) → layer ON
- `0` → layer disabled, behavior reverts to signature-dedup-only path for `BOUNDARY_BREACH`

To disable either wrapper: set the env var to `0` and restart the worker process. State accumulates in `data/telegram/dedup_state.json`.

## Frozen configs

### POSITION_CHANGE

- `cooldown_sec = 300`
- `value_delta_min = 0.05`
- `cluster_enabled = False`

### BOUNDARY_BREACH

- `cooldown_sec = 600`
- `value_delta_min = 0`
- `cluster_enabled = False`
- Per-bot isolation key: `str(bot_id)`

## Counters surfaced

The worker tracks per-emitter:
- `emitted` — sent to Telegram successfully
- `suppressed_layer` — blocked by the new layer
- `suppressed_signature` — blocked by the existing signature dedup

Read via `worker.dedup_metrics()`.

## 24h monitoring checklist — POSITION_CHANGE

- [ ] `POSITION_CHANGE` alerts still arrive in Telegram. They should not stop completely; the layer's job is to thin the stream, not silence it.
- [ ] No duplicates within 5 min for the same bot at same position size.
- [ ] Position changes ≥0.05 BTC emit after cooldown expiry.
- [ ] TEST_1 and TEST_2 remain independent with no cross-suppression.

## 24h monitoring checklist — BOUNDARY_BREACH

- [ ] `BOUNDARY_BREACH` alerts still arrive in Telegram during real LEVEL_BREAK cascades. Expect meaningful reduction, not disappearance.
- [ ] Repeated breaches from the same bot inside 10 minutes are suppressed even if top/bottom boundary differs.
- [ ] Different bots stay isolated: `TEST_1` boundary spam must not suppress `TEST_2`.
- [ ] Observed suppression is directionally near the dry-run baseline: around half of cascade spam removed, not 90%+ silence.

Note: `BOUNDARY_BREACH` tuned baseline is `49.1%` suppression on the 4-day sample, so operator should expect roughly half of raw cascade noise to disappear.

## Rollback procedure

If `POSITION_CHANGE` alerts behave wrong:

1. Set `DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE=0` in env.
2. Restart the worker process.

If `BOUNDARY_BREACH` alerts behave wrong:

1. Set `DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH=0` in env.
2. Restart the worker process.

Shared note:

1. `data/telegram/dedup_state.json` can be safely deleted — it regenerates when the layer is re-enabled.
2. No data loss — `events.jsonl` remains the source of truth and is unaffected.

## Current rollout boundary

- Wired now: `POSITION_CHANGE`, `BOUNDARY_BREACH`
- Not wired yet: `PNL_EVENT`, `PNL_EXTREME`
- Cluster collapse remains disabled in production v1 for all wired emitters
