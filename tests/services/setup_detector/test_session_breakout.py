"""Tests for session_breakout detector."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pytest

from services.setup_detector.session_breakout import (
    detect_session_breakout,
    _PRIOR_OF_NEW,
)
from services.setup_detector.models import SetupType


@dataclass
class _Ctx:
    pair: str = "BTCUSDT"
    current_price: float = 80000.0
    regime_label: str = "trend_up"
    session_label: str = "london"
    ohlcv_1m: pd.DataFrame = field(default_factory=pd.DataFrame)
    ohlcv_1h: pd.DataFrame = field(default_factory=pd.DataFrame)
    portfolio: object = None
    ict_context: dict = field(default_factory=dict)


def _make_1m(highs: list[float], lows: list[float]) -> pd.DataFrame:
    n = len(highs)
    return pd.DataFrame({
        "open": [(h + l) / 2 for h, l in zip(highs, lows)],
        "high": highs,
        "low": lows,
        "close": [(h + l) / 2 for h, l in zip(highs, lows)],
        "volume": [100.0] * n,
    })


def test_returns_none_when_no_ict_context():
    ctx = _Ctx()
    assert detect_session_breakout(ctx) is None


def test_returns_none_when_session_dead():
    ctx = _Ctx(ict_context={"session_active": "dead", "time_in_session_min": 5})
    assert detect_session_breakout(ctx) is None


def test_returns_none_when_outside_entry_window():
    """time_in_session_min > 30 should not fire."""
    ctx = _Ctx(
        current_price=80000.0,
        ict_context={
            "session_active": "london",
            "time_in_session_min": 45,  # > 30 ENTRY_WINDOW_MIN
            "asia_high": 79500.0,
            "asia_low": 79000.0,
        },
        ohlcv_1m=_make_1m([80000, 80100], [79900, 80000]),
    )
    assert detect_session_breakout(ctx) is None


def test_returns_none_when_prior_session_unknown():
    """Session without prior mapping → None."""
    ctx = _Ctx(
        ict_context={
            "session_active": "weird_unknown",
            "time_in_session_min": 10,
        },
        ohlcv_1m=_make_1m([80000, 80100], [79900, 80000]),
    )
    assert detect_session_breakout(ctx) is None


def test_returns_none_when_prior_high_zero():
    ctx = _Ctx(
        ict_context={
            "session_active": "london",
            "time_in_session_min": 10,
            "asia_high": 0.0,
            "asia_low": 0.0,
        },
        ohlcv_1m=_make_1m([80000, 80100], [79900, 80000]),
    )
    assert detect_session_breakout(ctx) is None


def test_long_signal_when_recent_high_breaks_prior_high():
    """Price.high in current session breaks asia_high → LONG."""
    ctx = _Ctx(
        pair="BTCUSDT",
        current_price=79550.0,
        ict_context={
            "session_active": "london",
            "time_in_session_min": 5,
            "asia_high": 79500.0,
            "asia_low": 79000.0,
        },
        ohlcv_1m=_make_1m(
            highs=[79400, 79450, 79550, 79520, 79480],  # breaks 79500 at idx 2
            lows=[79350, 79400, 79500, 79460, 79420],
        ),
    )
    setup = detect_session_breakout(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_SESSION_BREAKOUT
    assert setup.entry_price == pytest.approx(79550.0)
    # Stop is 0.8% below entry
    assert setup.stop_price < setup.entry_price
    # TP1 is above entry
    assert setup.tp1_price > setup.entry_price
    # RR ~= 1.5
    assert setup.risk_reward == pytest.approx(1.5, rel=0.05)


def test_short_signal_when_recent_low_breaks_prior_low():
    """Price.low in current session breaks asia_low → SHORT."""
    ctx = _Ctx(
        pair="BTCUSDT",
        current_price=78950.0,
        ict_context={
            "session_active": "london",
            "time_in_session_min": 5,
            "asia_high": 79500.0,
            "asia_low": 79000.0,
        },
        ohlcv_1m=_make_1m(
            highs=[79100, 79080, 79050, 79020, 79000],
            lows=[79050, 79020, 78950, 78920, 78890],  # breaks 79000
        ),
    )
    setup = detect_session_breakout(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.SHORT_SESSION_BREAKOUT
    assert setup.stop_price > setup.entry_price
    assert setup.tp1_price < setup.entry_price


def test_returns_none_when_neither_high_nor_low_broken():
    """Price stays within prior session range → no signal."""
    ctx = _Ctx(
        current_price=79250.0,
        ict_context={
            "session_active": "london",
            "time_in_session_min": 10,
            "asia_high": 79500.0,
            "asia_low": 79000.0,
        },
        ohlcv_1m=_make_1m(
            highs=[79300, 79350, 79400, 79380, 79320],  # max 79400 < 79500
            lows=[79100, 79150, 79200, 79180, 79120],   # min 79100 > 79000
        ),
    )
    assert detect_session_breakout(ctx) is None


def test_prior_of_new_complete():
    """All 5 sessions must have prior mapping."""
    for new in ("asia", "london", "ny_am", "ny_lunch", "ny_pm"):
        assert new in _PRIOR_OF_NEW


def test_session_chain_cyclic():
    """Sessions form a cycle: ny_pm → asia → london → ny_am → ny_lunch → ny_pm."""
    # Verify each step
    assert _PRIOR_OF_NEW["asia"] == "ny_pm"
    assert _PRIOR_OF_NEW["london"] == "asia"
    assert _PRIOR_OF_NEW["ny_am"] == "london"
    assert _PRIOR_OF_NEW["ny_lunch"] == "ny_am"
    assert _PRIOR_OF_NEW["ny_pm"] == "ny_lunch"


def test_setup_type_in_registry():
    """The detector function must be in DETECTOR_REGISTRY."""
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    assert detect_session_breakout in DETECTOR_REGISTRY
