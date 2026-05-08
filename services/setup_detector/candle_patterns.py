"""Candle pattern detectors — confirmation filters, not standalone triggers.

Two patterns:
  - Bullish/bearish engulfing (2 candles, body engulfs prev)
  - Hammer (long lower wick) / Shooting star (long upper wick)

Per operator request 2026-05-07: candle patterns used as **confirmation**
for existing detectors (e.g. PDL bounce + bullish engulfing = stronger
signal), not as standalone setups.

These are pure functions over a DataFrame with columns: open, high, low, close.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def is_bullish_engulfing(df: pd.DataFrame, idx: int = -1) -> bool:
    """Bullish engulfing: prev red candle, current green candle whose body
    fully engulfs the prev body (open <= prev_close, close >= prev_open).
    """
    if len(df) < 2 or idx == 0:
        return False
    cur = df.iloc[idx]
    prev = df.iloc[idx - 1]
    prev_red = prev["close"] < prev["open"]
    cur_green = cur["close"] > cur["open"]
    if not (prev_red and cur_green):
        return False
    return bool(cur["open"] <= prev["close"] and cur["close"] >= prev["open"])


def is_bearish_engulfing(df: pd.DataFrame, idx: int = -1) -> bool:
    """Bearish engulfing: prev green, current red whose body engulfs prev."""
    if len(df) < 2 or idx == 0:
        return False
    cur = df.iloc[idx]
    prev = df.iloc[idx - 1]
    prev_green = prev["close"] > prev["open"]
    cur_red = cur["close"] < cur["open"]
    if not (prev_green and cur_red):
        return False
    return bool(cur["open"] >= prev["close"] and cur["close"] <= prev["open"])


def is_bullish_hammer(df: pd.DataFrame, idx: int = -1, *, wick_to_body_min: float = 2.0) -> bool:
    """Hammer: lower wick at least 2× the body, small upper wick.

    Doesn't require green/red — pattern is about wick geometry.
    """
    if abs(idx) > len(df):
        return False
    c = df.iloc[idx]
    body = abs(c["close"] - c["open"])
    if body == 0:
        return False
    lower_wick = min(c["close"], c["open"]) - c["low"]
    upper_wick = c["high"] - max(c["close"], c["open"])
    if lower_wick < body * wick_to_body_min:
        return False
    # Upper wick must be smaller than body (otherwise it's a doji or spinning top)
    return bool(upper_wick < body)


def is_shooting_star(df: pd.DataFrame, idx: int = -1, *, wick_to_body_min: float = 2.0) -> bool:
    """Shooting star: upper wick at least 2× the body, small lower wick."""
    if abs(idx) > len(df):
        return False
    c = df.iloc[idx]
    body = abs(c["close"] - c["open"])
    if body == 0:
        return False
    upper_wick = c["high"] - max(c["close"], c["open"])
    lower_wick = min(c["close"], c["open"]) - c["low"]
    if upper_wick < body * wick_to_body_min:
        return False
    return bool(lower_wick < body)


def candle_confirmation(df: pd.DataFrame, *, side: str, idx: int = -1) -> Optional[str]:
    """Return name of the confirming pattern if any exists at idx.

    side='long' looks for bullish engulfing or hammer.
    side='short' looks for bearish engulfing or shooting star.
    Returns the pattern name as a string, or None if no pattern detected.
    """
    if side == "long":
        if is_bullish_engulfing(df, idx):
            return "bullish_engulfing"
        if is_bullish_hammer(df, idx):
            return "bullish_hammer"
    elif side == "short":
        if is_bearish_engulfing(df, idx):
            return "bearish_engulfing"
        if is_shooting_star(df, idx):
            return "shooting_star"
    return None
