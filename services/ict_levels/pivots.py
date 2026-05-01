from __future__ import annotations

import pandas as pd


def add_pivot_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Add daily/weekly/monthly pivot levels (forward-filled).

    Adds: d_open, pdh, pdl, pdc, pwh, pwl, pwc, pmh, pml
    All computed in UTC.
    """
    out = df.copy()
    idx = df.index  # UTC DatetimeIndex

    # ── Daily ──────────────────────────────────────────────────────────────────
    # Group by UTC calendar date
    date_key = idx.normalize()  # floor to 00:00 UTC

    daily = df.groupby(date_key).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    daily.index = pd.DatetimeIndex(daily.index, tz="UTC")

    # d_open: open of the current UTC day — forward-fill from 00:00 of each day
    d_open_events = pd.Series(daily["open"].values, index=daily.index)
    out["d_open"] = d_open_events.reindex(idx, method="ffill")

    # PDH/PDL/PDC: previous day — shift by 1 period (1 day)
    prev_daily = daily.shift(1)
    out["pdh"] = pd.Series(prev_daily["high"].values, index=daily.index).reindex(idx, method="ffill")
    out["pdl"] = pd.Series(prev_daily["low"].values, index=daily.index).reindex(idx, method="ffill")
    out["pdc"] = pd.Series(prev_daily["close"].values, index=daily.index).reindex(idx, method="ffill")

    # ── Weekly ─────────────────────────────────────────────────────────────────
    # ISO week: floor to Monday 00:00 UTC
    week_key = (idx - pd.to_timedelta(idx.dayofweek, unit="D")).normalize()

    weekly = df.groupby(week_key).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    weekly.index = pd.DatetimeIndex(weekly.index, tz="UTC")

    prev_weekly = weekly.shift(1)
    out["pwh"] = pd.Series(prev_weekly["high"].values, index=weekly.index).reindex(idx, method="ffill")
    out["pwl"] = pd.Series(prev_weekly["low"].values, index=weekly.index).reindex(idx, method="ffill")
    out["pwc"] = pd.Series(prev_weekly["close"].values, index=weekly.index).reindex(idx, method="ffill")

    # ── Monthly ────────────────────────────────────────────────────────────────
    # Floor to first day of month 00:00 UTC
    month_key = idx.normalize().map(lambda ts: ts.replace(day=1))

    monthly = df.groupby(month_key).agg(
        high=("high", "max"),
        low=("low", "min"),
    )
    monthly.index = pd.DatetimeIndex(monthly.index, tz="UTC")

    prev_monthly = monthly.shift(1)
    out["pmh"] = pd.Series(prev_monthly["high"].values, index=monthly.index).reindex(idx, method="ffill")
    out["pml"] = pd.Series(prev_monthly["low"].values, index=monthly.index).reindex(idx, method="ffill")

    return out
