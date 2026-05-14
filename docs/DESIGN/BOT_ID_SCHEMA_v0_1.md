# Bot ID Schema — v0.1

**Status:** DRAFT (TZ-BOT-ALIAS-HYGIENE, P6)
**Date:** 2026-05-05
**Track:** P6 (infrastructure debt) — direct enabler for P5 weekly comparison + P8 ensemble coordinator
**Pre-req for:** TZ-WEEKLY-COMPARISON-REPORT, TZ-RGE-DUAL-MODE-DESIGN

## Pain (Finding 3 from Block 6)

`docs/STATE/BOT_INVENTORY.md`: only 3 of 22 GinArea bots have stable aliases (`TEST_1`, `TEST_2`, `КЛОД_ИМПУЛЬС`). All other bots are referenced by:
- numeric GinArea ID (`6399265299`) — stable but opaque
- emoji-laden display name (`🐉GPT🐉% SHORT 1.1%`) — operator-readable but mutable
- informal label parsed from display string (`SHORT_1.1%`, `LONG_B`) — derived, breaks when display changes

**Concrete failure mode:** if paper journal or operator decisions tracker keys on alias, and operator renames a bot mid-week (e.g., adds a 🔥 emoji), all subsequent records detach from prior history.

**Adjacent failure mode:** P8 ensemble coordinator must address bots by stable role names (e.g., "trend SHORT bot"). With current state, the coordinator can't cleanly say "activate the MARKDOWN-trend SHORT" — there's no stable handle for that bot.

## Goal

Two-layer identification:
- **Layer 1 (data key, stable, immutable):** every bot has a stable `bot_uid` that never changes for that bot's lifetime.
- **Layer 2 (display, mutable, operator-friendly):** `alias` and `display_name` continue to exist for UI/Telegram rendering but are NOT used as keys anywhere in code.

Migration must be backward-compatible — old records reference the bot by GinArea numeric ID; the schema maps GinArea ID → `bot_uid` so historical data resolves correctly.

## ID schema

### Format

```
bot_uid = "{platform}:{side}:{symbol}:{seq:03d}"
```

Components:
- **`platform`**: `binance` (only one supported in v0.1; `kraken`, `bybit` deferred)
- **`side`**: `long`, `short`, `spot`, `hedge` (the side the bot trades on, not its current PnL direction)
- **`symbol`**: lowercase asset, e.g. `btcusdt`, `xrpusdt`
- **`seq`**: 3-digit sequence number unique within `(platform, side, symbol)`

### Examples

| GinArea ID | Display | bot_uid |
|------------|---------|---------|
| 6399265299 | `🐉GPT🐉% SHORT 1.1%` | `binance:short:btcusdt:001` |
| 5436680540 | `🐉🐉% SHORT 1%` | `binance:short:btcusdt:002` |
| 5427983401 | `BTC-LONG-B` | `binance:long:btcusdt:001` |
| 5312167170 | `BTC-LONG-C` | `binance:long:btcusdt:002` |
| 4361055038 | `spot btc Новый` | `binance:spot:btcusdt:001` |
| 4826691675 | `💎 XRP ШОРТ 2.5 КЛОД + ЖПТ` | `binance:short:xrpusdt:001` |
| 5196832375 | `🐉GPT🐉TEST 1` | `binance:test:btcusdt:001` |

### Why this format

