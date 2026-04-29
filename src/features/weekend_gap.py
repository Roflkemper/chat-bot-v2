"""Weekend gap features for Friday close reference and unfilled detection."""

from __future__ import annotations

import numpy as np
import pandas as pd


_THRESHOLD_PCT = 0.5
_FRIDAY_REF_START = 20 * 60 + 55
_FRIDAY_REF_END = 20 * 60 + 59


def is_weekend_window(ts: pd.Timestamp) -> bool:
    """Return True for Friday 21:00 UTC through Monday 23:59 UTC."""
    ts = ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")
    dow = ts.weekday()
    if dow == 4 and ts.hour >= 21:
        return True
    if dow in (5, 6):
        return True
    return dow == 0


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add weekend gap features to a 1-minute UTC DataFrame."""
    out = df.copy()
    n = len(out)
    if n == 0:
        return out

    idx = out.index
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("weekend_gap.compute requires DatetimeIndex")
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
        out.index = idx

    close = out["close"].to_numpy(dtype=float)
    low = out["low"].to_numpy(dtype=float)

    friday_close_arr = np.full(n, np.nan)
    gap_low_arr = np.full(n, np.nan)
    gap_size_arr = np.full(n, np.nan)
    gap_unfilled_arr = np.zeros(n, dtype=bool)

    weekend_active = False
    friday_close = np.nan
    running_low = np.nan
    gap_closed = False
    current_week_key: tuple[int, int] | None = None

    for i, ts in enumerate(idx):
        ts_utc = ts.tz_convert("UTC")
        week_key = (int(ts_utc.isocalendar().year), int(ts_utc.isocalendar().week))
        minute_of_day = ts_utc.hour * 60 + ts_utc.minute

        if ts_utc.weekday() == 4 and _FRIDAY_REF_START <= minute_of_day <= _FRIDAY_REF_END:
            friday_close = close[i]
            current_week_key = week_key

        weekend_now = is_weekend_window(ts_utc)
        weekend_start_now = ts_utc.weekday() == 4 and ts_utc.hour >= 21

        if weekend_start_now and current_week_key != week_key:
            current_week_key = week_key

        if weekend_now and not weekend_active:
            weekend_active = True
            running_low = np.nan
            gap_closed = False

        if weekend_active and weekend_now and pd.notna(friday_close):
            running_low = low[i] if np.isnan(running_low) else min(running_low, low[i])
            friday_close_arr[i] = friday_close
            gap_low_arr[i] = running_low
            gap_size_arr[i] = (friday_close - close[i]) / friday_close * 100.0
            if running_low <= friday_close * (1.0 - _THRESHOLD_PCT / 100.0):
                gap_closed = True
            gap_unfilled_arr[i] = not gap_closed

        if weekend_active and not weekend_now:
            weekend_active = False
            friday_close = np.nan
            running_low = np.nan
            gap_closed = False
            current_week_key = None

    out["weekend_gap_unfilled_below"] = gap_unfilled_arr
    out["weekend_gap_low_price"] = gap_low_arr
    out["weekend_gap_size_pct"] = gap_size_arr
    out["weekend_friday_close_price"] = friday_close_arr
    return out

