"""Market Structure Break (MSB) / Break of Structure (BoS) / CHoCH detector.

Definitions (ICT):
  BoS  (Break of Structure): continuation — price breaks in direction of trend
  MSB  (Market Structure Break): also called CHoCH — price breaks AGAINST
       the prior swing, signaling a potential reversal

Detection approach:
  1. Identify swing highs/lows via a rolling window
  2. BoS up:  close > previous swing high (bullish continuation)
  3. BoS dn:  close < previous swing low (bearish continuation)
  4. CHoCH:   BoS against the most recent confirmed trend direction

Designed to work on any timeframe OHLCV DataFrame.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class MSBType(str, Enum):
    BOS_UP = "bos_up"       # break of structure — bullish continuation
    BOS_DN = "bos_dn"       # break of structure — bearish continuation
    CHOCH_UP = "choch_up"   # change of character — bullish reversal signal
    CHOCH_DN = "choch_dn"   # change of character — bearish reversal signal


@dataclass
class MSBEvent:
    msb_type: MSBType
    ts: pd.Timestamp        # bar that broke the level
    broken_level: float     # swing high/low that was broken
    close: float            # close price of the breaking bar
    swing_ts: pd.Timestamp  # timestamp of the broken swing
    strength_pct: float     # how far above/below level the close is


def _find_swings(
    df: pd.DataFrame,
    window: int = 5,
) -> tuple[pd.Series, pd.Series]:
    """Return swing highs and swing lows series (NaN where not a swing)."""
    highs = df["high"]
    lows = df["low"]

    swing_highs = highs[(highs == highs.rolling(window * 2 + 1, center=True).max())]
    swing_lows = lows[(lows == lows.rolling(window * 2 + 1, center=True).min())]

    sh = pd.Series(float("nan"), index=df.index)
    sl = pd.Series(float("nan"), index=df.index)
    sh.loc[swing_highs.index] = swing_highs
    sl.loc[swing_lows.index] = swing_lows
    return sh, sl


def detect_msb(
    df: pd.DataFrame,
    window: int = 5,
    lookback: int = 200,
    max_events: int = 5,
) -> list[MSBEvent]:
    """Detect most recent MSB/BoS/CHoCH events in df.

    Returns list sorted by timestamp descending (most recent first).
    """
    if len(df) < window * 2 + lookback:
        tail = df.copy()
    else:
        tail = df.iloc[-lookback:].copy()

    if len(tail) < window * 2 + 2:
        return []

    sh, sl = _find_swings(tail, window=window)

    closes = tail["close"]
    events: list[MSBEvent] = []
    last_trend: Optional[str] = None  # "up" | "dn"

    for ts in tail.index[window:]:
        c = closes[ts]

        # Look at last confirmed swing high before ts
        prior_sh = sh[:ts].dropna()
        prior_sl = sl[:ts].dropna()

        if not prior_sh.empty:
            last_sh_ts = prior_sh.index[-1]
            last_sh_val = prior_sh.iloc[-1]
            if c > last_sh_val:
                strength = (c - last_sh_val) / last_sh_val * 100
                msb_type = MSBType.BOS_UP if last_trend == "up" else MSBType.CHOCH_UP
                events.append(MSBEvent(
                    msb_type=msb_type,
                    ts=ts,
                    broken_level=last_sh_val,
                    close=c,
                    swing_ts=last_sh_ts,
                    strength_pct=round(strength, 3),
                ))
                last_trend = "up"

        if not prior_sl.empty:
            last_sl_ts = prior_sl.index[-1]
            last_sl_val = prior_sl.iloc[-1]
            if c < last_sl_val:
                strength = (last_sl_val - c) / last_sl_val * 100
                msb_type = MSBType.BOS_DN if last_trend == "dn" else MSBType.CHOCH_DN
                events.append(MSBEvent(
                    msb_type=msb_type,
                    ts=ts,
                    broken_level=last_sl_val,
                    close=c,
                    swing_ts=last_sl_ts,
                    strength_pct=round(strength, 3),
                ))
                last_trend = "dn"

    # Return most recent unique-ts events
    seen: set = set()
    deduped: list[MSBEvent] = []
    for e in sorted(events, key=lambda x: x.ts, reverse=True):
        if e.ts not in seen:
            seen.add(e.ts)
            deduped.append(e)
        if len(deduped) >= max_events:
            break
    return deduped


def latest_msb(events: list[MSBEvent]) -> Optional[MSBEvent]:
    """Return the single most recent MSB event."""
    return events[0] if events else None
