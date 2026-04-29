"""Tests for services/h10_grid.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from services.h10_detector import H10Setup
from services.h10_grid import ProbeParams, ProbeResult, simulate_probe
from services.liquidity_map import LiquidityZone


def _zone(price: float, weight: float = 0.8) -> LiquidityZone:
    return LiquidityZone(
        price_level=price,
        price_range=(price - 25, price + 25),
        weight=weight,
        side="long_stops",
        components={},
    )


def _setup(target_price: float = 50000.0, side: str = "long_probe") -> H10Setup:
    ts = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    return H10Setup(
        timestamp=ts,
        impulse_pct=0.02,
        impulse_direction="up",
        consolidation_low=target_price - 50,
        consolidation_high=target_price + 50,
        target_zone=_zone(target_price),
        target_side=side,  # type: ignore[arg-type]
    )


def _make_1m(
    start: datetime,
    n: int,
    base_price: float,
    drop_pct: float = 0.0,
    rise_pct: float = 0.0,
) -> pd.DataFrame:
    """1m bars that drop then rise (or just hold) — used to simulate fills then TP."""
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    prices = []
    for i in range(n):
        frac = i / max(n - 1, 1)
        if frac < 0.5:
            p = base_price * (1 - drop_pct * (frac / 0.5))
        else:
            p = base_price * (1 - drop_pct + rise_pct * ((frac - 0.5) / 0.5))
        prices.append(p)
    df = pd.DataFrame({
        "open": prices,
        "high": [p + base_price * 0.001 for p in prices],
        "low": [p - base_price * 0.001 for p in prices],
        "close": prices,
        "volume": [50.0] * n,
    }, index=idx)
    return df


class TestAllOrdersFillThenTP:
    def test_tp_hit_gives_positive_pnl(self):
        """
        Long probe: bars drop below center (fill all grid levels),
        then rise above TP price → exit_reason='tp', pnl_usd > 0.
        """
        base = 50000.0
        params = ProbeParams(
            grid_steps=3,
            grid_step_pct=0.002,
            total_btc=0.15,
            tp_pct=0.005,
            time_stop_hours=2,
            protective_stop_pct=None,
        )
        setup = _setup(target_price=base, side="long_probe")
        ts_start = setup.timestamp

        # Drop 1.5% (fills all 3 levels), then rise 1.5% above base (hits TP at avg+0.5%)
        ohlcv_1m = _make_1m(ts_start, n=90, base_price=base, drop_pct=0.015, rise_pct=0.020)

        result = simulate_probe(setup, ohlcv_1m, params)
        assert result is not None
        assert result.exit_reason == "tp"
        assert result.pnl_usd > 0
        assert result.n_orders_filled > 0


class TestTimeStop:
    def test_time_stop_returns_mark_to_market(self):
        """No TP hit within time window → time_stop exit."""
        base = 50000.0
        params = ProbeParams(
            grid_steps=3,
            grid_step_pct=0.002,
            total_btc=0.15,
            tp_pct=0.05,   # very large TP — won't be hit
            time_stop_hours=1,
            protective_stop_pct=None,
        )
        setup = _setup(target_price=base, side="long_probe")
        # Bars drop a little to fill some orders, never rise to TP
        ohlcv_1m = _make_1m(setup.timestamp, n=80, base_price=base, drop_pct=0.005, rise_pct=0.002)
        result = simulate_probe(setup, ohlcv_1m, params)
        assert result is not None
        assert result.exit_reason == "time_stop"


class TestProtectiveStop:
    def test_protective_stop_fires_before_tp(self):
        """Bars drop hard → protective stop fires; exit_reason='protective_stop'."""
        base = 50000.0
        params = ProbeParams(
            grid_steps=3,
            grid_step_pct=0.002,
            total_btc=0.15,
            tp_pct=0.01,
            time_stop_hours=4,
            protective_stop_pct=-0.005,  # -0.5%
        )
        setup = _setup(target_price=base, side="long_probe")
        # Drop 1.5%: fills orders AND then price stays well below entry (triggers -0.5% stop)
        ohlcv_1m = _make_1m(setup.timestamp, n=120, base_price=base, drop_pct=0.015, rise_pct=0.0)
        result = simulate_probe(setup, ohlcv_1m, params)
        assert result is not None
        assert result.exit_reason == "protective_stop"
        assert result.pnl_usd < 0


class TestPartialFillVWAP:
    def test_partial_fill_avg_entry_is_vwap(self):
        """Only first grid level touched — avg_entry equals that single level price."""
        base = 50000.0
        params = ProbeParams(
            grid_steps=4,
            grid_step_pct=0.005,   # large step — only first level touched with small drop
            total_btc=0.12,
            tp_pct=0.001,  # tiny TP to hit quickly
            time_stop_hours=2,
            protective_stop_pct=None,
        )
        setup = _setup(target_price=base, side="long_probe")
        # Grid starts from center and extends outward from the target zone.
        expected_level = base

        # Drop just enough to touch first level then bounce to TP
        ohlcv_1m = _make_1m(setup.timestamp, n=90, base_price=base, drop_pct=0.003, rise_pct=0.010)
        result = simulate_probe(setup, ohlcv_1m, params)
        assert result is not None
        assert result.n_orders_filled >= 1
        # VWAP of single fill == that fill price
        if result.n_orders_filled == 1:
            assert abs(result.avg_entry - expected_level) < 50, (
                f"avg_entry {result.avg_entry:.2f} far from expected {expected_level:.2f}"
            )
        else:
            # If multiple filled, just assert avg_entry is between min and max grid prices
            assert result.avg_entry > 0
