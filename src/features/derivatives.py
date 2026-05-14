"""Derivative market features.

Input: 1-minute OHLCV + derivatives columns, pre-aligned by pipeline.compute().
No I/O — module receives an already-merged 1m UTC DataFrame.

Required source columns (set by pipeline from parquet files):
  metrics_5m:  oi_value, ls_ratio_top, ls_ratio_retail,
               taker_buy_volume, taker_sell_volume
  funding_8h:  funding_rate

Missing columns: derived features are filled with NaN/False (no crash).
Warmup: NaN until rolling window accumulates enough data.

Computes 12 columns:
  OI (3):      oi_delta_1h, oi_delta_pct_1h, oi_zscore_24h
  Funding (3): funding_zscore, funding_extreme_long, funding_extreme_short
  L/S (3):     ls_top_zscore, ls_retail_zscore, ls_divergence
  Taker (3):   taker_imbalance, taker_imbalance_zscore, taker_buy_ratio

Reference: ICT_KILLZONES_SPEC §13, TZ-017 §3.1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Window constants (1m bars)
_OI_DELTA_BARS      = 60      # 1h OI change
_OI_ZSCORE_WINDOW   = 1440    # 24h
_LS_ZSCORE_WINDOW   = 1440    # 24h
_TAKER_ZSCORE_WINDOW = 1440   # 24h
_FUNDING_ZSCORE_WINDOW = 10_080  # 7 days (funding updates every 8h = 480 bars)

# Extreme funding thresholds (absolute value of rate, expressed as fraction)
_FUNDING_EXTREME_LONG  =  0.0005   # +0.05%
_FUNDING_EXTREME_SHORT = -0.0005   # -0.05%


def _zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score. NaN during warm-up (< 2 observations)."""
    mean = series.rolling(window, min_periods=2).mean()
    std  = series.rolling(window, min_periods=2).std()
    return (series - mean) / std.replace(0, np.nan)


def _get(df: pd.DataFrame, col: str) -> pd.Series:
    """Return column if present, else NaN Series with same index."""
    if col in df.columns:
        return df[col].astype(float)
    return pd.Series(np.nan, index=df.index, dtype=float)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add 12 derivative feature columns to *df*.

    Args:
        df: 1-minute DataFrame with UTC tz-aware DatetimeIndex.
            Source columns provided by pipeline (missing → NaN features).

    Returns:
        Copy of *df* with additional columns.
    """
    out = df.copy()
    if len(out) == 0:
        return out

    oi     = _get(out, "oi_value")
    ls_top = _get(out, "ls_ratio_top")
    ls_ret = _get(out, "ls_ratio_retail")
    t_buy  = _get(out, "taker_buy_volume")
    t_sell = _get(out, "taker_sell_volume")
    fund   = _get(out, "funding_rate")

    # ── OI features ───────────────────────────────────────────────────────────
    oi_prev = oi.shift(_OI_DELTA_BARS)
    out["oi_delta_1h"]     = oi - oi_prev
    out["oi_delta_pct_1h"] = (oi - oi_prev) / oi_prev.replace(0, np.nan) * 100.0
    out["oi_zscore_24h"]   = _zscore(oi, _OI_ZSCORE_WINDOW)

    # ── Funding features ──────────────────────────────────────────────────────
    out["funding_zscore"]        = _zscore(fund, _FUNDING_ZSCORE_WINDOW)
    out["funding_extreme_long"]  = fund > _FUNDING_EXTREME_LONG
    out["funding_extreme_short"] = fund < _FUNDING_EXTREME_SHORT

    # ── L/S ratio features ────────────────────────────────────────────────────
    out["ls_top_zscore"]    = _zscore(ls_top, _LS_ZSCORE_WINDOW)
    out["ls_retail_zscore"] = _zscore(ls_ret, _LS_ZSCORE_WINDOW)
    out["ls_divergence"]    = ls_top - ls_ret

    # ── Taker features ────────────────────────────────────────────────────────
    t_total = t_buy + t_sell
    t_total_safe = t_total.replace(0, np.nan)
    out["taker_imbalance"]        = (t_buy - t_sell) / t_total_safe
    out["taker_imbalance_zscore"] = _zscore(out["taker_imbalance"], _TAKER_ZSCORE_WINDOW)
    out["taker_buy_ratio"]        = t_buy / t_total_safe

    return out
