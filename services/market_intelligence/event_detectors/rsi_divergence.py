"""RSI divergence detector (15m timeframe)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class DivType(str, Enum):
    BULLISH = "bullish"   # lower lows in price, higher lows in RSI
    BEARISH = "bearish"   # higher highs in price, lower highs in RSI
    NONE = "none"


@dataclass
class RSIDivSignal:
    div_type: DivType
    price_swing_pct: float   # magnitude of price divergence move
    note: str


def detect_rsi_divergence(df: pd.DataFrame) -> RSIDivSignal:
    """Detect RSI divergence from pre-computed rsi_div_bull/rsi_div_bear columns.

    Falls back to raw RSI computation on close column if divergence columns absent.
    """
    if df.empty:
        return RSIDivSignal(DivType.NONE, 0.0, "no_data")

    last = df.iloc[-1]

    # Use pre-computed columns if available
    bull = last.get("rsi_div_bull")
    bear = last.get("rsi_div_bear")

    if bull is not None and pd.notna(bull) and bool(bull):
        return RSIDivSignal(DivType.BULLISH, 0.0, "rsi_div_bull column")
    if bear is not None and pd.notna(bear) and bool(bear):
        return RSIDivSignal(DivType.BEARISH, 0.0, "rsi_div_bear column")

    # Fallback: simple RSI divergence from raw data
    if "rsi_1h" in df.columns and "close" in df.columns and len(df) >= 20:
        rsi = df["rsi_1h"].dropna()
        price = df["close"].dropna()
        if len(rsi) >= 10 and len(price) >= 10:
            # Last 10 bars
            r_tail = rsi.iloc[-10:]
            p_tail = price.iloc[-10:]
            # Bullish div: price lower low, RSI higher low
            if p_tail.iloc[-1] < p_tail.min() * 1.02:  # near recent low
                if r_tail.iloc[-1] > r_tail.min() * 1.05:  # RSI not near low
                    swing = (p_tail.max() - p_tail.min()) / p_tail.min() * 100
                    return RSIDivSignal(DivType.BULLISH, round(swing, 2), "computed")
            # Bearish div: price higher high, RSI lower high
            if p_tail.iloc[-1] > p_tail.max() * 0.98:  # near recent high
                if r_tail.iloc[-1] < r_tail.max() * 0.95:  # RSI not near high
                    swing = (p_tail.max() - p_tail.min()) / p_tail.min() * 100
                    return RSIDivSignal(DivType.BEARISH, round(swing, 2), "computed")

    return RSIDivSignal(DivType.NONE, 0.0, "no_divergence")
