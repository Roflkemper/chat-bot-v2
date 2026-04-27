"""Tests for src/features/dwm.py.

Acceptance criteria per §10, §11.4 and operator spec.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.features.dwm import compute


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_df(timestamps: list[str], highs=None, lows=None, closes=None, opens=None) -> pd.DataFrame:
    idx = pd.DatetimeIndex(timestamps, tz="UTC")
    n = len(idx)
    return pd.DataFrame(
        {
            "open":   opens  if opens  is not None else [100.0] * n,
            "high":   highs  if highs  is not None else [101.0] * n,
            "low":    lows   if lows   is not None else [99.0]  * n,
            "close":  closes if closes is not None else [100.0] * n,
        },
        index=idx,
    )


def _minute_range(start: str, periods: int) -> list[str]:
    return [str(t) for t in pd.date_range(start, periods=periods, freq="min", tz="UTC")]


# ── warmup: NaN before first UTC midnight ─────────────────────────────────────

class TestWarmup:
    def test_pdh_nan_before_first_midnight(self):
        # 3 bars on 2026-04-14 before midnight — no previous day yet
        ts = _minute_range("2026-04-14T23:57:00Z", 3)
        r = compute(_make_df(ts))
        assert r["pdh"].isna().all()

    def test_pdl_nan_before_first_midnight(self):
        ts = _minute_range("2026-04-14T23:57:00Z", 3)
        r = compute(_make_df(ts))
        assert r["pdl"].isna().all()

    def test_pwh_nan_before_first_monday(self):
        # 2026-04-15 is Wednesday — week boundary hasn't fired yet
        ts = _minute_range("2026-04-15T10:00:00Z", 5)
        r = compute(_make_df(ts))
        assert r["pwh"].isna().all()

    def test_pmh_nan_before_first_month_boundary(self):
        # 2026-04-15 is mid-month — month boundary hasn't fired yet
        ts = _minute_range("2026-04-15T10:00:00Z", 5)
        r = compute(_make_df(ts))
        assert r["pmh"].isna().all()

    def test_d_open_nan_before_first_midnight(self):
        ts = _minute_range("2026-04-14T23:57:00Z", 3)
        r = compute(_make_df(ts))
        assert r["d_open"].isna().all()

    def test_d_open_set_at_midnight(self):
        # bar at 2026-04-15 00:00 should have d_open = open of that bar
        ts = ["2026-04-15T00:00:00Z"]
        r = compute(_make_df(ts, opens=[55.0], highs=[56.0], lows=[54.0], closes=[55.0]))
        assert r.iloc[0]["d_open"] == 55.0


# ── day boundary at 00:00 UTC ─────────────────────────────────────────────────

class TestDayBoundary:
    def test_pdh_equals_previous_day_max_high(self):
        """PDH at day 2 start = max(high) of day 1."""
        # Day 1: 3 bars with highs 102, 105, 103
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z", "2026-04-15T00:01:00Z"]
        ts = d1 + d2
        highs = [102.0, 105.0, 103.0, 99.0, 99.0]
        r = compute(_make_df(ts, highs=highs))
        # pdh at 00:00 on day 2 = 105
        assert r.loc["2026-04-15T00:00:00+00:00", "pdh"] == 105.0

    def test_pdl_equals_previous_day_min_low(self):
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        lows = [98.0, 95.0, 97.0, 99.0]
        r = compute(_make_df(ts, lows=lows))
        assert r.loc["2026-04-15T00:00:00+00:00", "pdl"] == 95.0

    def test_pdh_does_not_include_current_day_open_bar(self):
        """At 00:00, pdh = yesterday's max, NOT current bar's high."""
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        # Yesterday's max = 102, current 00:00 bar high = 200
        highs = [102.0, 101.0, 100.0, 200.0]
        r = compute(_make_df(ts, highs=highs))
        # pdh at 00:00 should be 102, not 200
        assert r.loc["2026-04-15T00:00:00+00:00", "pdh"] == 102.0

    def test_pdh_updates_on_each_day_boundary(self):
        """Second day's pdh = first day's max, third day's pdh = second day's max."""
        # Day1: 22:00–23:59 (2 bars, high 100/105)
        d1 = ["2026-04-13T22:00:00Z", "2026-04-13T23:00:00Z"]
        # Day2 00:00 + one bar during day2 (high 200)
        d2 = ["2026-04-14T00:00:00Z", "2026-04-14T10:00:00Z"]
        # Day3 00:00
        d3 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2 + d3
        highs = [100.0, 105.0, 99.0, 200.0, 99.0]
        r = compute(_make_df(ts, highs=highs))
        assert r.loc["2026-04-14T00:00:00+00:00", "pdh"] == 105.0
        assert r.loc["2026-04-15T00:00:00+00:00", "pdh"] == 200.0

    def test_pdh_fires_at_0000_not_earlier(self):
        """23:59 bar still has pdh=NaN if no prior midnight crossed."""
        ts = ["2026-04-14T23:58:00Z", "2026-04-14T23:59:00Z"]
        r = compute(_make_df(ts))
        assert r["pdh"].isna().all()


# ── week boundary: Monday 00:00 UTC ──────────────────────────────────────────

class TestWeekBoundary:
    def test_pwh_fires_on_monday_not_sunday(self):
        """PWH fires at Monday 00:00, not Sunday 00:00."""
        # 2026-04-19 = Sunday, 2026-04-20 = Monday
        sun_bars = _minute_range("2026-04-19T22:00:00Z", 3)
        mon = ["2026-04-20T00:00:00Z"]
        ts = sun_bars + mon
        highs = [120.0, 125.0, 122.0, 99.0]
        r = compute(_make_df(ts, highs=highs))
        # Sunday 00:00 would be 2026-04-19 00:00 — not in this range
        # Monday 00:00 pwh = max of previous week (includes Sunday bars)
        assert not math.isnan(r.loc["2026-04-20T00:00:00+00:00", "pwh"])
        assert r.loc["2026-04-20T00:00:00+00:00", "pwh"] == 125.0

    def test_pwh_nan_before_first_monday(self):
        # Wednesday — no Monday has fired yet in this data slice
        ts = _minute_range("2026-04-15T10:00:00Z", 3)
        r = compute(_make_df(ts))
        assert r["pwh"].isna().all()

    def test_sunday_00_utc_is_not_week_boundary(self):
        """Sunday 00:00 should NOT fire week boundary."""
        # 2026-04-19 is Sunday
        ts = ["2026-04-19T00:00:00Z"]
        r = compute(_make_df(ts))
        assert math.isnan(r.iloc[0]["pwh"])


# ── month boundary: 1st 00:00 UTC ────────────────────────────────────────────

class TestMonthBoundary:
    def test_pmh_fires_on_first_of_month(self):
        # End of April → May 1
        apr_bars = _minute_range("2026-04-30T22:00:00Z", 3)
        may1 = ["2026-05-01T00:00:00Z"]
        ts = apr_bars + may1
        highs = [300.0, 310.0, 305.0, 99.0]
        r = compute(_make_df(ts, highs=highs))
        assert r.loc["2026-05-01T00:00:00+00:00", "pmh"] == 310.0

    def test_pmh_nan_before_first_month_boundary(self):
        ts = _minute_range("2026-04-15T10:00:00Z", 3)
        r = compute(_make_df(ts))
        assert r["pmh"].isna().all()


# ── hit flags ─────────────────────────────────────────────────────────────────

class TestHitFlags:
    def _build_hit_scenario(self):
        """Day1: high peaks at 105. Day2: pdh=105. We breach it mid-day."""
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        # Day2: 00:00 + 2 bars below, then 1 bar that breaches pdh
        d2 = ["2026-04-15T00:00:00Z", "2026-04-15T00:01:00Z",
               "2026-04-15T00:02:00Z", "2026-04-15T00:03:00Z"]
        ts = d1 + d2
        highs  = [102.0, 105.0, 103.0,  99.0, 99.0, 104.0, 106.0]
        lows   = [98.0,  98.0,  98.0,   97.0, 97.0, 97.0,  97.0 ]
        closes = [100.0, 104.0, 102.0, 100.0, 100.0, 103.0, 105.5]
        return compute(_make_df(ts, highs=highs, lows=lows, closes=closes))

    def test_pdh_hit_false_before_breach(self):
        r = self._build_hit_scenario()
        # bars 3 and 4 (00:00 and 00:01) — not yet breached
        assert not r.iloc[3]["pdh_hit"]
        assert not r.iloc[4]["pdh_hit"]

    def test_pdh_hit_true_after_breach(self):
        r = self._build_hit_scenario()
        # bar 6 (00:03): high=106 > pdh=105 → hit
        assert r.iloc[6]["pdh_hit"]

    def test_pdh_hit_cumulative_stays_true(self):
        # Once True, stays True until next day boundary
        d1 = _minute_range("2026-04-14T22:00:00Z", 2)
        d2 = ["2026-04-15T00:00:00Z", "2026-04-15T00:01:00Z",
               "2026-04-15T00:02:00Z", "2026-04-15T00:03:00Z"]
        ts = d1 + d2
        highs  = [105.0, 103.0, 99.0, 106.0, 99.0, 99.0]
        closes = [104.0, 102.0, 98.0, 100.0, 98.0, 98.0]
        r = compute(_make_df(ts, highs=highs, closes=closes))
        # After breach at bar 3, bars 4 and 5 should still be True
        assert r.iloc[3]["pdh_hit"]
        assert r.iloc[4]["pdh_hit"]
        assert r.iloc[5]["pdh_hit"]

    def test_pdh_hit_resets_at_day_boundary(self):
        """Hit flag resets to False at each new day boundary."""
        d1 = _minute_range("2026-04-14T22:00:00Z", 2)
        d2 = ["2026-04-15T00:00:00Z", "2026-04-15T06:00:00Z"]
        d3 = ["2026-04-16T00:00:00Z"]
        ts = d1 + d2 + d3
        highs  = [105.0, 103.0, 99.0, 106.0, 99.0]
        closes = [104.0, 102.0, 98.0, 100.0, 98.0]
        r = compute(_make_df(ts, highs=highs, closes=closes))
        # bar 3 (15th 06:00) has pdh_hit True (hit earlier)
        assert r.iloc[3]["pdh_hit"]
        # bar 4 (16th 00:00): new day boundary, pdh changes → reset False
        assert not r.iloc[4]["pdh_hit"]


# ── current_d_high / current_d_low ────────────────────────────────────────────

class TestCurrentDayHL:
    def test_current_d_high_is_cummax_within_day(self):
        """current_d_high grows monotonically within the day."""
        d1 = _minute_range("2026-04-14T23:59:00Z", 1)  # seed previous day
        d2 = _minute_range("2026-04-15T00:00:00Z", 5)
        ts = d1 + d2
        highs = [90.0, 100.0, 105.0, 103.0, 107.0, 104.0]
        r = compute(_make_df(ts, highs=highs))
        day2 = r.iloc[1:]
        assert list(day2["current_d_high"]) == [100.0, 105.0, 105.0, 107.0, 107.0]

    def test_current_d_low_is_cummin_within_day(self):
        d1 = _minute_range("2026-04-14T23:59:00Z", 1)
        d2 = _minute_range("2026-04-15T00:00:00Z", 5)
        ts = d1 + d2
        lows = [110.0, 99.0, 97.0, 98.0, 96.0, 97.0]
        r = compute(_make_df(ts, lows=lows))
        day2 = r.iloc[1:]
        assert list(day2["current_d_low"]) == [99.0, 97.0, 97.0, 96.0, 96.0]

    def test_current_d_high_resets_at_midnight(self):
        """At 00:00, current_d_high = high of that opening bar, not yesterday's max."""
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        # Yesterday: high up to 200; today 00:00 bar high = 50
        highs = [200.0, 200.0, 200.0, 50.0]
        r = compute(_make_df(ts, highs=highs))
        assert r.iloc[3]["current_d_high"] == 50.0

    def test_dist_to_d_high_pct(self):
        """dist_to_d_high_pct = (current_d_high - close) / close * 100."""
        d1 = _minute_range("2026-04-14T23:59:00Z", 1)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        highs = [90.0, 110.0]
        closes = [90.0, 100.0]
        r = compute(_make_df(ts, highs=highs, closes=closes))
        # current_d_high=110, close=100 → (110-100)/100*100 = 10.0
        assert abs(r.iloc[1]["dist_to_d_high_pct"] - 10.0) < 1e-9

    def test_dist_to_d_low_pct(self):
        """dist_to_d_low_pct = (close - current_d_low) / close * 100."""
        d1 = _minute_range("2026-04-14T23:59:00Z", 1)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        lows = [110.0, 90.0]
        closes = [110.0, 100.0]
        r = compute(_make_df(ts, lows=lows, closes=closes))
        # current_d_low=90, close=100 → (100-90)/100*100 = 10.0
        assert abs(r.iloc[1]["dist_to_d_low_pct"] - 10.0) < 1e-9


