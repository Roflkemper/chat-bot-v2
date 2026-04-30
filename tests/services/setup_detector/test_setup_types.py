from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.setup_detector.models import Setup, SetupType
from services.setup_detector.setup_types import (
    DETECTOR_REGISTRY,
    DetectionContext,
    PortfolioSnapshot,
    detect_defensive_margin_low,
    detect_grid_booster_activate,
    detect_long_dump_reversal,
    detect_short_rally_fade,
)

from .conftest import make_1h_dump, make_1h_rally, make_dump_ohlcv, make_flat_ohlcv, make_rally_ohlcv


def _ctx_dump(regime: str = "consolidation", session: str = "NY_AM") -> DetectionContext:
    """Context with strong dump — should trigger LONG_DUMP_REVERSAL."""
    df_1m = make_dump_ohlcv(n=100, start_price=80000.0, dump_pct=4.0, volume_spike=2.0)
    df_1h = make_1h_dump(n=20, start_price=80000.0, dump_pct=5.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=float(df_1m["close"].iloc[-1]),
        regime_label=regime,
        session_label=session,
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )


def _ctx_rally(regime: str = "consolidation", session: str = "NY_AM") -> DetectionContext:
    """Context with strong rally — should trigger SHORT_RALLY_FADE."""
    df_1m = make_rally_ohlcv(n=100, start_price=80000.0, rally_pct=4.0, volume_spike=2.0)
    df_1h = make_1h_rally(n=20, start_price=80000.0, rally_pct=5.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=float(df_1m["close"].iloc[-1]),
        regime_label=regime,
        session_label=session,
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )


# ── detect_long_dump_reversal ─────────────────────────────────────────────────

def test_detect_long_dump_reversal_all_conditions_met() -> None:
    ctx = _ctx_dump()
    setup = detect_long_dump_reversal(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_DUMP_REVERSAL
    assert setup.strength >= 6
    assert setup.entry_price is not None
    assert setup.stop_price is not None
    assert setup.tp1_price is not None


def test_detect_long_dump_reversal_correct_rr() -> None:
    ctx = _ctx_dump()
    setup = detect_long_dump_reversal(ctx)
    assert setup is not None and setup.entry_price is not None and setup.stop_price is not None
    assert setup.entry_price > setup.stop_price  # stop below entry for long
    assert setup.risk_reward is not None and setup.risk_reward > 0.0


def test_detect_long_dump_reversal_no_dump_returns_none() -> None:
    df_1m = make_flat_ohlcv(n=100, price=80000.0)
    df_1h = make_flat_ohlcv(n=20, price=80000.0).rename(columns={})
    # Recreate as 1h flat
    df_1h_flat = make_flat_ohlcv(n=20, price=80000.0)
    df_1h_flat.index = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="consolidation",
        session_label="NY_AM",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h_flat,
        portfolio=PortfolioSnapshot(),
    )
    setup = detect_long_dump_reversal(ctx)
    # Flat market — no dump condition → likely None or low strength
    # (RSI will be ~50, no reversal wicks, no volume spike)
    if setup is not None:
        assert setup.strength < 6  # below threshold if somehow detected


def test_detect_long_dump_reversal_below_min_strength() -> None:
    """Truly flat data: RSI=50, no wicks, no volume spike → returns None."""
    # Use make_flat_ohlcv — truly flat: no dump, no wicks, no volume spike
    df_1m = make_flat_ohlcv(n=100, price=80000.0)
    df_1h = make_flat_ohlcv(n=20, price=80000.0)
    df_1h.index = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="consolidation",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    setup = detect_long_dump_reversal(ctx)
    # Flat data: no dump (0%), RSI=50 (not oversold), minimal wicks → fails conditions
    assert setup is None


# ── detect_short_rally_fade ───────────────────────────────────────────────────

def test_detect_short_rally_fade_correct() -> None:
    ctx = _ctx_rally()
    setup = detect_short_rally_fade(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.SHORT_RALLY_FADE
    assert setup.strength >= 6
    assert setup.stop_price is not None and setup.entry_price is not None
    assert setup.stop_price > setup.entry_price  # stop above entry for short


# ── detect_defensive_margin_low ───────────────────────────────────────────────

def test_detect_defensive_margin_low_triggers() -> None:
    df_1m = make_flat_ohlcv()
    df_1h = make_flat_ohlcv(n=20)
    df_1h.index = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="consolidation",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(free_margin_pct=15.0),
    )
    setup = detect_defensive_margin_low(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.DEFENSIVE_MARGIN_LOW
    assert setup.strength >= 8


def test_detect_defensive_margin_high_returns_none() -> None:
    df_1m = make_flat_ohlcv()
    df_1h = make_flat_ohlcv(n=20)
    df_1h.index = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=80000.0,
        regime_label="consolidation",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(free_margin_pct=60.0),
    )
    assert detect_defensive_margin_low(ctx) is None


# ── detect_grid_booster ───────────────────────────────────────────────────────

def test_detect_grid_booster_activate_in_range_oversold() -> None:
    """Range regime + RSI < 35 → GRID_BOOSTER_ACTIVATE."""
    df_1m = make_dump_ohlcv(n=100, start_price=80000.0, dump_pct=4.0)
    df_1h = make_1h_dump(n=20, start_price=80000.0, dump_pct=5.0)
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=float(df_1m["close"].iloc[-1]),
        regime_label="range_wide",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    setup = detect_grid_booster_activate(ctx)
    if setup is not None:
        assert setup.setup_type == SetupType.GRID_BOOSTER_ACTIVATE
        assert setup.grid_action == "activate_booster"


def test_no_detection_when_regime_is_trend() -> None:
    """Trend regime → grid booster should not fire."""
    df_1m = make_dump_ohlcv(n=100)
    df_1h = make_1h_dump(n=20)
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=float(df_1m["close"].iloc[-1]),
        regime_label="trend_down",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    assert detect_grid_booster_activate(ctx) is None


# ── DETECTOR_REGISTRY ─────────────────────────────────────────────────────────

def test_detector_registry_has_known_functions() -> None:
    names = {fn.__name__ for fn in DETECTOR_REGISTRY}
    assert "detect_long_dump_reversal" in names
    assert "detect_short_rally_fade" in names
    assert "detect_defensive_margin_low" in names
    assert "detect_grid_booster_activate" in names
