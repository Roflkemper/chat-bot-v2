from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.setup_detector.indicators import (
    compute_rsi,
    compute_volume_ratio,
    detect_swing_highs,
    detect_swing_lows,
    find_pdh_pdl,
    count_touches_at_level,
)


# ── RSI ───────────────────────────────────────────────────────────────────────

def _make_close(prices: list[float]) -> pd.Series:
    return pd.Series(prices, dtype=float)


def test_rsi_oversold() -> None:
    """Sustained dump → RSI < 30."""
    prices = [100 - i * 0.5 for i in range(50)]
    rsi = compute_rsi(_make_close(prices), period=14)
    assert rsi < 30.0


def test_rsi_overbought() -> None:
    """Sustained rally → RSI > 70."""
    prices = [100 + i * 0.5 for i in range(50)]
    rsi = compute_rsi(_make_close(prices), period=14)
    assert rsi > 70.0


def test_rsi_neutral() -> None:
    """Flat market → RSI = 50.0 (both gain and loss are zero)."""
    prices = [100.0] * 30
    rsi = compute_rsi(_make_close(prices), period=14)
    assert rsi == pytest.approx(50.0)


def test_rsi_insufficient_data_returns_50() -> None:
    """Less than period+2 bars → returns 50.0."""
    prices = [100.0] * 5
    rsi = compute_rsi(_make_close(prices), period=14)
    assert rsi == 50.0


# ── Volume ratio ──────────────────────────────────────────────────────────────

def test_volume_ratio_above_average() -> None:
    vol = pd.Series([100.0] * 30 + [200.0])
    ratio = compute_volume_ratio(vol, lookback=30)
    assert ratio == pytest.approx(2.0, rel=0.01)


def test_volume_ratio_below_average() -> None:
    vol = pd.Series([100.0] * 30 + [50.0])
    ratio = compute_volume_ratio(vol, lookback=30)
    assert ratio == pytest.approx(0.5, rel=0.01)


def test_volume_ratio_insufficient_data_returns_one() -> None:
    vol = pd.Series([100.0] * 5)
    ratio = compute_volume_ratio(vol, lookback=30)
    assert ratio == 1.0


# ── Swing highs/lows ──────────────────────────────────────────────────────────

def test_swing_highs_correct_count() -> None:
    prices = [1, 2, 3, 2, 1, 2, 5, 2, 1, 2, 4, 2, 1]
    high = pd.Series(prices, dtype=float)
    highs = detect_swing_highs(high, window=2, max_count=3)
    assert len(highs) <= 3
    # All returned values should be local maxima
    for idx, price in highs:
        assert price > 1.0


def test_swing_lows_correct_count() -> None:
    prices = [5, 4, 1, 4, 5, 4, 2, 4, 5, 4, 3, 4, 5]
    low = pd.Series(prices, dtype=float)
    lows = detect_swing_lows(low, window=2, max_count=3)
    assert len(lows) <= 3
    for idx, price in lows:
        assert price <= 3.0


# ── PDH/PDL ──────────────────────────────────────────────────────────────────

def test_pdh_pdl_calculation() -> None:
    n = 24
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame({
        "open": 80000.0,
        "high": [80000.0 + i * 10 for i in range(n)],
        "low": [80000.0 - i * 5 for i in range(n)],
        "close": 80000.0,
        "volume": 1.0,
    }, index=idx)
    pdh, pdl = find_pdh_pdl(df)
    assert pdh == pytest.approx(80000.0 + (n - 1) * 10)
    assert pdl == pytest.approx(80000.0 - (n - 1) * 5)


def test_pdh_pdl_empty_returns_zeros() -> None:
    pdh, pdl = find_pdh_pdl(pd.DataFrame())
    assert pdh == 0.0
    assert pdl == 0.0


# ── test_count_at_level ───────────────────────────────────────────────────────

def test_test_count_at_level() -> None:
    # tolerance=0.05% of 80000 = $40 → only exact 80000 values match (±50 excluded)
    prices = pd.Series([80000.0, 80050.0, 80100.0, 80000.0, 79950.0, 80000.0])
    count = count_touches_at_level(prices, level=80000.0, tolerance_pct=0.04)
    assert count == 3  # 80000, 80000, 80000 (80050 and 79950 are $50 away, tol=$32)


def test_test_count_at_level_no_match() -> None:
    prices = pd.Series([75000.0, 76000.0, 77000.0])
    count = count_touches_at_level(prices, level=80000.0, tolerance_pct=0.5)
    assert count == 0
