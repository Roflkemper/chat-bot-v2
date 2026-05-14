from __future__ import annotations


def calculate_urgency(signal: str, vol_ratio: float, distance_atr: float, regime: str) -> float:
    score = 35.0
    if signal != "NO TRADE":
        score += 18.0
    score += min(20.0, max(0.0, (vol_ratio - 1.0) * 15.0))
    score += min(15.0, abs(distance_atr) * 5.0)
    if regime == "panic":
        score += 8.0
    if regime == "compression":
        score -= 8.0
    return round(max(0.0, min(100.0, score)), 2)
