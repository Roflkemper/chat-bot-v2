from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_flat_ohlcv(n: int = 100, price: float = 80000.0) -> pd.DataFrame:
    """Flat OHLCV: all OHLC = price, volume = 100."""
    idx = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({
        "open": price,
        "high": price * 1.001,
        "low": price * 0.999,
        "close": price,
        "volume": 100.0,
    }, index=idx)


def make_dump_ohlcv(
    n: int = 60,
    start_price: float = 80000.0,
    dump_pct: float = 3.0,
    volume_spike: float = 2.0,
) -> pd.DataFrame:
    """OHLCV with a gradual dump of dump_pct% over first n bars, then stabilises."""
    prices = np.linspace(start_price, start_price * (1 - dump_pct / 100), n)
    idx = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "open": prices,
        "high": prices * 1.001,
        "low": prices * 0.997,
        "close": prices,
        "volume": 100.0,
    }, index=idx)
    # spike volume on last 5 bars
    df.iloc[-5:, df.columns.get_loc("volume")] = 100.0 * volume_spike
    # bullish reversal wicks on last 5 bars (lower wick dominant)
    df.iloc[-5:, df.columns.get_loc("low")] = prices[-5:] * 0.994
    return df


def make_rally_ohlcv(
    n: int = 60,
    start_price: float = 80000.0,
    rally_pct: float = 3.0,
    volume_spike: float = 2.0,
) -> pd.DataFrame:
    """OHLCV with a rally of rally_pct% over n bars."""
    prices = np.linspace(start_price, start_price * (1 + rally_pct / 100), n)
    idx = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "open": prices,
        "high": prices * 1.004,
        "low": prices * 0.999,
        "close": prices,
        "volume": 100.0,
    }, index=idx)
    df.iloc[-5:, df.columns.get_loc("volume")] = 100.0 * volume_spike
    # bearish rejection wicks on last 5 bars (upper wick dominant)
    df.iloc[-5:, df.columns.get_loc("high")] = prices[-5:] * 1.006
    return df


def make_1h_dump(n: int = 20, start_price: float = 80000.0, dump_pct: float = 4.0) -> pd.DataFrame:
    """1h bars with dump."""
    prices = np.linspace(start_price, start_price * (1 - dump_pct / 100), n)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": prices,
        "high": prices * 1.002,
        "low": prices * 0.995,
        "close": prices,
        "volume": 1000.0,
    }, index=idx)


def make_1h_rally(n: int = 20, start_price: float = 80000.0, rally_pct: float = 4.0) -> pd.DataFrame:
    """1h bars with rally."""
    prices = np.linspace(start_price, start_price * (1 + rally_pct / 100), n)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": prices,
        "high": prices * 1.005,
        "low": prices * 0.998,
        "close": prices,
        "volume": 1000.0,
    }, index=idx)
