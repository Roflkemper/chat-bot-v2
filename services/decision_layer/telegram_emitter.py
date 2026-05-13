"""Decision Layer Telegram emitter.

Tails state/decision_log/decisions.jsonl, pushes new PRIMARY events to
Telegram. Filters out diagnostics (CAP-DIAG) — those are observability,
not action. Dedupe via state file (last seen ts).

Per DECISION_LAYER_v1 §2 the layer was supposed to gain Telegram emission
in TZ-DECISION-LAYER-TELEGRAM (step 4). That TZ never landed; this module
implements the missing surface.

Live as of 2026-05-08:
  decisions.jsonl has 5879 events all-time. PRIMARY events:
    D-2 (data stale): 19
    R-3 (regime instability): 16
    D-4 (margin data stale): 13
    R-2 (regime change): 9
    P-2 (price proximity): 9
    M-3 (margin critical): 8
    M-4 (margin emergency): 7
    P-1 (price near level): 2
    M-5 (margin spike): 1
  → 84 actionable PRIMARY in entire history operator never saw.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DECISIONS_PATH = Path("state/decision_log/decisions.jsonl")
LAST_SEEN_PATH = Path("state/decision_log/_telegram_last_seen.json")
PER_RULE_LAST_PUSH_PATH = Path("state/decision_log/_telegram_per_rule_last.json")

# Rule IDs we DO push. Excludes CAP-DIAG (observability noise) and any
# rule whose payload represents an internal cooldown / diagnostic.
ALLOWED_PUSH_RULES = frozenset({
    "M-1", "M-2", "M-3", "M-4", "M-5",
    "R-1", "R-2", "R-3", "R-4", "R-2+3",  # R-2+3 = merged regime_change + instability
    "P-1", "P-2",
    "T-1", "T-2", "T-3",
    "D-1", "D-2", "D-3", "D-4",
})

POLL_INTERVAL_SEC = 60

# Per-rule cooldown — even if the layer fires the same rule every 5 minutes,
# we push to Telegram at most once per cooldown window. Prevents alert
# fatigue. Operator can still see all events in /advise's DL block and
# state/decision_log/decisions.jsonl audit log.
PER_RULE_COOLDOWN_SEC: dict[str, int] = {
    "M-1": 1800,   # margin safe → margin warn: rare structural event, 30min
    "M-2": 1800,   # margin elevated: 30min
    "M-3": 3600,   # margin critical: hourly (was every 5min — spam)
    "M-4": 3600,   # margin emergency: hourly
    "M-5": 600,    # margin spike: 10min (rare structural, want fast)
    "R-1":  900,   # regime stable: 15min
    "R-2":  600,   # regime change: 10min (real edge — short cooldown)
    "R-3":  900,   # regime instability: 15min
    "R-2+3": 900,  # merged regime change+instability: 15min
    "R-4":  900,
    "P-1":  900,   # price near critical level: 15min
    "P-2":  900,
    "D-1": 1800,   # snapshots stale: 30min
    "D-2": 1800,
    "D-3": 1800,   # engine bugs: 30min
    "D-4": 1800,   # margin data stale: 30min
    "T-1": 3600,   # MTF coherent: hourly (informational)
    "T-2": 1800,   # MTF minor lag: 30min
    "T-3": 1800,   # MTF major disagreement: 30min (per design §4.4)
}
DEFAULT_COOLDOWN_SEC = 600   # fallback for unlisted rules


def _read_last_seen() -> str:
    if not LAST_SEEN_PATH.exists():
        return ""
    try:
        data = json.loads(LAST_SEEN_PATH.read_text(encoding="utf-8"))
        return str(data.get("last_ts", ""))
    except Exception:
        return ""


def _read_per_rule_last() -> dict[str, str]:
    """Per-rule last-push timestamps (ISO8601). Used for cooldown gate."""
    if not PER_RULE_LAST_PUSH_PATH.exists():
        return {}
    try:
        return json.loads(PER_RULE_LAST_PUSH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_per_rule_last(state: dict[str, str]) -> None:
    try:
        PER_RULE_LAST_PUSH_PATH.parent.mkdir(parents=True, exist_ok=True)
        PER_RULE_LAST_PUSH_PATH.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        logger.exception("decision_layer.telegram_emitter.per_rule_state_write_failed")


def _is_in_cooldown(rule_id: str, now: datetime, last_push_iso: str | None) -> bool:
    """True if this rule was pushed less than its cooldown ago."""
    if not last_push_iso:
        return False
    try:
        last = datetime.fromisoformat(last_push_iso.replace("Z", "+00:00"))
    except Exception:
        return False
    cooldown = PER_RULE_COOLDOWN_SEC.get(rule_id, DEFAULT_COOLDOWN_SEC)
    return (now - last).total_seconds() < cooldown


def _write_last_seen(ts: str) -> None:
    try:
        LAST_SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_SEEN_PATH.write_text(json.dumps({"last_ts": ts}), encoding="utf-8")
    except Exception:
        logger.exception("decision_layer.telegram_emitter.last_seen_write_failed")


def _read_decisions_since(last_ts: str) -> list[dict]:
    """Return decisions whose ts > last_ts, ordered by ts ascending."""
    if not DECISIONS_PATH.exists():
        return []
    out = []
    try:
        for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            ts = e.get("ts", "")
            if last_ts and ts <= last_ts:
                continue
            out.append(e)
    except OSError:
        return []
    out.sort(key=lambda e: e.get("ts", ""))
    return out


def _merge_r2_r3(events: list[dict], window_sec: int = 60) -> list[dict]:
    """Слить R-2 (regime_change) и R-3 (regime_instability), если они пришли в
    одном временном окне. Возвращает список с заменой пары на синтетический
    rule_id="R-2+3".

    Когда оркестратор фиксирует переход режима, decision_layer часто
    эмитит и R-2 (сам переход) и R-3 (нестабильность гистерезиса).
    Два TG-сообщения подряд про одно событие = шум.
    """
    if not events:
        return events

    def _parse(iso: str) -> datetime | None:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None

    skip: set[int] = set()
    out: list[dict] = []
    for i, e in enumerate(events):
        if i in skip:
            continue
        if e.get("rule_id") == "R-2":
            dt_a = _parse(e.get("ts", ""))
            r3_idx: int | None = None
            if dt_a is not None:
                for j in range(i + 1, min(i + 5, len(events))):
                    if j in skip:
                        continue
                    if events[j].get("rule_id") != "R-3":
                        continue
                    dt_b = _parse(events[j].get("ts", ""))
                    if dt_b is None:
                        continue
                    if abs((dt_b - dt_a).total_seconds()) <= window_sec:
                        r3_idx = j
                        break
            if r3_idx is not None:
                merged = dict(e)
                merged["rule_id"] = "R-2+3"
                stab = (events[r3_idx].get("payload") or {}).get("stability")
                p2 = (merged.get("payload") or {}).copy()
                if stab is not None:
                    p2["stability"] = stab
                merged["payload"] = p2
                if stab is not None:
                    merged["recommendation"] = (
                        (merged.get("recommendation", "") or "")
                        + f" Stability={stab:.2f} — hysteresis weakening."
                    )
                out.append(merged)
                skip.add(r3_idx)
                continue
        out.append(e)
    return out


def _format_decision(e: dict) -> str:
    """Render a decision event as a Telegram message."""
    rule_id = e.get("rule_id", "?")
    severity = e.get("severity", "INFO")
    event_type = e.get("event_type", "?")
    payload = e.get("payload", {})
    rec = e.get("recommendation", "")
    ts = e.get("ts", "")

    icon = {
        "M-1": "🟢", "M-2": "🟡", "M-3": "🟠", "M-4": "🔴", "M-5": "⚡",
        "R-1": "📈", "R-2": "🔄", "R-3": "⚠️", "R-4": "📊", "R-2+3": "🔄⚠️",
        "P-1": "💰", "P-2": "🎯",
        "T-1": "🟢", "T-2": "🟡", "T-3": "⚠️",
        "D-1": "📉", "D-2": "🕒", "D-3": "🐛", "D-4": "⏰",
    }.get(rule_id, "🔔")

    lines = [
        f"{icon} DECISION LAYER {severity} — {rule_id}",
        f"event: {event_type}",
    ]
    # Pretty-print key payload fields
    if payload:
        for k, v in payload.items():
            if isinstance(v, float):
                v = f"{v:.4g}"
            lines.append(f"  {k}: {v}")
    if rec:
        lines.append("")
        lines.append(f"💡 {rec}")
    lines.append("")
    lines.append(f"ts: {ts}")
    return "\n".join(lines)


async def decision_layer_telegram_loop(
    stop_event: asyncio.Event,
    *,
    send_fn: Optional[Callable[[str], None]] = None,
    interval_sec: float = POLL_INTERVAL_SEC,
) -> None:
    """Poll decisions.jsonl every `interval_sec`, push new PRIMARY events.

    First-run behaviour: don't blast operator with the entire backlog.
    Initialize last_ts to NOW on first call so only fresh events are pushed.
    """
    if send_fn is None:
        logger.info("decision_layer.telegram_emitter.disabled (no send_fn)")
        return

    last_seen = _read_last_seen()
    if not last_seen:
        # Cold start: skip backlog, only push events that fire from now on.
        last_seen = datetime.now(timezone.utc).isoformat()
        _write_last_seen(last_seen)
        logger.info("decision_layer.telegram_emitter.cold_start last_seen=%s", last_seen)

    logger.info("decision_layer.telegram_emitter.start last_seen=%s", last_seen)

    # Margin filter: M-3/M-4 fire on margin_coefficient >= 0.85, but with
    # large position the operator typically runs at coef ~0.95-1.00 by design,
    # while distance_to_liquidation stays comfortable (>15%). Pushing every
    # 5min is spam. Suppress when dist_to_liq is comfortable.
    SAFE_DIST_TO_LIQ_PCT = 15.0

    per_rule_last = _read_per_rule_last()

    while not stop_event.is_set():
        try:
            new_events = _read_decisions_since(last_seen)
            now = datetime.now(timezone.utc)
            # Merge R-2 (regime_change) + R-3 (regime_instability) that come
            # together (within 60s). Observed 13.05 03:12 — both fired in the
            # same minute, producing two near-duplicate TG messages.
            new_events = _merge_r2_r3(new_events)
            for e in new_events:
                rule_id = e.get("rule_id", "")
                severity = e.get("severity", "INFO")
                # Push only PRIMARY from allowed rules. INFO is observability.
                if severity != "PRIMARY":
                    continue
                if rule_id not in ALLOWED_PUSH_RULES:
                    continue
                # Margin-rule filter: skip if liquidation distance is safe.
                if rule_id in ("M-3", "M-4"):
                    payload = e.get("payload", {}) or {}
                    dist = payload.get("distance_to_liquidation_pct")
                    if dist is not None and dist >= SAFE_DIST_TO_LIQ_PCT:
                        continue
                # Per-rule cooldown — even if the layer fires the same rule
                # every poll, push to Telegram at most once per cooldown window.
                if _is_in_cooldown(rule_id, now, per_rule_last.get(rule_id)):
                    continue
                try:
                    send_fn(_format_decision(e))
                    per_rule_last[rule_id] = now.isoformat()
                    _write_per_rule_last(per_rule_last)
                    logger.info(
                        "decision_layer.telegram_emitter.pushed rule=%s event=%s",
                        rule_id, e.get("event_type"),
                    )
                except Exception:
                    logger.exception(
                        "decision_layer.telegram_emitter.send_failed rule=%s", rule_id
                    )

            # Advance last_seen even if no events, so we don't re-scan the file.
            if new_events:
                last_seen = new_events[-1].get("ts", last_seen)
                _write_last_seen(last_seen)
        except Exception:
            logger.exception("decision_layer.telegram_emitter.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
