from __future__ import annotations

import numpy as np


def build_pattern_vector(df):
    closes = df['close'].values[-30:]
    returns = np.diff(closes) / closes[:-1] if len(closes) > 1 else np.array([0.0])
    vol = df['volume'].values[-30:]
    vol_norm = vol / (float(np.mean(vol)) + 1e-9)
    return np.concatenate([returns, vol_norm])
