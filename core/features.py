from __future__ import annotations

from typing import List

import pandas as pd

from core.indicators import add_indicators

FEATURE_COLUMNS: List[str] = [
    "ret1", "ret5", "ret10", "vol_ratio", "trend_strength", "distance_ema20_atr",
    "distance_ema50_atr", "rsi14", "hl_range", "body_to_range"
]


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    out = add_indicators(df)
    out["target_up"] = (out["close"].shift(-3) > out["close"]).astype(int)
    return out


def latest_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    feat = prepare_features(df)
    return feat[FEATURE_COLUMNS].tail(1).fillna(0.0)



def build_feature_vector_v2(df):
    """Return the feature vector in the exact training-column order used by XGBoost.

    This keeps live inference aligned with tools/train_xgboost_models.py so trained
    models can be loaded safely instead of silently falling back because of a
    shape mismatch.
    """
    frame = latest_feature_frame(df)
    if frame.empty:
        return [0.0 for _ in FEATURE_COLUMNS]
    row = frame.iloc[-1]
    return [float(row.get(col, 0.0) or 0.0) for col in FEATURE_COLUMNS]
