"""H10 Setup Detector — v2 (TZ-056 rebuild).

Setup pattern: Impulse (2-12h sweep ≥1.5%) → Consolidation (6-48h corridor ≤2.5%) → NOW.
Both windows are separate, non-overlapping. The impulse precedes the consolidation.

C1: max sweep in any [2,3,4,6,8,12]-candle window BEFORE the consolidation ≥ 1.5%.
C2: price held a corridor of ≤ 2.5% range for 6-48 consecutive hours ending now,
    and the last close is NOT at the boundary (not a breakout).
C3: bilateral liquidity zones weight > threshold both above and below current price,
    within [cluster_radius_min, cluster_radius_max] of current price.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

from services.liquidity_map import LiquidityZone

# ── C1 constants ──────────────────────────────────────────────────────────────
_MIN_IMPULSE_PCT = 0.015          # 1.5% sweep — operator ground truth
_IMPULSE_WINDOWS = (2, 3, 4, 6, 8, 12)   # hours to scan for impulse

# ── C2 constants ──────────────────────────────────────────────────────────────
_CONSOL_MIN_HOURS = 6             # min consolidation duration
_CONSOL_MAX_HOURS = 48            # max consolidation duration (setup expires)
_CONSOL_RANGE_MAX = 0.025         # 2.5% corridor max width
_BOUNDARY_MARGIN = 0.002          # 0.2% — last close must not touch corridor edge

# ── C3 constants ──────────────────────────────────────────────────────────────
_CLUSTER_WEIGHT_MIN = 0.50        # data-driven: April 2026 p0=0.54, median=0.85
_CLUSTER_RADIUS_MIN = 0.007       # 0.7% from current price
_CLUSTER_RADIUS_MAX = 0.045       # 4.5% — within ±5% map coverage, captures distant structure


@dataclass
class H10Setup:
    timestamp: datetime
    impulse_pct: float
    impulse_direction: Literal["up", "down"]
    impulse_window_hours: int
    consolidation_low: float
    consolidation_high: float
    consolidation_hours: int
    target_zone: LiquidityZone
    target_side: Literal["long_probe", "short_probe"]


def detect_setup(
    ts: datetime,
    ohlcv_1h: pd.DataFrame,
    liq_map: list[LiquidityZone],
    weight_threshold: float = _CLUSTER_WEIGHT_MIN,
    min_impulse_pct: float = _MIN_IMPULSE_PCT,
    consol_range_max: float = _CONSOL_RANGE_MAX,
    consol_min_hours: int = _CONSOL_MIN_HOURS,
    consol_max_hours: int = _CONSOL_MAX_HOURS,
    cluster_radius_min: float = _CLUSTER_RADIUS_MIN,
    cluster_radius_max: float = _CLUSTER_RADIUS_MAX,
) -> H10Setup | None:
    ts_utc = _to_utc(ts)
    # Perf: ohlcv_1h is loaded sorted in scripts/backtest_h10.py::_load_ohlcv;
    # .loc[:ts_utc] is O(log n). The previous boolean-mask + .sort_index()
    # was O(n) on the full DataFrame for every backtest bar.
    if isinstance(ohlcv_1h.index, pd.DatetimeIndex):
        window = ohlcv_1h.loc[:ts_utc]
        if len(window) and window.index[-1] == ts_utc:
            window = window.iloc[:-1]
    else:
        window = ohlcv_1h[ohlcv_1h.index < ts_utc].sort_index()

    # Need enough history for impulse + consolidation + pre-impulse context
    if len(window) < consol_min_hours + min(_IMPULSE_WINDOWS) + 1:
        return None

    current_price = float(window["close"].iloc[-1])
    if current_price <= 0:
        return None

    # ── C1 + C2: find (impulse, consolidation) pair ───────────────────────────
    result = _detect_impulse_then_consolidation(
        window,
        min_impulse_pct=min_impulse_pct,
        consol_range_max=consol_range_max,
        consol_min_hours=consol_min_hours,
        consol_max_hours=consol_max_hours,
    )
    if result is None:
        return None

    impulse_pct, impulse_direction, impulse_window_hours, cons_low, cons_high, consol_hours = result

    # ── C3: bilateral zones ───────────────────────────────────────────────────
    zones_above = [
        z for z in liq_map
        if z.weight >= weight_threshold
        and cluster_radius_min <= (z.price_level - current_price) / current_price <= cluster_radius_max
    ]
    zones_below = [
        z for z in liq_map
        if z.weight >= weight_threshold
        and cluster_radius_min <= (current_price - z.price_level) / current_price <= cluster_radius_max
    ]
    if not zones_above or not zones_below:
        return None

    best_above = max(zones_above, key=lambda z: z.weight)
    best_below = max(zones_below, key=lambda z: z.weight)
    target_zone = best_above if best_above.weight >= best_below.weight else best_below
    target_side: Literal["long_probe", "short_probe"] = (
        "short_probe" if target_zone.price_level > current_price else "long_probe"
    )

    return H10Setup(
        timestamp=ts_utc.to_pydatetime(),
        impulse_pct=impulse_pct,
        impulse_direction=impulse_direction,
        impulse_window_hours=impulse_window_hours,
        consolidation_low=cons_low,
        consolidation_high=cons_high,
        consolidation_hours=consol_hours,
        target_zone=target_zone,
        target_side=target_side,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _detect_impulse_then_consolidation(
    window: pd.DataFrame,
    min_impulse_pct: float,
    consol_range_max: float,
    consol_min_hours: int,
    consol_max_hours: int,
) -> tuple[float, Literal["up", "down"], int, float, float, int] | None:
    """
    Scan for: [impulse window] immediately followed by [consolidation window]
    ending at the most recent candle.

    Tries all combinations of (impulse_size, consol_size) where:
      - impulse_size ∈ _IMPULSE_WINDOWS
      - consol_size ∈ [consol_min_hours, consol_max_hours]

    Returns: (impulse_pct, direction, impulse_window_hours, cons_low, cons_high, consol_hours)
    or None.
    """
    n = len(window)

    for consol_len in range(consol_min_hours, consol_max_hours + 1):
        if consol_len >= n:
            break
        consol = window.iloc[-consol_len:]
        cons_high = float(consol["high"].max())
        cons_low = float(consol["low"].min())
        center = (cons_high + cons_low) / 2.0
        if center <= 0:
            continue
        range_pct = (cons_high - cons_low) / center
        if range_pct > consol_range_max:
            # Range too wide — skip this consol_len entirely (wider windows will only be wider)
            # Actually wider consol_len might catch different structure, so continue
            continue

        # Last close must not be at corridor boundary (breakout in progress)
        last_close = float(consol["close"].iloc[-1])
        if last_close > cons_high * (1 - _BOUNDARY_MARGIN) or last_close < cons_low * (1 + _BOUNDARY_MARGIN):
            continue

        # Impulse window is the N candles immediately before the consolidation
        pre = window.iloc[:-consol_len]
        for imp_size in _IMPULSE_WINDOWS:
            if imp_size > len(pre):
                continue
            imp = pre.iloc[-imp_size:]
            sweep_high = float(imp["high"].max())
            sweep_low = float(imp["low"].min())
            if sweep_low <= 0:
                continue
            impulse_pct = (sweep_high - sweep_low) / sweep_low
            if impulse_pct < min_impulse_pct:
                continue
            direction: Literal["up", "down"] = (
                "up" if float(imp["close"].iloc[-1]) >= float(imp["open"].iloc[0]) else "down"
            )
            return (impulse_pct, direction, imp_size, cons_low, cons_high, consol_len)

    return None


def _to_utc(ts: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
