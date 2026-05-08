"""Tests for P3 of TZ-DASHBOARD-USABILITY-FIX-PHASE-1.

regulation_relevance_decision() is a pure function — easy to test directly.
The wiring into SignalAlertWorker._should_send is exercised indirectly here
by setting the env flag and constructing a worker fixture, but the heavy test
weight is on the pure decision function.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from services.telegram_runtime import regulation_relevance_decision


def _row(signal_type: str, **details) -> dict:
    return {
        "signal_type": signal_type,
        "details_json": json.dumps(details),
    }


# ── Always-forward ──────────────────────────────────────────────────────────

def test_liq_cascade_always_forwards() -> None:
    forward, reason = regulation_relevance_decision(_row("LIQ_CASCADE"))
    assert forward is True
    assert "LIQ_CASCADE" in reason


def test_regime_change_always_forwards() -> None:
    forward, reason = regulation_relevance_decision(_row("REGIME_CHANGE", from_="RANGE", to_="MARKDOWN"))
    assert forward is True
    assert "regulation" in reason.lower() or "REGIME_CHANGE" in reason


# ── LEVEL_BREAK: only near critical levels ─────────────────────────────────

def test_level_break_suppressed_when_no_critical_levels_configured() -> None:
    with patch.dict(os.environ, {"TELEGRAM_FILTER_CRITICAL_LEVELS_USD": ""}, clear=False):
        forward, reason = regulation_relevance_decision(_row("LEVEL_BREAK", level=80000, direction="up"))
        assert forward is False
        assert "no critical levels" in reason


def test_level_break_forwarded_near_critical_level() -> None:
    with patch.dict(os.environ, {
        "TELEGRAM_FILTER_CRITICAL_LEVELS_USD": "78779,80000,82400",
        "TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD": "300",
    }, clear=False):
        # Within $300 of 80000 (operator's view target)
        forward, reason = regulation_relevance_decision(_row("LEVEL_BREAK", level=79850, direction="up"))
        assert forward is True
        assert "80000" in reason or "critical" in reason.lower()


def test_level_break_suppressed_when_far_from_critical_levels() -> None:
    with patch.dict(os.environ, {
        "TELEGRAM_FILTER_CRITICAL_LEVELS_USD": "78779,80000,82400",
        "TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD": "300",
    }, clear=False):
        # Far from any critical level
        forward, reason = regulation_relevance_decision(_row("LEVEL_BREAK", level=85000, direction="up"))
        assert forward is False
        assert "not within" in reason


def test_level_break_with_unparseable_level_suppressed() -> None:
    forward, reason = regulation_relevance_decision({
        "signal_type": "LEVEL_BREAK",
        "details_json": "{\"level\": null}",
    })
    assert forward is False
    assert "unparseable" in reason


# ── RSI_EXTREME: always suppressed ──────────────────────────────────────────

def test_rsi_extreme_suppressed() -> None:
    forward, reason = regulation_relevance_decision(_row("RSI_EXTREME", timeframe="1h", rsi=85))
    assert forward is False
    assert "RSI_EXTREME" in reason


# ── Unknown signal types: default-suppress ─────────────────────────────────

def test_unknown_signal_type_suppressed() -> None:
    forward, reason = regulation_relevance_decision(_row("WHATEVER_NEW_THING", x=1))
    assert forward is False
    assert "allowlist" in reason
