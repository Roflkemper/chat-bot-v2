"""Tests for regime-specific calibration models."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import services.market_forward_analysis.regime_models.markup as _markup_mod
from services.market_forward_analysis.regime_models.markup import (
    run_markup_calibration,
    load_best_weights,
    _MARKUP_BASE_WEIGHTS,
    _BRIER_TARGET,
    _BRIER_YELLOW,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_markup_features(n: int = 500, seed: int = 0) -> pd.DataFrame:
    """Synthetic feature DataFrame matching markup.parquet schema."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-07-06", periods=n, freq="5min", tz="UTC")

    noise = rng.standard_normal(n).cumsum() * 0.3
    trend = np.linspace(0, n * 0.05, n)
    close = 50_000 + trend + noise

    return pd.DataFrame({
        "close": close,
        "sum_open_interest": rng.uniform(1e9, 2e9, n),
        "oi_delta_1h": rng.uniform(-0.02, 0.02, n),
        "oi_delta_4h": rng.uniform(-0.03, 0.03, n),
        "funding_rate": rng.uniform(-0.0002, 0.0002, n),
        "funding_z": rng.uniform(-2, 2, n),
        "ls_top_traders": rng.uniform(0.8, 1.8, n),
        "ls_global": rng.uniform(0.9, 1.5, n),
        "ls_long_extreme": rng.integers(0, 2, n),
        "ls_short_extreme": rng.integers(0, 2, n),
        "taker_imbalance_5m": rng.uniform(-0.1, 0.1, n),
        "taker_imbalance_15m": rng.uniform(-0.1, 0.1, n),
        "taker_imbalance_1h": rng.uniform(-0.15, 0.15, n),
        "dist_to_pdh_pct": rng.uniform(-2, 2, n),
        "dist_to_pdl_pct": rng.uniform(-2, 0, n),
        "dist_to_pwh_pct": rng.uniform(-3, 3, n),
        "dist_to_pwl_pct": rng.uniform(-3, 0, n),
        "dist_to_d_open_pct": rng.uniform(-2, 2, n),
        "dist_to_nearest_unmitigated_high_pct": rng.uniform(0, 5, n),
        "dist_to_nearest_unmitigated_low_pct": rng.uniform(0, 5, n),
        "nearest_unmitigated_high_above_age_h": rng.uniform(0, 48, n),
        "nearest_unmitigated_low_below_age_h": rng.uniform(0, 48, n),
        "unmitigated_count_7d": rng.integers(0, 10, n),
        "in_premium_zone": rng.integers(0, 2, n),
        "session_int": rng.integers(0, 4, n),
        "volume": rng.uniform(1e6, 1e7, n),
        "atr_14": rng.uniform(200, 800, n),
        "rsi_14": rng.uniform(40, 80, n),
        "rsi_50": rng.uniform(40, 70, n),
        "rvol_20": rng.uniform(0.5, 2.5, n),
        "body_to_range": rng.uniform(0.3, 0.9, n),
        "delta_24h_pct": rng.uniform(-5, 10, n),
        "upper_wick_dominance": rng.uniform(0, 0.5, n),
        "lower_wick_dominance": rng.uniform(0, 0.5, n),
        "tick_pressure": rng.uniform(-1, 1, n),
        "close_higher_20": rng.uniform(0.5, 0.9, n),
        "volume_acceleration": rng.uniform(0.8, 1.5, n),
        "regime_int": np.ones(n, dtype=np.float32),
        "vol_tier_int": rng.integers(0, 3, n),
        "candle_dir_int": rng.integers(-1, 2, n),
        "oi_price_div_1h": rng.uniform(-0.05, 0.05, n),
        "oi_price_div_4h": rng.uniform(-0.08, 0.08, n),
        "oi_price_div_1h_z": rng.uniform(-2, 2, n),
        "oi_price_div_4h_z": rng.uniform(-2, 2, n),
    }, index=ts)


def _patch_markup(tmp_path):
    """Return context manager patching _MARKUP_FEATURES and _CALIB_OUT_DIR."""
    return (
        patch.object(_markup_mod, "_MARKUP_FEATURES", tmp_path / "regime_markup.parquet"),
        patch.object(_markup_mod, "_CALIB_OUT_DIR", tmp_path),
    )


# ── Smoke test: importable ────────────────────────────────────────────────────

