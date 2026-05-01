from __future__ import annotations

import pandas as pd

from src.features.calendar import SESSION_NAMES, compute as _cal_compute

SESSION_DEAD = "dead"
# Lowercase versions of SESSION_NAMES for column values
SESSION_LABELS = [s.lower() for s in SESSION_NAMES]  # ['asia', 'london', 'ny_am', 'ny_lunch', 'ny_pm']


def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add session_active, time_in_session_min, and internal _kz_session_id to df.

    session_active: one of asia/london/ny_am/ny_lunch/ny_pm/dead
    time_in_session_min: minutes since session open (0 for dead zones)
    _kz_session_id: internal — unique ID per session instance, '' for dead zones
    """
    cal = _cal_compute(df)

    kz_active = cal["kz_active"].values  # ASIA/LONDON/... or NONE
    kz_session_id = cal["kz_session_id"].values  # e.g. "NY_AM_2026-04-29" or ""

    # session_active: lowercase, NONE → dead
    session_active = pd.array(
        [s.lower() if s != "NONE" else SESSION_DEAD for s in kz_active],
        dtype=object,
    )

    out = df.copy()
    out["session_active"] = session_active
    out["_kz_session_id"] = kz_session_id

    # time_in_session_min: cumcount within each kz_session_id group
    # Dead zone bars all land in group "" — we override them with 0 anyway
    cumcount = out.groupby("_kz_session_id").cumcount()
    dead_mask = out["session_active"] == SESSION_DEAD
    cumcount = cumcount.where(~dead_mask, other=0)
    out["time_in_session_min"] = cumcount.astype(int)

    return out
