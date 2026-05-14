from __future__ import annotations

import numpy as np
import pandas as pd

from services.setup_detector.models import SetupType
from services.setup_detector.setup_types import (
    DetectionContext,
    PortfolioSnapshot,
    detect_grid_adaptive_tighten,
    detect_grid_booster_activate,
    detect_grid_pause_entries,
    detect_grid_raise_boundary,
)


def _trend_1m() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=120, freq="1min", tz="UTC")
    base = np.linspace(80000.0, 82400.0, 120)
    base[-20:] = np.linspace(82320.0, 82400.0, 20)
    high = base * 1.001
    low = base * 0.999
    high[-30:] = base[-30:] * 1.0004
    low[-30:] = base[-30:] * 0.9997
    return pd.DataFrame(
        {
            "open": base,
            "high": high,
            "low": low,
            "close": base,
            "volume": np.concatenate([np.full(90, 140.0), np.full(30, 90.0)]),
        },
        index=idx,
    )


def _trend_1h() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=12, freq="1h", tz="UTC")
    close = np.linspace(80000.0, 82400.0, 12)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(12, 1000.0),
        },
        index=idx,
    )


def _ctx_grid() -> DetectionContext:
    df_1m = _trend_1m()
    df_1h = _trend_1h()
    return DetectionContext(
        pair="BTCUSDT",
        current_price=float(df_1m["close"].iloc[-1]),
        regime_label="trend_up",
        session_label="NY_AM",
        ohlcv_1m=df_1m,
        ohlcv_1h=df_1h,
        portfolio=PortfolioSnapshot(free_margin_pct=28.0, net_btc=-0.25),
    )


def test_grid_raise_boundary_all_conditions_met() -> None:
    setup = detect_grid_raise_boundary(_ctx_grid())
    assert setup is not None
    assert setup.setup_type == SetupType.GRID_RAISE_BOUNDARY
    assert setup.grid_action == "raise_boundary +0.3%"
    assert setup.grid_param_change is not None


def test_grid_raise_boundary_missing_condition() -> None:
    ctx = _ctx_grid()
    ctx.portfolio.net_btc = 0.1
    assert detect_grid_raise_boundary(ctx) is None


def test_grid_raise_boundary_below_min_strength() -> None:
    ctx = _ctx_grid()
    ctx.portfolio.free_margin_pct = 60.0
    assert detect_grid_raise_boundary(ctx) is None


def test_grid_pause_entries_all_conditions_met() -> None:
    setup = detect_grid_pause_entries(_ctx_grid())
    assert setup is not None
    assert setup.setup_type == SetupType.GRID_PAUSE_ENTRIES
    assert setup.grid_action == "pause_entries"


def test_grid_pause_entries_missing_condition() -> None:
    ctx = _ctx_grid()
    ctx.portfolio.net_btc = 0.0
    assert detect_grid_pause_entries(ctx) is None


def test_grid_pause_entries_below_min_strength() -> None:
    ctx = _ctx_grid()
    ctx.portfolio.free_margin_pct = 70.0
    assert detect_grid_pause_entries(ctx) is None


def test_grid_adaptive_tighten_all_conditions_met() -> None:
    setup = detect_grid_adaptive_tighten(_ctx_grid())
    assert setup is not None
    assert setup.setup_type == SetupType.GRID_ADAPTIVE_TIGHTEN
    assert setup.grid_action == "tighten"
    assert setup.grid_param_change == {"target_factor": 0.85, "gs_factor": 0.85}


def test_grid_adaptive_tighten_missing_condition() -> None:
    ctx = _ctx_grid()
    ctx.portfolio.net_btc = 0.0
    assert detect_grid_adaptive_tighten(ctx) is None


def test_grid_adaptive_tighten_below_min_strength() -> None:
    ctx = _ctx_grid()
    ctx.portfolio.free_margin_pct = 45.0
    assert detect_grid_adaptive_tighten(ctx) is None


def test_grid_booster_all_conditions_met() -> None:
    ctx = _ctx_grid()
    ctx.regime_label = "consolidation"
    ctx.portfolio.liq_below_price = ctx.current_price * 0.99
    idx = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    close = np.linspace(84000.0, 78000.0, len(idx))
    ctx.ohlcv_1h = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(idx), 1000.0),
        },
        index=idx,
    )
    setup = detect_grid_booster_activate(ctx)
    assert setup is not None
    assert setup.setup_type == SetupType.GRID_BOOSTER_ACTIVATE
    assert setup.grid_action == "activate_booster"


def test_grid_booster_missing_condition() -> None:
    ctx = _ctx_grid()
    ctx.regime_label = "trend_up"
    assert detect_grid_booster_activate(ctx) is None


def test_grid_booster_trade_envelope_present_for_future_tracking() -> None:
    ctx = _ctx_grid()
    ctx.regime_label = "consolidation"
    ctx.portfolio.liq_below_price = ctx.current_price * 0.99
    idx = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    close = np.linspace(84000.0, 78000.0, len(idx))
    ctx.ohlcv_1h = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(idx), 1000.0),
        },
        index=idx,
    )
    setup = detect_grid_booster_activate(ctx)
    assert setup is not None
    assert setup.entry_price is not None
    assert setup.stop_price is not None
    assert setup.tp1_price is not None
    assert setup.tp2_price is not None
    assert setup.window_minutes == 45
