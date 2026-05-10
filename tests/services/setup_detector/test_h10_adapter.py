"""Tests for H10 → Setup adapter (2026-05-10)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from services.h10_detector import H10Setup
from services.liquidity_map import LiquidityZone
from services.setup_detector.h10_adapter import (
    H10_STOP_PCT,
    H10_TP_PCT,
    detect_h10_liquidity_probe,
)
from services.setup_detector.models import SetupType
from services.setup_detector.setup_types import DetectionContext, PortfolioSnapshot


def _ctx(prices: list[float] = None) -> DetectionContext:
    if prices is None:
        prices = [80000.0] * 80
    df = pd.DataFrame({
        "open": prices,
        "high": [p * 1.001 for p in prices],
        "low": [p * 0.999 for p in prices],
        "close": prices,
        "volume": [100.0] * len(prices),
    })
    df.index = pd.date_range("2026-04-01", periods=len(prices), freq="1h", tz="UTC")
    return DetectionContext(
        pair="BTCUSDT", current_price=prices[-1],
        regime_label="range_wide", session_label="EU",
        ohlcv_1m=df, ohlcv_1h=df, ohlcv_15m=df,
        portfolio=PortfolioSnapshot(),
    )


def test_no_setup_returns_none():
    """Detector returns None → adapter returns None."""
    ctx = _ctx()
    with patch("services.setup_detector.h10_adapter._h10_detect_setup", return_value=None), \
         patch("services.setup_detector.h10_adapter.build_liquidity_map", return_value=[
             LiquidityZone(price_level=80800.0, price_range=(80750, 80850),
                           weight=0.8, side="short_stops"),
         ]):
        assert detect_h10_liquidity_probe(ctx) is None


def test_short_probe_setup_emitted():
    """Target zone above current price → SHORT probe (zone is short_stops to magnet)."""
    ctx = _ctx()
    fake_zone = LiquidityZone(price_level=80800.0, price_range=(80750, 80850),
                              weight=0.85, side="short_stops")
    fake_h10 = H10Setup(
        timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
        impulse_pct=0.018, impulse_direction="up", impulse_window_hours=4,
        consolidation_low=79800, consolidation_high=80200,
        consolidation_hours=10,
        target_zone=fake_zone, target_side="short_probe",
    )
    with patch("services.setup_detector.h10_adapter._h10_detect_setup", return_value=fake_h10), \
         patch("services.setup_detector.h10_adapter.build_liquidity_map", return_value=[fake_zone]):
        s = detect_h10_liquidity_probe(ctx)
    assert s is not None
    assert s.setup_type == SetupType.SHORT_LIQ_MAGNET
    # Entry near current price (80000)
    assert abs(s.entry_price - 80000.0) < 1.0
    # TP below entry for SHORT
    assert s.tp1_price < s.entry_price
    # Stop above entry for SHORT
    assert s.stop_price > s.entry_price
    # Stop is +0.8%
    assert abs((s.stop_price / s.entry_price - 1) * 100 - H10_STOP_PCT) < 0.01


def test_long_probe_setup_emitted():
    """Target zone below current price → LONG probe (long_stops below magnet)."""
    ctx = _ctx()
    fake_zone = LiquidityZone(price_level=79200.0, price_range=(79150, 79250),
                              weight=0.85, side="long_stops")
    fake_h10 = H10Setup(
        timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
        impulse_pct=0.018, impulse_direction="down", impulse_window_hours=4,
        consolidation_low=79800, consolidation_high=80200,
        consolidation_hours=10,
        target_zone=fake_zone, target_side="long_probe",
    )
    with patch("services.setup_detector.h10_adapter._h10_detect_setup", return_value=fake_h10), \
         patch("services.setup_detector.h10_adapter.build_liquidity_map", return_value=[fake_zone]):
        s = detect_h10_liquidity_probe(ctx)
    assert s is not None
    assert s.setup_type == SetupType.LONG_LIQ_MAGNET
    assert s.tp1_price > s.entry_price
    assert s.stop_price < s.entry_price


def test_basis_includes_h10_metrics():
    """Setup basis records impulse/consol/zone metrics."""
    ctx = _ctx()
    fake_zone = LiquidityZone(price_level=80800.0, price_range=(80750, 80850),
                              weight=0.91, side="short_stops")
    fake_h10 = H10Setup(
        timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
        impulse_pct=0.022, impulse_direction="up", impulse_window_hours=6,
        consolidation_low=79800, consolidation_high=80200,
        consolidation_hours=14,
        target_zone=fake_zone, target_side="short_probe",
    )
    with patch("services.setup_detector.h10_adapter._h10_detect_setup", return_value=fake_h10), \
         patch("services.setup_detector.h10_adapter.build_liquidity_map", return_value=[fake_zone]):
        s = detect_h10_liquidity_probe(ctx)
    labels = {b.label: b.value for b in s.basis}
    assert "impulse_pct" in labels
    assert labels["impulse_window_h"] == 6
    assert labels["consolidation_h"] == 14
    assert labels["zone_weight"] == 0.91


def test_short_history_returns_none():
    """OHLCV with <60 bars returns None (insufficient data)."""
    ctx = _ctx(prices=[80000.0] * 30)
    assert detect_h10_liquidity_probe(ctx) is None
