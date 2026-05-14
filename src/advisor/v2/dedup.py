"""Deduplication + lifecycle state machine for advisor recommendations."""
from __future__ import annotations

import time
from dataclasses import dataclass

from .cascade import Recommendation

DEDUP_WINDOW_MIN: int = 30
LIQ_OVERRIDE_DEDUP_MIN: int = 5

_DEFENSIVE_PLAYS: frozenset[str] = frozenset({"P-4"})

# Key: (play_id, symbol) — per-asset dedup (TZ-035)
_state: dict[tuple[str, str], "_Entry"] = {}


@dataclass
class _Entry:
    play_id: str
    symbol: str
    ts: float  # monotonic seconds
    state: str = "proposed"  # "proposed" | "acknowledged" | "expired"


def _key(play_id: str, symbol: str) -> tuple[str, str]:
    return (play_id, symbol)


def _window_s(play_id: str) -> float:
    if play_id in _DEFENSIVE_PLAYS:
        return LIQ_OVERRIDE_DEDUP_MIN * 60.0
    return DEDUP_WINDOW_MIN * 60.0


def is_duplicate(rec: Recommendation) -> bool:
    """Return True if this play+symbol was recently proposed and is still active."""
    entry = _state.get(_key(rec.play_id, rec.symbol))
    if entry is None:
        return False
    age_s = time.monotonic() - entry.ts
    if age_s >= _window_s(rec.play_id):
        entry.state = "expired"
        return False
    return entry.state in ("proposed", "acknowledged")


def record(rec: Recommendation) -> None:
    """Register a new recommendation as 'proposed'."""
    k = _key(rec.play_id, rec.symbol)
    _state[k] = _Entry(play_id=rec.play_id, symbol=rec.symbol, ts=time.monotonic())


def acknowledge(play_id: str, symbol: str = "BTCUSDT") -> None:
    """Mark a play as acknowledged (operator saw it)."""
    k = _key(play_id, symbol)
    if k in _state:
        _state[k].state = "acknowledged"


def get_state(play_id: str, symbol: str = "BTCUSDT") -> str:
    """Return lifecycle state: 'none' | 'proposed' | 'acknowledged' | 'expired'."""
    entry = _state.get(_key(play_id, symbol))
    if entry is None:
        return "none"
    age_s = time.monotonic() - entry.ts
    if age_s >= _window_s(play_id):
        return "expired"
    return entry.state


def clear(play_id: str | None = None, symbol: str | None = None) -> None:
    """Clear dedup state. If both given: clear specific entry. If only play_id: all symbols."""
    if play_id and symbol:
        _state.pop(_key(play_id, symbol), None)
    elif play_id:
        for k in list(_state.keys()):
            if k[0] == play_id:
                _state.pop(k, None)
    else:
        _state.clear()
