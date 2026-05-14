"""Tests for TZ-REGIME-RED-GREEN-FEATURE-EXTRACTION."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Test 1: Resampling correctness
# ---------------------------------------------------------------------------

def test_resampling_correct(tmp_path):
    """60 1m bars -> 1 1h bar with correct OHLC aggregation."""
    import csv
    from services.regime_red_green.resampler import resample_1m_to_1h

    # Base time: 2026-01-01 00:00 UTC in epoch ms
    base_ms = int(pd.Timestamp("2026-01-01 00:00:00", tz="UTC").timestamp() * 1000)
    rows = []
    for i in range(60):
        ts = base_ms + i * 60_000  # 1 minute increments
        open_ = 100.0 + i
        high = 100.0 + i + 0.5
        low = 100.0 + i - 0.5
        close = 100.0 + i + 0.1
        volume = float(i + 1)
        rows.append([ts, open_, high, low, close, volume])

    csv_path = tmp_path / "test_1m.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ts", "open", "high", "low", "close", "volume"])
        writer.writerows(rows)

    df_1h = resample_1m_to_1h(csv_path)

    # Should produce exactly 1 1h bar
    assert len(df_1h) == 1, f"Expected 1 bar, got {len(df_1h)}"

    bar = df_1h.iloc[0]
    # open = first bar's open
    assert bar["open"] == pytest.approx(100.0, abs=1e-6), f"open mismatch: {bar['open']}"
    # high = max of all highs = 100 + 59 + 0.5 = 159.5
    assert bar["high"] == pytest.approx(159.5, abs=1e-6), f"high mismatch: {bar['high']}"
    # low = min of all lows = 100 + 0 - 0.5 = 99.5
    assert bar["low"] == pytest.approx(99.5, abs=1e-6), f"low mismatch: {bar['low']}"
    # close = last bar's close = 100 + 59 + 0.1 = 159.1
    assert bar["close"] == pytest.approx(159.1, abs=1e-6), f"close mismatch: {bar['close']}"
    # volume = sum(1..60) = 1830
    assert bar["volume"] == pytest.approx(1830.0, abs=1e-6), f"volume mismatch: {bar['volume']}"


# ---------------------------------------------------------------------------
# Test 2: No lookahead in features
# ---------------------------------------------------------------------------

def test_features_no_lookahead():
    """Feature for bar T uses only data up to and including bar T."""
    from services.regime_red_green.features import compute_features

    np.random.seed(42)
    n = 100
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close_vals = 50000.0 + np.cumsum(np.random.randn(n) * 100)
    df = pd.DataFrame(
        {
            "open": close_vals - np.abs(np.random.randn(n) * 50),
            "high": close_vals + np.abs(np.random.randn(n) * 80),
            "low": close_vals - np.abs(np.random.randn(n) * 80),
            "close": close_vals,
            "volume": np.random.uniform(100, 1000, n),
        },
        index=idx,
    )

    # Verify: features at bar T with truncated df equal features at bar T with full df
    T = 50
    feats_full = compute_features(df)
    feats_trunc = compute_features(df.iloc[: T + 1])

    for col in feats_full.columns:
        val_full = feats_full[col].iloc[T]
        val_trunc = feats_trunc[col].iloc[T]
        assert abs(val_full - val_trunc) < 1e-9, (
            f"Feature '{col}' at bar {T} differs: full={val_full}, trunc={val_trunc}"
        )


# ---------------------------------------------------------------------------
# Test 3: classify() returns a valid label
# ---------------------------------------------------------------------------

def test_classify_returns_label():
    """rules.py classify() returns one of {TREND, RANGE, AMBIGUOUS}."""
    from services.regime_red_green import rules  # type: ignore[import]

    valid = {"TREND", "RANGE", "AMBIGUOUS"}

    # Empty dict
    result = rules.classify({})
    assert result in valid, f"classify({{}}) returned {result!r}"

    # All-zero dict
    zero_dict = {k: 0.0 for k in rules.FEATURE_NAMES}
    result = rules.classify(zero_dict)
    assert result in valid, f"classify(all_zeros) returned {result!r}"

    # Typical TREND-like features (strong displacement)
    trend_dict = {
        "vol_z_score_4h": 3.5,
        "body_to_range_max_4h": 0.85,
        "displacement_count_4h": 3.0,
        "single_bar_roc_max_pct_4h": 1.5,
        "roc_24h_pct": 4.0,
        "price_band_height_pct_24h": 5.0,
        "closed_outside_band_24h": 1.0,
    }
    result = rules.classify(trend_dict)
    assert result in valid, f"classify(trend_dict) returned {result!r}"

    # Typical RANGE-like features (tight, low volatility)
    range_dict = {
        "vol_z_score_4h": -0.5,
        "body_to_range_max_4h": 0.2,
        "displacement_count_4h": 0.0,
        "single_bar_roc_max_pct_4h": 0.1,
        "roc_24h_pct": 0.1,
        "price_band_height_pct_24h": 1.0,
        "time_inside_band_24h_pct": 0.9,
        "closed_outside_band_24h": 0.0,
        "pivot_density_24h": 6.0,
    }
    result = rules.classify(range_dict)
    assert result in valid, f"classify(range_dict) returned {result!r}"


# ---------------------------------------------------------------------------
# Test 4: Holdout isolation
# ---------------------------------------------------------------------------

def test_holdout_isolation():
    """Train labels exclude bars at or after 2026-05-01T00:00:00Z."""
    truth_path = Path("data/regime_truth/btc_1h_v1.json")
    if not truth_path.exists():
        pytest.skip("Truth file not found; skipping.")

    with open(truth_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    holdout_start = pd.Timestamp(data["holdout_period_start"], tz="UTC")
    intervals = data["intervals"]

    # Build a wide index to cover all labelled dates
    idx = pd.date_range("2026-01-01", "2026-06-01", freq="1h", tz="UTC")

    # Reuse runner logic
    import sys, os
    sys.path.insert(0, os.getcwd())
    from services.regime_red_green.runner import _build_label_series

    labels = _build_label_series(intervals, data["holdout_period_start"], idx)
    labelled = labels.dropna()

    if len(labelled) == 0:
        pytest.skip("No labels found in the index range.")

    # Verify no labelled bar is at or after holdout_start
    assert (labelled.index < holdout_start).all(), (
        f"Found {(labelled.index >= holdout_start).sum()} labelled bars at/after holdout start"
    )
