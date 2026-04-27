"""Tests for src/features/derivatives.py."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.features.derivatives import (
    _FUNDING_EXTREME_LONG,
    _FUNDING_EXTREME_SHORT,
    _OI_DELTA_BARS,
    compute,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _idx(n: int, start: str = "2026-04-15T00:00Z", freq: str = "min") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq=freq, tz="UTC")


def _base_df(n: int, **col_overrides) -> pd.DataFrame:
    """Minimal df with all source columns at constant neutral values."""
    idx = _idx(n)
    data = {
        "open":   100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0,
        "oi_value":          1_000_000.0,
        "ls_ratio_top":      1.0,
        "ls_ratio_retail":   1.0,
        "taker_buy_volume":  500.0,
        "taker_sell_volume": 500.0,
        "funding_rate":      0.0001,
    }
    data.update(col_overrides)
    return pd.DataFrame({k: [v] * n for k, v in data.items()}, index=idx)


# ── schema ────────────────────────────────────────────────────────────────────

EXPECTED_COLS = [
    "oi_delta_1h", "oi_delta_pct_1h", "oi_zscore_24h",
    "funding_zscore", "funding_extreme_long", "funding_extreme_short",
    "ls_top_zscore", "ls_retail_zscore", "ls_divergence",
    "taker_imbalance", "taker_imbalance_zscore", "taker_buy_ratio",
]


class TestSchema:
    def test_all_12_columns_present(self):
        r = compute(_base_df(120))
        for col in EXPECTED_COLS:
            assert col in r.columns, f"Missing: {col}"

    def test_input_columns_preserved(self):
        r = compute(_base_df(60))
        assert "oi_value" in r.columns

    def test_empty_df_returns_empty(self):
        idx = pd.DatetimeIndex([], tz="UTC")
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []}, index=idx)
        r = compute(df)
        assert len(r) == 0

    def test_missing_source_columns_yield_nan(self):
        """df without derivatives columns → all derived features NaN/False."""
        idx = _idx(60)
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            index=idx,
        )
        r = compute(df)
        assert r["oi_delta_1h"].isna().all()
        assert r["taker_imbalance"].isna().all()
        assert r["ls_divergence"].isna().all()


# ── OI delta ──────────────────────────────────────────────────────────────────

class TestOIDelta:
    def test_oi_delta_1h_equals_diff_60(self):
        """oi_delta_1h = oi[i] - oi[i-60]."""
        n = _OI_DELTA_BARS + 10
        idx = _idx(n)
        # First 60 bars: OI = 1_000_000; then last 10 bars: OI = 1_100_000
        oi = [1_000_000.0] * _OI_DELTA_BARS + [1_100_000.0] * 10
        df = _base_df(n)
        df["oi_value"] = oi
        r = compute(df)
        # Bar at index 60: delta = 1_100_000 - 1_000_000 = 100_000
        assert abs(r["oi_delta_1h"].iloc[_OI_DELTA_BARS] - 100_000.0) < 1e-6

    def test_oi_delta_nan_before_60_bars(self):
        """First 60 bars have no prior window → delta is NaN."""
        r = compute(_base_df(70))
        assert r["oi_delta_1h"].iloc[:_OI_DELTA_BARS].isna().all()

    def test_oi_delta_zero_for_constant_oi(self):
        """Constant OI → delta = 0 after warmup."""
        r = compute(_base_df(120))
        deltas = r["oi_delta_1h"].iloc[_OI_DELTA_BARS:]
        assert (deltas == 0).all()

    def test_oi_delta_pct_correct(self):
        """oi_delta_pct_1h = (new - old) / old * 100."""
        n = _OI_DELTA_BARS + 5
        df = _base_df(n)
        oi = [1_000_000.0] * _OI_DELTA_BARS + [1_010_000.0] * 5
        df["oi_value"] = oi
        r = compute(df)
        # 10000 / 1000000 * 100 = 1.0%
        assert abs(r["oi_delta_pct_1h"].iloc[_OI_DELTA_BARS] - 1.0) < 1e-9

    def test_oi_delta_pct_nan_when_prev_oi_zero(self):
        """Division by zero when prev OI = 0 → NaN."""
        n = _OI_DELTA_BARS + 2
        df = _base_df(n)
        df["oi_value"] = [0.0] * _OI_DELTA_BARS + [100.0] * 2
        r = compute(df)
        assert math.isnan(r["oi_delta_pct_1h"].iloc[_OI_DELTA_BARS])

    def test_oi_zscore_nan_during_warmup(self):
        """OI zscore requires ≥ 2 observations in window → NaN for first bar."""
        r = compute(_base_df(5))
        assert math.isnan(r["oi_zscore_24h"].iloc[0])

    def test_oi_zscore_zero_for_constant(self):
        """Constant OI → zscore = 0 after std stabilizes (or NaN when std=0)."""
        r = compute(_base_df(200))
        # std = 0 for constant series → NaN (0/0 replaced with NaN)
        # zscore is NaN because std = 0
        valid = r["oi_zscore_24h"].dropna()
        if len(valid) > 0:
            assert (valid.abs() < 1e-9).all()


# ── funding ───────────────────────────────────────────────────────────────────

class TestFunding:
    def test_funding_extreme_long_true_above_threshold(self):
        df = _base_df(10, funding_rate=_FUNDING_EXTREME_LONG + 0.0001)
        r = compute(df)
        assert r["funding_extreme_long"].all()

    def test_funding_extreme_long_false_below_threshold(self):
        df = _base_df(10, funding_rate=0.0001)  # below +0.05%
        r = compute(df)
        assert not r["funding_extreme_long"].any()

    def test_funding_extreme_short_true_below_threshold(self):
        df = _base_df(10, funding_rate=_FUNDING_EXTREME_SHORT - 0.0001)
        r = compute(df)
        assert r["funding_extreme_short"].all()

    def test_funding_extreme_short_false_above_threshold(self):
        df = _base_df(10, funding_rate=0.0)
        r = compute(df)
        assert not r["funding_extreme_short"].any()

    def test_funding_zscore_high_for_outlier(self):
        """Sudden spike in funding → zscore should be strongly positive."""
        n = 200
        df = _base_df(n)
        # 190 bars normal, 10 bars extreme spike
        funding = [0.0001] * 190 + [0.01] * 10
        df["funding_rate"] = funding
        r = compute(df)
        # Last bars: zscore should be high
        assert r["funding_zscore"].iloc[-1] > 2.0

    def test_funding_zscore_nan_first_bar(self):
        r = compute(_base_df(5))
        assert math.isnan(r["funding_zscore"].iloc[0])


# ── L/S ratio ─────────────────────────────────────────────────────────────────

class TestLSRatio:
    def test_ls_divergence_positive_when_top_above_retail(self):
        df = _base_df(10, ls_ratio_top=2.0, ls_ratio_retail=1.5)
        r = compute(df)
        assert np.allclose(r["ls_divergence"], 0.5)

    def test_ls_divergence_negative_when_retail_above_top(self):
        df = _base_df(10, ls_ratio_top=1.0, ls_ratio_retail=1.8)
        r = compute(df)
        assert np.allclose(r["ls_divergence"], -0.8)

    def test_ls_divergence_zero_when_equal(self):
        df = _base_df(10, ls_ratio_top=1.5, ls_ratio_retail=1.5)
        r = compute(df)
        assert (r["ls_divergence"].abs() < 1e-9).all()

    def test_ls_top_zscore_high_for_outlier(self):
        """Sustained top-trader long skew → zscore > 0."""
        n = 200
        df = _base_df(n)
        ls_top = [1.0] * 100 + [3.0] * 100  # sudden jump
        df["ls_ratio_top"] = ls_top
        r = compute(df)
        assert r["ls_top_zscore"].iloc[-1] > 0

    def test_ls_missing_column_yields_nan_divergence(self):
        idx = _idx(10)
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
             "ls_ratio_top": 2.0},  # retail missing
            index=idx,
        )
        r = compute(df)
        assert r["ls_divergence"].isna().all()


# ── taker imbalance ───────────────────────────────────────────────────────────

class TestTakerImbalance:
    def test_imbalance_positive_when_buy_dominates(self):
        """(buy - sell) / total = (800-200)/1000 = 0.6."""
        df = _base_df(10, taker_buy_volume=800.0, taker_sell_volume=200.0)
        r = compute(df)
        assert np.allclose(r["taker_imbalance"], 0.6)

    def test_imbalance_negative_when_sell_dominates(self):
        df = _base_df(10, taker_buy_volume=200.0, taker_sell_volume=800.0)
        r = compute(df)
        assert np.allclose(r["taker_imbalance"], -0.6)

    def test_imbalance_zero_when_balanced(self):
        df = _base_df(10, taker_buy_volume=500.0, taker_sell_volume=500.0)
        r = compute(df)
        assert (r["taker_imbalance"].abs() < 1e-9).all()

    def test_imbalance_nan_when_total_zero(self):
        df = _base_df(10, taker_buy_volume=0.0, taker_sell_volume=0.0)
        r = compute(df)
        assert r["taker_imbalance"].isna().all()

    def test_taker_buy_ratio_range_0_to_1(self):
        df = _base_df(100)
        r = compute(df)
        valid = r["taker_buy_ratio"].dropna()
        assert (valid >= 0).all() and (valid <= 1).all()

    def test_taker_buy_ratio_formula(self):
        """buy / (buy + sell) = 700 / 1000 = 0.7."""
        df = _base_df(10, taker_buy_volume=700.0, taker_sell_volume=300.0)
        r = compute(df)
        assert np.allclose(r["taker_buy_ratio"], 0.7)

    def test_taker_imbalance_zscore_nan_first_bar(self):
        r = compute(_base_df(5))
        assert math.isnan(r["taker_imbalance_zscore"].iloc[0])

    def test_taker_imbalance_bounds_minus1_to_plus1(self):
        """Imbalance must be in [-1, +1] by construction."""
        n = 100
        rng = np.random.default_rng(42)
        idx = _idx(n)
        buy  = rng.uniform(0, 1000, n)
        sell = rng.uniform(0, 1000, n)
        df = _base_df(n)
        df["taker_buy_volume"]  = buy
        df["taker_sell_volume"] = sell
        r = compute(df)
        valid = r["taker_imbalance"].dropna()
        assert (valid >= -1.0).all() and (valid <= 1.0).all()
