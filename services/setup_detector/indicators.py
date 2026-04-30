from __future__ import annotations

import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> float:
    """Wilder's RSI. Returns scalar for the last bar."""
    if len(close) < period + 2:
        return 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0.0:
        last_gain = float(gain.iloc[-1])
        return 50.0 if last_gain == 0.0 else 100.0
    rs = float(gain.iloc[-1]) / last_loss
    return float(min(100.0, max(0.0, 100.0 - 100.0 / (1.0 + rs))))


def compute_volume_ratio(volume: pd.Series, lookback: int = 30) -> float:
    """Current bar volume / mean of previous N bars. >1 = above average."""
    if len(volume) < lookback + 1:
        return 1.0
    current = float(volume.iloc[-1])
    avg = float(volume.iloc[-lookback - 1 : -1].mean())
    return current / avg if avg > 0.0 else 1.0


def detect_swing_highs(
    high: pd.Series,
    window: int = 5,
    max_count: int = 3,
) -> list[tuple[int, float]]:
    """Return up to max_count most recent swing highs as (bar_index, price)."""
    result: list[tuple[int, float]] = []
    arr = high.to_numpy()
    n = len(arr)
    for i in range(window, n - window):
        left = arr[max(0, i - window) : i]
        right = arr[i + 1 : min(n, i + window + 1)]
        if len(left) > 0 and len(right) > 0 and float(arr[i]) > float(left.max()) and float(arr[i]) > float(right.max()):
            result.append((i, float(arr[i])))
    return result[-max_count:]


def detect_swing_lows(
    low: pd.Series,
    window: int = 5,
    max_count: int = 3,
) -> list[tuple[int, float]]:
    """Return up to max_count most recent swing lows as (bar_index, price)."""
    result: list[tuple[int, float]] = []
    arr = low.to_numpy()
    n = len(arr)
    for i in range(window, n - window):
        left = arr[max(0, i - window) : i]
        right = arr[i + 1 : min(n, i + window + 1)]
        if len(left) > 0 and len(right) > 0 and float(arr[i]) < float(left.min()) and float(arr[i]) < float(right.min()):
            result.append((i, float(arr[i])))
    return result[-max_count:]


def find_pdh_pdl(ohlcv_24h: pd.DataFrame) -> tuple[float, float]:
    """Previous day high / low from up to 24h of OHLCV bars."""
    if ohlcv_24h.empty:
        return (0.0, 0.0)
    return (float(ohlcv_24h["high"].max()), float(ohlcv_24h["low"].min()))


def count_touches_at_level(
    prices: pd.Series,
    level: float,
    tolerance_pct: float = 0.1,
) -> int:
    """Count how many bars touched within tolerance_pct% of level."""
    if level <= 0.0:
        return 0
    tol = level * tolerance_pct / 100.0
    return int(((prices - level).abs() <= tol).sum())


def reversal_wick_count(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    direction: str = "long",
    min_ratio: float = 1.5,
) -> int:
    """Count bars where lower/upper wick dominates (signals reversal).

    direction='long'  → lower wick > upper wick × min_ratio (bullish pin)
    direction='short' → upper wick > lower wick × min_ratio (bearish pin)
    """
    body_low = open_.combine(close, min)
    body_high = open_.combine(close, max)
    lower_wick = body_low - low
    upper_wick = high - body_high
    if direction == "long":
        dominant = lower_wick > upper_wick * min_ratio
    else:
        dominant = upper_wick > lower_wick * min_ratio
    return int(dominant.sum())
