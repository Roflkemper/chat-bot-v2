"""Feature engineering for regime classification.

All features are computed per 1h bar with NO lookahead.
Rolling computations use only data up to and including bar T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute regime features for each 1h bar.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with UTC DatetimeIndex and columns: open, high, low, close, volume.
        Must be sorted ascending by index.

    Returns
    -------
    pd.DataFrame
        Same index as input, with feature columns. Uses min_periods=1 to avoid
        NaN on early rows.
    """
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    feats = pd.DataFrame(index=df.index)

    # ------------------------------------------------------------------
    # Range-based features
    # ------------------------------------------------------------------

    # Rolling 24h / 48h high and low
    high_24h = high.rolling(24, min_periods=1).max()
    low_24h = low.rolling(24, min_periods=1).min()
    high_48h = high.rolling(48, min_periods=1).max()
    low_48h = low.rolling(48, min_periods=1).min()

    feats["price_band_height_pct_24h"] = (high_24h - low_24h) / close.replace(0, np.nan) * 100
    feats["price_band_height_pct_48h"] = (high_48h - low_48h) / close.replace(0, np.nan) * 100

    # Fraction of last 24h bars where close is inside the band (with 0.1% inner margin)
    def _time_inside_band_24h(s_close, s_low24, s_high24):
        n = len(s_close)
        result = np.zeros(n, dtype=float)
        for i in range(n):
            window_start = max(0, i - 23)
            c_win = s_close.iloc[window_start : i + 1].values
            lo = s_low24.iloc[i]
            hi = s_high24.iloc[i]
            inner_lo = lo * 1.001
            inner_hi = hi * 0.999
            if inner_lo >= inner_hi:
                result[i] = 1.0
            else:
                result[i] = np.mean((c_win >= inner_lo) & (c_win <= inner_hi))
        return result

    feats["time_inside_band_24h_pct"] = _time_inside_band_24h(close, low_24h, high_24h)

    # Pivot density: local high/low pivots in T-26..T-2 (need i+1 for check)
    def _pivot_density_24h(s_high, s_low):
        n = len(s_high)
        result = np.zeros(n, dtype=float)
        h = s_high.values
        l = s_low.values
        for i in range(n):
            # Can safely check pivots at indices where we have i-1, i, i+1
            # For bar T (index i), we look at T-26..T-2
            # pivot at idx j requires j-1 and j+1, so j in [1..n-2]
            start = max(1, i - 25)  # T-25 to T-2 (25 bars back max, +1 offset)
            end = max(1, i - 1)    # T-2 (need j+1 <= T-1 <= i-1)
            count = 0
            for j in range(start, end + 1):
                if j + 1 <= i:  # ensure we don't use future data
                    if h[j] > h[j - 1] and h[j] > h[j + 1]:
                        count += 1
                    if l[j] < l[j - 1] and l[j] < l[j + 1]:
                        count += 1
            result[i] = count
        return result

    feats["pivot_density_24h"] = _pivot_density_24h(high, low)

    # ------------------------------------------------------------------
    # Displacement-based features
    # ------------------------------------------------------------------

    body = (close - df["open"]).abs()
    bar_range = (high - low).replace(0, np.nan)
    body_to_range = (body / bar_range).fillna(0.0)

    feats["body_to_range_max_4h"] = body_to_range.rolling(4, min_periods=1).max()

    close_prev = close.shift(1)
    roc_1h = ((close / close_prev.replace(0, np.nan)) - 1).abs() * 100
    feats["single_bar_roc_max_pct_4h"] = roc_1h.rolling(4, min_periods=1).max()

    disp_flag = ((body_to_range > 0.6) & (roc_1h > 0.5)).astype(float)
    feats["displacement_count_4h"] = disp_flag.rolling(4, min_periods=1).sum()

    feats["closed_outside_band_24h"] = (
        (close < low_24h * 0.997) | (close > high_24h * 1.003)
    ).astype(float)

    # ------------------------------------------------------------------
    # Volume features
    # ------------------------------------------------------------------

    vol_mean_24h = volume.rolling(24, min_periods=1).mean()
    vol_std_24h = volume.rolling(24, min_periods=1).std(ddof=0).clip(lower=1.0)
    feats["vol_z_score_4h"] = (volume - vol_mean_24h) / vol_std_24h

    vol_sum_4h = volume.rolling(4, min_periods=1).sum()
    # Rolling 7-day (168h) mean of 4h sums — no lookahead
    vol_sum_4h_mean_7d = vol_sum_4h.rolling(168, min_periods=1).mean().replace(0, np.nan)
    feats["vol_cumulative_4h_vs_avg"] = (vol_sum_4h / vol_sum_4h_mean_7d).fillna(1.0)

    # ------------------------------------------------------------------
    # Direction features
    # ------------------------------------------------------------------

    close_4 = close.shift(4)
    close_12 = close.shift(12)
    close_24 = close.shift(24)

    feats["roc_4h_pct"] = (close - close_4) / close_4.replace(0, np.nan) * 100
    feats["roc_12h_pct"] = (close - close_12) / close_12.replace(0, np.nan) * 100
    feats["roc_24h_pct"] = (close - close_24) / close_24.replace(0, np.nan) * 100

    # Consecutive higher highs in last 4 bars
    def _consec_hh(s_high):
        n = len(s_high)
        result = np.zeros(n, dtype=float)
        h = s_high.values
        for i in range(n):
            count = 0
            for j in range(max(1, i - 3), i + 1):
                if h[j] > h[j - 1]:
                    count += 1
                else:
                    count = 0  # reset on break
            result[i] = count
        return result

    def _consec_ll(s_low):
        n = len(s_low)
        result = np.zeros(n, dtype=float)
        l = s_low.values
        for i in range(n):
            count = 0
            for j in range(max(1, i - 3), i + 1):
                if l[j] < l[j - 1]:
                    count += 1
                else:
                    count = 0
            result[i] = count
        return result

    feats["consec_higher_highs_4h"] = _consec_hh(high)
    feats["consec_lower_lows_4h"] = _consec_ll(low)

    # ------------------------------------------------------------------
    # Volatility shape
    # ------------------------------------------------------------------

    atr_14h = (high - low).rolling(14, min_periods=1).mean() / close.replace(0, np.nan) * 100
    feats["atr_14h"] = atr_14h

    band_h = feats["price_band_height_pct_24h"].replace(0, np.nan)
    feats["atr_inside_band_ratio"] = (atr_14h / band_h).clip(lower=0.1, upper=10.0).fillna(0.1)

    # Fill remaining NaN with 0
    feats = feats.fillna(0.0)

    return feats


FEATURE_NAMES = [
    "price_band_height_pct_24h",
    "price_band_height_pct_48h",
    "time_inside_band_24h_pct",
    "pivot_density_24h",
    "body_to_range_max_4h",
    "single_bar_roc_max_pct_4h",
    "displacement_count_4h",
    "closed_outside_band_24h",
    "vol_z_score_4h",
    "vol_cumulative_4h_vs_avg",
    "roc_4h_pct",
    "roc_12h_pct",
    "roc_24h_pct",
    "consec_higher_highs_4h",
    "consec_lower_lows_4h",
    "atr_14h",
    "atr_inside_band_ratio",
]
