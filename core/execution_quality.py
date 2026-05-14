from __future__ import annotations

import pandas as pd


def assess_execution_quality(df: pd.DataFrame, signal: str) -> dict:
    last = df.iloc[-1]
    score = 50.0
    setup = "B"
    execution = "B"

    if signal == "LONG" and last["close"] > last["ema20"] > last["ema50"]:
        score += 18
        setup = "A"
    elif signal == "SHORT" and last["close"] < last["ema20"] < last["ema50"]:
        score += 18
        setup = "A"
    elif signal == "NO TRADE":
        score -= 20
        setup = "C"

    if 0.8 <= float(last["vol_ratio"]) <= 2.2:
        score += 10
        execution = "A"
    elif float(last["vol_ratio"]) < 0.7:
        score -= 8
        execution = "C"

    if abs(float(last["distance_ema20_atr"])) > 2.4:
        score -= 10

    return {
        "execution_quality": max(0.0, min(100.0, round(score, 2))),
        "setup_grade": setup,
        "execution_grade": execution,
    }
