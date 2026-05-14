"""Resample 1m CSV data to 1h OHLC bars."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def resample_1m_to_1h(csv_path: Path) -> pd.DataFrame:
    """Read 1m CSV, resample to 1h OHLC + sum volume.

    Returns DataFrame with UTC DatetimeIndex (hour-aligned), columns:
    open, high, low, close, volume
    """
    df = pd.read_csv(csv_path)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    agg = df.resample("1h").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna(subset=["open"])
    return agg
