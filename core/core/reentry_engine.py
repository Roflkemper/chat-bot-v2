from __future__ import annotations


def build_reentry_plan(signal: str, price: float, atr: float, ema20: float) -> dict:
    direction = "LONG" if signal == "LONG" else "SHORT" if signal == "SHORT" else "NONE"
    if direction == "NONE":
        return {"reentry_mode": "none", "reentry_score": 0.0, "reentry_zone": None}

    if direction == "LONG":
        zone = [round(max(ema20, price - 0.7 * atr), 4), round(price - 0.3 * atr, 4)]
    else:
        zone = [round(price + 0.3 * atr, 4), round(min(ema20, price + 0.7 * atr), 4)]
    return {
        "reentry_mode": "reclaim_or_continuation",
        "reentry_score": 68.0,
        "reentry_zone": zone,
    }
