"""Technical indicator features.

Input df: UTC tz-aware 1-minute OHLCV DataFrame.
Required columns: open, high, low, close.
Optional column: volume (needed for vol_zscore, vol_ratio; NaN otherwise).

Computes 22 columns:
  1m base (5):      body_pct_1m, consec_bull, consec_bear, vol_zscore, vol_ratio
  15m (5):          momentum_15m, pin_bar_bull_15m, pin_bar_bear_15m,
                    engulfing_bull_15m, engulfing_bear_15m
  1h (12):          atr_1h, atr_pct_1h, rsi_1h, rsi_ob_1h, rsi_os_1h, momentum_1h,
                    pin_bar_bull_1h, pin_bar_bear_1h,
                    engulfing_bull_1h, engulfing_bear_1h,
                    rsi_div_bull, rsi_div_bear

No look-ahead policy: 1h bar [12:00, 13:00) closes at 13:00.
  Its ATR/RSI/pattern become available at 13:00 (shift +1, ffill).
  Pattern flags are True for all 1m bars within the following 1h period.

Pin bar thresholds: relevant wick ≥ 2/3 of range, body ≤ 1/3 of range.
Engulfing: current bar fully engulfs previous bar's body, opposite directions.
RSI divergence: vectorized via scipy.signal.find_peaks on 1h series.
ATR/RSI: Wilder's smoothing (ewm alpha=1/period, adjust=False).

Reference: ICT_KILLZONES_SPEC §12.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

_ATR_PERIOD = 14
_RSI_PERIOD = 14
_VOL_WINDOW = 20
_MOM_PERIOD = 10
_DIV_DISTANCE = 3  # min bars between detected peaks/troughs

_OHLCV_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
_OHL_AGG   = {"open": "first", "high": "max", "low": "min", "close": "last"}


# ── indicator helpers ──────────────────────────────────────────────────────────

def _atr(df: pd.DataFrame, period: int = _ATR_PERIOD) -> pd.Series:
    """Wilder's ATR (RMA smoothing, ignore_na=True to match TradingView)."""
    h, lo, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - lo, (h - prev_c).abs(), (lo - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, ignore_na=True).mean()


def _rsi(series: pd.Series, period: int = _RSI_PERIOD) -> pd.Series:
    """Wilder's RSI (RMA smoothing, ignore_na=True). RSI = 100*gain/(gain+loss)."""
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False, ignore_na=True).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False, ignore_na=True).mean()
    total = gain + loss
    rsi_vals = np.where(total > 0, 100.0 * gain / total, np.nan)
    return pd.Series(rsi_vals, index=series.index, dtype=float)


def _pin_bar_bull(df: pd.DataFrame) -> pd.Series:
    """Bull pin bar: lower wick ≥ 2/3 of range AND body ≤ 1/3 of range."""
    full_range = df["high"] - df["low"]
    safe_range = full_range.replace(0, np.nan)
    body = (df["close"] - df["open"]).abs()
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    return (full_range > 0) & (lower_wick / safe_range >= 2 / 3) & (body / safe_range <= 1 / 3)


def _pin_bar_bear(df: pd.DataFrame) -> pd.Series:
    """Bear pin bar: upper wick ≥ 2/3 of range AND body ≤ 1/3 of range."""
    full_range = df["high"] - df["low"]
    safe_range = full_range.replace(0, np.nan)
    body = (df["close"] - df["open"]).abs()
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    return (full_range > 0) & (upper_wick / safe_range >= 2 / 3) & (body / safe_range <= 1 / 3)


def _engulfing_bull(df: pd.DataFrame) -> pd.Series:
    """Bullish engulfing: prev bar bearish, current bullish and body engulfs prev body."""
    prev_o, prev_c = df["open"].shift(1), df["close"].shift(1)
    return (
        (prev_c < prev_o)           # prev bearish
        & (df["close"] > df["open"])  # curr bullish
        & (df["open"] <= prev_c)      # opens at or below prev close
        & (df["close"] >= prev_o)     # closes at or above prev open
    )


def _engulfing_bear(df: pd.DataFrame) -> pd.Series:
    """Bearish engulfing: prev bar bullish, current bearish and body engulfs prev body."""
    prev_o, prev_c = df["open"].shift(1), df["close"].shift(1)
    return (
        (prev_c > prev_o)
        & (df["close"] < df["open"])
        & (df["open"] >= prev_c)
        & (df["close"] <= prev_o)
    )


def _rsi_divergence(
    close: pd.Series,
    rsi: pd.Series,
    distance: int = _DIV_DISTANCE,
) -> tuple[pd.Series, pd.Series]:
    """Vectorized RSI divergence on 1h series.

    Bullish: price lower low, RSI higher low.
    Bearish: price higher high, RSI lower high.
    Returns (bull_div, bear_div) as bool Series with same index as close.
    """
    valid = ~(close.isna() | rsi.isna())
    c_arr = close[valid].to_numpy(dtype=float)
    r_arr = rsi[valid].to_numpy(dtype=float)
    valid_idx = close[valid].index

    bull_arr = np.zeros(len(c_arr), dtype=bool)
    bear_arr = np.zeros(len(c_arr), dtype=bool)

    if len(c_arr) > 2 * distance:
        peaks, _   = find_peaks(c_arr,  distance=distance)
        troughs, _ = find_peaks(-c_arr, distance=distance)

        for i in range(1, len(peaks)):
            p1, p2 = peaks[i - 1], peaks[i]
            if c_arr[p2] > c_arr[p1] and r_arr[p2] < r_arr[p1]:
                bear_arr[p2] = True

        for i in range(1, len(troughs)):
            t1, t2 = troughs[i - 1], troughs[i]
            if c_arr[t2] < c_arr[t1] and r_arr[t2] > r_arr[t1]:
                bull_arr[t2] = True

    bull = pd.Series(bull_arr, index=valid_idx).reindex(close.index, fill_value=False)
    bear = pd.Series(bear_arr, index=valid_idx).reindex(close.index, fill_value=False)
    return bull, bear


