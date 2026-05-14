"""Multi-timeframe OHLCV cache — centralises candle fetching for 15m/1h/4h.

Data source: storage/market_state.json (current price) + OHLCV parquet files.
Falls back to on-the-fly resampling from 1m data if higher TF files absent.

Usage:
    cache = MTFDataCache()
    df_1h = cache.get("1h")   # pd.DataFrame with OHLCV + derived columns
    cache.refresh()            # call each loop tick
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_MARKET_STATE = _ROOT / "storage" / "market_state.json"

# Where to find 1m data for resampling
_OHLCV_1M_PATHS = [
    _ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv",
    _ROOT / "data" / "BTCUSDT_1m.csv",
]

_RESAMPLE_RULES = {
    "15m": "15min",
    "1h":  "1h",
    "4h":  "4h",
}

_AGGS = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


class MTFDataCache:
    """Lazy-loading MTF data cache. Refreshes on each call to refresh()."""

    def __init__(self) -> None:
        self._frames: dict[str, pd.DataFrame] = {}
        self._last_refresh: Optional[datetime] = None
        self._source_df: Optional[pd.DataFrame] = None

    def refresh(self) -> None:
        """Reload 1m source and resample all timeframes."""
        df1m = self._load_1m()
        if df1m is None or df1m.empty:
            logger.warning("mtf_data: no 1m source found, cache empty")
            return
        self._source_df = df1m
        for tf, rule in _RESAMPLE_RULES.items():
            try:
                self._frames[tf] = (
                    df1m.resample(rule).agg(_AGGS).dropna(subset=["close"])
                )
            except Exception:
                logger.exception("mtf_data: resample failed tf=%s", tf)
        self._last_refresh = datetime.now(timezone.utc)

    def get(self, timeframe: str) -> Optional[pd.DataFrame]:
        """Return latest cached DataFrame for given timeframe (15m/1h/4h)."""
        return self._frames.get(timeframe)

    def current_price(self) -> float:
        """Read current BTC price from market_state.json."""
        try:
            if _MARKET_STATE.exists():
                data = json.loads(_MARKET_STATE.read_text(encoding="utf-8"))
                return float(data.get("price", 0.0) or 0.0)
        except Exception:
            pass
        return 0.0

    def _load_1m(self) -> Optional[pd.DataFrame]:
        for path in _OHLCV_1M_PATHS:
            if path.exists():
                try:
                    df = pd.read_csv(path)
                    if "ts" in df.columns:
                        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
                        df = df.set_index("ts").sort_index()
                    elif df.index.dtype == "int64":
                        df.index = pd.to_datetime(df.index, unit="ms", utc=True)
                    for col in ("open", "high", "low", "close"):
                        if col not in df.columns:
                            return None
                    # Keep only last 30 days to limit memory
                    cutoff = df.index[-1] - pd.Timedelta(days=30)
                    return df[df.index >= cutoff].copy()
                except Exception:
                    logger.exception("mtf_data: load failed path=%s", path)
        return None
