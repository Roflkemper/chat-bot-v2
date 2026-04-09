from __future__ import annotations

from typing import Dict, Iterable, List

Candle = Dict[str, float]


def aggregate_candles(candles_1h: Iterable[Candle], tf: str) -> List[Candle]:
    """Aggregate closed 1h candles into closed 4h or 1d candles.

    Expected keys per candle: ts, open, high, low, close, volume
    The function only aggregates full groups and silently drops the tail.
    """
    step_map = {"4h": 4, "1d": 24}
    if tf not in step_map:
        raise ValueError(f"Unsupported tf: {tf}")

    step = step_map[tf]
    candles = list(candles_1h)
    full_count = len(candles) // step
    out: List[Candle] = []

    for i in range(full_count):
        chunk = candles[i * step : (i + 1) * step]
        out.append(
            {
                "ts": chunk[0]["ts"],
                "open": chunk[0]["open"],
                "high": max(c["high"] for c in chunk),
                "low": min(c["low"] for c in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(float(c.get("volume", 0.0)) for c in chunk),
            }
        )

    return out
