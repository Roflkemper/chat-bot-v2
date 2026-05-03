"""MARKUP regime calibration model.

Trains on MARKUP-only episodes (regime_label == 'markup').
MARKUP is a trend-continuation regime: signals A (phase coherence), B (OI
momentum), and E (momentum confirmation) are expected to be PREDICTIVE.
Signals C (positioning extreme, contrarian) and D (structural context,
contrarian at supply zones) are DOWN-WEIGHTED vs. the unified model.

DP-006 does NOT apply here — trend features are appropriate for MARKUP.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..calibration import (
    _compute_outcomes,
    _compute_signals_batch,
    _signals_to_prob_up,
    _brier_score,
    _weight_perturbations,
    _reliability_curve,
    _DIRECTION_THRESHOLD_PCT,
)

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_MARKUP_FEATURES = _ROOT / "data" / "forecast_features" / "regime_splits" / "regime_markup.parquet"
_CALIB_OUT_DIR   = _ROOT / "data" / "calibration"

# MARKUP-biased initial weights: [phase_coh, deriv_div, positioning, structural, momentum]
# A (phase coherence): HIGH — trend continuation context is the alpha edge
# B (derivatives divergence): HIGH — OI growth + taker buy confirms markup
# C (positioning extreme): LOW — contrarian signal hurts in trending regime
# D (structural context): LOW — supply zones hit then break in true markup
# E (momentum): MEDIUM-HIGH — momentum confirms trend continuation
_MARKUP_BASE_WEIGHTS: dict[str, list[float]] = {
    "1h":  [0.30, 0.35, 0.10, 0.10, 0.15],
    "4h":  [0.35, 0.30, 0.10, 0.10, 0.15],
    "1d":  [0.45, 0.25, 0.08, 0.07, 0.15],
}

# Brier gates
_BRIER_TARGET  = 0.22   # GREEN — proceed to MARKDOWN
_BRIER_YELLOW  = 0.28   # YELLOW — stop, operator decision
# > _BRIER_YELLOW → RED hard stop (qualitative only for MARKUP)


def run_markup_calibration(
    train_frac: float = 0.8,
    n_trials: int = 400,
) -> dict:
    """Run MARKUP-only calibration.

    Returns dict with per-horizon results plus _summary with gate status.
    Writes JSON report to data/calibration/regime_markup_<timestamp>.json.
    """
    if not _MARKUP_FEATURES.exists():
        return {"error": f"MARKUP features not found: {_MARKUP_FEATURES}"}

    logger.info("markup calibration: loading features (%s)...", _MARKUP_FEATURES)
    features = pd.read_parquet(_MARKUP_FEATURES)
    logger.info("markup calibration: %d rows, %d cols", *features.shape)

    # Compute outcomes from close price
    logger.info("markup calibration: computing outcomes...")
    outcomes = _compute_outcomes(features["close"])

    # Drop tail rows where future price unavailable (last ~288 bars for 1d horizon)
    valid_mask = outcomes.notna().all(axis=1)
    features = features[valid_mask]
    outcomes = outcomes[valid_mask]

    n = len(features)
    if n < 100:
        return {"error": f"Insufficient MARKUP data after trim: {n} rows"}

    # Time-based 80/20 split — no shuffle to avoid look-ahead
    split = int(n * train_frac)
    train_feat, test_feat = features.iloc[:split], features.iloc[split:]
    train_out,  test_out  = outcomes.iloc[:split], outcomes.iloc[split:]

    logger.info("markup calibration: train=%d  test=%d", split, n - split)

    # Batch signal computation
    logger.info("markup calibration: computing signals (batch)...")
    train_signals = _compute_signals_batch(train_feat)
    test_signals  = _compute_signals_batch(test_feat)

    results: dict = {}

    for horizon in ["1h", "4h", "1d"]:
        logger.info("markup calibration: optimizing weights for %s...", horizon)
        actual_col = f"actual_dir_{horizon}"

        train_actual = train_out[actual_col].values
        test_actual  = test_out[actual_col].values

        base_weights = _MARKUP_BASE_WEIGHTS[horizon]

        best_weights = list(base_weights)
        best_train_brier = _brier_score(
            _signals_to_prob_up(train_signals, base_weights), train_actual
        )

        for delta_set in _weight_perturbations(base_weights, n_trials=n_trials):
            prob_up = _signals_to_prob_up(train_signals, delta_set)
            bs = _brier_score(prob_up, train_actual)
            if bs < best_train_brier:
                best_train_brier = bs
                best_weights = delta_set

        test_prob_up = _signals_to_prob_up(test_signals, best_weights)
        test_brier   = _brier_score(test_prob_up, test_actual)
        reliability  = _reliability_curve(test_prob_up, test_actual)
        sharpness    = float(test_prob_up.std())

        # Fraction of up/down/range in MARKUP test set
        up_frac    = float((test_actual == 1).mean())
        down_frac  = float((test_actual == -1).mean())
        range_frac = float((test_actual == 0).mean())

        gate = (
            "GREEN" if test_brier <= _BRIER_TARGET
            else "YELLOW" if test_brier <= _BRIER_YELLOW
            else "RED"
        )

        results[horizon] = {
            "test_brier":   round(test_brier, 4),
            "train_brier":  round(best_train_brier, 4),
            "baseline_brier": 0.25,
            "improvement_vs_baseline": round(0.25 - test_brier, 4),
            "gate": gate,
            "target_met": test_brier <= _BRIER_TARGET,
            "sharpness": round(sharpness, 4),
            "best_weights": [round(w, 4) for w in best_weights],
            "base_weights":  [round(w, 4) for w in base_weights],
            "reliability": reliability,
            "train_size": split,
            "test_size": n - split,
            "outcome_distribution": {
                "up_frac": round(up_frac, 3),
                "down_frac": round(down_frac, 3),
                "range_frac": round(range_frac, 3),
            },
        }

        logger.info(
            "markup calibration: %s brier=%.4f (gate=%s, train=%.4f)",
            horizon, test_brier, gate, best_train_brier,
        )

    # Summary gate — worst (most conservative) horizon wins
    all_briers = [v["test_brier"] for v in results.values()]
    worst_brier = max(all_briers) if all_briers else 1.0
    best_brier  = min(all_briers) if all_briers else 1.0

    overall_gate = (
        "GREEN"  if worst_brier <= _BRIER_TARGET
        else "YELLOW" if worst_brier <= _BRIER_YELLOW
        else "RED"
    )

    train_period_start = str(features.index[0])
    train_period_end   = str(features.index[split - 1])
    test_period_start  = str(features.index[split])
    test_period_end    = str(features.index[-1])

    results["_summary"] = {
        "regime": "MARKUP",
        "n_total": n,
        "n_train": split,
        "n_test": n - split,
        "train_period": f"{train_period_start} → {train_period_end}",
        "test_period":  f"{test_period_start} → {test_period_end}",
        "best_brier":   round(best_brier, 4),
        "worst_brier":  round(worst_brier, 4),
        "overall_gate": overall_gate,
        "target_brier": _BRIER_TARGET,
        "hard_stop_brier": _BRIER_YELLOW,
        "note": (
            f"All horizons ≤{_BRIER_TARGET} — MARKUP model READY"
            if overall_gate == "GREEN"
            else f"Worst Brier={worst_brier:.4f} — {'STOP, qualitative only for MARKUP' if overall_gate == 'RED' else 'Marginal — report to operator'}"
        ),
    }

    # Write JSON report
    _CALIB_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = _CALIB_OUT_DIR / f"regime_markup_{ts}.json"
    report_path.write_text(
        json.dumps(results, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("markup calibration: report saved → %s", report_path)

    results["_report_path"] = str(report_path)
    return results


def load_best_weights(horizon: str) -> list[float]:
    """Load optimized weights from the most recent MARKUP calibration report.

    Falls back to _MARKUP_BASE_WEIGHTS if no report exists.
    """
    reports = sorted(_CALIB_OUT_DIR.glob("regime_markup_*.json"))
    if not reports:
        logger.warning("markup: no calibration report found, using base weights")
        return _MARKUP_BASE_WEIGHTS.get(horizon, [0.2] * 5)

    latest = reports[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    if horizon in data and "best_weights" in data[horizon]:
        return data[horizon]["best_weights"]
    return _MARKUP_BASE_WEIGHTS.get(horizon, [0.2] * 5)
