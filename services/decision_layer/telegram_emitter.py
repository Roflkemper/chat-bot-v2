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

# Rule IDs we DO push. Excludes CAP-DIAG (observability noise) and any
# rule whose payload represents an internal cooldown / diagnostic.
ALLOWED_PUSH_RULES = frozenset({
    "M-1", "M-2", "M-3", "M-4", "M-5",
    "R-1", "R-2", "R-3", "R-4",
    "P-1", "P-2",
    "D-1", "D-2", "D-3", "D-4",
})

POLL_INTERVAL_SEC = 60


def _read_last_seen() -> str:
    if not LAST_SEEN_PATH.exists():
        return ""
    try:
        data = json.loads(LAST_SEEN_PATH.read_text(encoding="utf-8"))
        return str(data.get("last_ts", ""))
    except Exception:
        return ""


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
        "R-1": "📈", "R-2": "🔄", "R-3": "⚠️", "R-4": "📊",
        "P-1": "💰", "P-2": "🎯",
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

    while not stop_event.is_set():
        try:
            new_events = _read_decisions_since(last_seen)
            for e in new_events:
                rule_id = e.get("rule_id", "")
                severity = e.get("severity", "INFO")
                # Push only PRIMARY from allowed rules. INFO is observability.
                if severity != "PRIMARY":
                    continue
                if rule_id not in ALLOWED_PUSH_RULES:
                    continue
                try:
                    send_fn(_format_decision(e))
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
