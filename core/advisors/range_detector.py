from __future__ import annotations

from typing import Any


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _extract_entry_bounds(snapshot: dict[str, Any], price: float, atr_pct: float) -> tuple[float, float]:
    plan = snapshot.get("execution_plan") or {}
    entry_zone = plan.get("entry_zone")

    if isinstance(entry_zone, (list, tuple)) and entry_zone:
        entry_low = _safe_float(entry_zone[0], price)
        entry_high = _safe_float(entry_zone[-1], price)
        if entry_high < entry_low:
            entry_low, entry_high = entry_high, entry_low
        return entry_low, entry_high

    if entry_zone is not None:
        one = _safe_float(entry_zone, price)
        return one, one

    width = max(price * 0.003, atr_pct if atr_pct > 0 else price * 0.002)
    return price - width, price + width


def detect_range_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    price = _safe_float(snapshot.get("price"), 0.0)
    atr_pct = _safe_float(snapshot.get("atr_pct"), 0.0)
    ret10_pct = _safe_float(snapshot.get("ret10_pct"), 0.0)
    ret20_pct = _safe_float(snapshot.get("ret20_pct"), 0.0)
    regime = str(snapshot.get("regime") or "unknown").lower()

    plan = snapshot.get("execution_plan") or {}
    invalidation = _safe_float(plan.get("invalidation"), price)

    entry_low, entry_high = _extract_entry_bounds(snapshot, price, atr_pct)
    range_mid = (entry_low + entry_high) / 2.0

    if invalidation > 0 and invalidation < entry_low:
        range_low = invalidation
        range_high = entry_high
    elif invalidation > entry_high:
        range_low = entry_low
        range_high = invalidation
    else:
        width = max(abs(entry_high - entry_low), max(price * 0.003, atr_pct if atr_pct > 0 else price * 0.002))
        range_low = range_mid - width
        range_high = range_mid + width

    breakout_risk = "medium"
    range_state = "range"
    range_advice = "prefer fade edges, cancel on structure break"

    trend_pressure = abs(ret20_pct) >= 1.2 or regime == "trend"
    compression_pressure = regime == "compression"

    if trend_pressure:
        range_state = "trend_like"
        breakout_risk = "high"
        range_advice = "avoid range bots, prefer trend continuation"
    elif compression_pressure:
        range_state = "range"
        breakout_risk = "medium"
        range_advice = "watch for squeeze and breakout from range edges"
    elif abs(ret10_pct) <= 0.35 and abs(ret20_pct) <= 0.8:
        range_state = "range"
        breakout_risk = "low"
        range_advice = "range is stable, can work from boundaries"

    return {
        "range_state": range_state,
        "range_low": round(range_low, 4),
        "range_high": round(range_high, 4),
        "range_mid": round((range_low + range_high) / 2.0, 4),
        "breakout_risk": breakout_risk,
        "range_advice": range_advice,
        "range_invalidation": round(invalidation if invalidation > 0 else range_low, 4),
    }


def analyze_range(snapshot: dict[str, Any]) -> dict[str, Any]:
    return detect_range_context(snapshot)