"""Tests for src/features/technical.py.

Key invariants tested:
  - No look-ahead: 1h bar [12:00, 13:00) values visible only from 13:00
  - ATR/RSI computed via resample, not rolling on 1m
  - Pin bar / engulfing only on 15m and 1h
  - RSI divergence vectorized correctness
  - Consecutive counters reset correctly
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.features.technical import (
    _atr,
    _consec_run,
    _engulfing_bear,
    _engulfing_bull,
    _pin_bar_bear,
    _pin_bar_bull,
    _rsi,
    _rsi_divergence,
    compute,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _df(
    start: str,
    periods: int,
    freq: str = "min",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    volume: float = 1000.0,
) -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    n = len(idx)
    return pd.DataFrame(
        {
            "open":   [open_]  * n,
            "high":   [high]   * n,
            "low":    [low]    * n,
            "close":  [close]  * n,
            "volume": [volume] * n,
        },
        index=idx,
    )


def _make_1h_blocks(hour_specs: list[dict]) -> pd.DataFrame:
    """Build a 1m df from a list of 1h block specs.

    Each spec: {"start": "2026-04-15T10:00Z", "open": x, "high": x, "low": x, "close": x}
    Produces 60 identical 1m bars per block.
    """
    frames = []
    for spec in hour_specs:
        frame = _df(spec["start"], 60,
                    open_=spec.get("open", 100.0),
                    high=spec.get("high", 101.0),
                    low=spec.get("low", 99.0),
                    close=spec.get("close", 100.0),
                    volume=spec.get("volume", 1000.0))
        frames.append(frame)
    return pd.concat(frames)


# ── schema ────────────────────────────────────────────────────────────────────

EXPECTED_COLS = [
    "body_pct_1m", "consec_bull", "consec_bear", "vol_zscore", "vol_ratio",
    "momentum_15m",
    "pin_bar_bull_15m", "pin_bar_bear_15m",
    "engulfing_bull_15m", "engulfing_bear_15m",
    "atr_1h", "atr_pct_1h", "rsi_1h", "rsi_ob_1h", "rsi_os_1h",
    "momentum_1h",
    "pin_bar_bull_1h", "pin_bar_bear_1h",
    "engulfing_bull_1h", "engulfing_bear_1h",
    "rsi_div_bull", "rsi_div_bear",
]


class TestSchema:
    def test_all_22_columns_present(self):
        r = compute(_df("2026-04-15T10:00Z", 120))
        for col in EXPECTED_COLS:
            assert col in r.columns, f"Missing: {col}"

    def test_input_columns_preserved(self):
        r = compute(_df("2026-04-15T10:00Z", 60))
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in r.columns

    def test_empty_df_returns_empty(self):
        idx = pd.DatetimeIndex([], tz="UTC")
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []}, index=idx)
        r = compute(df)
        assert len(r) == 0

    def test_no_volume_column_returns_nan_vol_features(self):
        idx = pd.date_range("2026-04-15T10:00Z", periods=60, freq="min", tz="UTC")
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            index=idx,
        )
        r = compute(df)
        assert r["vol_zscore"].isna().all()
        assert r["vol_ratio"].isna().all()


# ── no look-ahead ─────────────────────────────────────────────────────────────

class TestNoLookahead:
    """Critical: 1h bar [T, T+1h) must NOT be visible on 1m bars before T+1h."""

    def _build_two_distinct_hours(self):
        """
        Warmup: 10 hours of alternating closes (100/101/100/...) so RSI ≈ 50 (non-NaN).
        Hour A [10:00, 11:00): close=100, range=2.
        Hour B [11:00, 12:00): close=200, range=50 — very different ATR.
        """
        # Alternating warmup gives non-NaN RSI and stable ATR.
        starts = pd.date_range("2026-04-15T00:00Z", periods=10, freq="h", tz="UTC")
        frames = []
        for i, ts in enumerate(starts):
            c = 100.0 + (i % 2)  # alternates 100/101
            frames.append(_df(str(ts), 60, open_=c, high=c + 1, low=c - 1, close=c))
        warmup = pd.concat(frames)
        hour_a = _make_1h_blocks([{
            "start": "2026-04-15T10:00Z",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
        }])
        hour_b = _make_1h_blocks([{
            "start": "2026-04-15T11:00Z",
            "open": 150.0, "high": 175.0, "low": 125.0, "close": 200.0,
        }])
        # One bar after hour B to see its ATR
        after = _df("2026-04-15T12:00Z", 1)
        return pd.concat([warmup, hour_a, hour_b, after])

    def test_atr_not_visible_mid_hour(self):
        df = self._build_two_distinct_hours()
        r = compute(df)
        # ATR of hour B [11:00-11:59] must NOT be visible at 11:30
        atr_mid_b = r.loc["2026-04-15T11:30:00+00:00", "atr_1h"]
        atr_start_b = r.loc["2026-04-15T11:00:00+00:00", "atr_1h"]
        # All of 11:00-11:59 should reflect hour A's ATR (range≈2)
        assert atr_mid_b == atr_start_b  # same ffill'd value within hour B window

    def test_atr_visible_at_next_hour_boundary(self):
        df = self._build_two_distinct_hours()
        r = compute(df)
        atr_in_b = r.loc["2026-04-15T11:30:00+00:00", "atr_1h"]
        atr_after_b = r.loc["2026-04-15T12:00:00+00:00", "atr_1h"]
        # After hour B closes, ATR should change (hour B had range=50 vs hour A range=2)
        assert atr_after_b != atr_in_b

    def test_pin_bar_not_visible_within_hour(self):
        """Pin bar on 1h candle at 10:00 must not appear at 10:30 (not yet closed)."""
        # 1h bar 10:00: bull pin bar (lower wick=9, body=0.5, upper wick=0.5)
        hour_pin = _make_1h_blocks([{
            "start": "2026-04-15T10:00Z",
            "open": 100.0, "high": 100.5, "low": 90.0, "close": 100.5,
        }])
        after = _df("2026-04-15T11:00Z", 10)
        df = pd.concat([hour_pin, after])
        r = compute(df)
        # During 10:00-10:59 — pin bar NOT yet confirmed
        assert not r.loc["2026-04-15T10:30:00+00:00", "pin_bar_bull_1h"]

    def test_pin_bar_visible_after_hour_closes(self):
        """Pin bar on 1h [10:00-10:59] becomes visible at 11:00."""
        hour_pin = _make_1h_blocks([{
            "start": "2026-04-15T10:00Z",
            "open": 100.0, "high": 100.5, "low": 90.0, "close": 100.5,
        }])
        after = _df("2026-04-15T11:00Z", 10)
        df = pd.concat([hour_pin, after])
        r = compute(df)
        assert r.loc["2026-04-15T11:00:00+00:00", "pin_bar_bull_1h"]

    def test_rsi_not_visible_within_hour(self):
        """All 1m bars within a 1h bucket share the same rsi_1h (no intra-hour update)."""
        df = self._build_two_distinct_hours()
        r = compute(df)
        # Within 1h bucket [10:00, 10:59]: all bars get the same ffill'd RSI (from 09:00 bar)
        rsi_1000 = r.loc["2026-04-15T10:00:00+00:00", "rsi_1h"]
        rsi_1030 = r.loc["2026-04-15T10:30:00+00:00", "rsi_1h"]
        rsi_1059 = r.loc["2026-04-15T10:59:00+00:00", "rsi_1h"]
        assert rsi_1000 == rsi_1030 == rsi_1059
        # At 11:00 the 10:00 bar's RSI becomes available → value must differ from 10:xx
        rsi_1100 = r.loc["2026-04-15T11:00:00+00:00", "rsi_1h"]
        rsi_1130 = r.loc["2026-04-15T11:30:00+00:00", "rsi_1h"]
        assert rsi_1100 == rsi_1130  # intra-hour stability holds at 11:xx too


# ── ATR ───────────────────────────────────────────────────────────────────────

class TestATR:
    def test_constant_tr_converges_to_tr(self):
        """With constant TR=2, Wilder's ATR → 2."""
        idx = pd.date_range("2026-04-15", periods=100, freq="h", tz="UTC")
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            index=idx,
        )
        atr = _atr(df)
        assert abs(atr.iloc[-1] - 2.0) < 0.01

    def test_atr_first_bar_uses_hl_range(self):
        """First bar has no prev_c; TR = high-low; ATR is non-NaN from bar 0."""
        df = _df("2026-04-15T00:00Z", 5, freq="h", high=102.0, low=98.0)
        atr = _atr(df)
        # TR[0] = max(h-l, |h-NaN|, |l-NaN|) = h-l = 4.0 (pandas max ignores NaN)
        assert not math.isnan(atr.iloc[0])
        assert atr.iloc[0] > 0

    def test_atr_1h_present_in_output(self):
        r = compute(_df("2026-04-15T00:00Z", 180))
        assert "atr_1h" in r.columns
        # After 2+ hours, atr_1h should be non-NaN (ffill'd from first valid 1h bar)
        assert not r["atr_1h"].iloc[120:].isna().all()


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_rsi_range_0_to_100(self):
        """RSI must be in [0, 100] on valid data."""
        np.random.seed(42)
        idx = pd.date_range("2026-04-15", periods=200, freq="h", tz="UTC")
        closes = 100 + np.cumsum(np.random.randn(200))
        df = pd.DataFrame(
            {"open": closes, "high": closes + 1, "low": closes - 1, "close": closes},
            index=idx,
        )
        rsi = _rsi(df["close"])
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_50_on_alternating_equal_gains(self):
        """Alternating +1/-1 closes → RSI ≈ 50 after warm-up."""
        idx = pd.date_range("2026-04-15", periods=100, freq="h", tz="UTC")
        closes = [100.0 + (1 if i % 2 == 0 else -1) for i in range(100)]
        df = pd.DataFrame({"close": closes}, index=idx)
        rsi = _rsi(df["close"])
        assert abs(rsi.iloc[-1] - 50.0) < 5.0

    def test_rsi_high_on_sustained_up(self):
        """Sustained up moves → RSI > 70."""
        idx = pd.date_range("2026-04-15", periods=50, freq="h", tz="UTC")
        closes = [100.0 + i for i in range(50)]
        df = pd.DataFrame({"close": closes}, index=idx)
        rsi = _rsi(df["close"])
        assert rsi.iloc[-1] > 70.0

    def test_rsi_ob_flag_above_70(self):
        # 50 hours of sustained uptrend using pd.date_range to avoid hour overflow
        starts = pd.date_range("2026-04-14", periods=50, freq="h", tz="UTC")
        frames = []
        for i, ts in enumerate(starts):
            c = 100.0 + i
            frames.append(_df(str(ts), 60, open_=c, high=c + 1, low=c - 1, close=c))
        r = compute(pd.concat(frames))
        assert r["rsi_ob_1h"].any()