def test_markup_module_importable():
    from services.market_forward_analysis.regime_models import markup  # noqa: F401
    assert hasattr(markup, "run_markup_calibration")
    assert hasattr(markup, "load_best_weights")


def test_markup_base_weights_shape():
    for horizon in ["1h", "4h", "1d"]:
        w = _MARKUP_BASE_WEIGHTS[horizon]
        assert len(w) == 5, f"{horizon}: expected 5 weights"
        assert abs(sum(w) - 1.0) < 1e-6, f"{horizon}: weights must sum to 1"


def test_markup_base_weights_trend_bias():
    """Phase coherence (A) and derivatives (B) must exceed positioning (C) and structural (D)."""
    for horizon in ["1h", "4h", "1d"]:
        w = _MARKUP_BASE_WEIGHTS[horizon]
        a, b, c, d, e = w
        assert a > c, f"{horizon}: A={a} must exceed C={c} (MARKUP trend bias)"
        assert b > c, f"{horizon}: B={b} must exceed C={c}"
        assert a > d, f"{horizon}: A={a} must exceed D={d}"


# ── Core calibration on synthetic data ───────────────────────────────────────

def test_markup_calibration_runs_on_synthetic(tmp_path):
    """run_markup_calibration() completes without error on synthetic data."""
    df = _make_markup_features(n=1200)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=20)

    assert "_summary" in result
    assert "_report_path" in result
    for horizon in ["1h", "4h", "1d"]:
        assert horizon in result
        assert "test_brier" in result[horizon]
        assert "gate" in result[horizon]
        assert "best_weights" in result[horizon]


def test_markup_calibration_returns_valid_brier(tmp_path):
    """Brier scores are in [0, 1]."""
    df = _make_markup_features(n=1200)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=20)

    for horizon in ["1h", "4h", "1d"]:
        brier = result[horizon]["test_brier"]
        assert 0.0 <= brier <= 1.0, f"{horizon}: brier={brier} out of range"


def test_markup_calibration_gate_classification(tmp_path):
    """Gate labels match Brier thresholds."""
    df = _make_markup_features(n=1200)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=20)

    for horizon in ["1h", "4h", "1d"]:
        brier = result[horizon]["test_brier"]
        gate  = result[horizon]["gate"]
        if brier <= _BRIER_TARGET:
            assert gate == "GREEN", f"{horizon}: brier={brier} should be GREEN"
        elif brier <= _BRIER_YELLOW:
            assert gate == "YELLOW", f"{horizon}: brier={brier} should be YELLOW"
        else:
            assert gate == "RED", f"{horizon}: brier={brier} should be RED"


def test_markup_calibration_best_weights_sum_to_one(tmp_path):
    """Optimized weights must sum to ~1.0 (normalized)."""
    df = _make_markup_features(n=800)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=10)

    for horizon in ["1h", "4h", "1d"]:
        w = result[horizon]["best_weights"]
        assert len(w) == 5
        assert abs(sum(w) - 1.0) < 1e-3, f"{horizon}: weights sum={sum(w)}"


def test_markup_calibration_writes_json_report(tmp_path):
    """Report JSON is written and parseable."""
    df = _make_markup_features(n=800)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=10)

    report_path = Path(result["_report_path"])
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "_summary" in data
    assert data["_summary"]["regime"] == "MARKUP"


def test_markup_calibration_summary_gate_consistent(tmp_path):
    """Summary gate matches worst individual horizon gate."""
    df = _make_markup_features(n=1200)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=20)

    worst = result["_summary"]["worst_brier"]
    overall_gate = result["_summary"]["overall_gate"]
    expected_gate = (
        "GREEN"  if worst <= _BRIER_TARGET
        else "YELLOW" if worst <= _BRIER_YELLOW
        else "RED"
    )
    assert overall_gate == expected_gate


def test_markup_calibration_missing_features(tmp_path):
    """Missing feature file returns error dict without raising."""
    with patch.object(_markup_mod, "_MARKUP_FEATURES", tmp_path / "nonexistent.parquet"):
        result = run_markup_calibration()

    assert "error" in result


def test_markup_calibration_outcome_distribution(tmp_path):
    """Outcome distribution fractions sum to 1.0."""
    df = _make_markup_features(n=1200)
    df.to_parquet(tmp_path / "regime_markup.parquet")

    p1, p2 = _patch_markup(tmp_path)
    with p1, p2:
        result = run_markup_calibration(n_trials=10)

    for horizon in ["1h", "4h", "1d"]:
        dist = result[horizon]["outcome_distribution"]
        total = dist["up_frac"] + dist["down_frac"] + dist["range_frac"]
        assert abs(total - 1.0) < 0.01, f"{horizon}: distribution sum={total}"