# ── PDH/PDL sweep ─────────────────────────────────────────────────────────────

class TestPDHSweep:
    def _build_sweep_df(self, pdh_override=105.0, pdl_override=95.0):
        """
        Day1: two bars with highs to set pdh=105, lows to set pdl=95.
        Day2: 00:00 sets pdh/pdl, then intraday bars for sweep testing.
        """
        d1 = ["2026-04-14T22:00:00Z", "2026-04-14T23:00:00Z"]
        # Day2 bars: 00:00 + intraday
        d2 = _minute_range("2026-04-15T00:00:00Z", 10)
        ts = d1 + d2
        # Day1: set pdh/pdl precisely
        h1 = [pdh_override, 100.0]
        l1 = [pdl_override, 100.0]
        c1 = [100.0, 100.0]
        o1 = [100.0, 100.0]
        # Day2: first bar has high/low/close 100 (neutral)
        h2 = [100.0] * 10
        l2 = [100.0] * 10
        c2 = [100.0] * 10
        o2 = [100.0] * 10
        return (
            ts,
            [*o1, *o2],
            [*h1, *h2],
            [*l1, *l2],
            [*c1, *c2],
        )

    def test_pdh_sweep_same_bar_wick(self):
        """High exceeds PDH but close is back below → same-bar wick sweep."""
        ts, o, h, lo, cl = self._build_sweep_df()
        # Bar index 3 (day2 bar 1, 00:01): wick through pdh=105, close=104.9
        h[3] = 105.5
        cl[3] = 104.9
        lo[3] = 103.0
        r = compute(_make_df(ts, highs=h, lows=lo, closes=cl, opens=o))
        assert r.iloc[3]["pdh_sweep"]

    def test_pdh_sweep_false_before_wick(self):
        ts, o, h, lo, cl = self._build_sweep_df()
        h[3] = 105.5
        cl[3] = 104.9
        r = compute(_make_df(ts, highs=h, lows=lo, closes=cl, opens=o))
        # bar 2 (00:00) — no breach yet
        assert not r.iloc[2]["pdh_sweep"]

    def test_pdh_sweep_not_triggered_when_close_above(self):
        """High exceeds PDH and close stays above → breach only, no sweep (phase 1, wait)."""
        ts, o, h, lo, cl = self._build_sweep_df()
        # All bars: high > pdh but close stays above pdh (no return within Y)
        for i in range(2, len(ts)):
            h[i] = 106.0
            cl[i] = 105.5
        r = compute(_make_df(ts, highs=h, lows=lo, closes=cl, opens=o))
        # No return → no sweep
        assert not r.iloc[-1]["pdh_sweep"]

    def test_pdl_sweep_same_bar_wick(self):
        """Low exceeds PDL (downward) but close is back above → same-bar wick sweep."""
        ts, o, h, lo, cl = self._build_sweep_df()
        # Bar index 3 (day2 bar 1): wick through pdl=95, close=95.1
        lo[3] = 94.5
        cl[3] = 95.1
        h[3] = 97.0
        r = compute(_make_df(ts, highs=h, lows=lo, closes=cl, opens=o))
        assert r.iloc[3]["pdl_sweep"]

    def test_pdh_sweep_return_within_Y(self):
        """High breaches PDH, close returns below PDH within 30 min → sweep confirmed."""
        ts, o, h, lo, cl = self._build_sweep_df()
        # Bar i=2 (00:00): breach, close above pdh
        h[2] = 106.0
        cl[2] = 105.5
        # Bar i=3 (00:01): close drops back below pdh=105 → within Y=30min
        cl[3] = 104.5
        h[3] = 105.2
        r = compute(_make_df(ts, highs=h, lows=lo, closes=cl, opens=o))
        assert r.iloc[3]["pdh_sweep"]

    def test_pdh_sweep_resets_on_new_day(self):
        """PDH sweep flag resets at day boundary."""
        d1 = ["2026-04-14T22:00:00Z", "2026-04-14T23:00:00Z"]
        d2 = _minute_range("2026-04-15T00:00:00Z", 5)
        d3 = ["2026-04-16T00:00:00Z"]
        ts = d1 + d2 + d3
        n = len(ts)
        h  = [105.0, 100.0] + [106.0, 104.9, 100.0, 100.0, 100.0] + [100.0]
        lo = [100.0] * n
        cl = [100.0, 100.0] + [104.9, 100.0, 100.0, 100.0, 100.0] + [100.0]
        o  = [100.0] * n
        r = compute(_make_df(ts, highs=h, lows=lo, closes=cl, opens=o))
        # Day2: sweep confirmed
        assert r.iloc[2]["pdh_sweep"]
        # Day3 boundary: new day → sweep resets
        assert not r.iloc[-1]["pdh_sweep"]


