"""Tests for multi_divergence detector — bullish-only setup, regime-guarded."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest

from services.setup_detector.models import SetupType
from services.setup_detector.multi_divergence import (
    DIV_WINDOW_BARS,
    MIN_CONFLUENCE,
    PIVOT_LOOKBACK,
    _find_pivots,
    _is_double_trend_down,
    _nearest_pivot_within,
    detect_long_multi_divergence,
)


@dataclass
class _Ctx:
    pair: str = "BTCUSDT"
    current_price: float = 80000.0
    regime_label: str = "range_wide"
    session_label: str = "ny_am"
    ohlcv_1m: pd.DataFrame = field(default_factory=pd.DataFrame)
    ohlcv_1h: pd.DataFrame = field(default_factory=pd.DataFrame)
    portfolio: object = None
    ict_context: dict = field(default_factory=dict)


# ─── _find_pivots ─────────────────────────────────────────────────────────

def test_find_pivots_strict_extrema() -> None:
    s = pd.Series([10, 11, 12, 11, 10, 9, 11, 12, 13, 12, 11])
    p = _find_pivots(s, lookback=2)
    # idx=2 (12, surrounded by lower) is a pivot high
    # idx=5 (9, surrounded by higher) is a pivot low
    # idx=8 (13) is also a pivot high (strict max in [6..10])
    assert 2 in p.highs
    assert 5 in p.lows
    assert 8 in p.highs


def test_find_pivots_excludes_ties() -> None:
    # Center is tied with one of the wing values — must NOT be a pivot.
    s = pd.Series([10, 11, 12, 12, 11, 10, 9])
    p = _find_pivots(s, lookback=2)
    assert 2 not in p.highs
    assert 3 not in p.highs


# ─── _nearest_pivot_within ────────────────────────────────────────────────

def test_nearest_pivot_within_finds_closest() -> None:
    pivots = [10, 25, 30, 50]
    assert _nearest_pivot_within(pivots, 28, tolerance=3) == 30
    assert _nearest_pivot_within(pivots, 27, tolerance=3) == 25  # equidistant -> first found
    assert _nearest_pivot_within(pivots, 100, tolerance=3) is None
    assert _nearest_pivot_within([], 50, tolerance=3) is None


# ─── regime guard ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("trend_down", True),
    ("impulse_down", True),
    ("TREND_DOWN", True),    # case-insensitive
    ("trend_up", False),
    ("range_wide", False),
    ("range_tight", False),
    ("", False),
    (None, False),
])
def test_is_double_trend_down(label, expected) -> None:
    ctx = _Ctx(regime_label=label)
    assert _is_double_trend_down(ctx) is expected


# ─── End-to-end: synthetic divergence ─────────────────────────────────────

def _build_bullish_divergence_df(n: int = 70) -> pd.DataFrame:
    """Synthetic 1h series with a clean bullish divergence within DIV_WINDOW_BARS.

    Layout (≤ 30 bars between valleys, total 70 bars):
      bar 0-9:    plateau at 80000 (warmup; >= PIVOT_LOOKBACK before valley 1)
      bar 10-19:  sharp drop -1500 → 78500 (heavy down-volume)
      bar 20-29:  recovery up to ~79500
      bar 30-39:  mild second leg → 78300 (weak down-volume, less RSI dip)
      bar 40-69:  recovery (long enough for valley 2 + lookback to land freshly)

    Valley 1 ≈ bar 19, valley 2 ≈ bar 39. Distance = 20 bars (within window=30).
    """
    closes = []
    volumes = []
    for i in range(n):
        if i < 10:
            base = 80000.0
            vol = 100.0
        elif i < 20:
            # Sharp drop into valley 1 (-1500 over 10 bars).
            base = 80000.0 - (i - 9) * 150.0
            vol = 220.0
        elif i < 30:
            # Recovery to ~79900.
            base = 78500.0 + (i - 19) * 140.0
            vol = 150.0
        elif i < 40:
            # Mild second leg down to ~78300 (LL by 200 below valley 1).
            base = 79900.0 - (i - 29) * 160.0
            vol = 70.0   # weak selling — protects RSI/MFI/OBV from making LL
        else:
            # Recovery.
            base = 78300.0 + (i - 39) * 70.0
            vol = 180.0
        closes.append(base)
        volumes.append(vol)

    # Jitter for strict-extrema pivots.
    closes = [c + (0.5 if i % 2 == 0 else -0.5) for i, c in enumerate(closes)]
    df = pd.DataFrame({
        "open":   [c - 5 for c in closes],
        "high":   [c + 30 for c in closes],
        "low":    [c - 30 for c in closes],
        "close":  closes,
        "volume": volumes,
    })
    return df


def test_detect_long_multi_divergence_fires_on_synthetic_setup() -> None:
    df = _build_bullish_divergence_df(n=65)
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_1h=df, regime_label="range_wide")
    setup = detect_long_multi_divergence(ctx)
    assert setup is not None, "synthetic bullish divergence should fire detector"
    assert setup.setup_type == SetupType.LONG_MULTI_DIVERGENCE
    assert setup.entry_price == pytest.approx(round(last_close, 1))
    assert setup.stop_price < setup.entry_price
    assert setup.tp1_price > setup.entry_price
    # Confluence is in basis as a SetupBasis with label 'confluence_count'.
    confluence_basis = next((b for b in setup.basis if b.label == "confluence_count"), None)
    assert confluence_basis is not None
    assert int(confluence_basis.value) >= MIN_CONFLUENCE


def test_regime_guard_blocks_signal_in_trend_down() -> None:
    df = _build_bullish_divergence_df(n=65)
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_1h=df, regime_label="trend_down")
    setup = detect_long_multi_divergence(ctx)
    assert setup is None, "regime guard must suppress signal in trend_down"


def test_returns_none_on_short_dataframe() -> None:
    df = pd.DataFrame({
        "open": [80000] * 30, "high": [80050] * 30, "low": [79950] * 30,
        "close": [80000] * 30, "volume": [100] * 30,
    })
    ctx = _Ctx(ohlcv_1h=df)
    assert detect_long_multi_divergence(ctx) is None  # < 50 bars


def test_returns_none_when_no_price_LL() -> None:
    # Strictly rising series — no LL on price possible.
    n = 80
    closes = [80000 + i * 50 for i in range(n)]
    df = pd.DataFrame({
        "open":   [c - 10 for c in closes],
        "high":   [c + 30 for c in closes],
        "low":    [c - 30 for c in closes],
        "close":  closes,
        "volume": [100] * n,
    })
    ctx = _Ctx(ohlcv_1h=df)
    assert detect_long_multi_divergence(ctx) is None


def test_returns_none_when_required_columns_missing() -> None:
    df = pd.DataFrame({"close": [80000.0] * 80})
    ctx = _Ctx(ohlcv_1h=df)
    assert detect_long_multi_divergence(ctx) is None


def test_setup_strength_and_confidence_scale_with_confluence() -> None:
    """At minimum confluence=2 we expect strength=7, confidence=60.
    Higher confluence raises both. Use the synthetic case which yields
    enough confluence to verify the lower bound at least."""
    df = _build_bullish_divergence_df(n=65)
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_1h=df, regime_label="range_wide")
    setup = detect_long_multi_divergence(ctx)
    assert setup is not None
    assert setup.strength >= 7
    assert setup.confidence_pct >= 60.0
    assert setup.confidence_pct <= 85.0


def test_setup_registered_in_registry() -> None:
    """Sanity-check: the new detector is wired into DETECTOR_REGISTRY so the
    setup_detector loop will actually call it."""
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    assert detect_long_multi_divergence in DETECTOR_REGISTRY
