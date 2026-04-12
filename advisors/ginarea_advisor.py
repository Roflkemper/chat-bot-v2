from __future__ import annotations

from advisors.countertrend import analyze_countertrend
from advisors.range_detector import analyze_range


def build_ginarea_advice(snapshot: dict) -> dict:
    ct = analyze_countertrend(snapshot)
    rg = analyze_range(snapshot)

    if snapshot["signal"] == "NO TRADE":
        unified = "NO TRADE: wait structure reclaim / invalidation / new urgency spike"
    elif rg["range_state"] == "range":
        unified = "RANGE PLAY: fade edge only, take profit quicker, cancel on breakout"
    elif ct["ct_mode"] in {"stretch", "reversal"}:
        unified = "COUNTERTREND OK only with reclaim / confirmation"
    else:
        unified = "TREND FOLLOW OK if entry zone respected and invalidation intact"

    return {"countertrend": ct, "range": rg, "unified_advice": unified}