# ── distance features ─────────────────────────────────────────────────────────

class TestDistanceFeatures:
    def _two_day_df(self):
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        return ts

    def test_dist_to_pdh_pct(self):
        """dist_to_pdh = (pdh - close) / close * 100."""
        ts = self._two_day_df()
        highs  = [110.0, 108.0, 106.0, 100.0]
        closes = [105.0, 104.0, 103.0, 100.0]
        r = compute(_make_df(ts, highs=highs, closes=closes))
        # pdh = 110, close = 100 → (110-100)/100*100 = 10.0
        assert abs(r.iloc[3]["dist_to_pdh_pct"] - 10.0) < 1e-9

    def test_dist_to_pdl_pct(self):
        """dist_to_pdl = (close - pdl) / close * 100."""
        ts = self._two_day_df()
        lows   = [90.0, 92.0, 91.0, 100.0]
        closes = [95.0, 94.0, 93.0, 100.0]
        r = compute(_make_df(ts, lows=lows, closes=closes))
        # pdl = 90, close = 100 → (100-90)/100*100 = 10.0
        assert abs(r.iloc[3]["dist_to_pdl_pct"] - 10.0) < 1e-9

    def test_dist_to_d_open_pct(self):
        """dist_to_d_open = (close - d_open) / d_open * 100."""
        ts = ["2026-04-15T00:00:00Z", "2026-04-15T00:01:00Z"]
        opens  = [100.0, 100.0]
        closes = [100.0, 105.0]
        highs  = [101.0, 106.0]
        lows   = [99.0,  104.0]
        r = compute(_make_df(ts, highs=highs, lows=lows, closes=closes, opens=opens))
        # d_open=100, close=105 → (105-100)/100*100 = 5.0
        assert abs(r.iloc[1]["dist_to_d_open_pct"] - 5.0) < 1e-9

    def test_dist_nan_when_level_nan(self):
        """dist columns are NaN when the underlying level is NaN."""
        ts = _minute_range("2026-04-15T10:00:00Z", 3)
        r = compute(_make_df(ts))
        assert r["dist_to_pdh_pct"].isna().all()
        assert r["dist_to_pdl_pct"].isna().all()


