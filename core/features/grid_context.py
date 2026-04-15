from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

GRID_THRESHOLDS_PCT = (1.3, 2.2, 2.9)
MID_RANGE_NEUTRAL_LOW = 35.0
MID_RANGE_NEUTRAL_HIGH = 65.0
WICK_REJECTION_RATIO = 0.45
REPEAT_LEVEL_TOLERANCE_PCT = 0.35
DEFAULT_LOOKBACK = 8


def _pct_distance(price: float, level: Optional[float]) -> float:
    if not price or level is None:
        return 0.0
    return abs(level - price) / max(price, 1e-9) * 100.0



def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)



def _bar_direction(bar: Dict[str, Any]) -> str:
    o = _safe_float(bar.get("open"))
    c = _safe_float(bar.get("close"))
    if c > o:
        return "LONG"
    if c < o:
        return "SHORT"
    return "NEUTRAL"



def _rejection_candidates(candles: Iterable[Dict[str, Any]], side: str) -> List[float]:
    levels: List[float] = []
    bars = list(candles)
    if not bars:
        return levels

    volumes = [_safe_float(x.get("volume"), 0.0) for x in bars]
    avg_volume = sum(volumes) / max(len(volumes), 1)

    for bar in bars:
        high = _safe_float(bar.get("high"))
        low = _safe_float(bar.get("low"))
        opn = _safe_float(bar.get("open"))
        close = _safe_float(bar.get("close"))
        volume = _safe_float(bar.get("volume"), avg_volume)
        total_range = max(high - low, 1e-9)
        upper_wick = high - max(opn, close)
        lower_wick = min(opn, close) - low
        if side == "above":
            wick_ratio = upper_wick / total_range
            if wick_ratio >= WICK_REJECTION_RATIO and volume >= avg_volume * 0.9:
                levels.append(high)
        else:
            wick_ratio = lower_wick / total_range
            if wick_ratio >= WICK_REJECTION_RATIO and volume >= avg_volume * 0.9:
                levels.append(low)
    return levels



def _cluster_level(levels: List[float], side: str, current_price: float) -> Optional[float]:
    if not levels:
        return None
    tol = max(current_price * (REPEAT_LEVEL_TOLERANCE_PCT / 100.0), 1e-9)
    best_cluster: List[float] = []

    for level in sorted(levels):
        cluster = [x for x in levels if abs(x - level) <= tol]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster
        elif len(cluster) == len(best_cluster) and cluster:
            current_best = max(best_cluster) if side == "above" else min(best_cluster)
            candidate = max(cluster) if side == "above" else min(cluster)
            if side == "above" and candidate < current_best:
                best_cluster = cluster
            elif side == "below" and candidate > current_best:
                best_cluster = cluster

    if len(best_cluster) >= 2:
        return round(sum(best_cluster) / len(best_cluster), 2)
    if levels:
        return round(max(levels), 2) if side == 'above' else round(min(levels), 2)
    return None



def _fallback_level(candles: List[Dict[str, Any]], side: str, current_price: float) -> Optional[float]:
    if side == "above":
        highs = [
            _safe_float(bar.get("high"))
            for bar in candles
            if _safe_float(bar.get("high")) > current_price
        ]
        return round(min(highs), 2) if highs else None
    lows = [
        _safe_float(bar.get("low"))
        for bar in candles
        if _safe_float(bar.get("low")) < current_price
    ]
    return round(max(lows), 2) if lows else None



def detect_nearest_liquidity(candles: List[Dict[str, Any]], current_price: float, lookback: int = DEFAULT_LOOKBACK) -> Dict[str, Optional[float]]:
    window = candles[-lookback:] if len(candles) >= lookback else candles
    above_rejections = _rejection_candidates(window, "above")
    below_rejections = _rejection_candidates(window, "below")

    liquidity_above = _cluster_level(above_rejections, "above", current_price)
    liquidity_below = _cluster_level(below_rejections, "below", current_price)

    if liquidity_above is None:
        liquidity_above = _fallback_level(window, "above", current_price)
    if liquidity_below is None:
        liquidity_below = _fallback_level(window, "below", current_price)

    return {
        "above": liquidity_above,
        "below": liquidity_below,
        "above_rejections": len(above_rejections),
        "below_rejections": len(below_rejections),
    }



