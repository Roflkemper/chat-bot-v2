"""Tests for services/h10_detector.py."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from services.h10_detector import detect_setup
from services.liquidity_map import LiquidityZone


def _zone(price: float, weight: float = 0.8, side: str = "long_stops") -> LiquidityZone:
    return LiquidityZone(
        price_level=price,
        price_range=(price - 25, price + 25),
        weight=weight,
        side=side,  # type: ignore[arg-type]
        components={},
    )


def _ohlcv_with_impulse_then_cons(
    impulse_pct: float = 0.02,
    cons_range_pct: float = 0.004,
    n_pre: int = 20,
    base: float = 50000.0,
) -> tuple[pd.DataFrame, datetime]:
    """
    Build a synthetic 1h OHLCV DataFrame:
    - n_pre flat candles
    - 1 single large impulse candle (covers full impulse_pct range)
    - 3 tight consolidation candles at the impulse peak

    The detector uses window.tail(4) for C1 sweep and window.tail(3) for C2 overlap,
    so the impulse candle + 3 cons candles must all land in the last 4 bars of window.
    ts is set one period after the last bar so all bars are included in the window.
    """
    n_total = n_pre + 4   # n_pre flat + 1 impulse + 3 cons
    idx = pd.date_range("2025-01-01", periods=n_total, freq="1h", tz="UTC")
    rows = []

    # pre-history: flat
    for _ in range(n_pre):
        rows.append({"open": base, "high": base + 20, "low": base - 20, "close": base, "volume": 50.0})

    # 1 big impulse candle: sweeps full impulse_pct from base to top
    top = base * (1 + impulse_pct)
    rows.append({
        "open": base,
        "high": top + 10,
        "low": base - 10,
        "close": top,
        "volume": 500.0,
    })

    half = top * cons_range_pct / 2
    # 3 tight overlapping consolidation candles near top
    for j in range(3):
        mid = top + j * (half * 0.05)
        rows.append({
            "open": mid - half * 0.3,
            "high": mid + half,
            "low": mid - half,
            "close": mid + half * 0.2,
            "volume": 60.0,
        })

    df = pd.DataFrame(rows, index=idx)
    # ts one period after last bar — detect_setup uses index < ts_utc
    ts = (idx[-1] + pd.Timedelta(hours=1)).to_pydatetime()
    return df, ts


class TestC1Positive:
    def test_impulse_2pct_triggers_c1(self):
        df, ts = _ohlcv_with_impulse_then_cons(impulse_pct=0.02)
        current_price = float(df["close"].iloc[-1])
        liq_map = [
            _zone(current_price * 0.985, weight=0.8, side="long_stops"),
            _zone(current_price * 1.015, weight=0.8, side="short_stops"),
        ]
        setup = detect_setup(ts, df, liq_map)
        assert setup is not None, "2% impulse should produce a setup"
        assert setup.impulse_pct >= 0.015


class TestC1Negative:
    def test_impulse_0_5pct_does_not_trigger(self):
        df, ts = _ohlcv_with_impulse_then_cons(impulse_pct=0.005)
        current_price = float(df["close"].iloc[-1])
        liq_map = [
            _zone(current_price * 0.985),
            _zone(current_price * 1.015),
        ]
        setup = detect_setup(ts, df, liq_map)
        assert setup is None, "0.5% impulse is below threshold, no setup expected"


class TestC2Positive:
    def test_3_overlapping_candles_pass_c2(self):
        df, ts = _ohlcv_with_impulse_then_cons(impulse_pct=0.02, cons_range_pct=0.003)
        current_price = float(df["close"].iloc[-1])
        liq_map = [
            _zone(current_price * 0.985),
            _zone(current_price * 1.015),
        ]
        setup = detect_setup(ts, df, liq_map)
        assert setup is not None


class TestC2Negative:
    def test_non_overlapping_candles_fail_c2(self):
        """Three candles that don't overlap each other — C2 should reject."""
        n_pre = 20
        base = 50000.0
        # n_pre + 1 impulse + 3 non-overlapping cons = n_pre + 4 bars
        idx = pd.date_range("2025-01-01", periods=n_pre + 4, freq="1h", tz="UTC")
        rows = []
        for _ in range(n_pre):
            rows.append({"open": base, "high": base + 20, "low": base - 20, "close": base, "volume": 50})

        # 1 big impulse candle
        top = base * 1.02
        rows.append({"open": base, "high": top + 10, "low": base - 10, "close": top, "volume": 500})

        # 3 non-overlapping candles (gap of 500 between each, well above prior)
        for j in range(3):
            lo = top + 100 + j * 500
            hi = lo + 50
            rows.append({"open": lo, "high": hi, "low": lo, "close": hi, "volume": 60})

        df = pd.DataFrame(rows, index=idx)
        ts = (idx[-1] + pd.Timedelta(hours=1)).to_pydatetime()
        current_price = float(df["close"].iloc[-1])
        liq_map = [_zone(current_price * 0.985), _zone(current_price * 1.015)]
        setup = detect_setup(ts, df, liq_map)
        assert setup is None, "non-overlapping candles should fail C2"


class TestC3OneSided:
    def test_only_above_cluster_no_setup(self):
        """C3 requires bilateral zones; only zones above → no setup."""
        df, ts = _ohlcv_with_impulse_then_cons(impulse_pct=0.02)
        current_price = float(df["close"].iloc[-1])
        # Only zones above, none below within the radius
        liq_map = [
            _zone(current_price * 1.010, weight=0.9, side="short_stops"),
            _zone(current_price * 1.015, weight=0.8, side="short_stops"),
        ]
        setup = detect_setup(ts, df, liq_map)
        assert setup is None, "no bilateral clusters → setup should not activate"
