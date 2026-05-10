"""Tests for paper_trader confirmation gate (2026-05-10)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.paper_trader.loop import (
    CONFIRMATION_DRIFT_PCT,
    CONFIRMATION_LAG_MIN,
    CONFIRMATION_TIMEOUT_MIN,
    _check_confirmation,
)


def _entry(side: str, entry: float, age_min: float) -> dict:
    detected = datetime.now(timezone.utc) - timedelta(minutes=age_min)
    return {
        "detected_at": detected.isoformat(),
        "side": side,
        "entry": entry,
        "pair": "BTCUSDT",
    }


def test_long_too_young_waits():
    e = _entry("long", 80000, age_min=5)  # < 10 min lag
    state, _ = _check_confirmation(e, 80100, datetime.now(timezone.utc))
    assert state == "wait"


def test_long_drift_triggers_ready():
    e = _entry("long", 80000, age_min=12)
    cur = 80000 * (1 + (CONFIRMATION_DRIFT_PCT + 0.05) / 100)  # +0.15% > 0.1%
    state, reason = _check_confirmation(e, cur, datetime.now(timezone.utc))
    assert state == "ready"
    assert "drift" in reason


def test_long_no_drift_waits():
    e = _entry("long", 80000, age_min=12)
    cur = 80000 * (1 + 0.05 / 100)  # +0.05% < 0.1%
    state, _ = _check_confirmation(e, cur, datetime.now(timezone.utc))
    assert state == "wait"


def test_long_timeout_cancels():
    e = _entry("long", 80000, age_min=CONFIRMATION_TIMEOUT_MIN + 5)
    cur = 80000 * (1 + 0.05 / 100)  # tiny drift
    state, reason = _check_confirmation(e, cur, datetime.now(timezone.utc))
    assert state == "cancel"
    assert "timeout" in reason


def test_short_drift_down_triggers_ready():
    e = _entry("short", 80000, age_min=12)
    cur = 80000 * (1 - (CONFIRMATION_DRIFT_PCT + 0.05) / 100)  # -0.15%
    state, _ = _check_confirmation(e, cur, datetime.now(timezone.utc))
    assert state == "ready"


def test_short_drift_up_waits():
    e = _entry("short", 80000, age_min=12)
    cur = 80000 * (1 + 0.05 / 100)  # price went UP, wrong direction for SHORT
    state, _ = _check_confirmation(e, cur, datetime.now(timezone.utc))
    assert state == "wait"


def test_bad_side_cancels():
    e = _entry("invalid", 80000, age_min=12)
    state, reason = _check_confirmation(e, 80100, datetime.now(timezone.utc))
    assert state == "cancel"
    assert "side" in reason


def test_bad_entry_cancels():
    e = _entry("long", 0, age_min=12)
    state, reason = _check_confirmation(e, 80100, datetime.now(timezone.utc))
    assert state == "cancel"
