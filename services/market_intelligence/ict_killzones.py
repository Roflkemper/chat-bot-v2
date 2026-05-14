"""ICT killzone wrapper — thin layer over src/features/killzones.py for live use.

Maps the existing batch killzone feature columns into a simple live-readable
structure: current session, session range, and level distances.

Only reads already-computed columns — no new computation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import pandas as pd


class Session(str, Enum):
    ASIA = "ASIA"
    LONDON = "LONDON"
    NY_AM = "NY_AM"
    NY_LUNCH = "NY_LUNCH"
    NY_PM = "NY_PM"
    NONE = "NONE"


@dataclass
class KillzoneState:
    active_session: Session
    session_high: float
    session_low: float
    session_range: float
    session_midpoint: float
    current_price: float
    dist_to_session_high_pct: float
    dist_to_session_low_pct: float
    sweep_high_confirmed: bool
    sweep_low_confirmed: bool


_SESSION_MAP = {
    "ASIA": Session.ASIA,
    "LONDON": Session.LONDON,
    "NY_AM": Session.NY_AM,
    "NY_LUNCH": Session.NY_LUNCH,
    "NY_PM": Session.NY_PM,
}


def get_killzone_state(
    df: pd.DataFrame,
    current_price: float,
    session_col: str = "kz_session_id",
) -> KillzoneState:
    """Extract killzone state from the most recent row of a feature-enriched DataFrame.

    df should have been processed by src.features.killzones or have equivalent columns.
    If columns are missing, returns safe defaults.
    """
    if df.empty:
        return _default_state(current_price)

    last = df.iloc[-1]

    # Active session
    raw_sess = str(last.get(session_col, "")).split("-")[0].upper()
    active = _SESSION_MAP.get(raw_sess, Session.NONE)

    # Session OHLC from the prefix columns (e.g., nyam_high, asia_low…)
    pfx_map = {
        Session.ASIA:    "asia",
        Session.LONDON:  "london",
        Session.NY_AM:   "nyam",
        Session.NY_LUNCH: "nylu",
        Session.NY_PM:   "nypm",
    }
    pfx = pfx_map.get(active, "")

    sess_high = float(last.get(f"{pfx}_high", current_price) or current_price)
    sess_low  = float(last.get(f"{pfx}_low", current_price) or current_price)
    sess_mid  = float(last.get(f"{pfx}_midpoint", (sess_high + sess_low) / 2) or (sess_high + sess_low) / 2)
    sess_rng  = sess_high - sess_low if sess_high > sess_low else 0.0

    dist_high = (sess_high - current_price) / current_price * 100 if current_price else 0.0
    dist_low  = (current_price - sess_low) / current_price * 100 if current_price else 0.0

    # Sweep confirmation (if columns exist)
    sweep_high = bool(last.get(f"{pfx}_hs_confirmed", False))
    sweep_low  = bool(last.get(f"{pfx}_ls_confirmed", False))

    return KillzoneState(
        active_session=active,
        session_high=sess_high,
        session_low=sess_low,
        session_range=round(sess_rng, 2),
        session_midpoint=round(sess_mid, 2),
        current_price=current_price,
        dist_to_session_high_pct=round(dist_high, 3),
        dist_to_session_low_pct=round(dist_low, 3),
        sweep_high_confirmed=sweep_high,
        sweep_low_confirmed=sweep_low,
    )


def _default_state(current_price: float) -> KillzoneState:
    return KillzoneState(
        active_session=Session.NONE,
        session_high=current_price,
        session_low=current_price,
        session_range=0.0,
        session_midpoint=current_price,
        current_price=current_price,
        dist_to_session_high_pct=0.0,
        dist_to_session_low_pct=0.0,
        sweep_high_confirmed=False,
        sweep_low_confirmed=False,
    )


def current_session_from_utc(dt: Optional[datetime] = None) -> Session:
    """Determine current ICT session from UTC time (fallback without candle data)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    h = dt.hour

    if 0 <= h < 5:
        return Session.ASIA
    if 5 <= h < 10:
        return Session.LONDON
    if 10 <= h < 12:
        return Session.NY_AM
    if 12 <= h < 14:
        return Session.NY_LUNCH
    if 14 <= h < 17:
        return Session.NY_PM
    return Session.NONE
