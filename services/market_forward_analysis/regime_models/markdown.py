"""MARKDOWN regime calibration model.

Trains on MARKDOWN-only episodes (regime_int == -1).
MARKDOWN is a trend-continuation regime (bear): signals A (phase coherence,
bearish), B (OI deleveraging), and E (momentum confirmation, downside) are
expected to be PREDICTIVE. C (positioning extreme, contrarian) and D (structural
context) are DOWN-WEIGHTED — supply zones break in true MARKDOWN, similarly to
how MARKUP breaks resistance.

Architecture matches MARKUP (Tier-1 wired + Tier-2 features). Same 5-signal
ensemble, same _compute_signals_batch, same weight perturbation grid.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..calibration import (
    _compute_outcomes,
    _compute_signals_batch,
    _signals_to_prob_up,
    _brier_score,
    _weight_perturbations,
    _reliability_curve,
)

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[3]
_MARKDOWN_FEATURES = _ROOT / "data" / "forecast_features" / "regime_splits" / "regime_markdown.parquet"
_CALIB_OUT_DIR     = _ROOT / "data" / "calibration"

# MARKDOWN-biased initial weights (mirror of MARKUP):
# A: HIGH (bearish phase coherence)
# B: HIGH (OI changes confirming downside)
# C: LOW (contrarian — squeezes against trend)
# D: LOW (supply zones break in markdown, demand zones fail)
# E: MEDIUM-HIGH (momentum confirmation downside)
_MARKDOWN_BASE_WEIGHTS: dict[str, list[float]] = {
    "1h":  [0.30, 0.35, 0.10, 0.10, 0.15],
    "4h":  [0.35, 0.30, 0.10, 0.10, 0.15],
    "1d":  [0.45, 0.25, 0.08, 0.07, 0.15],
}

_BRIER_TARGET = 0.22
_BRIER_YELLOW = 0.28


def run_markdown_calibration(
    train_frac: float = 0.8,
    n_trials: int = 400,
) -> dict:
    """Run MARKDOWN-only calibration. Same architecture as MARKUP."""
    if not _MARKDOWN_FEATURES.exists():
        return {"error": f"MARKDOWN features not found: {_MARKDOWN_FEATURES}"}

    logger.info("markdown calibration: loading features...")
    features = pd.read_parquet(_MARKDOWN_FEATURES)
    logger.info("markdown calibration: %d rows, %d cols", *features.shape)

    outcomes = _compute_outcomes(features["close"])
    valid_mask = outcomes.notna().all(axis=1)
    features = features[valid_mask]
    outcomes = outcomes[valid_mask]

    n = len(features)
    if n < 100:
        return {"error": f"Insufficient MARKDOWN data: {n} rows"}

    split = int(n * train_frac)
    train_feat, test_feat = features.iloc[:split], features.iloc[split:]
    train_out,  test_out  = outcomes.iloc[:split], outcomes.iloc[split:]

    logger.info("markdown calibration: train=%d test=%d", split, n - split)

    results: dict = {}

    for horizon in ["1h", "4h", "1d"]:
        logger.info("markdown calibration: computing signals for %s...", horizon)
        train_signals = _compute_signals_batch(train_feat, horizon=horizon)
        test_signals  = _compute_signals_batch(test_feat,  horizon=horizon)

        actual_col = f"actual_dir_{horizon}"
        train_actual = train_out[actual_col].values
        test_actual  = test_out[actual_col].values

        base_weights = _MARKDOWN_BASE_WEIGHTS[horizon]
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

        up_frac    = float((test_actual == 1).mean())
        down_frac  = float((test_actual == -1).mean())
        range_frac = float((test_actual == 0).mean())

        gate = (
            "GREEN" if test_brier <= _BRIER_TARGET
            else "YELLOW" if test_brier <= _BRIER_YELLOW
            else "RED"
        )

        results[horizon] = {
            "test_brier": round(test_brier, 4),
            "train_brier": round(best_train_brier, 4),
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
            "markdown calibration: %s brier=%.4f (gate=%s)",
            horizon, test_brier, gate,
        )

    all_briers = [v["test_brier"] for v in results.values()]
    worst_brier = max(all_briers) if all_briers else 1.0
    best_brier  = min(all_briers) if all_briers else 1.0

    overall_gate = (
        "GREEN"  if worst_brier <= _BRIER_TARGET
        else "YELLOW" if worst_brier <= _BRIER_YELLOW
        else "RED"
    )

    results["_summary"] = {
        "regime": "MARKDOWN",
        "n_total": n,
        "n_train": split,
        "n_test": n - split,
        "train_period": f"{features.index[0]} to {features.index[split - 1]}",
        "test_period":  f"{features.index[split]} to {features.index[-1]}",
        "best_brier":  round(best_brier, 4),
        "worst_brier": round(worst_brier, 4),
        "overall_gate": overall_gate,
        "target_brier": _BRIER_TARGET,
        "hard_stop_brier": _BRIER_YELLOW,
    }

    _CALIB_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = _CALIB_OUT_DIR / f"regime_markdown_{ts}.json"
    report_path.write_text(
        json.dumps(results, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("markdown calibration: report saved to %s", report_path)

    results["_report_path"] = str(report_path)
    return results


def load_best_weights(horizon: str) -> list[float]:
    """Load optimized weights from the most recent MARKDOWN report."""
    reports = sorted(_CALIB_OUT_DIR.glob("regime_markdown_*.json"))
    if not reports:
        return _MARKDOWN_BASE_WEIGHTS.get(horizon, [0.2] * 5)
    data = json.loads(reports[-1].read_text(encoding="utf-8"))
    if horizon in data and "best_weights" in data[horizon]:
        return data[horizon]["best_weights"]
    return _MARKDOWN_BASE_WEIGHTS.get(horizon, [0.2] * 5)
