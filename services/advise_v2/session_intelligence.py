from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from src.features import calendar

from .schemas import SessionContext

NY_TZ = ZoneInfo("America/New_York")
_SESSION_STARTS = {
    "ASIA": (20, 0),
    "LONDON": (2, 0),
    "NY_AM": (9, 30),
    "NY_LUNCH": (12, 0),
    "NY_PM": (13, 30),
}
_SESSION_ENDS = {
    "ASIA": (24, 0),
    "LONDON": (5, 0),
    "NY_AM": (11, 0),
    "NY_LUNCH": (13, 0),
    "NY_PM": (16, 0),
}


def compute_session_context(ts: datetime) -> SessionContext:
    """
    Return SessionContext for a timezone-aware UTC timestamp using src.features.calendar.
    """
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("ts must be timezone-aware (UTC)")
    if ts.utcoffset().total_seconds() != 0:
        ts = ts.astimezone(ZoneInfo("UTC"))

    df = pd.DataFrame(index=pd.DatetimeIndex([ts], tz="UTC", name="timestamp"))
    df_with_calendar = calendar.compute(df)
    row = df_with_calendar.iloc[0]

    kz_active = str(row["kz_active"])
    kz_session_id_raw = row.get("kz_session_id")
    if kz_session_id_raw is None or pd.isna(kz_session_id_raw) or kz_session_id_raw == "":
        kz_session_id = None
    else:
        kz_session_id = str(kz_session_id_raw)

    dow_ny = int(row["dow_ny"])
    minutes_into = _compute_minutes_into_session(ts, kz_active)
    is_friday_close = _is_friday_close(ts, dow_ny)
    is_weekend = dow_ny in (1, 7)

    return SessionContext(
        kz_active=kz_active,
        kz_session_id=kz_session_id,
        minutes_into_session=minutes_into,
        dow_ny=dow_ny,
        is_weekend=is_weekend,
        is_friday_close=is_friday_close,
    )


def _compute_minutes_into_session(ts: datetime, kz_active: str) -> int | None:
    """Return minutes elapsed from the active session start, or None when inactive."""
    if kz_active == "NONE":
        return None

    hour, minute = _SESSION_STARTS[kz_active]
    ts_ny = ts.astimezone(NY_TZ)
    start = ts_ny.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if kz_active == "ASIA" and ts_ny.hour < 20:
        start = start - timedelta(days=1)
    minutes = int((ts_ny - start).total_seconds() // 60)
    return max(0, minutes)


def _is_friday_close(ts: datetime, dow_ny: int) -> bool:
    """Return True for Friday 15:00+ in New York time."""
    if dow_ny != 6:
        return False
    ts_ny = ts.astimezone(NY_TZ)
    return ts_ny.hour >= 15


def is_session_open_window(
    ctx: SessionContext,
    open_window_minutes: int = 30,
) -> bool:
    """Return True within the first N minutes of any active session."""
    if ctx.kz_active == "NONE":
        return False
    if ctx.minutes_into_session is None:
        return False
    return ctx.minutes_into_session <= open_window_minutes
