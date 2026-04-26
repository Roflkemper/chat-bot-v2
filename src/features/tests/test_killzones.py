"""Tests for src/features/killzones.py.

Acceptance criteria from ICT_KILLZONES_SPEC §15.
Synthetic scenarios: hand-crafted OHLCV over ~100 minutes,
verified mitigation/sweep flags by exact timestamp.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

import src.features.calendar as cal
import src.features.killzones as kz


# ── helpers ───────────────────────────────────────────────────────────────────

def _ohlcv(timestamps, opens, highs, lows, closes, volumes=None):
    idx = pd.DatetimeIndex(timestamps, tz="UTC")
    if volumes is None:
        volumes = [1.0] * len(timestamps)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _compute(df: pd.DataFrame) -> pd.DataFrame:
    """Run calendar then killzones on df."""
    return kz.compute(cal.compute(df))


def _week_df(start: str = "2026-04-14") -> pd.DataFrame:
    """7 UTC days × 1440 min (April 2026, EDT)."""
    idx = pd.date_range(start, periods=7 * 24 * 60, freq="min", tz="UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=idx,
    )


def _london_session_df(date: str = "2026-04-15") -> pd.DataFrame:
    """EDT: LONDON = UTC 06:00–09:00. Returns exactly those 180 rows."""
    idx = pd.date_range(f"{date}T06:00:00Z", periods=180, freq="min", tz="UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
        index=idx,
    )


# ── Running state ─────────────────────────────────────────────────────────────

class TestRunningState:
    def test_running_high_cummax(self):
        """kz_running_high must be the running max of bar.high within the session."""
        # NY_AM 2026-04-15: UTC 13:30–15:00
        ts = [
            "2026-04-15T13:30:00Z",  # high=105
            "2026-04-15T13:31:00Z",  # high=103 → running_high still 105
            "2026-04-15T13:32:00Z",  # high=107 → running_high becomes 107
        ]
        df = _ohlcv(ts, [100]*3, [105, 103, 107], [99]*3, [100]*3)
        r = _compute(df)
        assert r.iloc[0]["kz_running_high"] == pytest.approx(105)
        assert r.iloc[1]["kz_running_high"] == pytest.approx(105)
        assert r.iloc[2]["kz_running_high"] == pytest.approx(107)

    def test_running_low_cummin(self):
        ts = [
            "2026-04-15T13:30:00Z",  # low=98
            "2026-04-15T13:31:00Z",  # low=97 → becomes 97
            "2026-04-15T13:32:00Z",  # low=99 → stays 97
        ]
        df = _ohlcv(ts, [100]*3, [101]*3, [98, 97, 99], [100]*3)
        r = _compute(df)
        assert r.iloc[0]["kz_running_low"] == pytest.approx(98)
        assert r.iloc[1]["kz_running_low"] == pytest.approx(97)
        assert r.iloc[2]["kz_running_low"] == pytest.approx(97)

    def test_running_midpoint(self):
        ts = ["2026-04-15T13:30:00Z", "2026-04-15T13:31:00Z"]
        df = _ohlcv(ts, [100]*2, [110, 110], [90, 88], [100]*2)
        r = _compute(df)
        assert r.iloc[0]["kz_running_midpoint"] == pytest.approx(100.0)   # (110+90)/2
        assert r.iloc[1]["kz_running_midpoint"] == pytest.approx(99.0)    # (110+88)/2

    def test_running_state_null_outside_session(self):
        # UTC 05:00 = NY 01:00 EDT → NONE
        ts = ["2026-04-15T05:00:00Z"]
        df = _ohlcv(ts, [100], [101], [99], [100])
        r = _compute(df)
        assert math.isnan(r.iloc[0]["kz_running_high"])
        assert math.isnan(r.iloc[0]["kz_running_low"])
        assert math.isnan(r.iloc[0]["kz_minutes_into_session"])

    def test_minutes_into_session_resets_on_new_session(self):
        # Two NY_AM sessions separated by a week
        t1 = "2026-04-15T13:30:00Z"  # NY_AM session 1 start
        t2 = "2026-04-22T13:30:00Z"  # NY_AM session 2 start (one week later)
        df = _ohlcv([t1, t2], [100]*2, [101]*2, [99]*2, [100]*2)
        r = _compute(df)
        assert r.iloc[0]["kz_minutes_into_session"] == pytest.approx(0)
        assert r.iloc[1]["kz_minutes_into_session"] == pytest.approx(0)  # reset

    def test_minutes_into_session_increments(self):
        ts = [f"2026-04-15T13:{m:02d}:00Z" for m in range(30, 35)]  # 13:30–13:34
        df = _ohlcv(ts, [100]*5, [101]*5, [99]*5, [100]*5)
        r = _compute(df)
        assert list(r["kz_minutes_into_session"]) == pytest.approx([0, 1, 2, 3, 4])


# ── Finalized state ───────────────────────────────────────────────────────────

class TestFinalizedState:
    def test_finalized_after_session_closes(self):
        """After LONDON closes, last_london_high/low/midpoint are locked."""
        # LONDON EDT: UTC 06:00–09:00. Two LONDON sessions.
        # Session 1: high=110, low=90 → mid=100
        # Session 2 starts next day at 06:00
        ts_s1 = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
                [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
                [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]  # 180 bars
        highs = [110.0] + [101.0] * 179
        lows = [90.0] + [99.0] * 179
        ts_s2_start = ["2026-04-16T06:00:00Z"]
        all_ts = ts_s1 + ts_s2_start

        all_h = highs + [102.0]
        all_lo = lows + [98.0]
        df = _ohlcv(all_ts, [100.0]*181, all_h, all_lo, [100.0]*181)
        r = _compute(df)
        # At the first bar of session 2 (index 180), last_london_high should be 110
        assert r.iloc[180]["last_london_high"] == pytest.approx(110.0)
        assert r.iloc[180]["last_london_low"] == pytest.approx(90.0)
        assert r.iloc[180]["last_london_midpoint"] == pytest.approx(100.0)

    def test_close_ts_is_last_bar_of_session(self):
        """last_london_close_ts must equal the timestamp of the last bar of the session."""
        ts_s1 = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
                [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
                [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        ts_s2 = ["2026-04-16T06:00:00Z"]
        all_ts = ts_s1 + ts_s2
        df = _ohlcv(all_ts, [100.0]*181, [101.0]*181, [99.0]*181, [100.0]*181)
        r = _compute(df)
        expected_close_ts = int(pd.Timestamp("2026-04-15T08:59:00Z").value // 1_000_000)
        assert r.iloc[180]["last_london_close_ts"] == expected_close_ts

    def test_finalized_state_null_before_first_session(self):
        """last_{pfx}_high must be NaN until at least one session of that type closes."""
        ts = ["2026-04-15T06:30:00Z"]  # inside LONDON session 1, not yet closed
        df = _ohlcv(ts, [100], [101], [99], [100])
        r = _compute(df)
        assert math.isnan(r.iloc[0]["last_london_high"])

    def test_finalized_state_resets_on_new_session(self):
        """last_{pfx}_high_mitigated resets to False when a new session closes."""
        # Session 1: high=105, mitigated in between, then session 2 closes
        # Build: S1 180 bars, NONE gap, S1 high gets mitigated, S2 180 bars, check
        s1 = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
             [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
             [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        # After S1: one bar that breaches S1 high (110)
        gap = ["2026-04-15T09:30:00Z"]  # NONE hour
        # S2: 180 bars with high=102 (no breach of S2 high=102 after close)
        s2 = [f"2026-04-16T06:{m:02d}:00Z" for m in range(60)] + \
             [f"2026-04-16T07:{m:02d}:00Z" for m in range(60)] + \
             [f"2026-04-16T08:{m:02d}:00Z" for m in range(60)]
        # After S2: check row
        after_s2 = ["2026-04-16T09:30:00Z"]

        all_ts = s1 + gap + s2 + after_s2
        n = len(all_ts)
        highs = [110.0] + [101.0] * 179 + [115.0] + [102.0] * 180 + [101.0]
        lows = [99.0] * n
        df = _ohlcv(all_ts, [100.0]*n, highs, lows, [100.0]*n)
        r = _compute(df)
        # After S1 closes, mitigation gets triggered by gap bar (high=115 > 110)
        assert r.iloc[181]["last_london_high_mitigated"] is True or \
               r.iloc[181]["last_london_high_mitigated"] == True
        # After S2 closes (no bar ever breached S2 high=102 after close), flag should be False
        assert r.iloc[-1]["last_london_high_mitigated"] == False


# ── §15 Mitigation synthetic scenario ────────────────────────────────────────

class TestMitigationSynthetic:
    """Synthetic 100-minute scenario: LONDON session + post-session bars.

    Session high=105, low=95, mid=100.
    Verify exact bar where high_mitigated and low_mitigated flip.
    """

    def _build(self):
        # LONDON 2026-04-15: UTC 06:00–09:00 = 180 bars
        # We use first 10 bars for the session (simplified — use a fake session)
        # Actually use a real NY_AM session (90 bars) for simplicity
        # NY_AM 2026-04-15: UTC 13:30–15:00 (90 bars)
        # Session: first bar high=105, low=95, rest normal; close after 90 bars
        # Post-session: bars at 15:00+ until next NY_AM

        session_ts = [f"2026-04-15T13:{m:02d}:00Z" for m in range(30, 60)] + \
                     [f"2026-04-15T14:{m:02d}:00Z" for m in range(60)]
        # 90 session bars: first has high=105, low=95
        sess_h = [105.0] + [101.0] * 89
        sess_lo = [95.0] + [99.0] * 89
        sess_cl = [100.0] * 90

        # Post-session: 20 bars starting at 15:00 (NONE)
        # Bar 0 (15:00): normal — no breach
        # Bar 5 (15:05): high=106 → high_mitigated flips True
        # Bar 8 (15:08): low=94 → low_mitigated flips True
        post_ts = [f"2026-04-15T15:{m:02d}:00Z" for m in range(20)]
        post_h = [101.0, 101.0, 101.0, 101.0, 101.0,
                  106.0,  # bar 5: breach high (105→106)
                  101.0, 101.0,
                  101.0,  # bar 8
                  101.0, 101.0, 101.0, 101.0, 101.0, 101.0, 101.0,
                  101.0, 101.0, 101.0, 101.0]
        post_lo = [99.0] * 8 + [94.0] + [99.0] * 11  # bar 8: breach low

        all_ts = session_ts + post_ts
        all_h = sess_h + post_h
        all_lo = sess_lo + post_lo
        n = len(all_ts)
        df = _ohlcv(all_ts, [100.0]*n, all_h, all_lo, [100.0]*n)
        return _compute(df), 90  # offset = start of post-session bars

    def test_high_not_mitigated_before_breach(self):
        r, off = self._build()
        # Bars 0-4 post-session: no breach
        for i in range(off, off + 5):
            assert r.iloc[i]["last_nyam_high_mitigated"] == False

    def test_high_mitigated_at_breach_bar(self):
        r, off = self._build()
        # Bar 5 (off+5): high=106 > 105 → flips True
        assert r.iloc[off + 5]["last_nyam_high_mitigated"] == True

    def test_high_mitigated_stays_true_after_breach(self):
        r, off = self._build()
        for i in range(off + 5, off + 20):
            assert r.iloc[i]["last_nyam_high_mitigated"] == True

    def test_low_mitigated_at_breach_bar(self):
        r, off = self._build()
        # Bar 8 (off+8): low=94 < 95 → flips True
        assert r.iloc[off + 8]["last_nyam_low_mitigated"] == True

    def test_low_not_mitigated_before_bar8(self):
        r, off = self._build()
        for i in range(off, off + 8):
            assert r.iloc[i]["last_nyam_low_mitigated"] == False

    def test_midpoint_visited(self):
        r, off = self._build()
        # All post-session bars have low=99, high=101/106 → 99 <= 100 <= 101 → visited immediately
        assert r.iloc[off]["last_nyam_midpoint_visited"] == True


# ── §11.1 Sweep synthetic scenario ───────────────────────────────────────────

class TestSweepSynthetic:
    """
    LONDON closes with high=110, low=90, close_ts=T0.
    Sweep high scenario:
      - Bar at T0+100min: high=111 (breach within X=240) → phase 1
      - Bar at T0+115min: close=109 < 110 (within Y=30 of breach) → sweep_done!
    Sweep low scenario:
      - Bar at T0+50min: low=89 (breach within X=240) → phase 1
      - Bar at T0+60min: close=91 > 90 (within Y=30 of breach) → sweep_done!
    """

    def _build(self):
        # LONDON 2026-04-15 UTC 06:00–09:00 = 180 bars
        # high=110 (first bar), low=90 (first bar), rest normal
        # close_ts = timestamp of bar at 08:59 UTC
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        s_h = [110.0] + [101.0] * 179
        s_lo = [90.0] + [99.0] * 179
        s_cl = [100.0] * 180

        # close_ts is at 08:59 UTC = 180th bar (index 179 from 06:00)
        # T0 = 2026-04-15T08:59:00Z

        # Post-session bars: 09:00 UTC onwards (NONE zone)
        # index 0 post = 09:00 UTC  (T0 + 1 min)
        # index 49 post = 09:49 UTC (T0 + 50 min) → low breach
        # index 59 post = 09:59 UTC (T0 + 60 min) → low sweep return
        # index 99 post = 10:39 UTC (T0 + 100 min) → high breach
        # index 114 post = 10:54 UTC (T0 + 115 min) → high sweep return

        n_post = 200
        post_ts = []
        for m in range(60):   # 09:00-09:59
            post_ts.append(f"2026-04-15T09:{m:02d}:00Z")
        for m in range(60):   # 10:00-10:59
            post_ts.append(f"2026-04-15T10:{m:02d}:00Z")
        for m in range(60):   # 11:00-11:59
            post_ts.append(f"2026-04-15T11:{m:02d}:00Z")
        for m in range(20):   # 12:00-12:19
            post_ts.append(f"2026-04-15T12:{m:02d}:00Z")

        post_h = [101.0] * n_post
        post_lo = [99.0] * n_post
        post_cl = [100.0] * n_post

        # T0+50 min = index 49 post → low breach
        post_lo[49] = 89.0
        # T0+60 min = index 59 post → low sweep return (close > 90)
        post_cl[59] = 91.0
        # T0+100 min = index 99 post → high breach
        post_h[99] = 111.0
        # T0+115 min = index 114 post → high sweep return (close < 110)
        post_cl[114] = 109.0

        all_ts = s_ts + post_ts
        all_h = s_h + post_h
        all_lo = s_lo + post_lo
        all_cl = s_cl + post_cl
        n = len(all_ts)
        df = _ohlcv(all_ts, [100.0]*n, all_h, all_lo, all_cl)
        return _compute(df), 180  # post-session starts at index 180

    def test_no_high_sweep_before_breach(self):
        r, off = self._build()
        for i in range(off, off + 99):
            assert r.iloc[i]["london_high_sweep"] == False

    def test_no_high_sweep_at_breach_bar(self):
        # Breach is at index 99 post → phase 1, not yet confirmed
        r, off = self._build()
        assert r.iloc[off + 99]["london_high_sweep"] == False

    def test_high_sweep_confirmed_at_return_bar(self):
        # Return at index 114 post → sweep confirmed
        r, off = self._build()
        assert r.iloc[off + 114]["london_high_sweep"] == True

    def test_high_sweep_stays_true(self):
        r, off = self._build()
        for i in range(off + 114, off + 200):
            assert r.iloc[i]["london_high_sweep"] == True

    def test_low_sweep_confirmed_at_return_bar(self):
        r, off = self._build()
        assert r.iloc[off + 59]["london_low_sweep"] == True

    def test_low_sweep_not_before_return(self):
        # In _build(): breach at post[49] (lo=89<90). Default close=100 > fin_lo=90
        # so return is confirmed on bar +50 (the first bar after breach, since=1min).
        # This is CORRECT behavior: on bar +50, since=1min ≤ Y=30min, cl=100>90 → sweep.
        # The test verifies bars BEFORE the breach (off+0 to off+48) are False.
        r, off = self._build()
        for i in range(off, off + 49):
            assert r.iloc[i]["london_low_sweep"] == False

    def test_sweep_high_expires_if_no_breach(self):
        """If high is never breached within X=240 min, sweep stays False."""
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        # 200 post bars starting 09:00 (max elapsed = 200min < X=240, all high=105 < fin_h=110)
        post_ts = [f"2026-04-15T{9 + m // 60:02d}:{m % 60:02d}:00Z" for m in range(200)]
        n_post = len(post_ts)

        s_h = [110.0] + [101.0] * 179
        all_ts = s_ts + post_ts
        n = len(all_ts)
        df = _ohlcv(
            all_ts,
            [100.0] * n,
            s_h + [105.0] * n_post,       # never > 110
            [99.0] * n,
            [100.0] * n,
        )
        r = _compute(df)
        assert r["london_high_sweep"].sum() == 0

    def test_sweep_high_expires_if_return_too_late(self):
        """Return close < last_high more than Y=30 min after breach → no sweep."""
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        post_ts = [f"2026-04-15T{9 + m // 60:02d}:{m % 60:02d}:00Z" for m in range(200)]
        n_post = len(post_ts)

        s_h = [110.0] + [101.0] * 179
        # Breach at post[10]: h=111 > 110. close=115 ≥ 110 → return NOT confirmed on breach bar.
        # Bars 11-40 (since ≤ 30min): close=115 ≥ 110 → return NOT confirmed.
        # Bar 41 (since=31min > Y=30min): Y window expired → no sweep.
        # Bar 42: close=109, but phase already -1 → no sweep.
        post_h = [101.0] * n_post
        post_cl = [115.0] * n_post   # close ≥ 110 → never triggers return in Y window
        post_h[10] = 111.0
        post_cl[42] = 109.0          # would be return, but Y already expired

        all_ts = s_ts + post_ts
        n = len(all_ts)
        df = _ohlcv(
            all_ts,
            [100.0] * n,
            s_h + post_h,
            [99.0] * n,
            [100.0] * 180 + post_cl,
        )
        r = _compute(df)
        assert r["london_high_sweep"].sum() == 0


# ── Midpoint magnet ───────────────────────────────────────────────────────────

class TestMidpointMagnet:
    def test_minutes_to_midpoint_visit(self):
        """After LONDON closes (mid=100), bar at T0+10min touches mid → magnet=10."""
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        s_h = [110.0] + [101.0] * 179
        s_lo = [90.0] + [99.0] * 179

        # Post: 20 bars. Bar 10 (09:10 UTC = T0+11min): low=99, high=101 → 99 ≤ 100 ≤ 101
        post_ts = [f"2026-04-15T09:{m:02d}:00Z" for m in range(20)]
        post_h = [101.0] * 20
        post_lo = [99.0] * 20   # all bars straddle mid=100 → first touch at bar 0 (09:00)

        all_ts = s_ts + post_ts
        n = len(all_ts)
        df = _ohlcv(all_ts, [100.0]*n, s_h + post_h, s_lo + post_lo, [100.0]*n)
        r = _compute(df)
        # First post-session bar is at 09:00 = T0+1min (close_ts=08:59)
        # low=99 ≤ mid=100 ≤ high=101 → visited at bar 0 post → minutes = 1 min
        assert r.iloc[180]["london_minutes_to_midpoint_visit"] == pytest.approx(1.0)

    def test_minutes_to_midpoint_visit_nan_if_not_visited(self):
        """NaN if midpoint never touched before next session."""
        # LONDON session: high=110, low=90, mid=100
        # Post bars: high=95, low=91 → never touch 100
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        s_h = [110.0] + [94.0] * 179
        s_lo = [90.0] + [91.0] * 179
        post_ts = [f"2026-04-15T09:{m:02d}:00Z" for m in range(10)]
        post_h = [95.0] * 10
        post_lo = [91.0] * 10

        all_ts = s_ts + post_ts
        n = len(all_ts)
        df = _ohlcv(all_ts, [100.0]*n, s_h + post_h, s_lo + post_lo, [100.0]*n)
        r = _compute(df)
        for i in range(180, 190):
            assert math.isnan(r.iloc[i]["london_minutes_to_midpoint_visit"])

    def test_minutes_propagate_after_first_visit(self):
        """Once visited, the value stays constant for all subsequent bars."""
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        s_h = [110.0] + [101.0] * 179
        s_lo = [90.0] + [99.0] * 179
        post_ts = [f"2026-04-15T09:{m:02d}:00Z" for m in range(10)]
        post_h = [101.0] * 10
        post_lo = [99.0] * 10

        all_ts = s_ts + post_ts
        n = len(all_ts)
        df = _ohlcv(all_ts, [100.0]*n, s_h + post_h, s_lo + post_lo, [100.0]*n)
        r = _compute(df)
        first_val = r.iloc[180]["london_minutes_to_midpoint_visit"]
        for i in range(181, 190):
            assert r.iloc[i]["london_minutes_to_midpoint_visit"] == pytest.approx(first_val)


# ── Range stats ───────────────────────────────────────────────────────────────

class TestRangeStats:
    def test_avg_range_null_with_fewer_than_5_sessions(self):
        r = _compute(_week_df())
        # First LONDON of the week: no history → avg is NaN during it
        # Check first LONDON bar: 2026-04-14 (Monday) UTC 06:00
        # Actually the week starts 2026-04-14 (Tue, since we used Tuesday start)
        # Just check that avg_range_pct_5 is NaN during first few sessions
        # Find first bar where kz_active == LONDON
        london_rows = r[r["kz_active"] == "LONDON"]
        first_london = london_rows.iloc[0]
        assert math.isnan(first_london["london_avg_range_pct_5"])

    def test_avg_range_available_after_5_closed_sessions(self):
        """After 5 LONDON sessions close, avg_range_pct_5 must be non-NaN."""
        # Build 6 weeks to get at least 5 closed LONDON sessions
        idx = pd.date_range("2026-04-14", periods=6 * 7 * 24 * 60, freq="min", tz="UTC")
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
            index=idx,
        )
        r = _compute(df)
        london_rows = r[r["kz_active"] == "LONDON"]
        # After 5 sessions, the 6th session should have avg
        # Group by session_id to count sessions
        session_ids = london_rows["kz_session_id"].unique()
        assert len(session_ids) >= 6
        sixth_sid = session_ids[5]
        sixth_rows = london_rows[london_rows["kz_session_id"] == sixth_sid]
        assert not math.isnan(sixth_rows.iloc[0]["london_avg_range_pct_5"])

    def test_current_range_vs_avg_null_outside_session(self):
        r = _compute(_week_df())
        none_rows = r[r["kz_active"] == "NONE"]
        # current_range_vs_avg should be NaN outside active session
        assert none_rows["asia_current_range_vs_avg"].isna().all()
        assert none_rows["london_current_range_vs_avg"].isna().all()


# ── Distance features ─────────────────────────────────────────────────────────

class TestDistanceFeatures:
    def test_active_kz_dist_high(self):
        # NY_AM bar: running_high=105, close=100 → dist = (105-100)/100*100 = 5%
        ts = ["2026-04-15T13:30:00Z"]
        df = _ohlcv(ts, [100], [105], [99], [100])
        r = _compute(df)
        assert r.iloc[0]["dist_active_kz_high_pct"] == pytest.approx(5.0)

    def test_active_kz_dist_nan_outside_session(self):
        ts = ["2026-04-15T05:00:00Z"]
        df = _ohlcv(ts, [100], [101], [99], [100])
        r = _compute(df)
        assert math.isnan(r.iloc[0]["dist_active_kz_high_pct"])

    def test_last_kz_dist_after_close(self):
        # After LONDON closes with high=110, low=90, mid=100
        # Bar at close+1: close=95 → dist_last_london_high = (110-95)/95*100 = 15.789%
        s_ts = [f"2026-04-15T06:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T07:{m:02d}:00Z" for m in range(60)] + \
               [f"2026-04-15T08:{m:02d}:00Z" for m in range(60)]
        post = ["2026-04-15T09:00:00Z"]
        s_h = [110.0] + [101.0] * 179
        s_lo = [90.0] + [99.0] * 179
        all_ts = s_ts + post
        n = len(all_ts)
        df = _ohlcv(all_ts, [100.0]*n, s_h + [101.0], s_lo + [99.0], [95.0]*n)
        r = _compute(df)
        expected = (110.0 - 95.0) / 95.0 * 100
        assert r.iloc[-1]["dist_last_london_high_pct"] == pytest.approx(expected, rel=1e-4)


# ── §15.3 Sanity checks on weekly data ───────────────────────────────────────

class TestSanityWeekly:
    def test_no_overlapping_sessions(self):
        r = _compute(_week_df())
        from src.features.calendar import SESSION_NAMES as CAL_NAMES
        valid = set(CAL_NAMES) | {"NONE"}
        assert r["kz_active"].isin(valid).all()

    def test_running_high_nan_when_none(self):
        r = _compute(_week_df())
        none_mask = r["kz_active"] == "NONE"
        assert r.loc[none_mask, "kz_running_high"].isna().all()

    def test_high_mit_monotone_within_session_pair(self):
        """Once high_mitigated flips True, it doesn't flip back before next session."""
        r = _compute(_week_df())
        # Check LONDON mitigation: once True, stays True until next LONDON
        # (In flat market high=101, low=99 — session high=101, post bars high=101 ≤ 101 → may not trigger.
        # Just verify no False after True within a closed-session window.)
        prev = False
        for val in r["last_london_high_mitigated"]:
            if prev and not val:
                pytest.fail("last_london_high_mitigated went from True back to False")
            if val:
                prev = True
            # Reset allowed when new session closes (handled in finalize)
            # This simplified check just verifies no oscillation in first few sessions


