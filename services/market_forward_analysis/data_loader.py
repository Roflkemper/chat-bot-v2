"""Data loader for market_forward_analysis.

Reuses existing frozen OHLCV CSVs + derivatives parquets.
Extends MTFDataCache to include 1d timeframe + derivatives columns.

All frames returned have DatetimeIndex (UTC) and OHLCV columns.
Derivatives columns are merged onto the corresponding OHLCV frame.
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

_OHLCV_1M = {
    "BTCUSDT": _ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv",
    "ETHUSDT": _ROOT / "backtests" / "frozen" / "ETHUSDT_1m_2y.csv",
    "XRPUSDT": _ROOT / "backtests" / "frozen" / "XRPUSDT_1m_2y.csv",
}
_DERIV_DIR = _ROOT / "backtests" / "frozen" / "derivatives_1y"
_MARKET_STATE = _ROOT / "storage" / "market_state.json"

_AGGS = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def _load_1m(symbol: str = "BTCUSDT", tail_days: int = 90) -> Optional[pd.DataFrame]:
    """Load 1m OHLCV CSV, keep last tail_days days."""
    path = _OHLCV_1M.get(symbol)
    if path is None or not path.exists():
        logger.warning("data_loader: 1m CSV not found for %s", symbol)
        return None
    try:
        df = pd.read_csv(path, usecols=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts").sort_index()
        if tail_days:
            cutoff = df.index[-1] - pd.Timedelta(days=tail_days)
            df = df[df.index >= cutoff].copy()
        return df
    except Exception:
        logger.exception("data_loader: failed to load 1m %s", symbol)
        return None


def _resample(df1m: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df1m.resample(rule).agg(_AGGS).dropna(subset=["close"])


def _load_oi(symbol: str) -> Optional[pd.DataFrame]:
    path = _DERIV_DIR / f"{symbol}_OI_5m_1y.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        return df.set_index("ts").sort_index()
    except Exception:
        logger.exception("data_loader: OI load failed %s", symbol)
        return None


def _load_ls(symbol: str) -> Optional[pd.DataFrame]:
    path = _DERIV_DIR / f"{symbol}_LS_5m_1y.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        return df.set_index("ts").sort_index()
    except Exception:
        logger.exception("data_loader: LS load failed %s", symbol)
        return None


def _load_funding(symbol: str) -> Optional[pd.DataFrame]:
    path = _DERIV_DIR / f"{symbol}_funding_8h_1y.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        return df.set_index("ts").sort_index()
    except Exception:
        logger.exception("data_loader: funding load failed %s", symbol)
        return None


def _merge_derivatives(ohlcv: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Merge OI + LS + funding onto OHLCV (forward-fill for sparse funding)."""
    oi_df  = _load_oi(symbol)
    ls_df  = _load_ls(symbol)
    fr_df  = _load_funding(symbol)

    result = ohlcv.copy()

    if oi_df is not None:
        oi_cols = ["sum_open_interest", "sum_open_interest_value"]
        merged = result.join(oi_df[oi_cols], how="left")
        # Forward fill from 5m resolution
        merged[oi_cols] = merged[oi_cols].ffill().bfill()
        result = merged

    if ls_df is not None:
        ls_cols = ["top_trader_ls_ratio", "global_ls_ratio", "taker_vol_ratio"]
        available = [c for c in ls_cols if c in ls_df.columns]
        if available:
            merged = result.join(ls_df[available], how="left")
            merged[available] = merged[available].ffill().bfill()
            result = merged

    if fr_df is not None and "fundingRate" in fr_df.columns:
        merged = result.join(fr_df[["fundingRate"]], how="left")
        merged["fundingRate"] = merged["fundingRate"].ffill().bfill()
        result = merged

    return result


class ForwardAnalysisDataLoader:
    """Data loader for market_forward_analysis. Thread-safe after construction.

    Provides:
        get(timeframe)    — OHLCV DataFrame for given TF
        refresh(tail_days) — reload from disk (call each tick)
        current_price()   — float from market_state.json
    """

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol
        self._frames: dict[str, pd.DataFrame] = {}
        self._source_1m: Optional[pd.DataFrame] = None

    def refresh(self, tail_days: int = 90) -> None:
        """Reload 1m source, resample all TFs, merge derivatives."""
        df1m = _load_1m(self.symbol, tail_days=tail_days)
        if df1m is None or df1m.empty:
            logger.warning("ForwardAnalysisDataLoader: no 1m data for %s", self.symbol)
            return
        self._source_1m = df1m

        for tf, rule in [("15m", "15min"), ("1h", "1h"), ("4h", "4h"), ("1d", "1D")]:
            try:
                resampled = _resample(df1m, rule)
                # Merge derivatives on 1h and higher (OI/LS are 5m, funding 8h)
                if tf in ("1h", "4h", "1d"):
                    resampled = _merge_derivatives(resampled, self.symbol)
                self._frames[tf] = resampled
            except Exception:
                logger.exception("ForwardAnalysisDataLoader: resample failed tf=%s", tf)

    def get(self, timeframe: str) -> Optional[pd.DataFrame]:
        return self._frames.get(timeframe)

    def current_price(self) -> float:
        try:
            if _MARKET_STATE.exists():
                data = json.loads(_MARKET_STATE.read_text(encoding="utf-8"))
                return float(data.get("price", 0.0) or 0.0)
        except Exception:
            pass
        return 0.0

    def all_frames(self) -> dict[str, Optional[pd.DataFrame]]:
        return {tf: self._frames.get(tf) for tf in ("1d", "4h", "1h", "15m")}
