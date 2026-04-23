from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List


def _bar(ts: datetime, open_: float, high: float, low: float, close: float, volume: float = 100.0) -> dict:
    return {
        "open_time": int(ts.timestamp() * 1000),
        "open": round(open_, 6),
        "high": round(high, 6),
        "low": round(low, 6),
        "close": round(close, 6),
        "volume": round(volume, 6),
        "close_time": int((ts + timedelta(hours=1)).timestamp() * 1000),
    }


def _series(length: int, start: datetime, start_price: float, drift: float, wiggle: float, volume: float = 100.0) -> List[dict]:
    candles: List[dict] = []
    price = start_price
    ts = start
    for i in range(length):
        wave = ((i % 6) - 2.5) / 2.5
        open_ = price
        close = price * (1.0 + drift + wave * wiggle * 0.002)
        high = max(open_, close) * (1.0 + wiggle * 0.0025)
        low = min(open_, close) * (1.0 - wiggle * 0.0025)
        candles.append(_bar(ts, open_, high, low, close, volume + (i % 5) * 7.0))
        price = close
        ts += timedelta(hours=1)
    return candles


def gen_range_candles(length: int = 300) -> List[dict]:
    """Generate low-volatility range candles near 100."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: List[dict] = []
    center = 100.0
    for i in range(length):
        ts = start + timedelta(hours=i)
        offset = ((i % 12) - 6) / 6.0
        open_ = center + offset * 0.35
        close = center + ((i % 10) - 5) / 5.0 * 0.28
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.35
        candles.append(_bar(ts, open_, high, low, close, 85.0 + (i % 3) * 4.0))
    return candles


def gen_trend_up_candles(length: int = 300) -> List[dict]:
    """Generate bullish trend candles with persistent upward slope."""
    return _series(length, datetime(2026, 1, 1, tzinfo=timezone.utc), 100.0, drift=0.0032, wiggle=0.9, volume=140.0)


def gen_trend_down_candles(length: int = 300) -> List[dict]:
    """Generate bearish trend candles with persistent downward slope."""
    return _series(length, datetime(2026, 1, 1, tzinfo=timezone.utc), 140.0, drift=-0.0032, wiggle=0.9, volume=140.0)


def gen_cascade_down_candles(length: int = 120) -> List[dict]:
    """Generate a fresh dump in the last bars for cascade detection."""
    candles = _series(length, datetime(2026, 1, 1, tzinfo=timezone.utc), 120.0, drift=-0.0004, wiggle=0.7, volume=160.0)
    for idx in range(max(0, length - 15), length):
        prev = candles[idx - 1]["close"] if idx > 0 else candles[idx]["open"]
        close = prev * 0.988
        candles[idx]["open"] = round(prev, 6)
        candles[idx]["close"] = round(close, 6)
        candles[idx]["high"] = round(prev * 1.0005, 6)
        candles[idx]["low"] = round(close * 0.9975, 6)
        candles[idx]["volume"] = 260.0
    return candles


def gen_compression_candles(length: int = 300) -> List[dict]:
    """Generate extremely tight candles for compression tests."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: List[dict] = []
    price = 100.0
    for i in range(length):
        ts = start + timedelta(hours=i)
        change = ((i % 8) - 3.5) * 0.00004
        open_ = price
        close = price * (1.0 + change)
        high = max(open_, close) * 1.00045
        low = min(open_, close) * 0.99955
        candles.append(_bar(ts, open_, high, low, close, 70.0))
        price = 100.0 + ((i % 6) - 3) * 0.01
    return candles
