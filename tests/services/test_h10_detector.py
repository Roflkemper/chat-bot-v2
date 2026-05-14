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
    cons_range_pct: float = 0.008,
    n_pre: int = 20,
    n_cons: int = 8,
    base: float = 50000.0,
) -> tuple[pd.DataFrame, datetime]:
    """
    Build a synthetic 1h OHLCV DataFrame:
      - n_pre flat candles
      - 1 single large impulse candle (sweeps impulse_pct)
      - n_cons tight consolidation candles at the impulse peak

    With n_cons >= 8 (default), the impulse lands inside pre when the detector
    scans consol_len=n_cons (which must be >= consol_min_hours=6).  close is set
    to the center of the consolidation range so the boundary-margin check passes.
    """
    n_total = n_pre + 1 + n_cons
    idx = pd.date_range("2025-01-01", periods=n_total, freq="1h", tz="UTC")
    rows = []

    for _ in range(n_pre):
        rows.append({"open": base, "high": base + 20, "low": base - 20, "close": base, "volume": 50.0})

    top = base * (1 + impulse_pct)
    rows.append({
        "open": base,
        "high": top + 10,
        "low": base - 10,
        "close": top,
        "volume": 500.0,
    })

    half = top * cons_range_pct / 2
    for _ in range(n_cons):
        rows.append({
            "open": top - half * 0.1,
            "high": top + half,
            "low": top - half,
            "close": top,  # center of range — passes boundary-margin check
            "volume": 60.0,
        })

    df = pd.DataFrame(rows, index=idx)
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
        df, ts = _ohlcv_with_impulse_then_cons(impulse_pct=0.02, cons_range_pct=0.008)
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


# ── TZ-056 new tests ──────────────────────────────────────────────────────────

def _make_liq_map(current_price: float, weight: float = 0.8) -> list[LiquidityZone]:
    return [
        _zone(current_price * 0.985, weight=weight, side="long_stops"),
        _zone(current_price * 1.015, weight=weight, side="short_stops"),
    ]


class TestConsolidation12hPasses:
    def test_12h_tight_corridor_finds_setup(self):
        """Data with 12 consecutive tight consolidation hours produces a valid setup.
        The detector greedily picks the shortest valid window (≥6h), so we only assert
        that a setup is found — not that it uses exactly 12h."""
        df, ts = _ohlcv_with_impulse_then_cons(n_cons=12, cons_range_pct=0.008)
        liq_map = _make_liq_map(float(df["close"].iloc[-1]))
        setup = detect_setup(ts, df, liq_map)
        assert setup is not None
        assert 6 <= setup.consolidation_hours <= 48


class TestConsolidation4hFailsMinDuration:
    def test_4_cons_candles_returns_none(self):
        """Only 4 consolidation candles — the 6h minimum is never satisfied."""
        df, ts = _ohlcv_with_impulse_then_cons(n_cons=4, cons_range_pct=0.008)
        liq_map = _make_liq_map(float(df["close"].iloc[-1]))
        setup = detect_setup(ts, df, liq_map)
        assert setup is None, "4h consolidation is below the 6h minimum"


class TestConsolidation60hFailsMaxDuration:
    def test_60_cons_candles_returns_none(self):
        """60 consolidation candles push the impulse out of reach for any
        (consol_len≤48, imp_size≤12) scan window — detector returns None."""
        df, ts = _ohlcv_with_impulse_then_cons(n_cons=60, cons_range_pct=0.008)
        liq_map = _make_liq_map(float(df["close"].iloc[-1]))
        setup = detect_setup(ts, df, liq_map)
        assert setup is None, "60h consolidation exceeds the 48h maximum"


class TestRange3PctFailsC2:
    def test_3pct_corridor_fails_c2(self):
        """Consolidation range of 3% > 2.5% max → C2 rejects every window."""
        df, ts = _ohlcv_with_impulse_then_cons(n_cons=8, cons_range_pct=0.030)
        liq_map = _make_liq_map(float(df["close"].iloc[-1]))
        setup = detect_setup(ts, df, liq_map)
        assert setup is None, "3% corridor is above the 2.5% max"


class TestImpulse8hPasses:
    def test_8_candle_impulse_window_detected(self):
        """Impulse spread over 8 candles is detected with impulse_window_hours=8.

        No flat pre-bars: for consol_len < 8, len(pre) < 8 so imp_size=8 is skipped
        and smaller imp_sizes see only flat-near-top bars (< 1.5% sweep).  When
        consol_len=8 the pre is exactly the 8 impulse candles → sweep ≥ 1.5% ✓.
        """
        n_imp, n_cons = 8, 8
        n_total = n_imp + n_cons
        base = 50000.0
        top = base * 1.025
        half = top * 0.004

        idx = pd.date_range("2025-01-01", periods=n_total, freq="1h", tz="UTC")
        rows = []
        # 8-candle impulse: first candle does the full sweep, rest flat near top
        rows.append({"open": base, "high": top + 10, "low": base - 10, "close": top, "volume": 800.0})
        for _ in range(n_imp - 1):
            rows.append({"open": top, "high": top + 10, "low": top - 10, "close": top, "volume": 80.0})
        # 8 tight cons candles
        for _ in range(n_cons):
            rows.append({"open": top - half * 0.1, "high": top + half, "low": top - half, "close": top, "volume": 60.0})

        df = pd.DataFrame(rows, index=idx)
        ts = (idx[-1] + pd.Timedelta(hours=1)).to_pydatetime()
        liq_map = _make_liq_map(top)
        setup = detect_setup(ts, df, liq_map)
        assert setup is not None
        assert setup.impulse_window_hours == 8


class TestC3WeightBelowThreshold:
    def test_weight_045_fails_default_threshold_050(self):
        """Zones with weight=0.45 are below the 0.50 default threshold → no bilateral → None."""
        df, ts = _ohlcv_with_impulse_then_cons(impulse_pct=0.02)
        current_price = float(df["close"].iloc[-1])
        liq_map = _make_liq_map(current_price, weight=0.45)
        setup = detect_setup(ts, df, liq_map)  # default weight_threshold=0.50
        assert setup is None, "weight 0.45 < threshold 0.50 → C3 fails"
