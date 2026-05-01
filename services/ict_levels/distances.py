from __future__ import annotations

import numpy as np
import pandas as pd


def _pct(price: pd.Series, level: pd.Series) -> pd.Series:
    """(price - level) / level * 100. Positive = price above level."""
    return (price - level) / level.replace(0, np.nan) * 100.0


def add_distance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add distance-to-level columns (all in %).

    Sign convention: positive = current price above the level.
    """
    out = df.copy()
    close = df["close"]

    # Pivot distances
    for col_in, col_out in [
        ("pdh", "dist_to_pdh_pct"),
        ("pdl", "dist_to_pdl_pct"),
        ("pwh", "dist_to_pwh_pct"),
        ("pwl", "dist_to_pwl_pct"),
        ("d_open", "dist_to_d_open_pct"),
    ]:
        if col_in in df.columns:
            out[col_out] = _pct(close, df[col_in])
        else:
            out[col_out] = np.nan

    # Current Asia session H/L (today's, not previous)
    for col_in, col_out in [
        ("asia_high", "dist_to_asia_high_pct"),
        ("asia_low",  "dist_to_asia_low_pct"),
    ]:
        if col_in in df.columns:
            out[col_out] = _pct(close, df[col_in])
        else:
            out[col_out] = np.nan

    # Distance to active killzone midpoint (NaN in dead zones)
    if "session_active" in df.columns:
        kz_mid = pd.Series(np.nan, index=df.index)
        for sess in ("asia", "london", "ny_am", "ny_lunch", "ny_pm"):
            mask = df["session_active"] == sess
            mid_col = f"{sess}_midpoint"
            if mask.any() and mid_col in df.columns:
                kz_mid[mask] = df.loc[mask, mid_col]
        out["dist_to_kz_mid_pct"] = _pct(close, kz_mid)
    else:
        out["dist_to_kz_mid_pct"] = np.nan

    # Distances to nearest unmitigated levels
    if "nearest_unmitigated_high_above" in df.columns:
        out["dist_to_nearest_unmitigated_high_pct"] = _pct(
            close, df["nearest_unmitigated_high_above"]
        )
    else:
        out["dist_to_nearest_unmitigated_high_pct"] = np.nan

    if "nearest_unmitigated_low_below" in df.columns:
        out["dist_to_nearest_unmitigated_low_pct"] = _pct(
            close, df["nearest_unmitigated_low_below"]
        )
    else:
        out["dist_to_nearest_unmitigated_low_pct"] = np.nan

    return out