- **Structured, parseable**: code can ask "is this a SHORT bot on BTC?" via `bot_uid.split(":")` rather than regex on display name.
- **Human-readable**: operator can read `binance:short:btcusdt:001` and know what it means without lookup.
- **Stable across renames**: bot's display name can change to `🔥🔥SHORT 1.1% v2` and `bot_uid` stays the same.
- **Avoids UUID opacity**: UUIDs (`f47ac10b-58cc-...`) are stable but operator-hostile. Sequence numbers within `(platform, side, symbol)` keep cardinality manageable (we'll never have >999 SHORT BTC bots).
- **Migration is deterministic**: GinArea ID → `bot_uid` mapping is stable and stored once.

## Migration policy

### Source of truth

`data/bot_registry.json` — the canonical list. Hand-curated initially, programmatically maintained after.

```json
{
  "version": "v0.1",
  "updated_at": "2026-05-05T18:00:00Z",
  "bots": {
    "binance:short:btcusdt:001": {
      "ginarea_id": "6399265299",
      "display_name": "🐉GPT🐉% SHORT 1.1%",
      "alias_short": "SHORT_1.1%",
      "platform": "binance",
      "side": "short",
      "symbol": "BTCUSDT",
      "first_seen": "2026-04-15T00:00:00Z",
      "status": "running",
      "notes": ""
    },
    ...
  }
}
```

Aliases (`alias_short`) remain present for legacy code paths to read but new code must NOT use them as keys.

### Resolver function

`services/bot_registry/resolver.py` provides:
- `resolve_to_uid(any_handle: str) -> str | None` — accepts ginarea_id, alias, or display_name, returns `bot_uid` or None.
- `get_display(bot_uid: str) -> str` — returns operator-friendly label.
- `list_bots(filter_side: str | None = None) -> list[dict]` — for inventory readers.

This is the only entry point for bot identification anywhere in the codebase. New code calls these helpers; legacy code that reads `ginarea_id` from CSV continues to work.

### Migration steps (idempotent)

1. **Run `scripts/migrate_bot_ids.py --dry-run`** — reads `BOT_INVENTORY.md` + `ginarea_live/snapshots.csv`, prints proposed `bot_registry.json` for review. No writes.
2. **Operator reviews** the proposed registry, edits seq numbers if any conflicts.
3. **Run `scripts/migrate_bot_ids.py --apply`** — writes `data/bot_registry.json`.
4. **Optional:** scan referring records (`state/advise_signals.jsonl`, `data/operator_journal/*.jsonl`, `data/virtual_trader/positions_log.jsonl`) and add a `bot_uid` field where they currently store `bot_id` or `alias`. Old fields stay in place; new field is additive. Rollback = ignore the new field.
5. **Idempotency:** re-running `--apply` on an existing registry doesn't change UIDs (uses GinArea ID match to keep mapping stable). New bots get appended with next available seq number.

### What does NOT change

- **GinArea API integration:** GinArea owns its own bot IDs. Our resolver maps to/from those IDs but doesn't try to push UID into GinArea.
- **User-visible display:** Telegram messages, dashboard, briefs continue to show emoji display names. `bot_uid` only appears in logs and machine-readable state files.
- **Bot configurations / runtime:** no bot config edited, no positions touched, no params changed.

## Test plan (for the impl TZ)

The migration script + resolver should ship with these tests:

1. **UID format:** `re.match(r"^binance:(long|short|spot|hedge|test):[a-z]+:\d{3}$", uid)` for every UID in registry.
2. **Uniqueness:** no two bots share a UID.
3. **GinArea ID mapping is bijective:** each `ginarea_id` maps to exactly one `bot_uid`, and vice versa.
4. **Aliases can collide:** two bots may share an alias (e.g., legacy renames). UID resolves both correctly.
5. **`resolve_to_uid()` accepts**: GinArea ID (numeric string), alias (`SHORT_1.1%`), display_name (with emoji). Returns `None` on unknown handle.
6. **Migration idempotency:** running `--apply` twice produces identical registry.
7. **Backward compat read:** old records with only `bot_id`/`alias` still resolve via `resolve_to_uid()`.
8. **New-bot append:** if a new bot appears in `snapshots.csv` not in registry, `--apply` appends it with next available seq.

## Anti-drift held

- ✅ No GinArea API changes
- ✅ No display name renaming (only adds layer below)
- ✅ No bot configs / runtime state migrated
- ✅ No ML / heuristic for ID assignment — pure structural
- ✅ Schema bounded (4 components, 1 platform in v0.1) — no `tags`/`metadata` creep

## Open questions (1)

1. **For TEST_1/2/3 trio:** are they truly distinct bots or copies of one bot for replay? If copies, they collapse to one UID (`binance:test:btcusdt:001`) with notes. If distinct, three UIDs. **Default in v0.1: three distinct UIDs** (matches what BOT_INVENTORY.md observed — three different GinArea IDs). Operator can collapse later if confirmed copies.

## Acceptance for impl TZ

- `data/bot_registry.json` exists with 22+ entries (one per GinArea ID in current snapshots.csv)
- `services/bot_registry/resolver.py` implements 3 public functions
- `scripts/migrate_bot_ids.py --dry-run` and `--apply` work as described
- 8 tests above pass
- Operator can run `python -c "from services.bot_registry.resolver import resolve_to_uid; print(resolve_to_uid('SHORT_1.1%'))"` and get `binance:short:btcusdt:001`
- BOT_INVENTORY.md gets a "UIDs" column added in next-revision