def classify_grid_priority(state: str, consensus_direction: str, range_position_pct: float, up_impulse_pct: float, down_impulse_pct: float) -> str:
    neutral_mid = state == "MID_RANGE" or (MID_RANGE_NEUTRAL_LOW <= range_position_pct <= MID_RANGE_NEUTRAL_HIGH)
    if consensus_direction in {"NONE", "NEUTRAL"} and neutral_mid:
        return "NEUTRAL"
    if consensus_direction in {"LONG", "SHORT"}:
        return consensus_direction
    if neutral_mid:
        return "NEUTRAL"
    if range_position_pct > MID_RANGE_NEUTRAL_HIGH:
        return "SHORT"
    if range_position_pct < MID_RANGE_NEUTRAL_LOW:
        return "LONG"
    if down_impulse_pct > up_impulse_pct:
        return "SHORT"
    if up_impulse_pct > down_impulse_pct:
        return "LONG"
    return "NEUTRAL"



def build_grid_layers(impulse_pct: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, threshold in enumerate(GRID_THRESHOLDS_PCT, start=1):
        rows.append({
            "layer": idx,
            "threshold_pct": threshold,
            "active": impulse_pct >= threshold,
        })
    return rows



def build_grid_context(snapshot: Dict[str, Any], candles_1h: List[Dict[str, Any]]) -> Dict[str, Any]:
    price = _safe_float(snapshot.get("price"))
    liquidity = detect_nearest_liquidity(candles_1h, price)
    nearest_above = liquidity["above"]
    nearest_below = liquidity["below"]

    hedge_arm_up = snapshot.get("hedge_arm_up")
    hedge_arm_down = snapshot.get("hedge_arm_down")

    grid_target_above = _safe_float(hedge_arm_up, 0.0) or _safe_float(nearest_above, 0.0)
    grid_target_below = _safe_float(hedge_arm_down, 0.0) or _safe_float(nearest_below, 0.0)

    if grid_target_above <= price:
        grid_target_above = _safe_float(nearest_above, 0.0)
    if grid_target_below >= price and grid_target_below != 0.0:
        grid_target_below = _safe_float(nearest_below, 0.0)

    above = round(grid_target_above, 2) if grid_target_above else nearest_above
    below = round(grid_target_below, 2) if grid_target_below else nearest_below

    up_impulse_pct = round(_pct_distance(price, above), 2)
    down_impulse_pct = round(_pct_distance(price, below), 2)

    priority_side = classify_grid_priority(
        state=str(snapshot.get("state", "")),
        consensus_direction=str(snapshot.get("consensus_direction", "NONE")),
        range_position_pct=_safe_float(snapshot.get("range_position_pct")),
        up_impulse_pct=up_impulse_pct,
        down_impulse_pct=down_impulse_pct,
    )

    return {
        "priority_side": priority_side,
        "bias": str(snapshot.get("consensus_direction", "NONE")),
        "status": str(snapshot.get("state", "MID_RANGE")),
        "liquidity_above": above,
        "liquidity_below": below,
        "nearest_structure_above": nearest_above,
        "nearest_structure_below": nearest_below,
        "grid_target_above": above,
        "grid_target_below": below,
        "up_impulse_pct": up_impulse_pct,
        "down_impulse_pct": down_impulse_pct,
        "up_layers": build_grid_layers(up_impulse_pct),
        "down_layers": build_grid_layers(down_impulse_pct),
        "upper_rejections": int(liquidity.get("above_rejections") or 0),
        "lower_rejections": int(liquidity.get("below_rejections") or 0),
        "using_hedge_targets": bool(hedge_arm_up or hedge_arm_down),
    }
