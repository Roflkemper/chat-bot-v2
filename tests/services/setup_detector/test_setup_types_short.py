from __future__ import annotations

import pandas as pd

from services.setup_detector.models import SetupType
from services.setup_detector.setup_types import (
    DetectionContext,
    PortfolioSnapshot,
    detect_short_liq_magnet,
    detect_short_overbought_fade,
    detect_short_pdh_rejection,
)

from .conftest import make_1h_rally, make_flat_ohlcv, make_rally_ohlcv


def _ctx_pdh_rejection() -> DetectionContext:
    df_1m = make_rally_ohlcv(n=100, start_price=80000.0, rally_pct=2.0, volume_spike=1.8)
    df_1m.iloc[-1, df_1m.columns.get_loc("close")] = 81980.0
    df_1m.iloc[-1, df_1m.columns.get_loc("high")] = 82020.0
    df_1h = make_1h_rally(n=24, start_price=80000.0, rally_pct=2.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=81980.0,
        regime_label="range_wide",
        session_label="LONDON",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )


def _ctx_overbought_fade() -> DetectionContext:
    df_1m = make_rally_ohlcv(n=80, start_price=80000.0, rally_pct=5.0, volume_spike=1.0)
    df_1m.iloc[-3:, df_1m.columns.get_loc("close")] = [83600.0, 83350.0, 83100.0]
    df_1m.iloc[-3:, df_1m.columns.get_loc("volume")] = [130.0, 200.0, 280.0]
    df_1h = make_1h_rally(n=24, start_price=80000.0, rally_pct=12.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=83100.0,
        regime_label="consolidation",
        session_label="NY_AM",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )


def _ctx_short_liq() -> DetectionContext:
    df_1m = make_rally_ohlcv(n=80, start_price=80000.0, rally_pct=3.0, volume_spike=2.0)
    df_1m.iloc[-30:, df_1m.columns.get_loc("high")] = df_1m["high"].iloc[-30:] * 1.001
    df_1m.iloc[-1, df_1m.columns.get_loc("close")] = 82200.0
    df_1m.iloc[-1, df_1m.columns.get_loc("volume")] = 280.0
    df_1h = make_1h_rally(n=24, start_price=80000.0, rally_pct=4.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=82200.0,
        regime_label="consolidation",
        session_label="NY_PM",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(liq_above_price=82950.0),
    )


def test_short_pdh_rejection_all_conditions_met() -> None:
    setup = detect_short_pdh_rejection(_ctx_pdh_rejection())
    assert setup is not None
    assert setup.setup_type == SetupType.SHORT_PDH_REJECTION
    assert setup.stop_price is not None and setup.entry_price is not None
    assert setup.stop_price > setup.entry_price


def test_short_pdh_rejection_missing_condition() -> None:
    ctx = _ctx_pdh_rejection()
    ctx.regime_label = "trend_down"
    assert detect_short_pdh_rejection(ctx) is None


def test_short_pdh_rejection_below_min_strength() -> None:
    df_1m = make_flat_ohlcv(n=60, price=81600.0)
    df_1h = make_flat_ohlcv(n=24, price=81600.0)
    df_1h.index = pd.date_range("2026-01-01", periods=24, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=81600.0,
        regime_label="range_tight",
        session_label="ASIA",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    assert detect_short_pdh_rejection(ctx) is None


def test_short_overbought_fade_all_conditions_met() -> None:
    setup = detect_short_overbought_fade(_ctx_overbought_fade())
    assert setup is not None
    assert setup.setup_type == SetupType.SHORT_OVERBOUGHT_FADE
    assert setup.strength >= 6


def test_short_overbought_fade_missing_condition() -> None:
    ctx = _ctx_overbought_fade()
    ctx.ohlcv_1m.iloc[-3:, ctx.ohlcv_1m.columns.get_loc("close")] = [83100.0, 83350.0, 83600.0]
    assert detect_short_overbought_fade(ctx) is None


def test_short_overbought_fade_below_min_strength() -> None:
    df_1m = make_flat_ohlcv(n=80, price=83000.0)
    df_1h = make_flat_ohlcv(n=24, price=83000.0)
    df_1h.index = pd.date_range("2026-01-01", periods=24, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=83000.0,
        regime_label="consolidation",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    assert detect_short_overbought_fade(ctx) is None


def test_short_liq_magnet_all_conditions_met() -> None:
    setup = detect_short_liq_magnet(_ctx_short_liq())
    assert setup is not None
    assert setup.setup_type == SetupType.SHORT_LIQ_MAGNET


def test_short_liq_magnet_missing_condition() -> None:
    ctx = _ctx_short_liq()
    ctx.portfolio.liq_above_price = None
    assert detect_short_liq_magnet(ctx) is None


def test_short_liq_magnet_below_min_strength() -> None:
    ctx = _ctx_short_liq()
    ctx.ohlcv_1m.iloc[-1, ctx.ohlcv_1m.columns.get_loc("volume")] = 100.0
    assert detect_short_liq_magnet(ctx) is None
