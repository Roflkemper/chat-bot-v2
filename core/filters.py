from __future__ import annotations

from typing import Any

from config import MIN_CONFIDENCE_TO_TRADE, MIN_RR, MIN_URGENCY_TO_ACT


def evaluate_trade_filters(snapshot: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    allow = True

    confidence = float(snapshot.get("confidence", 0.0))
    urgency = float(snapshot.get("urgency", 0.0))
    rr = float(snapshot.get("rr", 0.0))
    regime = snapshot.get("regime", "unknown")
    signal = snapshot.get("signal", "NO TRADE")

    if signal == "NO TRADE":
        allow = False
        reasons.append("signal=no_trade")
    if confidence < MIN_CONFIDENCE_TO_TRADE:
        allow = False
        reasons.append(f"low_confidence<{MIN_CONFIDENCE_TO_TRADE}")
    if urgency < MIN_URGENCY_TO_ACT:
        allow = False
        reasons.append(f"low_urgency<{MIN_URGENCY_TO_ACT}")
    if rr < MIN_RR:
        allow = False
        reasons.append(f"rr<{MIN_RR}")
    if regime == "panic" and signal == "LONG":
        allow = False
        reasons.append("panic_regime_blocks_long")

    return {"allow": allow, "reasons": reasons}
