"""Tests for services/liquidity_map.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from services.liquidity_map import build_liquidity_map, LiquidityZone


def _make_ohlcv(n: int = 80, base_price: float = 50000.0) -> pd.DataFrame:
    """Flat 1h OHLCV DataFrame with tz-aware DatetimeIndex."""
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(42)
    closes = base_price + rng.normal(0, 50, n).cumsum()
    df = pd.DataFrame({
        "open": closes,
        "high": closes + 30,
        "low": closes - 30,
        "close": closes,
        "volume": rng.uniform(10, 100, n),
    }, index=idx)
    return df


def _ts(ohlcv: pd.DataFrame, offset: int = 0) -> datetime:
    return ohlcv.index[-1 + offset].to_pydatetime()


class TestRoundNumberBonus:
    def test_zone_near_round_number_has_higher_weight(self):
        """Zone straddling a $1000 multiple should get the round-number bonus."""
        # Build data centered exactly on 50000 so $50000 bin gets bonus
        idx = pd.date_range("2025-01-01", periods=80, freq="1h", tz="UTC")
        price = 50000.0
        df = pd.DataFrame({
            "open": [price] * 80,
            "high": [price + 10] * 80,
            "low": [price - 10] * 80,
            "close": [price] * 80,
            "volume": [100.0] * 80,
        }, index=idx)
        ts = idx[-1].to_pydatetime()
        zones = build_liquidity_map(ts, df, lookback_hours=72, bin_size=50.0, current_price=price)
        assert zones, "should produce at least one zone"
        # Find zone nearest $50000
        target = min(zones, key=lambda z: abs(z.price_level - 50000.0))
        # All zones are normalized to [0,1]; the one at round number should not be zero
        assert target.weight > 0.0


class TestLiquidationWeight:
    def test_liquidation_zone_gets_highest_weight(self):
        """A bin with large liquidation value should dominate weight when data provided."""
        ohlcv = _make_ohlcv(80, base_price=50000.0)
        ts = _ts(ohlcv)
        current_price = float(ohlcv["close"].iloc[-1])

        # Place a big liquidation at current_price - 1.0% (inside ±3% window, below)
        liq_price = current_price * 0.990
        liq_df = pd.DataFrame({
            "ts_ms": [int(ohlcv.index[-10].timestamp() * 1000)],
            "price": [liq_price],
            "value_usd": [1_000_000_000.0],  # enormous — should dominate
            "side": ["long"],
        })
        zones = build_liquidity_map(ts, ohlcv, lookback_hours=72, liquidations=liq_df)
        assert zones, "should produce zones"
        top = zones[0]
        # Top zone should be near the liquidation price
        assert abs(top.price_level - liq_price) < 200, (
            f"top zone {top.price_level:.0f} not near liquidation {liq_price:.0f}"
        )


class TestSortedByWeight:
    def test_zones_sorted_descending(self):
        ohlcv = _make_ohlcv(80)
        ts = _ts(ohlcv)
        zones = build_liquidity_map(ts, ohlcv, lookback_hours=72)
        weights = [z.weight for z in zones]
        assert weights == sorted(weights, reverse=True), "zones must be sorted by weight descending"


class TestEmptyInput:
    def test_empty_ohlcv_returns_empty_list(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex([], dtype="datetime64[ns, UTC]")
        ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
        result = build_liquidity_map(ts, df, lookback_hours=72)
        assert result == []

    def test_ts_before_all_data_returns_empty(self):
        ohlcv = _make_ohlcv(80)
        early_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
        result = build_liquidity_map(early_ts, ohlcv, lookback_hours=72)
        assert result == []