# ── column completeness ───────────────────────────────────────────────────────

class TestOutputSchema:
    EXPECTED_COLS = [
        "d_open", "w_open", "m_open",
        "pdh", "pdl", "pwh", "pwl", "pmh", "pml",
        "pdh_hit", "pdl_hit", "pwh_hit", "pwl_hit", "pmh_hit", "pml_hit",
        "current_d_high", "current_d_low",
        "pdh_sweep", "pdl_sweep",
        "dist_to_pdh_pct", "dist_to_pdl_pct",
        "dist_to_pwh_pct", "dist_to_pwl_pct",
        "dist_to_pmh_pct", "dist_to_pml_pct",
        "dist_to_d_open_pct", "dist_to_w_open_pct", "dist_to_m_open_pct",
        "dist_to_d_high_pct", "dist_to_d_low_pct",
    ]

    def test_all_columns_present(self):
        ts = _minute_range("2026-04-15T00:00:00Z", 5)
        r = compute(_make_df(ts))
        for col in self.EXPECTED_COLS:
            assert col in r.columns, f"Missing column: {col}"

    def test_input_columns_preserved(self):
        ts = _minute_range("2026-04-15T00:00:00Z", 3)
        df = _make_df(ts)
        r = compute(df)
        for col in ["open", "high", "low", "close"]:
            assert col in r.columns

    def test_empty_df_returns_empty(self):
        idx = pd.DatetimeIndex([], tz="UTC")
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": []}, index=idx)
        r = compute(df)
        assert len(r) == 0


