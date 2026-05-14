from __future__ import annotations

from pathlib import Path

import pandas as pd

_REQUIRED_COLS = ("open", "high", "low", "close", "volume")
_MIN_MS_THRESHOLD = 1e11  # below this = looks like Unix seconds, not ms


def load_ohlcv_csv(path: str | Path) -> pd.DataFrame:
    """Load 1m OHLCV CSV with Unix-ms ts column into UTC DatetimeIndex DataFrame.

    ts column MUST be Unix milliseconds (integer). Raises ValueError otherwise.
    """
    p = Path(path)
    df = pd.read_csv(p)

    if "ts" not in df.columns:
        raise ValueError(f"No 'ts' column found in {p}")

    ts_sample = df["ts"].iloc[0]
    # pandas reads integers as numpy.int64; also accept numpy numeric types
    import numpy as np
    if not isinstance(ts_sample, (int, float, np.integer, np.floating)):
        raise ValueError(
            f"ts column must be Unix milliseconds (int), got {type(ts_sample).__name__}. "
            "ISO strings and other formats are not accepted."
        )
    if float(ts_sample) < _MIN_MS_THRESHOLD:
        raise ValueError(
            f"ts={ts_sample!r} looks like Unix seconds, not milliseconds. "
            f"Expected values ≥ {_MIN_MS_THRESHOLD:.0e}. Check source format."
        )

    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("ts").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    for col in _REQUIRED_COLS:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {p}")

    return df[list(_REQUIRED_COLS)].copy()
