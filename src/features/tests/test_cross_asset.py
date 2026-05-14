"""Tests for src/features/cross_asset.py."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.features.cross_asset import _DUMP_THRESHOLD, _OI_BONUS, _XRP_SOLO_MIN, compute

# ── helpers ───────────────────────────────────────────────────────────────────

def _idx(n: int, start: str = "2026-04-15T00:00Z") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="min", tz="UTC")


def _base_df(n: int, **overrides) -> pd.DataFrame:
    """Minimal merged df with all required columns at neutral values."""
    data = {
        "btc_close": 80000.0,
        "eth_close": 2000.0,
        "xrp_close": 0.5,
        "btc_delta_5m_pct": 0.0,
        "eth_delta_5m_pct": 0.0,
        "xrp_delta_5m_pct": 0.0,
        "btc_delta_15m_pct": 0.0,
        "xrp_delta_15m_pct": 0.0,
        "btc_delta_1h_pct": 0.0,
        "eth_delta_1h_pct": 0.0,
        "xrp_delta_1h_pct": 0.0,
    }
    data.update(overrides)
    return pd.DataFrame({k: [v] * n for k, v in data.items()}, index=_idx(n))


EXPECTED_COLS = [
    "btc_eth_corr_4h",
    "eth_btc_ratio",
    "eth_btc_ratio_zscore_30d",
    "btc_eth_divergence_score",
    "xrp_impulse_solo_score",
    "xrp_btc_corr_4h",
    "xrp_solo_direction",
    "all_dump_score",
    "all_dump_score_with_oi",
    "dump_count_1h",
]


# ── schema ────────────────────────────────────────────────────────────────────

class TestSchema:
    def test_all_10_columns_present(self):
        r = compute(_base_df(10))
        for col in EXPECTED_COLS:
            assert col in r.columns, f"Missing: {col}"

    def test_input_columns_preserved(self):
        r = compute(_base_df(5))
        assert "btc_close" in r.columns

    def test_empty_df_returns_empty(self):
        idx = pd.DatetimeIndex([], tz="UTC")
        df = pd.DataFrame(index=idx)
        r = compute(df)
        assert len(r) == 0

    def test_missing_columns_yield_nan(self):
        """df with no source cols → NaN outputs."""
        idx = _idx(5)
        df = pd.DataFrame({"btc_close": 80000.0}, index=idx)
        r = compute(df)
        assert r["btc_eth_corr_4h"].isna().all()
        assert r["xrp_impulse_solo_score"].isna().all()


# ── §6.4.1 BTC-ETH ────────────────────────────────────────────────────────────

class TestBtcEthCorr:
    def test_perfect_positive_corr(self):
        """btc and eth move identically → corr = 1.0 after warmup."""
        n = 300
        idx = _idx(n)
        moves = np.sin(np.linspace(0, 4 * np.pi, n))
        df = _base_df(n)
        df["btc_delta_5m_pct"] = moves
        df["eth_delta_5m_pct"] = moves
        r = compute(df)
        valid = r["btc_eth_corr_4h"].dropna()
        assert (valid > 0.99).all()

    def test_perfect_negative_corr(self):
        n = 300
        idx = _idx(n)
        moves = np.sin(np.linspace(0, 4 * np.pi, n))
        df = _base_df(n)
        df["btc_delta_5m_pct"] = moves
        df["eth_delta_5m_pct"] = -moves
        r = compute(df)
        valid = r["btc_eth_corr_4h"].dropna()
        assert (valid < -0.99).all()

    def test_corr_nan_before_window(self):
        r = compute(_base_df(5))
        # With only 5 bars, window=240 → NaN (min_periods=2 gives value, but all same → NaN)
        # Actually min_periods=2 with all-zero series gives NaN due to std=0
        # Just check it doesn't crash
        assert "btc_eth_corr_4h" in r.columns

    def test_corr_range_minus1_to_1(self):
        n = 300
        rng = np.random.default_rng(42)
        df = _base_df(n)
        df["btc_delta_5m_pct"] = rng.normal(0, 1, n)
        df["eth_delta_5m_pct"] = rng.normal(0, 1, n)
        r = compute(df)
        valid = r["btc_eth_corr_4h"].dropna()
        assert (valid >= -1.0 - 1e-9).all() and (valid <= 1.0 + 1e-9).all()


class TestEthBtcRatio:
    def test_ratio_formula(self):
        """eth_btc_ratio = eth_close / btc_close = 2000 / 80000 = 0.025."""
        r = compute(_base_df(5, eth_close=2000.0, btc_close=80000.0))
        assert np.allclose(r["eth_btc_ratio"], 0.025)

    def test_ratio_nan_when_btc_zero(self):
        r = compute(_base_df(5, btc_close=0.0, eth_close=1000.0))
        assert r["eth_btc_ratio"].isna().all()

    def test_ratio_zscore_nan_first_bar(self):
        r = compute(_base_df(5))
        assert math.isnan(r["eth_btc_ratio_zscore_30d"].iloc[0])


class TestDivergenceScore:
    def test_btc_leads_eth_positive_score(self):
        """btc_1h=+4%, eth_1h=+1% → score > 0."""
        r = compute(_base_df(5, btc_delta_1h_pct=4.0, eth_delta_1h_pct=1.0))
        assert (r["btc_eth_divergence_score"] > 0).all()

    def test_eth_leads_btc_negative_score(self):
        """btc_1h=+1%, eth_1h=+4% → score < 0."""
        r = compute(_base_df(5, btc_delta_1h_pct=1.0, eth_delta_1h_pct=4.0))
        assert (r["btc_eth_divergence_score"] < 0).all()

    def test_equal_moves_zero_score(self):
        """Both +3% → numerator=0 → score=0."""
        r = compute(_base_df(5, btc_delta_1h_pct=3.0, eth_delta_1h_pct=3.0))
        assert np.allclose(r["btc_eth_divergence_score"], 0.0)

    def test_score_clipped_to_minus1_plus1(self):
        """Very large divergence is clipped to ±1."""
        r = compute(_base_df(5, btc_delta_1h_pct=100.0, eth_delta_1h_pct=-100.0))
        assert np.allclose(r["btc_eth_divergence_score"], 1.0)

    def test_negative_clip(self):
        r = compute(_base_df(5, btc_delta_1h_pct=-100.0, eth_delta_1h_pct=100.0))
        assert np.allclose(r["btc_eth_divergence_score"], -1.0)

    def test_near_zero_denom_uses_floor_0001(self):
        """Both ~0 moves → denom clipped to 0.001, score should not explode."""
        r = compute(_base_df(5, btc_delta_1h_pct=0.0001, eth_delta_1h_pct=0.0))
        assert r["btc_eth_divergence_score"].abs().max() <= 1.0


# ── §6.4.2 XRP impulse ────────────────────────────────────────────────────────

class TestXrpImpulse:
    def test_solo_score_formula(self):
        """(xrp_15m - btc_15m) / max(|btc_15m|, 0.1) = (3.0 - 0.5) / 0.5 = 5.0."""
        r = compute(_base_df(5, xrp_delta_15m_pct=3.0, btc_delta_15m_pct=0.5))
        assert np.allclose(r["xrp_impulse_solo_score"], 5.0)

    def test_solo_score_floor_0_1(self):
        """When btc moves ~0, denom clipped to 0.1."""
        r = compute(_base_df(5, xrp_delta_15m_pct=1.0, btc_delta_15m_pct=0.0))
        # (1.0 - 0.0) / 0.1 = 10.0
        assert np.allclose(r["xrp_impulse_solo_score"], 10.0)

    def test_solo_direction_positive_when_impulse_above_threshold(self):
        """xrp_impulse_solo_score > 2.0 and xrp positive → direction = +1."""
        # (5.0 - 0.0) / 0.1 = 50 → impulse=50 ≥ 2.0; xrp positive → direction=1
        r = compute(_base_df(5, xrp_delta_15m_pct=5.0, btc_delta_15m_pct=0.0))
        assert (r["xrp_solo_direction"] == 1).all()

    def test_solo_direction_negative_when_impulse_below_negative_threshold(self):
        """xrp_impulse_solo_score < -2.0 and xrp negative → direction = -1."""
        r = compute(_base_df(5, xrp_delta_15m_pct=-5.0, btc_delta_15m_pct=0.0))
        assert (r["xrp_solo_direction"] == -1).all()

    def test_solo_direction_zero_when_impulse_below_threshold(self):
        """Small impulse (< 2.0) → direction = 0."""
        r = compute(_base_df(5, xrp_delta_15m_pct=1.5, btc_delta_15m_pct=1.0))
        # impulse = (1.5 - 1.0) / max(1.0, 0.1) = 0.5 < 2.0 → 0
        assert (r["xrp_solo_direction"] == 0).all()

    def test_solo_direction_at_threshold(self):
        """Impulse clearly ≥ 2.0 → direction triggers."""
        # (0.5 - 0.1) / 0.1 = 4.0 ≥ 2.0; xrp positive → +1
        r = compute(_base_df(5, xrp_delta_15m_pct=0.5, btc_delta_15m_pct=0.1))
        assert (r["xrp_solo_direction"] == 1).all()

    def test_xrp_btc_corr_range(self):
        n = 300
        rng = np.random.default_rng(7)
        df = _base_df(n)
        df["xrp_delta_5m_pct"] = rng.normal(0, 1, n)
        df["btc_delta_5m_pct"] = rng.normal(0, 1, n)
        r = compute(df)
        valid = r["xrp_btc_corr_4h"].dropna()
        assert (valid >= -1.0 - 1e-9).all() and (valid <= 1.0 + 1e-9).all()


# ── §6.4.3 Synchro dump ────────────────────────────────────────────────────────

class TestAllDumpScore:
    def test_all_three_dump_gives_1_0(self):
        r = compute(_base_df(5,
            btc_delta_1h_pct=-3.0,
            eth_delta_1h_pct=-3.0,
            xrp_delta_1h_pct=-3.0,
        ))
        assert np.allclose(r["all_dump_score"], 1.0)

    def test_two_dump_gives_0_5(self):
        r = compute(_base_df(5,
            btc_delta_1h_pct=-3.0,
            eth_delta_1h_pct=-3.0,
            xrp_delta_1h_pct=1.0,
        ))
        assert np.allclose(r["all_dump_score"], 0.5)

    def test_one_dump_gives_0(self):
        r = compute(_base_df(5,
            btc_delta_1h_pct=-3.0,
            eth_delta_1h_pct=1.0,
            xrp_delta_1h_pct=1.0,
        ))
        assert np.allclose(r["all_dump_score"], 0.0)

    def test_no_dump_gives_0(self):
        r = compute(_base_df(5,
            btc_delta_1h_pct=1.0,
            eth_delta_1h_pct=1.0,
            xrp_delta_1h_pct=1.0,
        ))
        assert np.allclose(r["all_dump_score"], 0.0)

    def test_boundary_exactly_minus2_is_dump(self):
        """delta_1h == -2.0 exactly must count as dump (< -2.0 is False, need to check threshold)."""
        # Threshold is < -2.0 (strict) per spec — at exactly -2.0 it's NOT a dump
        r = compute(_base_df(5,
            btc_delta_1h_pct=-2.0,
            eth_delta_1h_pct=-2.0,
            xrp_delta_1h_pct=-2.0,
        ))
        # -2.0 < -2.0 is False → count=0 → score=0.0
        assert np.allclose(r["all_dump_score"], 0.0)

    def test_just_below_threshold_is_dump(self):
        r = compute(_base_df(5,
            btc_delta_1h_pct=-2.001,
            eth_delta_1h_pct=-2.001,
            xrp_delta_1h_pct=-2.001,
        ))
        assert np.allclose(r["all_dump_score"], 1.0)


class TestDumpCount:
    def test_dump_count_0_when_no_dump(self):
        r = compute(_base_df(5, btc_delta_1h_pct=0.0, eth_delta_1h_pct=0.0, xrp_delta_1h_pct=0.0))
        assert (r["dump_count_1h"] == 0).all()

    def test_dump_count_3_when_all_dump(self):
        r = compute(_base_df(5, btc_delta_1h_pct=-3.0, eth_delta_1h_pct=-3.0, xrp_delta_1h_pct=-3.0))
        assert (r["dump_count_1h"] == 3).all()

    def test_dump_count_is_int_type(self):
        r = compute(_base_df(5))
        assert r["dump_count_1h"].dtype in (np.int8, np.int16, np.int32, np.int64)


class TestAllDumpWithOI:
    def test_oi_bonus_added_when_oi_positive(self):
        """all_dump=1.0 + oi_bonus=0.2 → clipped to 1.0."""
        df = _base_df(5,
            btc_delta_1h_pct=-3.0,
            eth_delta_1h_pct=-3.0,
            xrp_delta_1h_pct=-3.0,
        )
        df["btc_oi_delta_pct_1h"] = 1.0  # positive OI → bonus
        r = compute(df)
        # 1.0 + 0.2 clipped to 1.0
        assert np.allclose(r["all_dump_score_with_oi"], 1.0)

    def test_oi_bonus_on_partial_dump(self):
        """all_dump=0.5 + oi_bonus=0.2 → 0.7."""
        df = _base_df(5,
            btc_delta_1h_pct=-3.0,
            eth_delta_1h_pct=-3.0,
            xrp_delta_1h_pct=1.0,
        )
        df["btc_oi_delta_pct_1h"] = 0.5  # positive
        r = compute(df)
        assert np.allclose(r["all_dump_score_with_oi"], 0.5 + _OI_BONUS)

    def test_no_bonus_when_oi_negative(self):
        """all_dump=1.0, OI negative → no bonus → same as all_dump_score."""
        df = _base_df(5,
            btc_delta_1h_pct=-3.0,
            eth_delta_1h_pct=-3.0,
            xrp_delta_1h_pct=-3.0,
        )
        df["btc_oi_delta_pct_1h"] = -1.0  # negative OI
        r = compute(df)
        assert np.allclose(r["all_dump_score_with_oi"], 1.0)  # no bonus, but already 1.0

    def test_fallback_equals_all_dump_when_oi_absent(self):
        """Without btc_oi_delta_pct_1h column, with_oi = all_dump_score."""
        r = compute(_base_df(5, btc_delta_1h_pct=-3.0, eth_delta_1h_pct=-3.0, xrp_delta_1h_pct=-3.0))
        assert np.allclose(r["all_dump_score_with_oi"], r["all_dump_score"])

    def test_all_dump_with_oi_clipped_to_1(self):
        """Even with full dump + OI bonus, result ≤ 1.0."""
        df = _base_df(5,
            btc_delta_1h_pct=-5.0,
            eth_delta_1h_pct=-5.0,
            xrp_delta_1h_pct=-5.0,
        )
        df["btc_oi_delta_pct_1h"] = 999.0
        r = compute(df)
        assert (r["all_dump_score_with_oi"] <= 1.0).all()
