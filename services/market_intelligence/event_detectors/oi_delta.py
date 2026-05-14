"""Open Interest delta extreme detector."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class OIBias(str, Enum):
    SPIKE_UP = "spike_up"     # OI adding rapidly — strong trend or manipulation
    SPIKE_DN = "spike_dn"     # OI dropping — liquidation or position closing
    NEUTRAL  = "neutral"


@dataclass
class OIDeltaSignal:
    bias: OIBias
    oi_delta_pct_1h: float
    oi_zscore: Optional[float]
    note: str


_ZSCORE_EXTREME = 2.0


def detect_oi_extreme(df: pd.DataFrame) -> OIDeltaSignal:
    """Detect OI extremes from oi_delta_pct_1h and oi_zscore_24h columns."""
    if df.empty:
        return OIDeltaSignal(OIBias.NEUTRAL, 0.0, None, "no_data")

    last = df.iloc[-1]
    delta = float(last.get("oi_delta_pct_1h", 0.0) or 0.0)
    zscore_raw = last.get("oi_zscore_24h")
    zscore: Optional[float] = float(zscore_raw) if zscore_raw is not None and pd.notna(zscore_raw) else None

    if zscore is not None:
        if zscore > _ZSCORE_EXTREME:
            return OIDeltaSignal(OIBias.SPIKE_UP, delta, zscore,
                                 f"oi_zscore={zscore:.2f}")
        if zscore < -_ZSCORE_EXTREME:
            return OIDeltaSignal(OIBias.SPIKE_DN, delta, zscore,
                                 f"oi_zscore={zscore:.2f}")

    if delta > 3.0:
        return OIDeltaSignal(OIBias.SPIKE_UP, delta, zscore, f"delta_1h={delta:.1f}%")
    if delta < -3.0:
        return OIDeltaSignal(OIBias.SPIKE_DN, delta, zscore, f"delta_1h={delta:.1f}%")

    return OIDeltaSignal(OIBias.NEUTRAL, delta, zscore, "normal")