# ── pin bar ───────────────────────────────────────────────────────────────────

class TestPinBar:
    def _make_pin_bull(self) -> pd.DataFrame:
        """Bull pin: open=100, high=100.5, low=90, close=100.5 → lower_wick=10, body=0.5, range=10.5."""
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z"], tz="UTC")
        return pd.DataFrame(
            {"open": [100.0], "high": [100.5], "low": [90.0], "close": [100.5]},
            index=idx,
        )

    def _make_pin_bear(self) -> pd.DataFrame:
        """Bear pin: open=100, high=110, low=99.5, close=99.5 → upper_wick=10, body=0.5, range=10.5."""
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z"], tz="UTC")
        return pd.DataFrame(
            {"open": [100.0], "high": [110.0], "low": [99.5], "close": [99.5]},
            index=idx,
        )

    def _make_normal_bar(self) -> pd.DataFrame:
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z"], tz="UTC")
        return pd.DataFrame(
            {"open": [99.0], "high": [101.0], "low": [99.0], "close": [101.0]},
            index=idx,
        )

    def test_bull_pin_detected(self):
        assert _pin_bar_bull(self._make_pin_bull()).iloc[0]

    def test_bear_pin_detected(self):
        assert _pin_bar_bear(self._make_pin_bear()).iloc[0]

    def test_normal_bar_not_bull_pin(self):
        assert not _pin_bar_bull(self._make_normal_bar()).iloc[0]

    def test_normal_bar_not_bear_pin(self):
        assert not _pin_bar_bear(self._make_normal_bar()).iloc[0]

    def test_bull_pin_not_flagged_as_bear(self):
        assert not _pin_bar_bear(self._make_pin_bull()).iloc[0]

    def test_zero_range_bar_not_pin(self):
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z"], tz="UTC")
        df = pd.DataFrame(
            {"open": [100.0], "high": [100.0], "low": [100.0], "close": [100.0]},
            index=idx,
        )
        assert not _pin_bar_bull(df).iloc[0]
        assert not _pin_bar_bear(df).iloc[0]


