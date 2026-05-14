"""Tests for MTF (multi-TF) disagreement check (2026-05-10)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.setup_detector.mtf_check import (
    compute_mtf_view,
    mtf_setup_alignment,
    _trend_dir,
)
from services.setup_detector.setup_types import DetectionContext, PortfolioSnapshot


def _flat_df(n: int = 60, price: float = 80000.0) -> pd.DataFrame:
    df = pd.DataFrame({
        "open": [price] * n, "high": [price * 1.001] * n,
        "low": [price * 0.999] * n, "close": [price] * n,
        "volume": [100.0] * n,
    })
    df.index = pd.date_range("2026-04-01", periods=n, freq="1h", tz="UTC")
    return df


def _rising_df(n: int = 60, start: float = 80000.0, end: float = 82000.0,
               freq: str = "1h") -> pd.DataFrame:
    prices = np.linspace(start, end, n)
    df = pd.DataFrame({
        "open": prices, "high": prices * 1.001, "low": prices * 0.999,
        "close": prices, "volume": [100.0] * n,
    })
    df.index = pd.date_range("2026-04-01", periods=n, freq=freq, tz="UTC")
    return df


def test_trend_dir_flat():
    assert _trend_dir(_flat_df()) == "flat"


def test_trend_dir_up():
    assert _trend_dir(_rising_df()) == "up"


def test_trend_dir_down():
    df = _rising_df(start=82000.0, end=80000.0)  # falling
    assert _trend_dir(df) == "down"


def test_trend_dir_short_data():
    df = _flat_df(n=10)
    assert _trend_dir(df) == "flat"


def _ctx(df_15m, df_1h):
    return DetectionContext(
        pair="BTCUSDT", current_price=float(df_1h["close"].iloc[-1]),
        regime_label="range_wide", session_label="EU",
        ohlcv_1m=df_15m, ohlcv_1h=df_1h, ohlcv_15m=df_15m,
        portfolio=PortfolioSnapshot(),
    )


def test_mtf_view_all_flat():
    ctx = _ctx(_flat_df(60, 80000), _flat_df(60, 80000))
    v = compute_mtf_view(ctx)
    assert v.dir_15m == "flat"
    assert v.dir_1h == "flat"
    assert v.majority == "flat"
    assert not v.has_top_down_conflict


def test_mtf_view_all_up():
    df = _rising_df(60, 80000.0, 84000.0)
    ctx = _ctx(df, df)
    v = compute_mtf_view(ctx)
    assert v.dir_15m == "up"
    assert v.dir_1h == "up"
    assert v.majority == "up"
    assert not v.has_top_down_conflict


def test_mtf_view_top_down_conflict():
    df_15m_up = _rising_df(60, 80000.0, 82000.0, freq="15min")
    df_1h_down = _rising_df(60, 82000.0, 80000.0, freq="1h")
    ctx = _ctx(df_15m_up, df_1h_down)
    v = compute_mtf_view(ctx)
    # 15m up, 1h down, 4h likely down
    assert v.dir_15m == "up"
    assert v.dir_1h == "down"
    # 4h is built from 1h — should also be down
    assert v.has_top_down_conflict


def test_alignment_long_aligned_when_all_up():
    df = _rising_df(60, 80000.0, 84000.0)
    ctx = _ctx(df, df)
    v = compute_mtf_view(ctx)
    assert mtf_setup_alignment("long", v) == "aligned"


def test_alignment_long_conflict_when_all_down():
    df = _rising_df(60, 84000.0, 80000.0)
    ctx = _ctx(df, df)
    v = compute_mtf_view(ctx)
    assert mtf_setup_alignment("long", v) == "conflict"


def test_alignment_short_aligned_when_all_down():
    df = _rising_df(60, 84000.0, 80000.0)
    ctx = _ctx(df, df)
    v = compute_mtf_view(ctx)
    assert mtf_setup_alignment("short", v) == "aligned"


def test_alignment_neutral_on_flat():
    df = _flat_df(60)
    ctx = _ctx(df, df)
    v = compute_mtf_view(ctx)
    assert mtf_setup_alignment("long", v) == "neutral"
    assert mtf_setup_alignment("short", v) == "neutral"
