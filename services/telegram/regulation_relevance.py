"""Regulation-relevance filter for Telegram VERBOSE channel.

P4 of TZ-DASHBOARD-AND-TELEGRAM-USABILITY-PHASE-1.

Some VERBOSE-channel events are still noisy even after dedup. This module
gates the VERBOSE pipe further: forward only if the event indicates a state
that materially intersects REGULATION_v0_1_1 §3 activation matrix or the
operator's active cleanup work.

Scope:
  - This module is consulted ONLY for events bound for the VERBOSE channel.
  - PRIMARY-channel events bypass this filter (they always forward to
    subscribed PRIMARY recipients).

Decision policy for VERBOSE candidates:
  FORWARD if any of:
    1. Event type is REGIME_CHANGE              — admissibility matrix changes.
    2. Event type is LIQ_CASCADE                — risk event, never suppress.
    3. Event is LEVEL_BREAK near a critical level (operator-supplied env list).
    4. Event meta marks `affects_cleanup=True`  — emitter-side opt-in flag.
  SUPPRESS otherwise (e.g. raw RSI extremes that are not paired with a
  regime/level/cleanup signal).

Configuration (env, all optional):
  TELEGRAM_REGULATION_FILTER_ENABLED       ("1" / "0", default "0")
  TELEGRAM_FILTER_CRITICAL_LEVELS_USD      comma-separated USD prices
  TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD   default 300

When TELEGRAM_REGULATION_FILTER_ENABLED=0, this module is a no-op: every
candidate forwards. The default is OFF so existing behavior is preserved
during Phase 1 validation.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Mapping

logger = logging.getLogger(__name__)


# Always-forward event types (regulation/risk-relevant regardless of channel).
_ALWAYS_FORWARD = frozenset({"LIQ_CASCADE", "REGIME_CHANGE"})


@dataclass(frozen=True)
class FilterDecision:
    forward: bool
    reason: str


def _enabled() -> bool:
    return bool(int(os.environ.get("TELEGRAM_REGULATION_FILTER_ENABLED", "0")))


def _critical_levels_usd() -> list[float]:
    raw = os.environ.get("TELEGRAM_FILTER_CRITICAL_LEVELS_USD", "")
    out: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            continue
    return out


def _critical_proximity_usd() -> float:
    try:
        return float(os.environ.get("TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD", "300"))
    except ValueError:
        return 300.0


def evaluate_signal_row(row: Mapping[str, object]) -> FilterDecision:
    """Apply the filter to a signals.csv row (SignalAlertWorker stream).

    The row shape is the same as services.telegram_runtime.SignalAlertWorker
    expects: dict with keys 'signal_type' and 'details_json' (JSON-encoded
    string). Pure function — no side effects.
    """
    if not _enabled():
        return FilterDecision(forward=True, reason="filter disabled (env)")
    sig = str(row.get("signal_type") or "")
    if sig in _ALWAYS_FORWARD:
        return FilterDecision(forward=True, reason=f"always-forward: {sig}")
    if sig == "LEVEL_BREAK":
        try:
            details = json.loads(str(row.get("details_json") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            details = {}
        level = details.get("level")
        try:
            level_f = float(level) if level is not None else None
        except (TypeError, ValueError):
            level_f = None
        if level_f is None:
            return FilterDecision(forward=False, reason="LEVEL_BREAK with unparseable level")
        levels = _critical_levels_usd()
        if not levels:
            return FilterDecision(forward=False, reason="LEVEL_BREAK suppressed: no critical levels configured")
        proximity = _critical_proximity_usd()
        for crit in levels:
            if abs(level_f - crit) <= proximity:
                return FilterDecision(
                    forward=True,
                    reason=f"LEVEL_BREAK within {proximity:.0f} USD of critical level {crit:.0f}",
                )
        return FilterDecision(
            forward=False,
            reason=f"LEVEL_BREAK at {level_f:.0f} not within {proximity:.0f} USD of any critical level",
        )
    if sig == "RSI_EXTREME":
        return FilterDecision(forward=False, reason="RSI_EXTREME suppressed: raw indicator without regulation impact")
    return FilterDecision(forward=False, reason=f"signal_type={sig!r} not in regulation-relevance allowlist")


def evaluate_decision_log_event(event_type: str, payload: Mapping[str, object] | None,
                                affects_cleanup: bool = False) -> FilterDecision:
    """Apply the filter to a decision_log event (DecisionLogAlertWorker stream).

    Used for VERBOSE-channel candidates only. PRIMARY-channel events bypass.
    """
    if not _enabled():
        return FilterDecision(forward=True, reason="filter disabled (env)")
    if event_type in _ALWAYS_FORWARD:
        return FilterDecision(forward=True, reason=f"always-forward: {event_type}")
    if affects_cleanup:
        return FilterDecision(forward=True, reason="emitter marked affects_cleanup=True")
    if event_type == "LEVEL_BREAK":
        # Decision-log payload may carry a `level` or `price` field
        p = dict(payload or {})
        level_f: float | None = None
        for key in ("level", "price", "price_btc"):
            v = p.get(key)
            try:
                level_f = float(v) if v is not None else None
                if level_f is not None:
                    break
            except (TypeError, ValueError):
                continue
        if level_f is None:
            return FilterDecision(forward=False, reason="LEVEL_BREAK without parseable level/price")
        levels = _critical_levels_usd()
        if not levels:
            return FilterDecision(forward=False, reason="LEVEL_BREAK suppressed: no critical levels configured")
        proximity = _critical_proximity_usd()
        for crit in levels:
            if abs(level_f - crit) <= proximity:
                return FilterDecision(
                    forward=True,
                    reason=f"LEVEL_BREAK within {proximity:.0f} USD of critical level {crit:.0f}",
                )
        return FilterDecision(
            forward=False,
            reason=f"LEVEL_BREAK at {level_f:.0f} not within {proximity:.0f} USD of any critical level",
        )
    return FilterDecision(forward=False, reason=f"event_type={event_type!r} not regulation-relevant")
