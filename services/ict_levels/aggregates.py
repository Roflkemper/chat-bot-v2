from __future__ import annotations

import pandas as pd

from .sessions import SESSION_LABELS


def add_session_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-session OHLC aggregates (forward-filled after session close).

    For each session type in SESSION_LABELS adds:
      {sess}_open, {sess}_high, {sess}_low, {sess}_close
      {sess}_midpoint, {sess}_range, {sess}_range_avg5

    Values are NaN before the first instance of that session type is completed.
    """
    out = df.copy()

    for sess in SESSION_LABELS:
        # Filter to bars belonging to this session type
        mask = df["session_active"] == sess
        if not mask.any():
            for col in ("open", "high", "low", "close", "midpoint", "range", "range_avg5"):
                out[f"{sess}_{col}"] = float("nan")
            continue

        sess_df = df[mask][["open", "high", "low", "close", "_kz_session_id"]].copy()

        # Per-instance OHLC
        instances = sess_df.groupby("_kz_session_id").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
        )

        # Close timestamp for each instance = last bar index in group
        close_ts = sess_df.groupby("_kz_session_id")["close"].apply(
            lambda g: g.index[-1]
        )
        instances.index = close_ts.loc[instances.index]
        instances = instances.sort_index()

        # Derived fields
        instances["midpoint"] = (instances["high"] + instances["low"]) / 2
        instances["range"] = instances["high"] - instances["low"]
        instances["range_avg5"] = instances["range"].rolling(5, min_periods=1).mean()

        # Forward-fill each column to full DatetimeIndex
        for col in ("open", "high", "low", "close", "midpoint", "range", "range_avg5"):
            series = instances[col]
            ffilled = series.reindex(df.index, method="ffill")
            out[f"{sess}_{col}"] = ffilled

    return out
