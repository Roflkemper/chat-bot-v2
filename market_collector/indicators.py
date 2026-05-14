"""On-demand technical indicators computed from OHLCV CSVs."""
from __future__ import annotations

import csv
from pathlib import Path


def _read_ohlcv(path: Path) -> tuple[list[float], list[float], list[float]]:
    """Return (highs, lows, closes) in chronological order."""
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    if not path.exists():
        return highs, lows, closes
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                highs.append(float(row["high"]))
                lows.append(float(row["low"]))
                closes.append(float(row["close"]))
            except (KeyError, ValueError):
                continue
    return highs, lows, closes


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas[-period:]]
    losses = [abs(min(d, 0.0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        h, lo, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    recent = trs[-period:]
    return round(sum(recent) / len(recent), 2)


def move_pct(closes: list[float], hours: int) -> float | None:
    """Percentage change over N hours using 1h candles."""
    if len(closes) < hours + 1:
        return None
    current = closes[-1]
    past = closes[-(hours + 1)]
    if past == 0.0:
        return None
    return round((current - past) / past * 100.0, 4)


def compute_rsi_from_csv(path: Path, period: int = 14) -> float | None:
    _, _, closes = _read_ohlcv(path)
    return rsi(closes, period)


def compute_atr_from_csv(path: Path, period: int = 14) -> float | None:
    highs, lows, closes = _read_ohlcv(path)
    return atr(highs, lows, closes, period)


def compute_move_pct_from_csv(path_1h: Path, hours: int) -> float | None:
    _, _, closes = _read_ohlcv(path_1h)
    return move_pct(closes, hours)
