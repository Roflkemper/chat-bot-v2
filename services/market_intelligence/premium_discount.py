"""Premium/Discount zone detector + Fair Value Gap (FVG) detector.

Premium/Discount (ICT):
  Equilibrium = midpoint of the most recent swing range (high - low)
  Premium zone: price > 75% of range (expensive for longs, ideal for shorts)
  Discount zone: price < 25% of range (cheap for longs)
  Equilibrium: 25–75% band

FVG (Fair Value Gap):
  3-candle pattern where candle[i-1].high < candle[i+1].low (bullish FVG)
  or candle[i-1].low > candle[i+1].high (bearish FVG)
  Gap = untraded zone between candle[0] and candle[2]
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class PriceZone(str, Enum):
    PREMIUM = "premium"
    DISCOUNT = "discount"
    EQUILIBRIUM = "equilibrium"
    UNKNOWN = "unknown"


@dataclass
class PremiumDiscountLevel:
    swing_high: float
    swing_low: float
    equilibrium: float
    premium_threshold: float    # 75% of range
    discount_threshold: float   # 25% of range
    current_zone: PriceZone
    current_price: float
    zone_pct: float             # 0..100 within the range


@dataclass
class FVG:
    bullish: bool               # True=bullish, False=bearish
    ts: pd.Timestamp            # middle candle timestamp
    high: float                 # upper bound of gap
    low: float                  # lower bound of gap
    size_pct: float             # gap size as % of price
    filled: bool = False        # True if price has traded into gap


def compute_premium_discount(
    df: pd.DataFrame,
    current_price: float,
    lookback: int = 100,
) -> PremiumDiscountLevel:
    """Compute premium/discount zone from most recent lookback bars."""
    tail = df.iloc[-lookback:] if len(df) > lookback else df
    swing_high = float(tail["high"].max())
    swing_low = float(tail["low"].min())
    rng = swing_high - swing_low

    if rng == 0:
        eq = swing_high
        prem_thresh = swing_high
        disc_thresh = swing_low
        zone = PriceZone.UNKNOWN
        zone_pct = 50.0
    else:
        eq = swing_low + rng * 0.5
        prem_thresh = swing_low + rng * 0.75
        disc_thresh = swing_low + rng * 0.25
        zone_pct = (current_price - swing_low) / rng * 100

        if current_price > prem_thresh:
            zone = PriceZone.PREMIUM
        elif current_price < disc_thresh:
            zone = PriceZone.DISCOUNT
        else:
            zone = PriceZone.EQUILIBRIUM

    return PremiumDiscountLevel(
        swing_high=swing_high,
        swing_low=swing_low,
        equilibrium=eq,
        premium_threshold=prem_thresh,
        discount_threshold=disc_thresh,
        current_zone=zone,
        current_price=current_price,
        zone_pct=round(zone_pct, 1),
    )


def detect_fvg(
    df: pd.DataFrame,
    min_size_pct: float = 0.05,
    lookback: int = 50,
    max_gaps: int = 5,
) -> list[FVG]:
    """Detect Fair Value Gaps in the last `lookback` bars.

    Returns list sorted most-recent first, filtered by min_size_pct.
    """
    if len(df) < 3:
        return []

    tail = df.iloc[-lookback:] if len(df) > lookback else df
    highs = tail["high"].values
    lows = tail["low"].values
    closes = tail["close"].values
    idx = tail.index

    gaps: list[FVG] = []

    for i in range(1, len(tail) - 1):
        mid_price = closes[i]
        if mid_price == 0:
            continue

        # Bullish FVG: gap between candle[i-1].high and candle[i+1].low
        if lows[i + 1] > highs[i - 1]:
            gap_low = highs[i - 1]
            gap_high = lows[i + 1]
            size_pct = (gap_high - gap_low) / mid_price * 100
            if size_pct >= min_size_pct:
                # Check if later price filled the gap
                later = tail.iloc[i + 2:]
                filled = bool(not later.empty and later["low"].min() <= gap_low)
                gaps.append(FVG(
                    bullish=True,
                    ts=idx[i],
                    high=gap_high,
                    low=gap_low,
                    size_pct=round(size_pct, 3),
                    filled=filled,
                ))

        # Bearish FVG: gap between candle[i-1].low and candle[i+1].high
        if highs[i + 1] < lows[i - 1]:
            gap_high = lows[i - 1]
            gap_low = highs[i + 1]
            size_pct = (gap_high - gap_low) / mid_price * 100
            if size_pct >= min_size_pct:
                later = tail.iloc[i + 2:]
                filled = bool(not later.empty and later["high"].max() >= gap_high)
                gaps.append(FVG(
                    bullish=False,
                    ts=idx[i],
                    high=gap_high,
                    low=gap_low,
                    size_pct=round(size_pct, 3),
                    filled=filled,
                ))

    active = [g for g in gaps if not g.filled]
    all_sorted = sorted(active, key=lambda g: g.ts, reverse=True) + \
                 sorted([g for g in gaps if g.filled], key=lambda g: g.ts, reverse=True)
    return all_sorted[:max_gaps]
