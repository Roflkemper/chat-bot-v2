"""Pin bar (hammer/shooting star) detector on 15m bars."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class PinBarType(str, Enum):
    HAMMER = "hammer"           # bullish — long lower wick
    SHOOTING_STAR = "shooting_star"  # bearish — long upper wick
    NONE = "none"


@dataclass
class PinBarSignal:
    pin_type: PinBarType
    wick_ratio: float     # dominant wick / total range
    note: str


_WICK_MIN_RATIO = 0.667   # wick must be >= 2/3 of range
_BODY_MAX_RATIO = 0.333   # body must be <= 1/3 of range


def detect_pin_bar(df: pd.DataFrame) -> PinBarSignal:
    """Detect pin bar on the most recent bar.

    Uses pre-computed columns if available (pin_bar_bull_15m, pin_bar_bear_15m),
    otherwise computes from OHLC.
    """
    if df.empty:
        return PinBarSignal(PinBarType.NONE, 0.0, "no_data")

    last = df.iloc[-1]

    # Pre-computed columns
    bull = last.get("pin_bar_bull_15m")
    bear = last.get("pin_bar_bear_15m")
    if bull is not None and pd.notna(bull) and bool(bull):
        return PinBarSignal(PinBarType.HAMMER, _WICK_MIN_RATIO, "pin_bar_bull_15m")
    if bear is not None and pd.notna(bear) and bool(bear):
        return PinBarSignal(PinBarType.SHOOTING_STAR, _WICK_MIN_RATIO, "pin_bar_bear_15m")

    # Compute from OHLC
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            return PinBarSignal(PinBarType.NONE, 0.0, "missing_ohlc")

    o = float(last["open"])
    h = float(last["high"])
    l = float(last["low"])
    c = float(last["close"])

    total_range = h - l
    if total_range < 1e-8:
        return PinBarSignal(PinBarType.NONE, 0.0, "zero_range")

    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    body_ratio = body / total_range

    if body_ratio <= _BODY_MAX_RATIO:
        upper_ratio = upper_wick / total_range
        lower_ratio = lower_wick / total_range

        if lower_ratio >= _WICK_MIN_RATIO:
            return PinBarSignal(PinBarType.HAMMER, round(lower_ratio, 3), "computed")
        if upper_ratio >= _WICK_MIN_RATIO:
            return PinBarSignal(PinBarType.SHOOTING_STAR, round(upper_ratio, 3), "computed")

    return PinBarSignal(PinBarType.NONE, 0.0, "no_pin_bar")
