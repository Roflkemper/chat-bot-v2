"""H10 setup detector."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

from services.liquidity_map import LiquidityZone


@dataclass
class H10Setup:
    timestamp: datetime
    impulse_pct: float
    impulse_direction: Literal["up", "down"]
    consolidation_low: float
    consolidation_high: float
    target_zone: LiquidityZone
    target_side: Literal["long_probe", "short_probe"]


def detect_setup(
    ts: datetime,
    ohlcv_1h: pd.DataFrame,
    liq_map: list[LiquidityZone],
    weight_threshold: float = 0.5,
    min_impulse_pct: float = 0.012,
    consolidation_range_max: float = 0.010,
    cluster_radius_min: float = 0.007,
    cluster_radius_max: float = 0.020,
) -> H10Setup | None:
    ts_utc = _to_utc(ts)
    window = ohlcv_1h[ohlcv_1h.index < ts_utc].sort_index()
    if len(window) < 4:
        return None

    current_price = float(window["close"].iloc[-1])
    if current_price <= 0:
        return None

    impulse_pct, impulse_direction = _detect_impulse(window, min_impulse_pct=min_impulse_pct)
    if impulse_pct is None or impulse_direction is None:
        return None

    consolidation = _detect_consolidation(window, current_price, consolidation_range_max)
    if consolidation is None:
        return None
    consolidation_low, consolidation_high = consolidation

    zones_above = [
        zone
        for zone in liq_map
        if zone.weight > weight_threshold
        and cluster_radius_min <= ((zone.price_level - current_price) / current_price) <= cluster_radius_max
    ]
    zones_below = [
        zone
        for zone in liq_map
        if zone.weight > weight_threshold
        and cluster_radius_min <= ((current_price - zone.price_level) / current_price) <= cluster_radius_max
    ]
    if not zones_above or not zones_below:
        return None

    best_above = max(zones_above, key=lambda zone: zone.weight)
    best_below = max(zones_below, key=lambda zone: zone.weight)
    target_zone = best_above if best_above.weight >= best_below.weight else best_below
    target_side: Literal["long_probe", "short_probe"] = (
        "short_probe" if target_zone.price_level > current_price else "long_probe"
    )

    return H10Setup(
        timestamp=ts_utc.to_pydatetime(),
        impulse_pct=impulse_pct,
        impulse_direction=impulse_direction,
        consolidation_low=consolidation_low,
        consolidation_high=consolidation_high,
        target_zone=target_zone,
        target_side=target_side,
    )


def _detect_impulse(
    window: pd.DataFrame,
    min_impulse_pct: float,
) -> tuple[float | None, Literal["up", "down"] | None]:
    best_pct = 0.0
    best_direction: Literal["up", "down"] | None = None
    for size in (2, 3, 4):
        if len(window) < size:
            continue
        chunk = window.tail(size)
        sweep_high = float(chunk["high"].max())
        sweep_low = float(chunk["low"].min())
        if sweep_low <= 0:
            continue
        impulse_pct = (sweep_high - sweep_low) / sweep_low
        if impulse_pct >= best_pct:
            best_pct = impulse_pct
            best_direction = "up" if float(chunk["close"].iloc[-1]) >= float(chunk["open"].iloc[0]) else "down"
    if best_pct < min_impulse_pct or best_direction is None:
        return None, None
    return best_pct, best_direction


def _detect_consolidation(
    window: pd.DataFrame,
    current_price: float,
    consolidation_range_max: float,
) -> tuple[float, float] | None:
    if len(window) < 3:
        return None
    chunk = window.tail(3)
    lows = chunk["low"].astype(float)
    highs = chunk["high"].astype(float)
    overlap_low = float(lows.max())
    overlap_high = float(highs.min())
    if overlap_low >= overlap_high:
        return None
    total_range_pct = (float(highs.max()) - float(lows.min())) / current_price
    if total_range_pct >= consolidation_range_max:
        return None
    return float(lows.min()), float(highs.max())


def _to_utc(ts: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
