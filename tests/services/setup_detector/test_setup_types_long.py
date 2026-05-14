from __future__ import annotations

import pandas as pd

from services.setup_detector.models import SetupType
from services.setup_detector.setup_types import (
    DetectionContext,
    PortfolioSnapshot,
    detect_long_liq_magnet,
    detect_long_oversold_reclaim,
    detect_long_pdl_bounce,
)

from .conftest import make_1h_dump, make_dump_ohlcv, make_flat_ohlcv


def _ctx_pdl_bounce() -> DetectionContext:
    df_1m = make_dump_ohlcv(n=100, start_price=80000.0, dump_pct=2.0, volume_spike=1.8)
    df_1m.iloc[-1, df_1m.columns.get_loc("close")] = 78210.0
    df_1m.iloc[-1, df_1m.columns.get_loc("low")] = 78020.0
    df_1h = make_1h_dump(n=24, start_price=80000.0, dump_pct=2.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=78210.0,
        regime_label="range_wide",
        session_label="LONDON",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )


def _ctx_oversold_reclaim() -> DetectionContext:
    df_1m = make_dump_ohlcv(n=80, start_price=80000.0, dump_pct=4.0, volume_spike=1.0)
    df_1m.iloc[-3:, df_1m.columns.get_loc("close")] = [76800.0, 77080.0, 77350.0]
    df_1m.iloc[-3:, df_1m.columns.get_loc("high")] = [76820.0, 77100.0, 77380.0]
    df_1m.iloc[-3:, df_1m.columns.get_loc("volume")] = [120.0, 180.0, 260.0]
    df_1h = make_1h_dump(n=24, start_price=80000.0, dump_pct=10.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=77350.0,
        regime_label="consolidation",
        session_label="NY_AM",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )


def _ctx_long_liq() -> DetectionContext:
    df_1m = make_dump_ohlcv(n=80, start_price=80000.0, dump_pct=3.0, volume_spike=2.0)
    df_1m.iloc[-30:, df_1m.columns.get_loc("low")] = df_1m["low"].iloc[-30:] * 0.999
    df_1m.iloc[-1, df_1m.columns.get_loc("close")] = 77800.0
    df_1m.iloc[-1, df_1m.columns.get_loc("volume")] = 260.0
    df_1h = make_1h_dump(n=24, start_price=80000.0, dump_pct=4.0)
    return DetectionContext(
        pair="BTCUSDT",
        current_price=77800.0,
        regime_label="consolidation",
        session_label="NY_PM",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(liq_below_price=77100.0),
    )


def test_long_pdl_bounce_all_conditions_met() -> None:
    setup = detect_long_pdl_bounce(_ctx_pdl_bounce())
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_PDL_BOUNCE
    assert setup.entry_price is not None and setup.stop_price is not None
    assert setup.entry_price > setup.stop_price


def test_long_pdl_bounce_missing_condition() -> None:
    ctx = _ctx_pdl_bounce()
    ctx.regime_label = "trend_up"
    assert detect_long_pdl_bounce(ctx) is None


def test_long_pdl_bounce_below_min_strength() -> None:
    df_1m = make_flat_ohlcv(n=60, price=78400.0)
    df_1h = make_flat_ohlcv(n=24, price=78400.0)
    df_1h.index = pd.date_range("2026-01-01", periods=24, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=78400.0,
        regime_label="range_tight",
        session_label="ASIA",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    assert detect_long_pdl_bounce(ctx) is None


def test_long_oversold_reclaim_all_conditions_met() -> None:
    setup = detect_long_oversold_reclaim(_ctx_oversold_reclaim())
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_OVERSOLD_RECLAIM
    assert setup.strength >= 6


def test_long_oversold_reclaim_missing_condition() -> None:
    ctx = _ctx_oversold_reclaim()
    ctx.ohlcv_1m.iloc[-3:, ctx.ohlcv_1m.columns.get_loc("volume")] = [100.0, 100.0, 100.0]
    assert detect_long_oversold_reclaim(ctx) is None


def test_long_oversold_reclaim_below_min_strength() -> None:
    df_1m = make_flat_ohlcv(n=80, price=78000.0)
    df_1h = make_flat_ohlcv(n=24, price=78000.0)
    df_1h.index = pd.date_range("2026-01-01", periods=24, freq="1h", tz="UTC")
    ctx = DetectionContext(
        pair="BTCUSDT",
        current_price=78000.0,
        regime_label="consolidation",
        session_label="NONE",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(),
    )
    assert detect_long_oversold_reclaim(ctx) is None


def test_long_liq_magnet_all_conditions_met() -> None:
    setup = detect_long_liq_magnet(_ctx_long_liq())
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_LIQ_MAGNET
    assert setup.stop_price is not None and setup.entry_price is not None


def test_long_liq_magnet_missing_condition() -> None:
    ctx = _ctx_long_liq()
    ctx.portfolio.liq_below_price = None
    assert detect_long_liq_magnet(ctx) is None


def test_long_liq_magnet_below_min_strength() -> None:
    ctx = _ctx_long_liq()
    ctx.ohlcv_1m.iloc[-1, ctx.ohlcv_1m.columns.get_loc("volume")] = 100.0
    assert detect_long_liq_magnet(ctx) is None
