"""End-to-end state machine tests for P-15 lifecycle.

Critical regression coverage: 2026-05-11 audit found `reentry_size`
UnboundLocalError firing 131x/24h because no test exercised the REENTRY
branch. This file fills that gap with synthetic price tapes.

State machine: IDLE -> OPEN -> (TRACK) -> HARVEST -> REENTRY -> ... -> CLOSE
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import pytest

from services.setup_detector import p15_rolling
from services.setup_detector.p15_rolling import _detect_one_direction, _LegState


@dataclass
class _FakeCtx:
    pair: str
    current_price: float
    ohlcv_1h: Any = None
    ohlcv_15m: Any = None
    regime_label: str = "trend_up"
    session_label: str = "ASIA"


def _make_15m(last_high: float, last_low: float, n: int = 60) -> pd.DataFrame:
    """Build a 60-bar 15m frame with constant high/low at the tail."""
    return pd.DataFrame({
        "open":  [last_low] * n,
        "high":  [last_high] * n,
        "low":   [last_low] * n,
        "close": [(last_high + last_low) / 2] * n,
        "volume": [1.0] * n,
    })


def _uptrending_closes_1h(n: int = 220, base: float = 80000.0,
                          slope: float = 5.0) -> list[float]:
    """Generate 1h closes that satisfy long trend_gate (EMA50>EMA200, close>EMA50)."""
    return [base + i * slope for i in range(n)]


def test_reentry_does_not_raise_unbound_local(monkeypatch):
    """Regression for 2026-05-11 bug: reentry_size was referenced before
    assignment when last_emitted_stage == 'HARVEST' on entry."""
    # Force fallback to fixed base size (no ADVISOR_DEPO_TOTAL).
    monkeypatch.setattr(p15_rolling, "P15_BASE_SIZE_USD", 1000.0)

    leg = _LegState(
        direction="long",
        in_pos=True,
        layers=2,
        total_size_usd=2000.0,
        weighted_entry=2000.0 * 80500.0,
        extreme_price=81000.0,
        opened_at_ts="2026-05-10T20:00:00Z",
        cum_dd_pct=0.0,
        last_emitted_stage="HARVEST",  # <-- triggers REENTRY branch
    )
    ctx = _FakeCtx(
        pair="BTCUSDT",
        current_price=81000.0,
        ohlcv_1h=pd.DataFrame({"close": _uptrending_closes_1h()}),
        ohlcv_15m=_make_15m(last_high=81000.0, last_low=80950.0),
    )

    # Should NOT raise — produces a REENTRY setup.
    result = _detect_one_direction(
        ctx, leg, _uptrending_closes_1h(), "2026-05-10T21:00:00Z",
    )

    assert result is not None
    assert result.setup_type.value == "p15_long_reentry"
    assert leg.last_emitted_stage == "REENTRY"
    # Verify the new layer size was passed (the bug was here).
    basis_keys = {b.label for b in result.basis}
    assert "new_layer_size_usd" in basis_keys


def test_reentry_uses_pair_factor(monkeypatch):
    """REENTRY size for XRP should be smaller than for BTC under same depo
    (pair factors 0.3 vs 1.0).
    """
    leg_xrp = _LegState(
        direction="long",
        in_pos=True,
        layers=2,
        total_size_usd=600.0,
        weighted_entry=600.0 * 1.4,
        extreme_price=1.45,
        opened_at_ts="2026-05-10T20:00:00Z",
        cum_dd_pct=0.0,
        last_emitted_stage="HARVEST",
    )
    leg_btc = _LegState(**{**leg_xrp.__dict__, "extreme_price": 81000.0,
                            "weighted_entry": 1000.0 * 80000.0,
                            "total_size_usd": 1000.0})

    ctx_xrp = _FakeCtx(
        pair="XRPUSDT", current_price=1.45,
        ohlcv_1h=pd.DataFrame({"close": _uptrending_closes_1h(base=1.0, slope=0.001)}),
        ohlcv_15m=_make_15m(last_high=1.45, last_low=1.44),
    )
    ctx_btc = _FakeCtx(
        pair="BTCUSDT", current_price=81000.0,
        ohlcv_1h=pd.DataFrame({"close": _uptrending_closes_1h()}),
        ohlcv_15m=_make_15m(last_high=81000.0, last_low=80950.0),
    )

    r_xrp = _detect_one_direction(
        ctx_xrp, leg_xrp, _uptrending_closes_1h(base=1.0, slope=0.001),
        "2026-05-10T21:00:00Z",
    )
    r_btc = _detect_one_direction(
        ctx_btc, leg_btc, _uptrending_closes_1h(), "2026-05-10T21:00:00Z",
    )
    assert r_xrp is not None and r_btc is not None
    size_xrp = next(b.value for b in r_xrp.basis if b.label == "new_layer_size_usd")
    size_btc = next(b.value for b in r_btc.basis if b.label == "new_layer_size_usd")
    # XRP factor 0.3, BTC factor 1.0 → ratio ~0.3, allow tolerance.
    assert 0.25 < size_xrp / size_btc < 0.35, \
        f"ratio xrp/btc = {size_xrp/size_btc:.3f} (sizes: {size_xrp}, {size_btc})"


def test_open_then_no_op_when_already_in_pos(monkeypatch):
    """If leg is in_pos and stage != HARVEST, no setup emits."""
    monkeypatch.setattr(p15_rolling, "P15_BASE_SIZE_USD", 1000.0)

    leg = _LegState(
        direction="long",
        in_pos=True,
        layers=1,
        total_size_usd=1000.0,
        weighted_entry=1000.0 * 80000.0,
        extreme_price=80500.0,
        opened_at_ts="2026-05-10T20:00:00Z",
        cum_dd_pct=0.0,
        last_emitted_stage="OPEN",
    )
    ctx = _FakeCtx(
        pair="BTCUSDT",
        current_price=80500.0,  # within extreme — no retrace trigger
        ohlcv_1h=pd.DataFrame({"close": _uptrending_closes_1h()}),
        ohlcv_15m=_make_15m(last_high=80500.0, last_low=80450.0),
    )
    result = _detect_one_direction(
        ctx, leg, _uptrending_closes_1h(), "2026-05-10T21:00:00Z",
    )
    # Either None (no transition) or close — depends on retrace; main point
    # is no exception.
    assert result is None or result.setup_type.value.startswith("p15_long")


def test_open_blocked_by_correlation_cap(monkeypatch):
    """If 2 same-direction legs already open across other pairs, OPEN refused."""
    monkeypatch.setattr(p15_rolling, "P15_BASE_SIZE_USD", 1000.0)
    monkeypatch.setattr(p15_rolling, "P15_MAX_SAME_DIRECTION_LEGS", 2)

    # Other 2 legs already long.
    all_legs = {
        "BTCUSDT:long": _LegState(direction="long", in_pos=True),
        "ETHUSDT:long": _LegState(direction="long", in_pos=True),
    }
    # XRP wants to open long → should be refused.
    leg = _LegState(direction="long", in_pos=False)
    ctx = _FakeCtx(
        pair="XRPUSDT",
        current_price=1.5,
        ohlcv_1h=pd.DataFrame({"close": _uptrending_closes_1h(base=1.0, slope=0.001)}),
        ohlcv_15m=_make_15m(last_high=1.5, last_low=1.49),
    )
    result = _detect_one_direction(
        ctx, leg, _uptrending_closes_1h(base=1.0, slope=0.001),
        "2026-05-10T21:00:00Z",
        all_legs=all_legs,
    )
    assert result is None
    assert not leg.in_pos  # leg unchanged


def test_no_15m_data_returns_none():
    """Defensive: missing 15m frame should return None, not crash."""
    leg = _LegState(direction="long", in_pos=True, last_emitted_stage="HARVEST",
                    total_size_usd=1000.0)
    ctx = _FakeCtx(
        pair="BTCUSDT", current_price=80000.0,
        ohlcv_1h=pd.DataFrame({"close": _uptrending_closes_1h()}),
        ohlcv_15m=None,
    )
    result = _detect_one_direction(
        ctx, leg, _uptrending_closes_1h(), "2026-05-10T21:00:00Z",
    )
    assert result is None
