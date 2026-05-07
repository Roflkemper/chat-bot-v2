"""Taker buy/sell imbalance detector."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class TakerBias(str, Enum):
    HEAVY_BUY  = "heavy_buy"   # dominant market buy pressure
    HEAVY_SELL = "heavy_sell"  # dominant market sell pressure
    NEUTRAL    = "neutral"


@dataclass
class TakerSignal:
    bias: TakerBias
    taker_buy_ratio: float
    imbalance_zscore: Optional[float]
    note: str


_BUY_RATIO_EXTREME  = 0.65   # >65% taker buys = heavy buy
_SELL_RATIO_EXTREME = 0.35   # <35% taker buys = heavy sell
_ZSCORE_EXTREME = 2.0


def detect_taker_imbalance(df: pd.DataFrame) -> TakerSignal:
    """Detect taker imbalance from taker_buy_ratio and taker_imbalance_zscore columns."""
    if df.empty:
        return TakerSignal(TakerBias.NEUTRAL, 0.5, None, "no_data")

    last = df.iloc[-1]
    ratio = float(last.get("taker_buy_ratio", 0.5) or 0.5)
    zscore_raw = last.get("taker_imbalance_zscore")
    zscore: Optional[float] = float(zscore_raw) if zscore_raw is not None and pd.notna(zscore_raw) else None

    if zscore is not None and abs(zscore) > _ZSCORE_EXTREME:
        bias = TakerBias.HEAVY_BUY if zscore > 0 else TakerBias.HEAVY_SELL
        return TakerSignal(bias, ratio, zscore, f"imbalance_zscore={zscore:.2f}")

    if ratio > _BUY_RATIO_EXTREME:
        return TakerSignal(TakerBias.HEAVY_BUY, ratio, zscore, f"buy_ratio={ratio:.2f}")
    if ratio < _SELL_RATIO_EXTREME:
        return TakerSignal(TakerBias.HEAVY_SELL, ratio, zscore, f"buy_ratio={ratio:.2f}")

    return TakerSignal(TakerBias.NEUTRAL, ratio, zscore, "normal")
