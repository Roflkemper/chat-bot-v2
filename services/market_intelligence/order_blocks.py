"""Order Block detector — bullish OB, bearish OB, and breaker blocks.

ICT definition:
  Bullish OB:  last bearish candle before a strong bullish impulse (BOS up)
  Bearish OB:  last bullish candle before a strong bearish impulse (BOS down)
  Breaker OB:  mitigated OB that price returns to from the opposite side

A "strong impulse" is defined as a move of at least `min_impulse_pct` over
`impulse_bars` subsequent bars.

Works on any OHLCV DataFrame with DatetimeIndex.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class OBType(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    BREAKER_BULL = "breaker_bull"  # bullish OB turned breaker (price re-entered)
    BREAKER_BEAR = "breaker_bear"


@dataclass
class OrderBlock:
    ob_type: OBType
    ts: pd.Timestamp           # candle timestamp of OB
    high: float
    low: float
    mid: float
    impulse_pct: float         # size of the confirming impulse
    mitigated: bool = False    # True if price has traded back into OB body
    breaker: bool = False      # True if price re-entered from opposite side


def detect_order_blocks(
    df: pd.DataFrame,
    min_impulse_pct: float = 0.5,
    impulse_bars: int = 3,
    lookback: int = 100,
    max_blocks: int = 5,
) -> list[OrderBlock]:
    """Detect the most recent active order blocks in df.

    Parameters
    ----------
    df:               OHLCV DataFrame with DatetimeIndex
    min_impulse_pct:  minimum % move to confirm OB
    impulse_bars:     bars to look ahead for impulse
    lookback:         how many bars to scan (from end)
    max_blocks:       max OBs to return (most recent first)
    """
    if len(df) < impulse_bars + 2:
        return []

    tail = df.iloc[-lookback:].copy()
    closes = tail["close"].values
    opens = tail["open"].values
    highs = tail["high"].values
    lows = tail["low"].values
    idx = tail.index

    blocks: list[OrderBlock] = []
    n = len(tail)

    for i in range(n - impulse_bars - 1):
        # Bullish OB: current bar is bearish, followed by strong up impulse
        is_bearish = closes[i] < opens[i]
        if is_bearish:
            future_high = max(highs[i + 1: i + 1 + impulse_bars])
            impulse = (future_high - closes[i]) / closes[i] * 100
            if impulse >= min_impulse_pct:
                ob = OrderBlock(
                    ob_type=OBType.BULLISH,
                    ts=idx[i],
                    high=opens[i],   # OB body: open is higher for bearish candle
                    low=closes[i],
                    mid=(opens[i] + closes[i]) / 2,
                    impulse_pct=round(impulse, 3),
                )
                # Check mitigation (later price traded into OB range)
                later_lows = lows[i + impulse_bars:]
                if len(later_lows) > 0 and min(later_lows) <= ob.high:
                    ob.mitigated = True
                    if min(later_lows) <= ob.low:
                        ob.ob_type = OBType.BREAKER_BULL
                        ob.breaker = True
                blocks.append(ob)

        # Bearish OB: current bar is bullish, followed by strong down impulse
        is_bullish = closes[i] > opens[i]
        if is_bullish:
            future_low = min(lows[i + 1: i + 1 + impulse_bars])
            impulse = (closes[i] - future_low) / closes[i] * 100
            if impulse >= min_impulse_pct:
                ob = OrderBlock(
                    ob_type=OBType.BEARISH,
                    ts=idx[i],
                    high=closes[i],
                    low=opens[i],    # OB body: open is lower for bullish candle
                    mid=(closes[i] + opens[i]) / 2,
                    impulse_pct=round(impulse, 3),
                )
                later_highs = highs[i + impulse_bars:]
                if len(later_highs) > 0 and max(later_highs) >= ob.low:
                    ob.mitigated = True
                    if max(later_highs) >= ob.high:
                        ob.ob_type = OBType.BREAKER_BEAR
                        ob.breaker = True
                blocks.append(ob)

    # Sort most-recent first, filter unmitigated (active) OBs first
    active = [b for b in blocks if not b.mitigated]
    inactive = [b for b in blocks if b.mitigated]
    combined = sorted(active, key=lambda b: b.ts, reverse=True) + \
               sorted(inactive, key=lambda b: b.ts, reverse=True)
    return combined[:max_blocks]


def nearest_ob(
    blocks: list[OrderBlock],
    current_price: float,
    ob_type: Optional[OBType] = None,
) -> Optional[OrderBlock]:
    """Return the nearest OB of given type to current price."""
    candidates = [b for b in blocks if ob_type is None or b.ob_type == ob_type]
    if not candidates:
        return None
    return min(candidates, key=lambda b: abs(b.mid - current_price))