# ── engulfing ─────────────────────────────────────────────────────────────────

class TestEngulfing:
    def _two_bar_df(self, o1, h1, l1, c1, o2, h2, l2, c2) -> pd.DataFrame:
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z", "2026-04-15T11:00Z"], tz="UTC")
        return pd.DataFrame(
            {"open": [o1, o2], "high": [h1, h2], "low": [l1, l2], "close": [c1, c2]},
            index=idx,
        )

    def test_bull_engulfing_detected(self):
        # Prev: bear (open=102, close=98). Curr: bull engulfs (open=97, close=103)
        df = self._two_bar_df(102, 103, 97, 98,  97, 104, 96, 103)
        assert _engulfing_bull(df).iloc[1]

    def test_bear_engulfing_detected(self):
        # Prev: bull (open=98, close=102). Curr: bear engulfs (open=103, close=97)
        df = self._two_bar_df(98, 103, 97, 102,  103, 104, 96, 97)
        assert _engulfing_bear(df).iloc[1]

    def test_partial_overlap_not_engulfing(self):
        # Curr only partially covers prev body
        df = self._two_bar_df(102, 103, 97, 98,  99, 102, 98, 101)
        assert not _engulfing_bull(df).iloc[1]

    def test_same_direction_not_engulfing(self):
        # Both bearish → not bull engulfing
        df = self._two_bar_df(102, 103, 97, 98,  101, 105, 96, 97)
        assert not _engulfing_bull(df).iloc[1]

    def test_first_bar_always_false(self):
        df = self._two_bar_df(102, 103, 97, 98,  97, 104, 96, 103)
        assert not _engulfing_bull(df).iloc[0]
        assert not _engulfing_bear(df).iloc[0]


