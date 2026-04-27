"""Cross-asset features (BTC ↔ ETH ↔ XRP).

Input: merged 1m UTC DataFrame with prefixed columns prepared by pipeline.
  btc_*/eth_*/xrp_* OHLCV + delta cols already computed per-symbol.

Required columns:
  btc_close, eth_close, xrp_close
  btc_delta_5m_pct, eth_delta_5m_pct, xrp_delta_5m_pct
  btc_delta_15m_pct, xrp_delta_15m_pct
  btc_delta_1h_pct, eth_delta_1h_pct, xrp_delta_1h_pct

Optional:
  btc_oi_delta_pct_1h  (for all_dump_score_with_oi bonus)

Missing columns → NaN / neutral value (no crash).

Computes 10 columns (no prefix):

  §6.4.1 BTC-ETH (4):
    btc_eth_corr_4h          — rolling Pearson corr(btc_delta_5m_pct, eth_delta_5m_pct), 240 bars
    eth_btc_ratio            — eth_close / btc_close
    eth_btc_ratio_zscore_30d — 30d rolling zscore of ratio (window=43200)
    btc_eth_divergence_score — clip((btc_1h-eth_1h)/max(|btc_1h|,|eth_1h|,0.001), -1, 1)

  §6.4.2 XRP impulse (3):
    xrp_impulse_solo_score   — (xrp_15m - btc_15m) / max(|btc_15m|, 0.1)
    xrp_btc_corr_4h          — rolling Pearson corr(xrp_delta_5m_pct, btc_delta_5m_pct), 240 bars
    xrp_solo_direction       — sign(xrp_15m) if |xrp_impulse_solo_score|≥2.0, else 0

  §6.4.3 Synchro dump (3):
    all_dump_score           — 1.0 (all 3 <-2%), 0.5 (any 2 <-2%), 0.0 otherwise
    all_dump_score_with_oi   — all_dump_score + 0.2 if btc_oi_delta_1h_pct>0, clipped [0,1]
    dump_count_1h            — int 0-3: count of assets with delta_1h < -2%

Reference: TZ-017 §6.4, TZ-018 D-XRP-IMPULSE-SOLO, D-ALL-DUMP-SYNCHRO.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_CORR_WINDOW   = 240      # 4h in 1m bars
_RATIO_WINDOW  = 43_200   # 30d in 1m bars
_DUMP_THRESHOLD = -2.0    # % delta_1h to count as "dump"
_XRP_SOLO_MIN  = 2.0      # min |impulse_score| for xrp_solo_direction
_OI_BONUS      = 0.2


def _get(df: pd.DataFrame, col: str) -> pd.Series:
    """Return column as float; NaN Series if missing."""
    if col in df.columns:
        return df[col].astype(float)
    return pd.Series(np.nan, index=df.index, dtype=float)


def _zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=2).mean()
    std  = series.rolling(window, min_periods=2).std()
    return (series - mean) / std.replace(0, np.nan)


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Add 10 cross-asset feature columns to *df*.

    Args:
        df: merged 1m DataFrame with btc_*/eth_*/xrp_* prefixed columns.

    Returns:
        Copy of *df* with additional columns.
    """
    out = df.copy()
    if len(out) == 0:
        return out

    # Source columns
    btc_close   = _get(out, "btc_close")
    eth_close   = _get(out, "eth_close")

    btc_d5m  = _get(out, "btc_delta_5m_pct")
    eth_d5m  = _get(out, "eth_delta_5m_pct")
    xrp_d5m  = _get(out, "xrp_delta_5m_pct")

    btc_d15m = _get(out, "btc_delta_15m_pct")
    xrp_d15m = _get(out, "xrp_delta_15m_pct")

    btc_d1h  = _get(out, "btc_delta_1h_pct")
    eth_d1h  = _get(out, "eth_delta_1h_pct")
    xrp_d1h  = _get(out, "xrp_delta_1h_pct")

    # ── §6.4.1 BTC-ETH ────────────────────────────────────────────────────────
    out["btc_eth_corr_4h"] = btc_d5m.rolling(_CORR_WINDOW, min_periods=2).corr(eth_d5m)

    ratio = eth_close / btc_close.replace(0, np.nan)
    out["eth_btc_ratio"]            = ratio
    out["eth_btc_ratio_zscore_30d"] = _zscore(ratio, _RATIO_WINDOW)

    denom_div = (
        pd.concat([btc_d1h.abs(), eth_d1h.abs()], axis=1)
        .max(axis=1)
        .clip(lower=0.001)
    )
    out["btc_eth_divergence_score"] = ((btc_d1h - eth_d1h) / denom_div).clip(-1.0, 1.0)

    # ── §6.4.2 XRP impulse ────────────────────────────────────────────────────
    xrp_impulse = (xrp_d15m - btc_d15m) / btc_d15m.abs().clip(lower=0.1)
    out["xrp_impulse_solo_score"] = xrp_impulse

    out["xrp_btc_corr_4h"] = xrp_d5m.rolling(_CORR_WINDOW, min_periods=2).corr(btc_d5m)

    solo_active = xrp_impulse.abs() >= _XRP_SOLO_MIN
    out["xrp_solo_direction"] = np.where(
        solo_active,
        np.sign(xrp_d15m.fillna(0)),
        0,
    ).astype(np.int8)

    # ── §6.4.3 Synchro dump ───────────────────────────────────────────────────
    btc_dump = (btc_d1h < _DUMP_THRESHOLD).astype(int)
    eth_dump = (eth_d1h < _DUMP_THRESHOLD).astype(int)
    xrp_dump = (xrp_d1h < _DUMP_THRESHOLD).astype(int)

    dump_count = btc_dump + eth_dump + xrp_dump
    out["dump_count_1h"] = dump_count.astype(np.int8)

    all_dump = pd.Series(0.0, index=out.index, dtype=float)
    all_dump = all_dump.where(dump_count < 2, 0.5)
    all_dump = all_dump.where(dump_count < 3, 1.0)
    out["all_dump_score"] = all_dump

    if "btc_oi_delta_pct_1h" in out.columns:
        oi_col = out["btc_oi_delta_pct_1h"].astype(float)
        oi_bonus = (oi_col > 0).astype(float) * _OI_BONUS
        out["all_dump_score_with_oi"] = (all_dump + oi_bonus).clip(upper=1.0)
    else:
        out["all_dump_score_with_oi"] = all_dump

    return out
