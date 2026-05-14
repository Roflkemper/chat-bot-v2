"""Unit tests for ProtectionAlerts — 10 тестов."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.protection_alerts import ProtectionAlerts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pa(**overrides) -> ProtectionAlerts:
    """Build a ProtectionAlerts with default thresholds, no real files needed."""
    pa = ProtectionAlerts.__new__(ProtectionAlerts)
    # defaults matching protection_alerts.yaml
    pa._enabled   = True
    pa._dry_run   = True
    pa._bfm_warn  = 1.5;  pa._bfm_crit = 2.5;  pa._bfm_extr = 4.0; pa._bfm_db = 30
    pa._ps_warn   = -150; pa._ps_crit  = -300;  pa._ps_extr  = -500
    pa._ps_minpos = 2000; pa._ps_db    = 15
    pa._ld_crit   = 15.0; pa._ld_emer  = 10.0;  pa._ld_db    = 5
    pa._debounce  = {}
    for k, v in overrides.items():
        setattr(pa, k, v)
    return pa


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# BTC_FAST_MOVE
# ---------------------------------------------------------------------------

def test_btc_fast_move_warning_triggered():
    pa = _make_pa()
    pa._1h_change = lambda: (1.6, 76000.0, 77216.0)  # +1.6% → WARNING
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    async def go():
        await pa._check_btc_fast_move()
    _run(go())
    assert sent, "WARNING must fire"
    assert "WARNING" in sent[0]


def test_btc_fast_move_critical_triggered():
    pa = _make_pa()
    pa._1h_change = lambda: (3.1, 76000.0, 78356.0)
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_btc_fast_move())
    assert "CRITICAL" in sent[0]


def test_btc_fast_move_extreme_triggered():
    pa = _make_pa()
    pa._1h_change = lambda: (5.0, 76000.0, 79800.0)
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_btc_fast_move())
    assert "EXTREME" in sent[0]


def test_btc_fast_move_no_trigger_below_threshold():
    pa = _make_pa()
    pa._1h_change = lambda: (0.8, 76000.0, 76608.0)  # +0.8% — below warning
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_btc_fast_move())
    assert not sent, "Should not fire below threshold"


def test_btc_fast_move_negative_move_triggers():
    pa = _make_pa()
    pa._1h_change = lambda: (-2.8, 79000.0, 76788.0)  # −2.8% → CRITICAL
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_btc_fast_move())
    assert "CRITICAL" in sent[0]


# ---------------------------------------------------------------------------
# POSITION_STRESS
# ---------------------------------------------------------------------------

def test_position_stress_critical():
    pa = _make_pa()
    pa._current_price = lambda: 80000.0
    # current_profit = -0.004 BTC → -0.004 * 80000 = -320 USD → CRITICAL
    pa._bot_snapshots = lambda: {
        "TEST_1": {"current_profit": "-0.004", "position": "12000", "average_price": "76000", "liquidation_price": "95000"}
    }
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_position_stress())
    assert sent
    assert "CRITICAL" in sent[0]
    assert "TEST_1" in sent[0]


def test_position_stress_extreme():
    pa = _make_pa()
    pa._current_price = lambda: 80000.0
    # -0.007 BTC * 80000 = -560 USD → EXTREME
    pa._bot_snapshots = lambda: {
        "TEST_2": {"current_profit": "-0.007", "position": "12000", "average_price": "73000", "liquidation_price": "0"}
    }
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_position_stress())
    assert "EXTREME" in sent[0]


def test_position_stress_warning_skipped_small_position():
    pa = _make_pa()
    pa._current_price = lambda: 80000.0
    # -0.002 BTC * 80000 = -160 USD → WARNING level, but position=500 < min_position_usd=2000
    pa._bot_snapshots = lambda: {
        "TINY_BOT": {"current_profit": "-0.002", "position": "500", "average_price": "79000", "liquidation_price": "0"}
    }
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_position_stress())
    assert not sent, "WARNING must be skipped for small positions"


# ---------------------------------------------------------------------------
# LIQ_DANGER
# ---------------------------------------------------------------------------

def test_liq_danger_critical():
    pa = _make_pa()
    # current=78000, liq=88000 → dist=12.8% → CRITICAL (< 15%)
    pa._current_price = lambda: 78000.0
    pa._bot_snapshots = lambda: {
        "TEST_3": {"liquidation_price": "88000", "position": "-12000"}
    }
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_liq_danger())
    assert sent
    assert "CRITICAL" in sent[0]
    assert "TEST_3" in sent[0]


def test_liq_danger_emergency():
    pa = _make_pa()
    # current=78000, liq=85000 → dist=8.97% → EMERGENCY (< 10%)
    pa._current_price = lambda: 78000.0
    pa._bot_snapshots = lambda: {
        "TEST_4": {"liquidation_price": "85000", "position": "-12000"}
    }
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_liq_danger())
    assert "EMERGENCY" in sent[0]


# ---------------------------------------------------------------------------
# Debounce
# ---------------------------------------------------------------------------

def test_debounce_suppresses_repeated_alert():
    pa = _make_pa(_bfm_db=30)
    pa._1h_change = lambda: (2.0, 76000.0, 77520.0)
    sent = []
    pa._emit = AsyncMock(side_effect=lambda t: sent.append(t))

    _run(pa._check_btc_fast_move())
    _run(pa._check_btc_fast_move())  # second call — должен быть подавлен
    assert len(sent) == 1, "Debounce must suppress the second alert within window"