# ── load_best_weights ─────────────────────────────────────────────────────────

def test_load_best_weights_fallback_no_reports(tmp_path):
    """load_best_weights falls back to base weights when no report exists."""
    with patch.object(_markup_mod, "_CALIB_OUT_DIR", tmp_path):
        w = load_best_weights("4h")

    assert w == _MARKUP_BASE_WEIGHTS["4h"]


def test_load_best_weights_reads_latest_report(tmp_path):
    """load_best_weights reads optimized weights from most recent JSON."""
    report = {
        "4h": {"best_weights": [0.35, 0.30, 0.10, 0.10, 0.15]},
        "_summary": {"regime": "MARKUP"},
    }
    report_path = tmp_path / "regime_markup_20260503T120000Z.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with patch.object(_markup_mod, "_CALIB_OUT_DIR", tmp_path):
        w = load_best_weights("4h")

    assert w == [0.35, 0.30, 0.10, 0.10, 0.15]


# ── Integration: live features (skipped if not present) ──────────────────────

@pytest.mark.skipif(
    not Path("data/forecast_features/regime_splits/regime_markup.parquet").exists(),
    reason="Live MARKUP features not built",
)
def test_markup_calibration_live():
    """Run full calibration on live MARKUP data.

    Gate assertion:
      GREEN  (<0.22): proceed to MARKDOWN
      YELLOW (0.22-0.28): operator decision
      RED    (>0.28): qualitative only for MARKUP
    """
    result = run_markup_calibration(n_trials=400)
    summary = result["_summary"]
    worst   = summary["worst_brier"]

    # Hard rule: never worse than random (0.25 baseline) by more than 0.03
    assert worst < 0.28, (
        f"RED gate: worst Brier={worst:.4f} -- MARKUP model fails quality gate."
    )

    gate = summary["overall_gate"]
    import sys
    msg = f"\nMARKUP calibration gate: {gate}  (worst_brier={worst:.4f})\n"
    if gate == "GREEN":
        msg += "  -> PROCEED to TZ-REGIME-MODEL-MARKDOWN\n"
    elif gate == "YELLOW":
        msg += f"  -> STOP -- worst={worst:.4f} between 0.22-0.28, operator decision required\n"
    sys.stdout.buffer.write(msg.encode("utf-8", errors="replace"))


# ── MARKDOWN model tests ──────────────────────────────────────────────────────

def test_markdown_module_importable():
    """MARKDOWN module imports cleanly."""
    from services.market_forward_analysis.regime_models import markdown as md
    assert hasattr(md, "run_markdown_calibration")
    assert hasattr(md, "load_best_weights")
    assert hasattr(md, "_MARKDOWN_BASE_WEIGHTS")


def test_markdown_base_weights_shape():
    """MARKDOWN base weights match (1h, 4h, 1d) x 5 signals shape."""
    from services.market_forward_analysis.regime_models.markdown import _MARKDOWN_BASE_WEIGHTS
    assert set(_MARKDOWN_BASE_WEIGHTS.keys()) == {"1h", "4h", "1d"}
    for hz, w in _MARKDOWN_BASE_WEIGHTS.items():
        assert len(w) == 5, f"{hz}: expected 5 weights, got {len(w)}"
        assert abs(sum(w) - 1.0) < 1e-6, f"{hz}: weights don't sum to 1.0"


@pytest.mark.skipif(
    not Path("data/forecast_features/regime_splits/regime_markdown.parquet").exists(),
    reason="Live MARKDOWN features not built",
)
def test_markdown_calibration_live():
    """Run full calibration on live MARKDOWN data and report gate."""
    from services.market_forward_analysis.regime_models.markdown import run_markdown_calibration
    result = run_markdown_calibration(n_trials=400)
    summary = result["_summary"]
    worst   = summary["worst_brier"]
    gate    = summary["overall_gate"]
    import sys
    msg = f"\nMARKDOWN calibration gate: {gate}  (worst_brier={worst:.4f})\n"
    sys.stdout.buffer.write(msg.encode("utf-8", errors="replace"))
    # Soft check: at least one horizon must beat random baseline
    best = summary["best_brier"]
    assert best < 0.25, f"All horizons worse than random baseline: best={best:.4f}"
