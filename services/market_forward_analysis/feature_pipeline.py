"""Feature engineering pipeline for forecast quality upgrade.

Builds a unified 5m feature DataFrame from all available data sources:
  - Derivatives (OI, LS ratios, funding) — 5m aligned
  - ICT structural levels (PDH/PDL/PWH/PWL, session levels) — 1m, downsampled
  - Whatif-v3 enriched OHLCV (ATR, RSI, regime, session) — 1m, downsampled
  - MTF phase coherence (from phase_classifier) — resampled to 5m

Output: data/forecast_features/full_features_1y.parquet
  ~105k rows × ~50 features, DatetimeIndex UTC, 5m freq

All features are numeric. Categoricals are integer-encoded.
No lookahead: every feature at bar T uses only data available at T.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DERIV_DIR = _ROOT / "backtests" / "frozen" / "derivatives_1y"
_ICT_PATH  = _ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"
_WHATIF_PATH = _ROOT / "data" / "whatif_v3" / "btc_1m_enriched_2y.parquet"
_OUT_DIR   = _ROOT / "data" / "forecast_features"
_OUT_PATH  = _OUT_DIR / "full_features_1y.parquet"


# ── Loaders ──────────────────────────────────────────────────────────────────

def _load_oi(symbol: str = "BTCUSDT") -> pd.DataFrame:
    path = _DERIV_DIR / f"{symbol}_OI_5m_1y.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df.index.name = "ts"
    return df[["sum_open_interest", "sum_open_interest_value"]].sort_index()


def _load_ls(symbol: str = "BTCUSDT") -> pd.DataFrame:
    path = _DERIV_DIR / f"{symbol}_LS_5m_1y.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df.index.name = "ts"
    return df[["top_trader_ls_ratio", "global_ls_ratio", "taker_vol_ratio"]].sort_index()


def _load_funding(symbol: str = "BTCUSDT") -> pd.DataFrame:
    path = _DERIV_DIR / f"{symbol}_funding_8h_1y.parquet"
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df.index.name = "ts"
    return df[["fundingRate"]].sort_index()


def _load_ict() -> pd.DataFrame:
    """Load ICT 1m parquet. Returns with DatetimeIndex."""
    df = pd.read_parquet(_ICT_PATH)
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("ICT parquet index is not DatetimeIndex")
    return df.sort_index()


def _load_whatif() -> pd.DataFrame:
    """Load whatif-v3 enriched 1m OHLCV."""
    df = pd.read_parquet(_WHATIF_PATH)
    df.index = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df.index.name = "ts"
    return df.sort_index()


# ── Derivatives features ──────────────────────────────────────────────────────

def _build_deriv_features(oi: pd.DataFrame, ls: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    """Build derivative features at 5m granularity."""
    df = oi.copy()
    df = df.join(ls, how="left")

    # OI delta features
    df["oi_delta_1h"] = df["sum_open_interest"].pct_change(12) * 100   # 12×5m = 1h
    df["oi_delta_4h"] = df["sum_open_interest"].pct_change(48) * 100   # 48×5m = 4h

    # OI-price divergence: rolling OI change vs rolling price change (z-score)
    # Price is not available here — computed in merge step; set placeholder
    # (filled in _merge_all after OHLCV join)

    # Funding: forward-fill 8h rate to 5m bars
    funding_5m = funding.reindex(df.index, method="ffill")
    df["funding_rate"] = funding_5m["fundingRate"].fillna(0.0)

    # Funding z-score vs 30d rolling (30d × 24h / 8h = 90 obs)
    funding_roll_mean = df["funding_rate"].rolling(90, min_periods=10).mean()
    funding_roll_std  = df["funding_rate"].rolling(90, min_periods=10).std()
    df["funding_z"] = (df["funding_rate"] - funding_roll_mean) / (funding_roll_std + 1e-9)

    # LS ratios: top-traders ratio (>1 = more longs than shorts among top traders)
    df["ls_top_traders"] = df["top_trader_ls_ratio"].fillna(1.0)
    df["ls_global"]      = df["global_ls_ratio"].fillna(1.0)

    # Extreme flags: >70/30 long-short crowding
    # ls_ratio > 2.33 means 70/30 long crowded (70% long / 30% short = ratio 2.33)
    df["ls_long_extreme"]  = (df["ls_top_traders"] > 2.33).astype(np.int8)
    df["ls_short_extreme"] = (df["ls_top_traders"] < 0.43).astype(np.int8)

    # Taker buy/sell imbalance
    # taker_vol_ratio > 1 = more buy volume (bullish aggression)
    df["taker_imbalance_5m"] = df["taker_vol_ratio"].fillna(1.0) - 1.0  # center at 0

    # Rolling taker imbalance: 15m (3 bars) and 1h (12 bars)
    df["taker_imbalance_15m"] = df["taker_imbalance_5m"].rolling(3, min_periods=1).mean()
    df["taker_imbalance_1h"]  = df["taker_imbalance_5m"].rolling(12, min_periods=3).mean()

    # Taker aggression z-score vs 24h rolling
    taker_roll_mean = df["taker_imbalance_5m"].rolling(288, min_periods=20).mean()
    taker_roll_std  = df["taker_imbalance_5m"].rolling(288, min_periods=20).std()
    df["taker_aggression_z"] = (df["taker_imbalance_5m"] - taker_roll_mean) / (taker_roll_std + 1e-9)

    return df


# ── ICT / microstructure features ────────────────────────────────────────────

def _build_ict_features_5m(ict_1m: pd.DataFrame) -> pd.DataFrame:
    """Downsample ICT 1m features to 5m (last bar of each 5m window)."""
    ict_5m = ict_1m.resample("5min").last()

    # Pre-computed dist columns already in ICT parquet
    cols_needed = [
        "dist_to_pdh_pct", "dist_to_pdl_pct",
        "dist_to_pwh_pct", "dist_to_pwl_pct",
        "dist_to_d_open_pct",
        "dist_to_nearest_unmitigated_high_pct",
        "dist_to_nearest_unmitigated_low_pct",
        "nearest_unmitigated_high_above_age_h",
        "nearest_unmitigated_low_below_age_h",
        "unmitigated_count_7d",
        # Asia dist — pre-computed in ICT parquet
        "dist_to_asia_high_pct",
        "dist_to_asia_low_pct",
        # Kill zone midpoint — pre-computed in ICT parquet
        "dist_to_kz_mid_pct",
        # Raw session levels for derived distances + MSB proxy
        "close", "london_high", "london_low",
        "ny_am_high", "ny_am_low",
        "ny_pm_high", "ny_pm_low",
        "session_active",
    ]
    available = [c for c in cols_needed if c in ict_5m.columns]
    out = ict_5m[available].copy()

    # Compute london/ny_am/ny_pm distances from raw levels (not pre-computed in parquet)
    if "close" in out.columns:
        close = out["close"]
        for sess, hi, lo in [
            ("london",  "london_high",  "london_low"),
            ("ny_am",   "ny_am_high",   "ny_am_low"),
            ("ny_pm",   "ny_pm_high",   "ny_pm_low"),
        ]:
            hi_col = f"dist_to_{sess}_high_pct"
            lo_col = f"dist_to_{sess}_low_pct"
            if hi in out.columns:
                out[hi_col] = (close - out[hi]) / out[hi].replace(0, np.nan) * 100
                out[lo_col] = (close - out[lo]) / out[lo].replace(0, np.nan) * 100

        # MSB proxy: did close break a prior session level?
        # Negative dist means close is BELOW the level (break of high = price below it = no break)
        # dist_to_X_high_pct < 0 means close < session_high (inside)
        # dist_to_X_high_pct > 0 means close > session_high (break above = bullish MSB)
        for dist_hi_col, dist_lo_col, flag_prefix in [
            ("dist_to_asia_high_pct",   "dist_to_asia_low_pct",   "asia"),
            ("dist_to_london_high_pct", "dist_to_london_low_pct", "london"),
            ("dist_to_ny_am_high_pct",  "dist_to_ny_am_low_pct",  "ny_am"),
        ]:
            if dist_hi_col in out.columns and dist_lo_col in out.columns:
                broke_high = (out[dist_hi_col] > 0).astype(np.int8)
                broke_low  = (out[dist_lo_col] < 0).astype(np.int8)
                out[f"{flag_prefix}_high_broken"] = broke_high
                out[f"{flag_prefix}_low_broken"]  = broke_low

        # Rolling bars since last session high/low break (capped at 48 bars = 4h)
        # Uses Asia as primary MSB proxy (most liquid reference session)
        if "asia_high_broken" in out.columns:
            not_broken_h = (out["asia_high_broken"] == 0).astype(int)
            not_broken_l = (out["asia_low_broken"]  == 0).astype(int)
            # Cumsum trick: bars since last break = bar_idx - last_break_bar_idx
            grp_h = not_broken_h.cumsum()
            grp_l = not_broken_l.cumsum()
            out["bars_since_asia_high_break"] = out.groupby(grp_h).cumcount().clip(0, 48).astype(np.int8)
            out["bars_since_asia_low_break"]  = out.groupby(grp_l).cumcount().clip(0, 48).astype(np.int8)

    # Drop raw level columns used only for distance computation
    raw_level_cols = ["close", "london_high", "london_low",
                      "ny_am_high", "ny_am_low", "ny_pm_high", "ny_pm_low"]
    out = out.drop(columns=[c for c in raw_level_cols if c in out.columns])

    # Derived: in premium zone (price above d_open) and discount zone (below)
    if "dist_to_d_open_pct" in out.columns:
        out["in_premium_zone"] = (out["dist_to_d_open_pct"] > 0).astype(np.int8)
        out["in_discount_zone"] = (out["dist_to_d_open_pct"] < 0).astype(np.int8)

    # Session active as integer
    if "session_active" in out.columns:
        sess_map = {"dead": 0, "asia": 1, "london": 2, "ny_am": 3, "ny_lunch": 4, "ny_pm": 5}
        out["session_int"] = out["session_active"].map(sess_map).fillna(0).astype(np.int8)
        out = out.drop(columns=["session_active"])

    return out.sort_index()


def _build_microstructure_features_5m(whatif_1m: pd.DataFrame) -> pd.DataFrame:
    """Build microstructure features from 1m OHLCV, downsampled to 5m."""
    df = whatif_1m[["open", "high", "low", "close", "volume",
                     "atr_14", "rsi_14", "rsi_50", "rvol_20",
                     "candle_dir", "session", "regime_24h",
                     "delta_24h_pct", "volatility_tier"]].copy()

    # Per-bar candle metrics
    df["body_abs"]   = (df["close"] - df["open"]).abs()
    df["range_abs"]  = df["high"] - df["low"]
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["body_to_range"] = (df["body_abs"] / (df["range_abs"] + 1e-9)).clip(0, 1)

    # Resample to 5m
    agg = {
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum",
        "atr_14": "last", "rsi_14": "last", "rsi_50": "last", "rvol_20": "last",
        "body_to_range": "mean",
        "upper_wick": "sum", "lower_wick": "sum", "range_abs": "sum",
        "candle_dir": "last",
        "regime_24h": "last", "volatility_tier": "last",
        "delta_24h_pct": "last",
    }
    # Only include columns that exist
    agg = {k: v for k, v in agg.items() if k in df.columns}
    out = df.resample("5min").agg(agg)

    # Volume profile features (5m window)
    if "upper_wick" in out.columns and "lower_wick" in out.columns and "range_abs" in out.columns:
        out["upper_wick_dominance"] = out["upper_wick"] / (out["range_abs"] + 1e-9)
        out["lower_wick_dominance"] = out["lower_wick"] / (out["range_abs"] + 1e-9)

    # Rolling features at 5m granularity (1h = 12 bars, 4h = 48 bars)
    if "close" in out.columns:
        # Tick pressure: close vs midpoint of bar
        out["tick_pressure"] = (out["close"] - (out["high"] + out["low"]) / 2) / (out["high"] - out["low"] + 1e-9)

        # Consecutive closes higher (rolling 20 bars = ~100 min)
        out["close_higher_20"] = (out["close"] > out["close"].shift(1)).rolling(20, min_periods=5).sum()

    if "volume" in out.columns:
        # Volume acceleration: current vol vs rolling 12-bar mean
        vol_roll = out["volume"].rolling(12, min_periods=3).mean()
        out["volume_acceleration"] = out["volume"] / (vol_roll + 1e-9) - 1.0

    # Realized vol ratio: 5m std vs 30m std (6 bars)
    if "close" in out.columns:
        ret = out["close"].pct_change()
        rv_5m = ret.rolling(1).std()
        rv_30m = ret.rolling(6, min_periods=2).std()
        out["realized_vol_ratio"] = rv_5m / (rv_30m + 1e-9)

    # CCI(20) on hlc3
    if all(c in out.columns for c in ["high", "low", "close"]):
        hlc3 = (out["high"] + out["low"] + out["close"]) / 3
        sma20 = hlc3.rolling(20, min_periods=5).mean()
        mean_dev = hlc3.rolling(20, min_periods=5).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=True
        )
        out["cci_20"] = (hlc3 - sma20) / (0.015 * mean_dev.replace(0, np.nan))
        out["cci_20"] = out["cci_20"].fillna(0.0).clip(-500, 500)
        out["cci_overbought"]   = (out["cci_20"] > 100).astype(np.int8)
        out["cci_oversold"]     = (out["cci_20"] < -100).astype(np.int8)
        out["cci_extreme_high"] = (out["cci_20"] > 300).astype(np.int8)
        out["cci_extreme_low"]  = (out["cci_20"] < -300).astype(np.int8)

    # Regime encoding
    if "regime_24h" in out.columns:
        regime_map = {"bullish": 1, "bearish": -1, "neutral": 0, "range": 0,
                      "uptrend": 1, "downtrend": -1, "sideways": 0}
        out["regime_int"] = out["regime_24h"].map(regime_map).fillna(0).astype(np.int8)
        out = out.drop(columns=["regime_24h"])

    if "volatility_tier" in out.columns:
        vt_map = {"low": 0, "medium": 1, "high": 2, "extreme": 3}
        out["vol_tier_int"] = out["volatility_tier"].map(vt_map).fillna(1).astype(np.int8)
        out = out.drop(columns=["volatility_tier"])

    if "candle_dir" in out.columns:
        out["candle_dir_int"] = out["candle_dir"].map({1: 1, -1: -1, 0: 0}).fillna(0).astype(np.int8)
        out = out.drop(columns=["candle_dir"])

    return out.sort_index()


# ── Tier-2 features (volume profile + RSI derivatives) ───────────────────────

def _build_tier2_features_5m(df: pd.DataFrame, high: pd.Series, low: pd.Series) -> pd.DataFrame:
    """Compute Tier-2 features on an already-merged 5m DataFrame.

    Requires: close, volume, atr_14, rsi_14, rsi_50 in df.
    high/low must be aligned Series (from raw OHLCV source).
    """
    out = df.copy()
    close  = out["close"]
    volume = out["volume"] if "volume" in out.columns else pd.Series(1.0, index=out.index)
    rsi14  = out["rsi_14"]
    rsi50  = out["rsi_50"] if "rsi_50" in out.columns else pd.Series(50.0, index=out.index)

    # ── Volume Profile (100-bar VWAP as POC proxy) ──
    window = 100
    typical = (high + low + close) / 3
    vwap100  = (typical * volume).rolling(window, min_periods=20).sum() / volume.rolling(window, min_periods=20).sum()
    pstd     = typical.rolling(window, min_periods=20).std()
    va_high  = vwap100 + pstd
    va_low   = vwap100 - pstd

    out["vol_profile_poc_dist_pct"]    = ((close - vwap100) / (vwap100 + 1e-9) * 100).clip(-50, 50)
    out["vol_profile_va_high_dist_pct"] = ((close - va_high) / (va_high + 1e-9) * 100).clip(-50, 50)
    out["vol_profile_va_low_dist_pct"]  = ((close - va_low)  / (va_low  + 1e-9) * 100).clip(-50, 50)
    out["vol_profile_position"] = np.where(close > va_high, 1, np.where(close < va_low, -1, 0)).astype(np.int8)

    # Realized vol percentile (ATR rank in 24h rolling window)
    atr_pctile = out["atr_14"].rolling(288, min_periods=10).apply(lambda x: (x <= x[-1]).mean(), raw=True).fillna(0.5)
    out["realized_vol_pctile_24h"] = atr_pctile.clip(0, 1)
    out["vol_regime_int"] = pd.cut(atr_pctile, bins=[0, 0.33, 0.67, 1.0],
                                   labels=[0, 1, 2], include_lowest=True).astype(float).fillna(1).astype(np.int8)

    # ── RSI Derivatives ──
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    vw_gain = (gain * volume).rolling(14, min_periods=14).sum() / volume.rolling(14, min_periods=14).sum()
    vw_loss = (loss * volume).rolling(14, min_periods=14).sum() / volume.rolling(14, min_periods=14).sum()
    rs = vw_gain / (vw_loss + 1e-9)
    out["rsi_14_volume_weighted"] = (100 - 100 / (1 + rs)).fillna(50).clip(0, 100)

    out["orsi_14"] = (rsi14 - rsi14.ewm(span=9, min_periods=3).mean()).clip(-50, 50)

    out["rsi_zone_int"] = pd.cut(rsi14, bins=[0, 30, 50, 70, 100],
                                 labels=[0, 1, 2, 3], include_lowest=True).astype(float).fillna(1).astype(np.int8)

    prev14 = rsi14.shift(1)
    prev50 = rsi50.shift(1)
    out["rsi_crossover_up"]   = ((rsi14 > rsi50) & (prev14 <= prev50)).astype(np.int8)
    out["rsi_crossover_down"] = ((rsi14 < rsi50) & (prev14 >= prev50)).astype(np.int8)

    lag = 60  # 5h at 5m resolution
    price_ago = close.shift(lag)
    rsi_ago   = rsi14.shift(lag)
    bear_div = ((close > price_ago) & (rsi14 < rsi_ago)).astype(np.int8)
    bull_div = ((close < price_ago) & (rsi14 > rsi_ago)).astype(np.int8)
    out["rsi_divergence_5h"] = np.where(bear_div, -1, np.where(bull_div, 1, 0)).astype(np.int8)

    return out.sort_index()


# ── OI-price divergence (needs both) ─────────────────────────────────────────

def _add_oi_price_divergence(df: pd.DataFrame) -> pd.DataFrame:
    """Compute OI-price divergence after merging OHLCV and OI."""
    if "close" not in df.columns or "sum_open_interest" not in df.columns:
        return df

    price_ret_1h = df["close"].pct_change(12) * 100
    price_ret_4h = df["close"].pct_change(48) * 100

    # Divergence = OI change - price change (both %)
    # Positive: OI growing faster than price (potential squeeze setup)
    df["oi_price_div_1h"] = df["oi_delta_1h"].fillna(0) - price_ret_1h.fillna(0)
    df["oi_price_div_4h"] = df["oi_delta_4h"].fillna(0) - price_ret_4h.fillna(0)

    # Z-score of divergence (rolling 24h = 288 bars)
    for col in ["oi_price_div_1h", "oi_price_div_4h"]:
        roll_mean = df[col].rolling(288, min_periods=20).mean()
        roll_std  = df[col].rolling(288, min_periods=20).std()
        df[f"{col}_z"] = (df[col] - roll_mean) / (roll_std + 1e-9)

    return df


# ── Main pipeline ─────────────────────────────────────────────────────────────

def build_full_features(
    symbol: str = "BTCUSDT",
    force_rebuild: bool = False,
) -> pd.DataFrame:
    """Build full 5m feature DataFrame and cache to parquet.

    Returns DataFrame with DatetimeIndex (UTC), 5m frequency.
    Date range: overlap of all sources (May 2025 → Apr 2026, ~105k bars).
    """
    if _OUT_PATH.exists() and not force_rebuild:
        logger.info("feature_pipeline: loading cached features from %s", _OUT_PATH)
        return pd.read_parquet(_OUT_PATH)

    logger.info("feature_pipeline: building full features for %s", symbol)

    # ── Load all sources ──
    logger.info("feature_pipeline: loading derivatives...")
    oi      = _load_oi(symbol)
    ls      = _load_ls(symbol)
    funding = _load_funding(symbol)

    logger.info("feature_pipeline: loading ICT 1m (%s rows)...", len(pd.read_parquet(_ICT_PATH)) if _ICT_PATH.exists() else "missing")
    ict_1m = _load_ict() if _ICT_PATH.exists() else pd.DataFrame()

    logger.info("feature_pipeline: loading whatif 1m enriched...")
    whatif_1m = _load_whatif() if _WHATIF_PATH.exists() else pd.DataFrame()

    # ── Build feature blocks ──
    logger.info("feature_pipeline: building derivatives features...")
    deriv = _build_deriv_features(oi, ls, funding)

    logger.info("feature_pipeline: building ICT 5m features...")
    ict_5m = _build_ict_features_5m(ict_1m) if not ict_1m.empty else pd.DataFrame()

    logger.info("feature_pipeline: building microstructure 5m features...")
    micro_5m = _build_microstructure_features_5m(whatif_1m) if not whatif_1m.empty else pd.DataFrame()

    # ── Merge on 5m DatetimeIndex ──
    # Base: derivatives (already 5m)
    base = deriv.copy()
    if not ict_5m.empty:
        base = base.join(ict_5m, how="left", rsuffix="_ict")
    if not micro_5m.empty:
        base = base.join(micro_5m, how="left", rsuffix="_micro")

    # ── OI-price divergence (needs close) ──
    base = _add_oi_price_divergence(base)

    # ── Trim to common window ──
    # All sources must have data. Drop rows where key features are all NaN.
    key_cols = ["sum_open_interest", "taker_imbalance_5m"]
    available_keys = [c for c in key_cols if c in base.columns]
    if available_keys:
        base = base.dropna(subset=available_keys[:1])

    # Drop pure-NaN columns
    base = base.dropna(axis=1, how="all")

    # Forward-fill remaining NaNs (e.g., ICT levels that don't update every 5m)
    base = base.ffill().fillna(0.0)

    # Replace infs (from pct_change at series start or zero denominators)
    base = base.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)

    # Drop non-numeric columns
    numeric_cols = base.select_dtypes(include=[np.number]).columns
    base = base[numeric_cols]

    # Remove raw OHLCV price levels (perfect corr with each other; close kept for reference only)
    # and helper columns not needed downstream
    drop_cols = [
        "ts_ms", "sum_open_interest_value", "top_trader_ls_ratio",
        "global_ls_ratio", "taker_vol_ratio",
        "open", "high", "low",          # raw prices — redundant with close
        "upper_wick", "lower_wick", "range_abs",  # raw wicks — encoded via ratios
        "in_discount_zone",             # perfect complement of in_premium_zone
        "taker_aggression_z",           # 0.957 corr with taker_imbalance_5m; keep 5m
    ]
    base = base.drop(columns=[c for c in drop_cols if c in base.columns])

    logger.info("feature_pipeline: final shape %s, date range %s -> %s",
                base.shape, base.index[0] if len(base) else "?", base.index[-1] if len(base) else "?")

    # ── Cache ──
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    base.to_parquet(_OUT_PATH, compression="zstd")
    logger.info("feature_pipeline: saved to %s", _OUT_PATH)

    return base


# ── Sanity report (CHECKPOINT 1) ─────────────────────────────────────────────

def feature_sanity_report(df: pd.DataFrame) -> dict:
    """Run CHECKPOINT 1 sanity checks on the feature DataFrame."""
    report: dict = {}

    report["shape"] = {"rows": len(df), "cols": len(df.columns)}
    report["date_range"] = {
        "start": str(df.index[0]) if len(df) else "empty",
        "end":   str(df.index[-1]) if len(df) else "empty",
    }

    # Null check
    null_counts = df.isnull().sum()
    report["nulls"] = {
        "total_null_cells": int(null_counts.sum()),
        "cols_with_nulls": null_counts[null_counts > 0].to_dict(),
    }

    # Inf check
    inf_counts = {c: int(np.isinf(df[c]).sum()) for c in df.columns if df[c].dtype.kind == "f"}
    inf_nonzero = {k: v for k, v in inf_counts.items() if v > 0}
    report["infs"] = {"cols_with_infs": inf_nonzero}

    # Distribution summary
    desc = df.describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95])
    report["distributions"] = {
        col: {
            "mean": round(float(desc.loc["mean", col]), 4),
            "std":  round(float(desc.loc["std", col]), 4),
            "p5":   round(float(desc.loc["5%", col]), 4),
            "p95":  round(float(desc.loc["95%", col]), 4),
        }
        for col in df.columns
        if col in desc.columns
    }

    # Degenerate features: std near zero (constant) or extreme correlation
    stds = df.std()
    report["degenerate_low_std"] = stds[stds < 1e-6].index.tolist()

    # Sample at known events: Aug-Sep 2025 correction
    sample_window = df["2025-08-01":"2025-09-30"]
    if not sample_window.empty:
        report["sample_aug_sep_2025"] = {
            "rows": len(sample_window),
            "oi_delta_4h_mean": round(float(sample_window["oi_delta_4h"].mean()), 4) if "oi_delta_4h" in sample_window.columns else None,
            "funding_z_mean": round(float(sample_window["funding_z"].mean()), 4) if "funding_z" in sample_window.columns else None,
            "taker_imbalance_1h_mean": round(float(sample_window["taker_imbalance_1h"].mean()), 4) if "taker_imbalance_1h" in sample_window.columns else None,
        }

    # Cross-correlation check (flag pairs > 0.95)
    numeric_df = df.select_dtypes(include=[np.number])
    if len(numeric_df.columns) > 1:
        # Sample for speed
        sample = numeric_df.iloc[::10]  # every 10th row
        corr = sample.corr().abs()
        high_corr_pairs = []
        cols = corr.columns.tolist()
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                if corr.iloc[i, j] > 0.95:
                    high_corr_pairs.append((cols[i], cols[j], round(float(corr.iloc[i, j]), 3)))
        report["high_correlation_pairs"] = high_corr_pairs[:20]  # cap at 20

    return report
