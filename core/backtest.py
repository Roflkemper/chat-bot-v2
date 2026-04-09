from __future__ import annotations

import pandas as pd


def quick_directional_backtest(df: pd.DataFrame, signal: str, horizon: int = 5) -> dict:
    if len(df) < horizon + 20:
        return {"trades": 0, "winrate": 0.0}
    closes = df["close"].reset_index(drop=True)
    wins = 0
    trades = 0
    for i in range(20, len(closes) - horizon):
        future = closes.iloc[i + horizon]
        current = closes.iloc[i]
        if signal == "LONG":
            wins += int(future > current)
        elif signal == "SHORT":
            wins += int(future < current)
        else:
            continue
        trades += 1
    winrate = (wins / trades * 100.0) if trades else 0.0
    return {"trades": trades, "winrate": round(winrate, 2)}
