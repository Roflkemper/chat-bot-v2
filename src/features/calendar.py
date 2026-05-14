"""Per-minute session calendar: killzone classification and day-of-week.

Computes three columns on a 1m UTC DatetimeIndex DataFrame:

    kz_active      : object — {ASIA, LONDON, NY_AM, NY_LUNCH, NY_PM, NONE}
    kz_session_id  : object — "{name}_{YYYY-MM-DD}" (NY date of session start), or ""
    dow_ny         : int8   — 1=Sunday … 7=Saturday (America/New_York)

Sessions are defined in NY local time with DST handled automatically via zoneinfo.
Sessions are half-open [start, end).  They never overlap by design.

Reference: ICT_KILLZONES_SPEC §4, §5.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY_TZ = ZoneInfo("America/New_York")

# (name, start_decimal_hour, end_decimal_hour) — NY local time [start, end)
_SESSIONS: list[tuple[str, float, float]] = [
    ("ASIA",     20.0,  24.0),   # 20:00 – 00:00 next day (4 h)
    ("LONDON",    2.0,   5.0),   # 02:00 – 05:00 (3 h)
    ("NY_AM",     9.5,  11.0),   # 09:30 – 11:00 (1.5 h)
    ("NY_LUNCH", 12.0,  13.0),   # 12:00 – 13:00 (1 h)
    ("NY_PM",    13.5,  16.0),   # 13:30 – 16:00 (2.5 h)
]

SESSION_NAMES: list[str] = [s[0] for s in _SESSIONS]


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add kz_active, kz_session_id, dow_ny to *df*.

    Args:
        df: DataFrame with UTC tz-aware DatetimeIndex and OHLCV columns.

    Returns:
        Copy of *df* with three additional columns.
    """
    ny_idx = df.index.tz_convert(NY_TZ)

    # Decimal NY local hour for vectorised range checks
    h = np.asarray(ny_idx.hour, dtype=float) + np.asarray(ny_idx.minute) / 60.0

    # NY calendar date strings for session_id construction
    ny_date_arr = np.array(ny_idx.strftime("%Y-%m-%d"), dtype=object)

    kz_active = np.full(len(df), "NONE", dtype=object)
    kz_session_id = np.full(len(df), "", dtype=object)

    for name, start, end in _SESSIONS:
        mask: np.ndarray = (h >= start) & (h < end)
        if not mask.any():
            continue
        kz_active[mask] = name
        # List comprehension is safe: total active rows ≪ total rows
        kz_session_id[mask] = [name + "_" + d for d in ny_date_arr[mask]]

    # pandas dayofweek: 0=Mon … 6=Sun  →  target: 1=Sun, 2=Mon … 7=Sat
    # Formula: ((dow + 1) % 7) + 1
    dow_ny = ((np.asarray(ny_idx.dayofweek) + 1) % 7 + 1).astype("int8")

    out = df.copy()
    out["kz_active"] = kz_active
    out["kz_session_id"] = kz_session_id
    out["dow_ny"] = dow_ny
    return out
