from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pathlib import Path


def make_synthetic_ohlcv(
    n: int = 1000,
    start_price: float = 80000.0,
    freq: str = "1min",
    start: str = "2026-01-01",
    include_dumps: bool = True,
) -> pd.DataFrame:
    """Synthetic 1-minute OHLCV with some dump episodes."""
    rng = np.random.default_rng(42)
    prices = [start_price]
    for i in range(n - 1):
        # Every 200 bars, simulate a 3% dump
        if include_dumps and i % 200 == 100:
            change = -0.005
        else:
            change = rng.normal(0, 0.0005)
        prices.append(prices[-1] * (1 + change))
    prices_arr = np.array(prices)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": prices_arr,
        "high": prices_arr * (1 + rng.uniform(0, 0.002, n)),
        "low": prices_arr * (1 - rng.uniform(0, 0.002, n)),
        "close": prices_arr,
        "volume": rng.uniform(50, 200, n),
    }, index=idx)


@pytest.fixture
def synthetic_1m_df() -> pd.DataFrame:
    return make_synthetic_ohlcv(n=2000)


@pytest.fixture
def synthetic_parquet(tmp_path: Path, synthetic_1m_df: pd.DataFrame) -> Path:
    p = tmp_path / "synthetic.parquet"
    synthetic_1m_df.to_parquet(p)
    return p