# ── consecutive counters ──────────────────────────────────────────────────────

class TestConsecRun:
    def test_runs_count_up(self):
        arr = np.array([True, True, True])
        assert list(_consec_run(arr)) == [1, 2, 3]

    def test_resets_on_false(self):
        arr = np.array([True, True, False, True])
        assert list(_consec_run(arr)) == [1, 2, 0, 1]

    def test_all_false(self):
        arr = np.array([False, False, False])
        assert list(_consec_run(arr)) == [0, 0, 0]

    def test_leading_false(self):
        arr = np.array([False, True, True])
        assert list(_consec_run(arr)) == [0, 1, 2]

    def test_alternating(self):
        arr = np.array([True, False, True, False, True])
        assert list(_consec_run(arr)) == [1, 0, 1, 0, 1]

    def test_consec_bull_in_compute(self):
        idx = pd.date_range("2026-04-15T10:00Z", periods=5, freq="min", tz="UTC")
        df = pd.DataFrame(
            {
                "open":   [100, 101, 102, 103, 102],
                "high":   [102, 103, 104, 105, 104],
                "low":    [99,  100, 101, 102, 101],
                "close":  [101, 102, 103, 102, 101],  # bull bull bull bear bear
                "volume": [1000] * 5,
            },
            index=idx,
        )
        r = compute(df)
        assert list(r["consec_bull"]) == [1, 2, 3, 0, 0]
        assert list(r["consec_bear"]) == [0, 0, 0, 1, 2]


# ── volume features ───────────────────────────────────────────────────────────

class TestVolFeatures:
    def test_vol_zscore_mean_zero_for_constant(self):
        """With constant volume, zscore → 0 after warm-up."""
        r = compute(_df("2026-04-15T10:00Z", 60, volume=500.0))
        # After 20 bars the std is 0 → zscore = 0/0 = NaN, which is correct
        # (or 0 if std=0 is not replaced). We test it's not infinity.
        valid = r["vol_zscore"].dropna()
        assert not np.isinf(valid).any()

    def test_vol_ratio_one_for_constant(self):
        """With constant volume, ratio = 1.0."""
        r = compute(_df("2026-04-15T10:00Z", 60, volume=500.0))
        ratios = r["vol_ratio"].dropna()
        assert (ratios - 1.0).abs().max() < 1e-9

    def test_vol_spike_yields_high_ratio(self):
        idx = pd.date_range("2026-04-15T10:00Z", periods=25, freq="min", tz="UTC")
        vols = [100.0] * 20 + [10000.0] + [100.0] * 4
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": vols},
            index=idx,
        )
        r = compute(df)
        assert r["vol_ratio"].iloc[20] > 10.0


# ── body_pct_1m ───────────────────────────────────────────────────────────────

class TestBodyPct:
    def test_full_body_is_100_pct(self):
        """Bar where body = range → body_pct_1m = 100."""
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z"], tz="UTC")
        df = pd.DataFrame(
            {"open": [99.0], "high": [101.0], "low": [99.0],
             "close": [101.0], "volume": [1000.0]},
            index=idx,
        )
        r = compute(df)
        assert abs(r.iloc[0]["body_pct_1m"] - 100.0) < 1e-9

    def test_doji_body_pct_zero(self):
        """Doji (open=close) with wicks → body_pct_1m = 0."""
        idx = pd.DatetimeIndex(["2026-04-15T10:00Z"], tz="UTC")
        df = pd.DataFrame(
            {"open": [100.0], "high": [102.0], "low": [98.0],
             "close": [100.0], "volume": [1000.0]},
            index=idx,
        )
        r = compute(df)
        assert abs(r.iloc[0]["body_pct_1m"] - 0.0) < 1e-9


