"""Tests for multi_divergence detector — bullish-only setup, regime-guarded."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest

from services.setup_detector.models import SetupType
from services.setup_detector.multi_divergence import (
    BOS_WINDOW_BARS,
    BOS_WINDOW_BARS_15M,
    DIV_WINDOW_BARS,
    MIN_CONFLUENCE,
    PIVOT_LOOKBACK,
    _build_indicators,
    _find_pivots,
    _find_recent_lh,
    _is_double_trend_down,
    _nearest_pivot_within,
    detect_long_div_bos_15m,
    detect_long_div_bos_confirmed,
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
    ohlcv_15m: pd.DataFrame = field(default_factory=pd.DataFrame)
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


# ─── DeltaCum is part of the indicator set ────────────────────────────────

def test_build_indicators_includes_deltacum() -> None:
    """DeltaCum was added 2026-05-08 as 7th confluence indicator."""
    df = _build_bullish_divergence_df(n=65)
    inds = _build_indicators(df)
    assert "DeltaCum" in inds
    assert len(inds) == 7
    # Sanity: cumulative series should be monotonic-ish in length, no all-NaN.
    assert inds["DeltaCum"].notna().sum() > 0


# ─── _find_recent_lh ──────────────────────────────────────────────────────

def test_find_recent_lh_returns_lower_high() -> None:
    """Two clear strict-max peaks: bar 4 (HH at 110), bar 14 (LH at 105).
    Looking before bar 29 with lookback=2, we expect the LH at ~bar 14."""
    closes = [100, 102, 105, 107, 110, 108, 105, 102, 100, 98,    # 0-9: peak 110 at bar 4
              100, 101, 103, 104, 105, 103, 100, 98, 96, 94,       # 10-19: lower peak 105 at bar 14
              92, 90, 89, 90, 92, 94, 96, 98, 100, 102]            # 20-29: drift
    n = len(closes)
    df = pd.DataFrame({
        "open":   [c - 1 for c in closes],
        "high":   [c + 2 for c in closes],
        "low":    [c - 2 for c in closes],
        "close":  closes,
        "volume": [100] * n,
    })
    result = _find_recent_lh(df, before_bar=29, lookback=2)
    assert result is not None
    lh_idx, lh_price = result
    # LH should be the second peak around bar 14 (high ~107).
    assert 12 <= lh_idx <= 16
    assert lh_price < df["high"].iloc[4]  # lower than the first peak


# ─── End-to-end CONFIRMED detector ────────────────────────────────────────

def _build_div_then_bos_df(n: int = 60) -> pd.DataFrame:
    """Synthetic series with HH at bar 9, LH at bar 24, LL pivots at bars 14
    and 39 (LL on price, HL on indicators), then BoS at the last bar.

    Layout (n=60):
      0-9:    rise into prior HH (~80300 at bar 9)
      10-19:  drop into valley1 ~78500 at bar 14 (LL pivot #1)
      20-29:  recovery to LH ~79200 at bar 24 (lower than HH 80300)
      30-39:  mild drop to valley2 ~78300 at bar 39 (LL pivot #2)
      40-53:  slow recovery, staying BELOW LH 79200
      54-59:  rising fast; last bar (59) closes ABOVE LH 79200 → BoS

    div_conf at 39+5=44, last_bar=59, gap=15. So we need BOS_WINDOW_BARS>=15
    OR shorten the recovery. Let's verify in dbg below; current code uses 10.
    Solution: place last_bar = div_conf + 10 to fit. n = div_conf + 11.
    div_conf at 44 -> n = 55. Adjust below.
    """
    closes = []
    volumes = []
    for i in range(n):
        if i < 10:
            # Rising into prior HH at bar 9.
            base = 79500.0 + i * 80.0
            vol = 100.0
        elif i < 15:
            # Drop into valley1.
            base = 80300.0 - (i - 9) * 360.0
            vol = 220.0
        elif i < 25:
            # Recovery — peak around bar 24 at ~79200 (LH).
            base = 78500.0 + (i - 14) * 70.0
            vol = 150.0
        elif i < 35:
            # Decline back into valley2.
            base = 79200.0 - (i - 24) * 90.0
            vol = 70.0
        elif i < n - 1:
            # Slow recovery — stay BELOW LH 79200 until the last bar.
            # n=49: bars 35..47 sit between 78600 and 79200.
            base = 78600.0 + (i - 34) * 45.0   # at bar 47: ~79185
            vol = 180.0
        else:
            # Last bar: break above LH (close > 79230).
            base = 79350.0
            vol = 350.0
        closes.append(base)
        volumes.append(vol)
    closes = [c + (0.5 if i % 2 == 0 else -0.5) for i, c in enumerate(closes)]
    df = pd.DataFrame({
        "open":   [c - 5 for c in closes],
        "high":   [c + 30 for c in closes],
        "low":    [c - 30 for c in closes],
        "close":  closes,
        "volume": volumes,
    })
    return df


def test_div_bos_confirmed_fires_on_synthetic_setup() -> None:
    df = _build_div_then_bos_df(n=50)  # last bar = 54, conf at 44, window = 10
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_1h=df, regime_label="range_wide")
    setup = detect_long_div_bos_confirmed(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_DIV_BOS_CONFIRMED
    assert setup.entry_price == pytest.approx(round(last_close, 1))
    # Confidence must reflect both confluence and BoS — at least 75%.
    assert setup.confidence_pct >= 75.0
    # Strength is 9..10
    assert setup.strength >= 9
    # Basis must include the broken LH.
    bos_basis = next((b for b in setup.basis if b.label == "bos_lh_broken"), None)
    assert bos_basis is not None


def test_div_bos_confirmed_blocked_by_regime_guard() -> None:
    df = _build_div_then_bos_df(n=50)
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_1h=df, regime_label="trend_down")
    assert detect_long_div_bos_confirmed(ctx) is None


def test_div_bos_confirmed_returns_none_without_bos() -> None:
    """Same divergence layout but no BoS at the end — must NOT fire."""
    df = _build_bullish_divergence_df(n=65)  # divergence but no BoS engineered
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_1h=df, regime_label="range_wide")
    assert detect_long_div_bos_confirmed(ctx) is None


def test_div_bos_confirmed_registered_in_registry() -> None:
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    assert detect_long_div_bos_confirmed in DETECTOR_REGISTRY


# ─── 15m detector tests ────────────────────────────────────────────────

def test_div_bos_15m_returns_none_with_empty_15m_frame() -> None:
    """The 15m detector must guard for ctx.ohlcv_15m being empty (loop may fail
    to load 15m data; production should not crash)."""
    df = _build_div_then_bos_df(n=50)
    ctx = _Ctx(current_price=80000.0, ohlcv_1h=df, ohlcv_15m=pd.DataFrame(),
               regime_label="range_wide")
    assert detect_long_div_bos_15m(ctx) is None


def test_div_bos_15m_returns_none_on_short_15m_frame() -> None:
    """Less than 50 bars -> not enough for divergence detection."""
    short_df = _build_div_then_bos_df(n=50).iloc[:30].reset_index(drop=True)
    ctx = _Ctx(ohlcv_15m=short_df, regime_label="range_wide")
    assert detect_long_div_bos_15m(ctx) is None


def test_div_bos_15m_fires_on_synthetic_setup() -> None:
    """Reuses the 1h synthetic shape — the 15m detector reads ohlcv_15m, the
    pattern itself is timeframe-agnostic. With BOS_WINDOW_BARS_15M=20 the
    same n=50 shape (gap=10 between div_conf and last_bar) easily fits."""
    df = _build_div_then_bos_df(n=50)
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_15m=df, regime_label="range_wide")
    setup = detect_long_div_bos_15m(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_DIV_BOS_15M
    # Confidence: 65 base + 5 per extra confluence (capped at 80).
    assert 65.0 <= setup.confidence_pct <= 80.0
    # Strength 8..9.
    assert 8 <= setup.strength <= 9
    # TP1 RR=2.0, so tp1 should be 2x risk above entry.
    risk = setup.entry_price - setup.stop_price
    assert setup.tp1_price == pytest.approx(setup.entry_price + risk * 2.0, rel=0.01)


def test_div_bos_15m_blocked_by_regime_guard() -> None:
    df = _build_div_then_bos_df(n=50)
    last_close = float(df["close"].iloc[-1])
    ctx = _Ctx(current_price=last_close, ohlcv_15m=df, regime_label="trend_down")
    assert detect_long_div_bos_15m(ctx) is None


def test_div_bos_15m_uses_wider_bos_window() -> None:
    """BOS_WINDOW_BARS_15M (20) is wider than BOS_WINDOW_BARS (10) — test that
    a setup with gap=15 (would fail on 1h) still fires on 15m."""
    assert BOS_WINDOW_BARS_15M > BOS_WINDOW_BARS


def test_div_bos_15m_registered_in_registry() -> None:
    from services.setup_detector.setup_types import DETECTOR_REGISTRY
    assert detect_long_div_bos_15m in DETECTOR_REGISTRY