# ── boundary order ─────────────────────────────────────────────────────────────

class TestBoundaryOrder:
    def test_pdh_at_boundary_is_yesterday_not_current(self):
        """
        At 00:00 on Apr 15: pdh must reflect Apr 14 max, not Apr 15 00:00 bar.
        This verifies the FIX-FIRST, RESET-AFTER order.
        """
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        # Apr 14 max = 150; Apr 15 00:00 bar high = 200
        highs  = [150.0, 140.0, 145.0, 200.0]
        closes = [140.0, 139.0, 144.0, 199.0]
        r = compute(_make_df(ts, highs=highs, closes=closes))
        pdh_at_boundary = r.iloc[3]["pdh"]
        assert pdh_at_boundary == 150.0, (
            f"Expected pdh=150 (yesterday max), got {pdh_at_boundary}"
        )

    def test_current_d_high_at_boundary_is_new_day_first_bar(self):
        """At 00:00, current_d_high = this bar's high (yesterday's max is gone)."""
        d1 = _minute_range("2026-04-14T22:00:00Z", 3)
        d2 = ["2026-04-15T00:00:00Z"]
        ts = d1 + d2
        highs = [150.0, 160.0, 155.0, 50.0]
        r = compute(_make_df(ts, highs=highs))
        assert r.iloc[3]["current_d_high"] == 50.0
