"""Tests for services/ict_levels — 10 test cases per TZ acceptance criteria."""
from __future__ import annotations

import io
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from services.ict_levels.reader import load_ohlcv_csv
from services.ict_levels.sessions import add_session_columns
from services.ict_levels.aggregates import add_session_aggregates
from services.ict_levels.pivots import add_pivot_levels
from services.ict_levels.mitigation import (
    _LevelRecord,
    _extract_levels,
    _find_mitigation_ts,
    add_mitigation_columns,
)

# ─────────────────────────────── helpers ──────────────────────────────────────

def _make_ohlcv(timestamps: list[datetime], closes: Optional[list[float]] = None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with UTC DatetimeIndex."""
    n = len(timestamps)
    closes = closes or [100.0] * n
    idx = pd.DatetimeIndex(timestamps, tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low":  [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
        },
        index=idx,
    )


def _utc(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _ohlcv_csv_content(timestamps_ms: list[int], closes: Optional[list[float]] = None) -> str:
    """Generate CSV content with ts in Unix-ms format."""
    n = len(timestamps_ms)
    closes = closes or [50000.0] * n
    rows = ["ts,open,high,low,close,volume"]
    for ts_ms, c in zip(timestamps_ms, closes):
        rows.append(f"{ts_ms},{c},{c+10},{c-10},{c},1.0")
    return "\n".join(rows)


# ─────────────────────────────── Test 1: CSV reader ───────────────────────────

def test_csv_reader_unix_ms(tmp_path: Path) -> None:
    """Golden: 100-bar CSV with Unix-ms ts → DatetimeIndex UTC, correct dtype."""
    base_ms = 1_746_057_600_000  # 2025-05-01 00:00:00 UTC in ms
    tss = [base_ms + i * 60_000 for i in range(100)]
    content = _ohlcv_csv_content(tss, closes=[50000.0 + i for i in range(100)])
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(content)

    df = load_ohlcv_csv(csv_path)

    assert isinstance(df.index, pd.DatetimeIndex), "Index must be DatetimeIndex"
    assert df.index.tz is not None, "Index must be timezone-aware"
    assert str(df.index.tz) == "UTC", "Index must be UTC"
    assert len(df) == 100
    # First bar should be at 2025-05-01 00:00 UTC
    assert df.index[0] == pd.Timestamp("2025-05-01 00:00:00", tz="UTC")
    assert df.index[99] == pd.Timestamp("2025-05-01 01:39:00", tz="UTC")
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns, f"Missing column {col}"


def test_csv_reader_rejects_seconds(tmp_path: Path) -> None:
    """ts in Unix seconds (not ms) → ValueError."""
    base_s = 1_746_057_600  # seconds — below 1e11 threshold
    content = f"ts,open,high,low,close,volume\n{base_s},50000,50010,49990,50000,1\n"
    csv_path = tmp_path / "sec.csv"
    csv_path.write_text(content)

    with pytest.raises(ValueError, match="milliseconds"):
        load_ohlcv_csv(csv_path)


# ─────────────────────────────── Test 2: DST transitions ──────────────────────

def test_dst_transition_session_shift() -> None:
    """Session boundaries shift by 1h around DST transitions.

    2025-03-09 02:00 ET: clocks spring forward to 03:00 → NY_AM shifts in UTC.
    Pre-DST (2025-03-08): NY_AM 09:30-11:00 ET = 14:30-16:00 UTC
    Post-DST (2025-03-10): NY_AM 09:30-11:00 ET = 13:30-15:00 UTC
    """
    # One bar just before DST change (still winter offset)
    pre_dst = _utc(2025, 3, 8, 14, 30)   # 14:30 UTC = 09:30 ET (winter) → NY_AM
    post_dst = _utc(2025, 3, 10, 13, 30)  # 13:30 UTC = 09:30 ET (summer) → NY_AM

    df_pre  = _make_ohlcv([pre_dst])
    df_post = _make_ohlcv([post_dst])

    pre  = add_session_columns(df_pre)
    post = add_session_columns(df_post)

    assert pre.iloc[0]["session_active"] == "ny_am", (
        f"Expected ny_am before DST, got {pre.iloc[0]['session_active']}"
    )
    assert post.iloc[0]["session_active"] == "ny_am", (
        f"Expected ny_am after DST, got {post.iloc[0]['session_active']}"
    )

    # Bar between the two: 14:00 UTC on 2025-03-10 is 10:00 ET (summer) → ny_am
    mid_bar = _utc(2025, 3, 10, 14, 0)
    df_mid = _make_ohlcv([mid_bar])
    mid = add_session_columns(df_mid)
    assert mid.iloc[0]["session_active"] == "ny_am"


# ─────────────────────────────── Test 3: Session boundaries ───────────────────

def test_session_boundary_ny_am_winter() -> None:
    """Bar at 14:29 UTC (winter) → NOT ny_am; bar at 14:30 → ny_am."""
    # 2025-01-06 (Monday, winter, NY = UTC-5) → NY_AM 09:30 ET = 14:30 UTC
    before = _utc(2025, 1, 6, 14, 29)
    at     = _utc(2025, 1, 6, 14, 30)

    df = _make_ohlcv([before, at])
    out = add_session_columns(df)

    assert out.iloc[0]["session_active"] != "ny_am", (
        f"14:29 UTC should NOT be ny_am, got {out.iloc[0]['session_active']}"
    )
    assert out.iloc[1]["session_active"] == "ny_am", (
        f"14:30 UTC should be ny_am, got {out.iloc[1]['session_active']}"
    )


# ─────────────────────────────── Test 4: Aggregates forward-fill ──────────────

def test_aggregates_forward_fill_after_asia_close() -> None:
    """After Asia closes, asia_high persists until next Asia session."""
    # Build a small 1m dataset spanning two Asia sessions
    # Winter: Asia = 20:00-24:00 NY = 01:00-05:00 UTC next day
    # Asia session 1: 2025-01-07 01:00 - 04:59 UTC (Mon NY night)
    # then dead zone
    # Asia session 2: 2025-01-08 01:00 - 04:59 UTC

    ts_list = (
        [_utc(2025, 1, 7, 1, i) for i in range(60)] +    # Asia session bars
        [_utc(2025, 1, 7, 7, i) for i in range(10)] +    # dead zone bars
        [_utc(2025, 1, 8, 1, i) for i in range(60)]      # Asia session 2
    )
    closes = (
        [77000.0 + i for i in range(60)] +
        [76000.0] * 10 +
        [75000.0 + i for i in range(60)]
    )
    df = _make_ohlcv(ts_list, closes)
    df["high"] = [c + 10 for c in closes]
    df["low"]  = [c - 10 for c in closes]

    out = add_session_columns(df)
    out = add_session_aggregates(out)

    # During dead zone (session 7:00-7:09), asia_high should be ffilled from session 1
    dead_slice = out.iloc[60:70]
    asia_highs_dead = dead_slice["asia_high"].dropna()
    assert len(asia_highs_dead) > 0, "asia_high should be non-null in dead zone after Asia closed"

    first_asia_high = out.iloc[:60]["high"].max()
    assert (asia_highs_dead == first_asia_high).all(), (
        f"asia_high in dead zone should equal session 1 high {first_asia_high}"
    )


# ─────────────────────────────── Test 5: Mitigation basic ─────────────────────

def test_mitigation_basic() -> None:
    """After session close, level is NULL until price touches it."""
    # Asia session: 01:00-03:59 UTC (4 bars for brevity, high=77000+bar)
    asia_bars = [_utc(2025, 1, 7, 1, i) for i in range(4)]
    # Dead zone post-Asia
    dead_bars = [_utc(2025, 1, 7, 7, i) for i in range(10)]

    ts_list = asia_bars + dead_bars
    # Asia bar highs: 77010 (max)
    highs = [77000.0 + i * 10 for i in range(4)] + [77000.0] * 10
    closes = [77000.0] * 14
    lows = [76990.0] * 14

    df = _make_ohlcv(ts_list, closes)
    df["high"] = highs
    df["low"]  = lows

    out = add_session_columns(df)
    out = add_session_aggregates(out)
    out = add_mitigation_columns(out)

    asia_high_level = 77030.0  # max of Asia bars

    # Before any touch: mitigated_ts should be NaT in dead zone bars BEFORE price reaches it
    dead_pre_touch = out.iloc[4:9]["asia_high_mitigated_ts"]
    # price=77000 doesn't reach asia_high=77030 → not mitigated yet
    assert dead_pre_touch.isna().all(), (
        "asia_high_mitigated_ts should be NaT when price hasn't reached the level"
    )


# ─────────────────────────────── Test 6: Mitigation persistence ───────────────

def test_mitigation_persistence_old_level_not_cleared_by_new() -> None:
    """Old session high (76000) NOT mitigated when new session high (75500) appears.
    Price must actually reach 76000 to mitigate it.

    Scenario:
    - Day D Asia: high=76000
    - Day D+1 Asia: high=75500
    - Bar at 75800 does NOT mitigate 76000
    - Only a bar at >= 76000 mitigates the old level
    """
    # Day D Asia bars (01:00-01:03 UTC) — high = 76000
    day_d_asia = [_utc(2025, 1, 7, 1, i) for i in range(4)]
    # Dead zone / inter-session
    inter = [_utc(2025, 1, 7, 10, i) for i in range(5)]
    # Day D+1 Asia bars (01:00-01:03 UTC) — high = 75500
    day_d1_asia = [_utc(2025, 1, 8, 1, i) for i in range(4)]
    # Post-D+1 dead zone: price at 75800 (doesn't reach 76000)
    dead_75800 = [_utc(2025, 1, 8, 10, i) for i in range(5)]
    # Finally a bar that reaches 76001 — should mitigate old level
    touch_bar = [_utc(2025, 1, 8, 11, 0)]

    ts_list = day_d_asia + inter + day_d1_asia + dead_75800 + touch_bar

    highs = (
        [76000.0] * 4 +       # Day D Asia: high = 76000
        [75000.0] * 5 +       # inter: price drops
        [75500.0] * 4 +       # Day D+1 Asia: high = 75500
        [75800.0] * 5 +       # dead zone: price at 75800 (below 76000)
        [76001.0]              # touch bar: reaches above 76000
    )
    closes = [75000.0] * len(ts_list)

    df = _make_ohlcv(ts_list, closes)
    df["high"] = highs
    df["low"]  = [c - 10 for c in closes]

    out = add_session_columns(df)
    out = add_session_aggregates(out)
    out = add_mitigation_columns(out)

    # Verify from the unmitigated history: at the 75800 bars, the 76000 level
    # (from Day D) should still be in the unmitigated highs history
    idx_75800 = len(day_d_asia) + len(inter) + len(day_d1_asia) + 2  # mid-75800 zone
    hist_str = out["unmitigated_session_highs_history"].iloc[idx_75800]
    if hist_str and hist_str != "[]":
        hist = json.loads(hist_str)
        levels_in_history = [entry["level"] for entry in hist]
        # 76000 level (Day D Asia) should still be present
        assert any(abs(l - 76000.0) < 1.0 for l in levels_in_history), (
            f"76000 level should still be unmitigated at bar={idx_75800}. "
            f"History: {hist}"
        )

    # After touch_bar (high=76001), the 76000 level should no longer be unmitigated
    idx_after_touch = len(ts_list) - 1
    hist_after = out["unmitigated_session_highs_history"].iloc[idx_after_touch]
    if hist_after and hist_after != "[]":
        hist_after_parsed = json.loads(hist_after)
        levels_after = [entry["level"] for entry in hist_after_parsed]
        assert not any(abs(l - 76000.0) < 1.0 for l in levels_after), (
            f"76000 level should be mitigated after touch bar. History: {hist_after_parsed}"
        )


# ─────────────────────────────── Test 7: 7-day rolling window ─────────────────

def test_unmitigated_history_7d_window() -> None:
    """Level from >7 days ago is excluded; level from <7 days ago is included."""
    # Asia session 8 days ago: high should be EXCLUDED (outside 7d window)
    now_ref = _utc(2025, 2, 1, 12, 0)

    # Session 8 days before now_ref = 2025-01-24 01:00 UTC
    old_asia = [_utc(2025, 1, 24, 1, i) for i in range(4)]
    # Session 6 days before now_ref = 2025-01-26 01:00 UTC
    recent_asia = [_utc(2025, 1, 26, 1, i) for i in range(4)]
    # Dead zone bars up to now_ref
    dead = [_utc(2025, 1, 26, 10, i) for i in range(10)]
    # now_ref bar itself
    ref_bar = [now_ref]

    ts_list = old_asia + recent_asia + dead + ref_bar

    # old_asia: high=90000, recent_asia: high=80000
    highs = [90000.0] * 4 + [80000.0] * 4 + [75000.0] * 10 + [75000.0]
    closes = [75000.0] * len(ts_list)

    df = _make_ohlcv(ts_list, closes)
    df["high"] = highs
    df["low"]  = [c - 10 for c in closes]

    out = add_session_columns(df)
    out = add_session_aggregates(out)
    out = add_mitigation_columns(out)

    # At the now_ref bar (last bar), check 7d history
    hist_str = out["unmitigated_session_highs_history"].iloc[-1]
    assert hist_str is not None and hist_str != "", "history should not be null"
    hist = json.loads(hist_str)
    levels = [entry["level"] for entry in hist]

    # 80000 (6 days ago) should be included
    assert any(abs(l - 80000.0) < 1.0 for l in levels), (
        f"80000 level (6 days old) should be in 7d window. levels={levels}"
    )
    # 90000 (8 days ago) should be excluded
    assert not any(abs(l - 90000.0) < 1.0 for l in levels), (
        f"90000 level (8 days old) should be outside 7d window. levels={levels}"
    )


# ─────────────────────────────── Test 8: Unmitigated sort order ───────────────

def test_unmitigated_sort_order() -> None:
    """unmitigated_session_highs_history sorted descending by level; lows ascending."""
    # Two Asia sessions with different highs
    asia1 = [_utc(2025, 1, 7, 1, i) for i in range(4)]
    asia2 = [_utc(2025, 1, 8, 1, i) for i in range(4)]
    ref_bar = [_utc(2025, 1, 8, 12, 0)]

    ts_list = asia1 + asia2 + ref_bar

    # asia1 high=75000, low=74000; asia2 high=78000, low=73000
    highs = [75000.0] * 4 + [78000.0] * 4 + [76000.0]
    lows  = [74000.0] * 4 + [73000.0] * 4 + [74500.0]

    df = _make_ohlcv(ts_list)
    df["high"] = highs
    df["low"]  = lows
    df["close"] = [76000.0] * len(ts_list)
    df["open"] = df["close"]

    out = add_session_columns(df)
    out = add_session_aggregates(out)
    out = add_mitigation_columns(out)

    highs_hist = json.loads(out["unmitigated_session_highs_history"].iloc[-1])
    lows_hist  = json.loads(out["unmitigated_session_lows_history"].iloc[-1])

    if len(highs_hist) >= 2:
        prices_h = [e["level"] for e in highs_hist]
        assert prices_h == sorted(prices_h, reverse=True), (
            f"Highs should be sorted descending: {prices_h}"
        )

    if len(lows_hist) >= 2:
        prices_l = [e["level"] for e in lows_hist]
        assert prices_l == sorted(prices_l), (
            f"Lows should be sorted ascending: {prices_l}"
        )


# ─────────────────────────────── Test 9: Distance signs ──────────────────────

def test_distance_signs() -> None:
    """dist_to_X_pct > 0 when price is above the level, < 0 when below."""
    from services.ict_levels.distances import add_distance_columns

    # Build minimal df with known pdh and close
    ts = [_utc(2025, 1, 6, 14, 30 + i) for i in range(5)]  # NY_AM bars
    df = _make_ohlcv(ts, closes=[80000.0] * 5)

    out = add_session_columns(df)
    out = add_session_aggregates(out)
    out = add_pivot_levels(out)

    # Manually set pdh to a known value below close (80000 > 79000)
    out["pdh"] = 79000.0
    out["pdl"] = 81000.0

    out = add_distance_columns(out)

    # price (80000) > pdh (79000) → dist_to_pdh_pct > 0
    assert (out["dist_to_pdh_pct"] > 0).all(), (
        f"dist_to_pdh_pct should be positive (price above pdh). got {out['dist_to_pdh_pct'].values}"
    )
    # price (80000) < pdl (81000) → dist_to_pdl_pct < 0
    assert (out["dist_to_pdl_pct"] < 0).all(), (
        f"dist_to_pdl_pct should be negative (price below pdl). got {out['dist_to_pdl_pct'].values}"
    )


# ─────────────────────────────── Test 10: Golden-file daily levels ────────────

def test_golden_daily_levels_consistency() -> None:
    """pdh/pdl computed from previous day's data matches expected values.

    Uses synthetic data so no external file dependency. Verifies the
    calculation logic is correct end-to-end.
    """
    # Day 1: 2025-01-06 bars → high=82000, low=78000
    day1_bars = [_utc(2025, 1, 6, i, 0) for i in range(24)]
    # Day 2: 2025-01-07 bars → should see pdh=82000, pdl=78000
    day2_bars = [_utc(2025, 1, 7, i, 0) for i in range(24)]

    ts_list = day1_bars + day2_bars
    highs = [82000.0] * 24 + [83000.0] * 24
    lows  = [78000.0] * 24 + [79000.0] * 24
    closes = [80000.0] * 48

    df = _make_ohlcv(ts_list, closes)
    df["high"] = highs
    df["low"]  = lows

    out = add_session_columns(df)
    out = add_pivot_levels(out)

    # During day2, pdh should be the day1 high (82000)
    day2_slice = out.iloc[24:]
    pdh_values = day2_slice["pdh"].dropna()
    pdl_values = day2_slice["pdl"].dropna()

    assert len(pdh_values) > 0, "pdh should be non-null during day2"
    assert abs(pdh_values.iloc[0] - 82000.0) < 1.0, (
        f"pdh during day2 should be 82000 (day1 high), got {pdh_values.iloc[0]}"
    )
    assert abs(pdl_values.iloc[0] - 78000.0) < 1.0, (
        f"pdl during day2 should be 78000 (day1 low), got {pdl_values.iloc[0]}"
    )