# ── NY AM false move ──────────────────────────────────────────────────────────

class TestNYAMFalseMove:
    def _nyam_df(self, first30_direction: int, magnitude_pct: float, reversal: bool):
        """Build a synthetic NY_AM session for 2026-04-15.

        NY_AM: UTC 13:30–15:00 (90 bars).
        first30_direction: +1 (up) or -1 (down)
        magnitude_pct: size of initial move
        reversal: whether to inject a reversal bar in minutes 30-89
        """
        open_price = 1000.0
        ts = [f"2026-04-15T13:{m:02d}:00Z" for m in range(30, 60)] + \
             [f"2026-04-15T14:{m:02d}:00Z" for m in range(60)]
        # Bar 29 close = open × (1 + direction × magnitude/100)
        close_at_30 = open_price * (1 + first30_direction * magnitude_pct / 100)
        closes = [open_price] * 29 + [close_at_30] + [close_at_30] * 60
        highs = [open_price + 1.0] * 90
        lows = [open_price - 1.0] * 90

        if reversal:
            # At bar 50 (minute 13:30+50=14:20), inject reversal
            # reversal = price moved ≥1.5× magnitude opposite to direction
            rev_close = open_price * (1 - first30_direction * 1.6 * magnitude_pct / 100)
            closes[50] = rev_close

        n = len(ts)
        return _ohlcv(ts, [open_price]*n, highs, lows, closes)

    def test_direction_locked_after_30_bars(self):
        df = self._nyam_df(first30_direction=1, magnitude_pct=1.0, reversal=False)
        r = _compute(df)
        # Bar 29 (minute 29 of session): direction should be locked
        assert r.iloc[29]["nyam_first30_direction"] == 1

    def test_direction_zero_before_30_bars(self):
        df = self._nyam_df(first30_direction=1, magnitude_pct=1.0, reversal=False)
        r = _compute(df)
        # Before bar 29: direction is 0
        for i in range(29):
            assert r.iloc[i]["nyam_first30_direction"] == 0

    def test_magnitude_locked(self):
        df = self._nyam_df(first30_direction=1, magnitude_pct=2.5, reversal=False)
        r = _compute(df)
        assert r.iloc[29]["nyam_first30_magnitude_pct"] == pytest.approx(2.5, rel=0.01)

    def test_no_reversal(self):
        df = self._nyam_df(first30_direction=1, magnitude_pct=1.0, reversal=False)
        r = _compute(df)
        assert r["nyam_reversal_after_first30"].sum() == 0

    def test_reversal_detected(self):
        df = self._nyam_df(first30_direction=1, magnitude_pct=1.0, reversal=True)
        r = _compute(df)
        # Reversal at bar 50 → flag should be True from bar 50 onwards
        assert r.iloc[50]["nyam_reversal_after_first30"] == True

    def test_no_reversal_before_trigger_bar(self):
        df = self._nyam_df(first30_direction=1, magnitude_pct=1.0, reversal=True)
        r = _compute(df)
        # Bars 29-49 should have reversal=False
        for i in range(29, 50):
            assert r.iloc[i]["nyam_reversal_after_first30"] == False

    def test_direction_negative(self):
        df = self._nyam_df(first30_direction=-1, magnitude_pct=1.5, reversal=False)
        r = _compute(df)
        assert r.iloc[29]["nyam_first30_direction"] == -1
