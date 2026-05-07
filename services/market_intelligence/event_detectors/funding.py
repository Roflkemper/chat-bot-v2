"""Funding rate extreme detector."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class FundingBias(str, Enum):
    EXTREME_LONG = "extreme_long"   # market too long, bearish signal
    EXTREME_SHORT = "extreme_short" # market too short, bullish signal
    NEUTRAL = "neutral"


@dataclass
class FundingSignal:
    bias: FundingBias
    funding_rate: float
    zscore: Optional[float]
    note: str


_EXTREME_LONG  =  0.0005   # +0.05%
_EXTREME_SHORT = -0.0005   # -0.05%
_ZSCORE_EXTREME = 2.0


def detect_funding_extreme(df: pd.DataFrame) -> FundingSignal:
    """Detect extreme funding from a DataFrame with funding_zscore + funding_rate columns.

    Falls back to rate-only check if zscore is unavailable.
    """
    if df.empty:
        return FundingSignal(FundingBias.NEUTRAL, 0.0, None, "no_data")

    last = df.iloc[-1]
    rate = float(last.get("funding_rate", 0.0) or 0.0)
    zscore = last.get("funding_zscore")
    zscore_val: Optional[float] = float(zscore) if zscore is not None and pd.notna(zscore) else None

    if zscore_val is not None:
        if zscore_val > _ZSCORE_EXTREME:
            return FundingSignal(FundingBias.EXTREME_LONG, rate, zscore_val,
                                 f"zscore={zscore_val:.2f} > {_ZSCORE_EXTREME}")
        if zscore_val < -_ZSCORE_EXTREME:
            return FundingSignal(FundingBias.EXTREME_SHORT, rate, zscore_val,
                                 f"zscore={zscore_val:.2f} < -{_ZSCORE_EXTREME}")
    else:
        if rate > _EXTREME_LONG:
            return FundingSignal(FundingBias.EXTREME_LONG, rate, None,
                                 f"rate={rate:.5f} > threshold")
        if rate < _EXTREME_SHORT:
            return FundingSignal(FundingBias.EXTREME_SHORT, rate, None,
                                 f"rate={rate:.5f} < threshold")

    return FundingSignal(FundingBias.NEUTRAL, rate, zscore_val, "normal")