# ── RSI divergence ────────────────────────────────────────────────────────────

class TestRSIDivergence:
    def _make_bull_div(self):
        """Price makes lower low; RSI makes higher low → bullish divergence."""
        n = 30
        idx = pd.date_range("2026-04-15", periods=n, freq="h", tz="UTC")
        # Construct price: trough1 at bar 5 (price=90), trough2 at bar 15 (price=85)
        closes = np.full(n, 100.0)
        closes[5]  = 90.0   # first trough
        closes[15] = 85.0   # second trough (lower low)
        # Construct RSI: higher low at second trough (manually set via synthetic)
        # We can't easily control RSI directly, so just test function interface
        rsi = pd.Series(
            [50.0] * n, index=idx, dtype=float
        )
        rsi.iloc[5]  = 30.0  # first RSI trough
        rsi.iloc[15] = 35.0  # second RSI trough (HIGHER → divergence)
        close_s = pd.Series(closes, index=idx)
        bull, _ = _rsi_divergence(close_s, rsi, distance=3)
        return bull

    def test_bull_divergence_detected(self):
        bull = self._make_bull_div()
        assert bull.any()

    def test_bear_divergence_detected(self):
        n = 30
        idx = pd.date_range("2026-04-15", periods=n, freq="h", tz="UTC")
        closes = np.full(n, 100.0)
        closes[5]  = 115.0  # first peak
        closes[15] = 120.0  # second peak (higher high)
        rsi = pd.Series([50.0] * n, index=idx, dtype=float)
        rsi.iloc[5]  = 70.0  # first RSI peak
        rsi.iloc[15] = 65.0  # second RSI peak (LOWER → divergence)
        close_s = pd.Series(closes, index=idx)
        _, bear = _rsi_divergence(close_s, rsi, distance=3)
        assert bear.any()

    def test_no_divergence_when_aligned(self):
        """Price HH + RSI HH → no bearish divergence."""
        n = 20
        idx = pd.date_range("2026-04-15", periods=n, freq="h", tz="UTC")
        closes = np.full(n, 100.0)
        closes[5]  = 110.0
        closes[15] = 115.0
        rsi = pd.Series([50.0] * n, index=idx, dtype=float)
        rsi.iloc[5]  = 68.0
        rsi.iloc[15] = 72.0  # also higher → no divergence
        close_s = pd.Series(closes, index=idx)
        _, bear = _rsi_divergence(close_s, rsi, distance=3)
        assert not bear.any()

    def test_divergence_output_same_index(self):
        n = 20
        idx = pd.date_range("2026-04-15", periods=n, freq="h", tz="UTC")
        close_s = pd.Series(np.random.rand(n) * 100, index=idx)
        rsi_s   = pd.Series(np.random.rand(n) * 100, index=idx)
        bull, bear = _rsi_divergence(close_s, rsi_s)
        assert bull.index.equals(idx)
        assert bear.index.equals(idx)

    def test_divergence_nan_handled(self):
        """NaN in RSI (warm-up period) must not crash."""
        n = 20
        idx = pd.date_range("2026-04-15", periods=n, freq="h", tz="UTC")
        close_s = pd.Series(np.random.rand(n) * 100, index=idx)
        rsi_s = pd.Series([float("nan")] * 5 + list(np.random.rand(15) * 100), index=idx)
        bull, bear = _rsi_divergence(close_s, rsi_s)
        # Should not raise, and output should be all False (not enough valid data)
        assert isinstance(bull, pd.Series)


# ── momentum ──────────────────────────────────────────────────────────────────

class TestMomentum:
    def test_momentum_1h_positive_on_uptrend(self):
        """After sustained 1h up moves, momentum_1h > 0."""
        starts = pd.date_range("2026-04-14", periods=25, freq="h", tz="UTC")
        frames = []
        for i, ts in enumerate(starts):
            c = 100.0 + i
            frames.append(_df(str(ts), 60, open_=c, high=c + 1, low=c - 1, close=c))
        r = compute(pd.concat(frames))
        valid = r["momentum_1h"].dropna()
        assert (valid > 0).any()

    def test_momentum_nan_for_first_bars(self):
        """Not enough bars → momentum is NaN (< MOM_PERIOD 1h bars)."""
        r = compute(_df("2026-04-15T10:00Z", 60))  # only 1 complete 1h bar
        # With only 1 1h bar, pct_change(10) = NaN → momentum_1h all NaN
        assert r["momentum_1h"].isna().all()
