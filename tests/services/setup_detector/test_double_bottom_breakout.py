"""Tests for detect_double_bottom_breakout (2026-05-10)."""
from __future__ import annotations

import pandas as pd

from services.setup_detector.double_top_bottom import detect_double_bottom_breakout
from services.setup_detector.models import SetupType
from services.setup_detector.setup_types import DetectionContext, PortfolioSnapshot


def _ctx(prices: list[float]) -> DetectionContext:
    df = pd.DataFrame({
        "open": prices,
        "high": [p * 1.005 for p in prices],
        "low": [p * 0.998 for p in prices],
        "close": prices,
        "volume": [1000.0] * len(prices),
    })
    df.index = pd.date_range("2026-01-01", periods=len(prices), freq="1h", tz="UTC")
    return DetectionContext(
        pair="BTCUSDT",
        current_price=prices[-1],
        regime_label="range_wide",
        session_label="EU",
        ohlcv_1m=df,
        ohlcv_1h=df,
        ohlcv_15m=df,
        portfolio=PortfolioSnapshot(),
    )


def test_breakout_with_pullback_emits():
    """Double bottom + breakout above neckline + pullback >=0.3% → setup."""
    prices = [
        100, 99.5, 99, 99.5, 99,
        96.5, 95, 95.5, 96, 97, 98, 98.5, 99, 98.7, 96.5, 95.2,
        96, 96.5, 97, 97.5, 98,
        98.5, 100.0, 101.5, 102.0, 101.5, 100.8, 100.0, 99.5, 99.5,
    ]
    setup = detect_double_bottom_breakout(_ctx(prices))
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_DOUBLE_BOTTOM_BREAKOUT
    # Entry near current pullback price
    assert abs(setup.entry_price - prices[-1]) / prices[-1] < 0.01
    # Stop below 2nd swing low
    assert setup.stop_price < 96.0
    # TP1 above breakout high
    assert setup.tp1_price > 102.0
    assert setup.risk_reward is not None and setup.risk_reward > 0


def test_no_breakout_no_setup():
    """Double bottom forms but price never breaks above neckline → None."""
    prices = [
        100, 99.5, 99, 99.5, 99,
        96.5, 95, 95.5, 96, 97, 98, 97.5, 96, 95.7, 95.5, 95.2,
        96, 96.5, 97, 97.2,  # never reaches peak ~98
    ]
    setup = detect_double_bottom_breakout(_ctx(prices))
    assert setup is None


def test_no_pullback_no_setup():
    """Breakout happened but no pullback yet (last_close at breakout high) → None."""
    prices = [
        100, 99.5, 99, 99.5, 99,
        96.5, 95, 95.5, 96, 97, 98, 98.5, 99, 98.7, 96.5, 95.2,
        96, 96.5, 97, 97.5, 98,
        98.5, 100.0, 101.5, 102.0, 102.0,  # still at peak
    ]
    setup = detect_double_bottom_breakout(_ctx(prices))
    # Pullback from 102.0 to 102.0 = 0% < 0.3% → None
    assert setup is None


def test_pullback_below_neckline_no_setup():
    """Breakout, but pullback went BELOW neckline → invalid pattern."""
    prices = [
        100, 99.5, 99, 99.5, 99,
        96.5, 95, 95.5, 96, 97, 98, 98.5, 99, 98.7, 96.5, 95.2,
        96, 96.5, 97, 97.5, 98,
        98.5, 100.0, 101.5, 102.0, 101.5, 100.8, 100.0, 97.0, 96.5,  # below ~98 neckline
    ]
    setup = detect_double_bottom_breakout(_ctx(prices))
    assert setup is None


def test_short_data_no_setup():
    """Less than 30 bars → None (can't form pattern)."""
    setup = detect_double_bottom_breakout(_ctx([100.0] * 20))
    assert setup is None
