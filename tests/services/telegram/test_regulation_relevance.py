"""Tests for services.telegram.regulation_relevance (P4 of TZ-DASHBOARD-AND-TELEGRAM-USABILITY-PHASE-1)."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from services.telegram.regulation_relevance import (
    evaluate_decision_log_event,
    evaluate_signal_row,
)


def _row(signal_type: str, **details) -> dict:
    return {
        "signal_type": signal_type,
        "details_json": json.dumps(details),
    }


# ── Disabled-by-default behavior ────────────────────────────────────────────

def test_filter_disabled_passes_everything_through() -> None:
    """When TELEGRAM_REGULATION_FILTER_ENABLED=0 (default), everything forwards."""
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "0"}, clear=False):
        for sig in ("RSI_EXTREME", "WHATEVER", "LEVEL_BREAK"):
            d = evaluate_signal_row(_row(sig, level=80000))
            assert d.forward is True
            assert "disabled" in d.reason


# ── Always-forward ──────────────────────────────────────────────────────────

def test_liq_cascade_always_forwards_when_enabled() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_signal_row(_row("LIQ_CASCADE"))
        assert d.forward is True
        assert "LIQ_CASCADE" in d.reason


def test_regime_change_always_forwards_when_enabled() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_signal_row(_row("REGIME_CHANGE", from_="RANGE", to_="MARKDOWN"))
        assert d.forward is True


# ── LEVEL_BREAK proximity gate ─────────────────────────────────────────────

def test_level_break_suppressed_when_no_critical_levels_configured() -> None:
    with patch.dict(os.environ, {
        "TELEGRAM_REGULATION_FILTER_ENABLED": "1",
        "TELEGRAM_FILTER_CRITICAL_LEVELS_USD": "",
    }, clear=False):
        d = evaluate_signal_row(_row("LEVEL_BREAK", level=80000, direction="up"))
        assert d.forward is False
        assert "no critical" in d.reason


def test_level_break_forwarded_near_critical_level() -> None:
    with patch.dict(os.environ, {
        "TELEGRAM_REGULATION_FILTER_ENABLED": "1",
        "TELEGRAM_FILTER_CRITICAL_LEVELS_USD": "78779,80000,82400",
        "TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD": "300",
    }, clear=False):
        d = evaluate_signal_row(_row("LEVEL_BREAK", level=79850, direction="up"))
        assert d.forward is True


def test_level_break_suppressed_when_far_from_critical_levels() -> None:
    with patch.dict(os.environ, {
        "TELEGRAM_REGULATION_FILTER_ENABLED": "1",
        "TELEGRAM_FILTER_CRITICAL_LEVELS_USD": "78779,80000,82400",
        "TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD": "300",
    }, clear=False):
        d = evaluate_signal_row(_row("LEVEL_BREAK", level=85000, direction="up"))
        assert d.forward is False


# ── RSI_EXTREME suppression ─────────────────────────────────────────────────

def test_rsi_extreme_suppressed_when_enabled() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_signal_row(_row("RSI_EXTREME", timeframe="1h", rsi=85))
        assert d.forward is False
        assert "RSI_EXTREME" in d.reason


# ── Unknown signals ─────────────────────────────────────────────────────────

def test_unknown_signal_suppressed_when_enabled() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_signal_row(_row("WHATEVER_NEW_THING", x=1))
        assert d.forward is False
        assert "allowlist" in d.reason


# ── Decision-log event surface ──────────────────────────────────────────────

def test_decision_log_disabled_default_forwards() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "0"}, clear=False):
        d = evaluate_decision_log_event("RSI_EXTREME", {"rsi": 85})
        assert d.forward is True


def test_decision_log_regime_change_always_forwards() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_decision_log_event("REGIME_CHANGE", {"from": "RANGE", "to": "MARKDOWN"})
        assert d.forward is True


def test_decision_log_affects_cleanup_forwards() -> None:
    """Emitter-side opt-in flag forces forwarding."""
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_decision_log_event("RSI_EXTREME", {"rsi": 85}, affects_cleanup=True)
        assert d.forward is True
        assert "affects_cleanup" in d.reason


def test_decision_log_level_break_proximity() -> None:
    with patch.dict(os.environ, {
        "TELEGRAM_REGULATION_FILTER_ENABLED": "1",
        "TELEGRAM_FILTER_CRITICAL_LEVELS_USD": "80000",
        "TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD": "300",
    }, clear=False):
        d_near = evaluate_decision_log_event("LEVEL_BREAK", {"price": 79850})
        assert d_near.forward is True
        d_far = evaluate_decision_log_event("LEVEL_BREAK", {"price": 85000})
        assert d_far.forward is False


def test_decision_log_random_event_suppressed() -> None:
    with patch.dict(os.environ, {"TELEGRAM_REGULATION_FILTER_ENABLED": "1"}, clear=False):
        d = evaluate_decision_log_event("PARAM_CHANGE", {"bot_id": "x"})
        assert d.forward is False
        assert "not regulation-relevant" in d.reason
