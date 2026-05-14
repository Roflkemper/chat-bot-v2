from __future__ import annotations

from typing import Any, Dict

from core.data_loader import load_klines


def _position_label(pos: float) -> str:
    if pos >= 0.90:
        return "HIGH_EDGE"
    if pos >= 0.72:
        return "UPPER_PART"
    if pos <= 0.10:
        return "LOW_EDGE"
    if pos <= 0.28:
        return "LOWER_PART"
    return "MID"


def analyze_range(symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    df = load_klines(symbol=symbol, timeframe=timeframe, limit=160)
    tail = df.tail(48)
    low = float(tail["low"].min())
    high = float(tail["high"].max())
    mid = (low + high) / 2.0
    price = float(df.iloc[-1]["close"])

    band = max(high - low, 1e-9)
    pos = (price - low) / band
    dist_low_pct = ((price - low) / max(price, 1e-9)) * 100.0
    dist_high_pct = ((high - price) / max(price, 1e-9)) * 100.0

    position = _position_label(pos)
    edge_bias = "NONE"
    edge_score = 0.0
    breakout_risk = "LOW"
    if position in {"HIGH_EDGE", "UPPER_PART"}:
        edge_bias = "SHORT_EDGE"
        edge_score = min(1.0, max(0.0, (pos - 0.65) / 0.35))
        breakout_risk = "HIGH" if pos >= 0.94 else "MEDIUM"
    elif position in {"LOW_EDGE", "LOWER_PART"}:
        edge_bias = "LONG_EDGE"
        edge_score = min(1.0, max(0.0, (0.35 - pos) / 0.35))
        breakout_risk = "HIGH" if pos <= 0.06 else "MEDIUM"

    if position == "HIGH_EDGE":
        state = "верх диапазона / риск ложного пробоя вверх"
    elif position == "UPPER_PART":
        state = "верхняя часть диапазона / продавец может защищать high"
    elif position == "LOW_EDGE":
        state = "низ диапазона / риск ложного пробоя вниз"
    elif position == "LOWER_PART":
        state = "нижняя часть диапазона / покупатель может защищать low"
    else:
        state = "середина диапазона"

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "range_low": round(low, 2),
        "range_mid": round(mid, 2),
        "range_high": round(high, 2),
        "range_state": state,
        "range_position": position,
        "range_ratio": round(pos, 4),
        "distance_to_low_pct": round(dist_low_pct, 3),
        "distance_to_high_pct": round(dist_high_pct, 3),
        "edge_bias": edge_bias,
        "edge_score": round(edge_score, 3),
        "breakout_risk": breakout_risk,
    }