def _consec_run(arr: np.ndarray) -> np.ndarray:
    """Vectorized consecutive-True counter.

    Returns int array: positive run length at each True, 0 at each False.
    """
    arr = np.asarray(arr, dtype=bool)
    cumsum = np.cumsum(arr).astype(np.int64)
    # At every False position record the cumsum; NaN at True positions
    reset_at = np.where(~arr, cumsum.astype(float), np.nan)
    reset_ff = (
        pd.Series(reset_at).ffill().fillna(0).to_numpy(dtype=np.int64)
    )
    return np.where(arr, cumsum - reset_ff, 0).astype(np.int64)


# ── resample / map helpers ─────────────────────────────────────────────────────

def _resample_ohlcv(df_1m: pd.DataFrame, tf: str) -> pd.DataFrame:
    agg = _OHLCV_AGG if "volume" in df_1m.columns else _OHL_AGG
    return df_1m.resample(tf, label="left", closed="left").agg(agg).dropna(subset=["close"])


def _map_to_1m(series_tf: pd.Series, idx_1m: pd.DatetimeIndex) -> pd.Series:
    """Shift +1 bar (no look-ahead) then forward-fill to 1m index."""
    return series_tf.shift(1).reindex(idx_1m, method="ffill")


def _map_bool_to_1m(series_tf: pd.Series, idx_1m: pd.DatetimeIndex) -> pd.Series:
    """Bool pattern: shift +1 (confirmed only after bar closes) then ffill to 1m."""
    return (
        series_tf.shift(1)
        .astype(float)                          # avoid object dtype for ffill/fillna
        .reindex(idx_1m, method="ffill")
        .fillna(0.0)
        .astype(bool)
    )


# ── public API ─────────────────────────────────────────────────────────────────

def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add 22 technical feature columns to *df*.

    Args:
        df: 1-minute OHLCV DataFrame with UTC tz-aware DatetimeIndex.

    Returns:
        Copy of *df* with additional columns.
    """
    out = df.copy()
    if len(out) == 0:
        return out

    has_vol = "volume" in out.columns
    idx_1m = out.index
    close_1m = out["close"]
    open_1m  = out["open"]

    # ── 1m features ───────────────────────────────────────────────────────────
    full_range_1m = (out["high"] - out["low"]).replace(0, np.nan)
    out["body_pct_1m"] = (close_1m - open_1m).abs() / full_range_1m * 100.0

    out["consec_bull"] = _consec_run((close_1m > open_1m).to_numpy())
    out["consec_bear"] = _consec_run((close_1m < open_1m).to_numpy())

    if has_vol:
        vol = out["volume"]
        vol_mean = vol.rolling(_VOL_WINDOW, min_periods=1).mean()
        vol_std  = vol.rolling(_VOL_WINDOW, min_periods=2).std()
        out["vol_zscore"] = (vol - vol_mean) / vol_std.replace(0, np.nan)
        out["vol_ratio"]  = vol / vol_mean.replace(0, np.nan)
    else:
        out["vol_zscore"] = np.nan
        out["vol_ratio"]  = np.nan

    # ── 15m features ──────────────────────────────────────────────────────────
    df_15m = _resample_ohlcv(out, "15min")

    out["momentum_15m"]       = _map_to_1m(df_15m["close"].pct_change(_MOM_PERIOD) * 100.0, idx_1m)
    out["pin_bar_bull_15m"]   = _map_bool_to_1m(_pin_bar_bull(df_15m), idx_1m)
    out["pin_bar_bear_15m"]   = _map_bool_to_1m(_pin_bar_bear(df_15m), idx_1m)
    out["engulfing_bull_15m"] = _map_bool_to_1m(_engulfing_bull(df_15m), idx_1m)
    out["engulfing_bear_15m"] = _map_bool_to_1m(_engulfing_bear(df_15m), idx_1m)

    # ── 1h features ───────────────────────────────────────────────────────────
    df_1h = _resample_ohlcv(out, "1h")

    atr_1h_s = _atr(df_1h)
    rsi_1h_s = _rsi(df_1h["close"])

    out["atr_1h"]     = _map_to_1m(atr_1h_s, idx_1m)
    out["atr_pct_1h"] = out["atr_1h"] / close_1m * 100.0
    out["rsi_1h"]     = _map_to_1m(rsi_1h_s, idx_1m)
    out["rsi_ob_1h"]  = out["rsi_1h"] > 70.0
    out["rsi_os_1h"]  = out["rsi_1h"] < 30.0
    out["momentum_1h"] = _map_to_1m(df_1h["close"].pct_change(_MOM_PERIOD) * 100.0, idx_1m)

    out["pin_bar_bull_1h"]   = _map_bool_to_1m(_pin_bar_bull(df_1h), idx_1m)
    out["pin_bar_bear_1h"]   = _map_bool_to_1m(_pin_bar_bear(df_1h), idx_1m)
    out["engulfing_bull_1h"] = _map_bool_to_1m(_engulfing_bull(df_1h), idx_1m)
    out["engulfing_bear_1h"] = _map_bool_to_1m(_engulfing_bear(df_1h), idx_1m)

    rsi_div_bull, rsi_div_bear = _rsi_divergence(df_1h["close"], rsi_1h_s)
    out["rsi_div_bull"] = _map_bool_to_1m(rsi_div_bull, idx_1m)
    out["rsi_div_bear"] = _map_bool_to_1m(rsi_div_bear, idx_1m)

    return out
