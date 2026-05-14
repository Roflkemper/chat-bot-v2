from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from core.import_compat import to_float


def _safe_div(a: float, b: float) -> float:
    if abs(b) < 1e-9:
        return 0.0
    return a / b


def _candle_stats(row: pd.Series) -> Dict[str, float]:
    o = float(row["open"])
    h = float(row["high"])
    l = float(row["low"])
    c = float(row["close"])
    body = abs(c - o)
    full = max(h - l, 1e-9)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    return {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "body": body,
        "range": full,
        "upper_wick": max(0.0, upper_wick),
        "lower_wick": max(0.0, lower_wick),
        "body_ratio": body / full,
        "upper_ratio": max(0.0, upper_wick) / full,
        "lower_ratio": max(0.0, lower_wick) / full,
    }


def analyze_reversal(df: pd.DataFrame, range_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if df is None or len(df) < 25:
        return {
            "direction": "NEUTRAL",
            "confidence": 0.0,
            "score_long": 0.0,
            "score_short": 0.0,
            "summary": "недостаточно данных для reversal-анализа",
            "patterns": [],
            "signal": "NO_REVERSAL",
            "strength": "LOW",
            "false_break_signal": "NONE",
            "trap_side": "NONE",
            "trap_comment": "",
        }

    last = df.iloc[-1]
    prev = df.iloc[-2]
    last_s = _candle_stats(last)
    prev_s = _candle_stats(prev)

    price = float(last_s["close"])
    prev_high = float(prev_s["high"])
    prev_low = float(prev_s["low"])
    local_high = float(df["high"].tail(12).max())
    local_low = float(df["low"].tail(12).min())
    avg_range = float((df["high"] - df["low"]).tail(20).mean())
    avg_body = float((df["close"] - df["open"]).abs().tail(20).mean())
    avg_vol = float(df["volume"].tail(20).mean()) if "volume" in df.columns else 0.0
    last_vol = float(last.get("volume", 0.0))
    vol_ratio = _safe_div(last_vol, avg_vol) if avg_vol > 0 else 1.0

    short_score = 0.0
    long_score = 0.0
    patterns: List[str] = []
    false_break_signal = "NONE"
    trap_side = "NONE"
    trap_comment = ""

    upper_pin = last_s["upper_wick"] >= max(last_s["body"] * 2.2, avg_body * 0.8) and last_s["upper_ratio"] >= 0.45
    lower_pin = last_s["lower_wick"] >= max(last_s["body"] * 2.2, avg_body * 0.8) and last_s["lower_ratio"] >= 0.45

    if upper_pin:
        short_score += 0.30
        patterns.append("bearish pinbar / верхний rejection")
    if lower_pin:
        long_score += 0.30
        patterns.append("bullish pinbar / нижний rejection")

    bearish_reject = last_s["close"] < last_s["open"] and last_s["upper_wick"] > max(last_s["body"] * 1.8, avg_body * 0.7)
    bullish_reject = last_s["close"] > last_s["open"] and last_s["lower_wick"] > max(last_s["body"] * 1.8, avg_body * 0.7)
    if bearish_reject:
        short_score += 0.15
        patterns.append("продавец продавил закрытие от high")
    if bullish_reject:
        long_score += 0.15
        patterns.append("покупатель выкупил закрытие от low")

    false_break_up = last_s["high"] > prev_high and last_s["close"] < prev_high and last_s["close"] <= (last_s["high"] + last_s["low"]) / 2
    false_break_down = last_s["low"] < prev_low and last_s["close"] > prev_low and last_s["close"] >= (last_s["high"] + last_s["low"]) / 2
    if false_break_up:
        short_score += 0.24
        false_break_signal = "UP_TRAP"
        trap_side = "LONG_TRAP"
        trap_comment = "сверху сняли ликвидность и закрылись обратно в диапазон"
        patterns.append("false break up / ложный вынос вверх")
    if false_break_down:
        long_score += 0.24
        false_break_signal = "DOWN_TRAP"
        trap_side = "SHORT_TRAP"
        trap_comment = "снизу сняли ликвидность и закрылись обратно в диапазон"
        patterns.append("false break down / ложный вынос вниз")

    if last_s["high"] >= local_high * 0.9985 and last_s["close"] < last_s["open"]:
        short_score += 0.12
        patterns.append("rejection у локального high")
    if last_s["low"] <= local_low * 1.0015 and last_s["close"] > last_s["open"]:
        long_score += 0.12
        patterns.append("rejection у локального low")

    if vol_ratio >= 1.15:
        if short_score > long_score and last_s["close"] < last_s["open"]:
            short_score += 0.08
            patterns.append("объём подтверждает продавца")
        elif long_score > short_score and last_s["close"] > last_s["open"]:
            long_score += 0.08
            patterns.append("объём подтверждает покупателя")

    range_info = range_info or {}
    range_low = to_float(range_info.get("range_low"))
    range_mid = to_float(range_info.get("range_mid"))
    range_high = to_float(range_info.get("range_high"))
    range_ratio = to_float(range_info.get("range_ratio"))
    if range_low is not None and range_high is not None and range_high > range_low:
        band = max(range_high - range_low, 1e-9)
        ratio = (price - range_low) / band if range_ratio is None else float(range_ratio)
        if ratio >= 0.70 and short_score > 0:
            short_score += 0.10
            patterns.append("reversal идёт из верхней части диапазона")
        if ratio <= 0.30 and long_score > 0:
            long_score += 0.10
            patterns.append("reversal идёт из нижней части диапазона")
        if range_mid is not None and abs(price - range_mid) / band <= 0.10:
            if short_score > 0:
                short_score += 0.03
            if long_score > 0:
                long_score += 0.03
        if ratio >= 0.90 and false_break_up:
            short_score += 0.08
            patterns.append("ловушка сформирована прямо у края диапазона")
        if ratio <= 0.10 and false_break_down:
            long_score += 0.08
            patterns.append("ловушка сформирована прямо у края диапазона")

    if prev_s["close"] > prev_s["open"] and last_s["close"] < last_s["open"] and last_s["close"] < prev_s["open"]:
        short_score += 0.12
        patterns.append("двухсвечный bearish shift")
    if prev_s["close"] < prev_s["open"] and last_s["close"] > last_s["open"] and last_s["close"] > prev_s["open"]:
        long_score += 0.12
        patterns.append("двухсвечный bullish shift")

    short_score = min(short_score, 1.0)
    long_score = min(long_score, 1.0)

    if short_score >= long_score + 0.12 and short_score >= 0.34:
        direction = "SHORT"
        confidence = short_score
        signal = "BEARISH_REVERSAL"
    elif long_score >= short_score + 0.12 and long_score >= 0.34:
        direction = "LONG"
        confidence = long_score
        signal = "BULLISH_REVERSAL"
    else:
        direction = "NEUTRAL"
        confidence = max(short_score, long_score)
        signal = "NO_REVERSAL"

    if confidence >= 0.72:
        strength = "HIGH"
    elif confidence >= 0.52:
        strength = "MID"
    elif confidence >= 0.34:
        strength = "LOW"
    else:
        strength = "NONE"

    summary_map = {
        "SHORT": "найден медвежий reversal / rejection — рынок может развернуться вниз раньше EMA-подтверждений",
        "LONG": "найден бычий reversal / rejection — рынок может развернуться вверх раньше EMA-подтверждений",
        "NEUTRAL": "чистого reversal-паттерна сейчас нет",
    }

    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "score_long": round(long_score, 3),
        "score_short": round(short_score, 3),
        "summary": summary_map[direction],
        "patterns": patterns[:6],
        "signal": signal,
        "strength": strength,
        "false_break_signal": false_break_signal,
        "trap_side": trap_side,
        "trap_comment": trap_comment,
        "last_candle": {
            "body": round(last_s["body"], 4),
            "range": round(last_s["range"], 4),
            "upper_wick": round(last_s["upper_wick"], 4),
            "lower_wick": round(last_s["lower_wick"], 4),
        },
        "vol_ratio": round(vol_ratio, 3),
        "avg_range": round(avg_range, 4),
    }


__all__ = ["analyze_reversal"]
