"""Historical calibration framework for projection_v2.

For each 5m bar in features_1y.parquet:
  - Compute projection_v2 signals (no phase_state — uses feature-only signals B/C/D/E)
  - Lookup actual outcome at +1h, +4h, +1d (from price series)
  - Record (predicted_prob, actual_direction, actual_magnitude)

Calibration metrics:
  - Brier score per horizon (target ≤0.22)
  - Reliability: per prob-decile, what fraction actually moved up?
  - Sharpness: std of predicted probs (non-trivial if > 0.1)

Weight optimization:
  - Grid search over signal weights (A-E) per horizon
  - 80/20 train/test split (time-based: first 80% train)
  - Target: minimize Brier on test set

Per-phase Brier:
  - Classify each bar's phase from pre-computed phase labels
  - Compute Brier separately per phase
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .projection_v2 import (
    _signal_derivatives_divergence,
    _signal_positioning_extreme,
    _signal_structural_context,
    _signal_momentum_exhaustion,
    _ensemble_votes,
    SignalVote,
)

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_FEATURES_PATH = _ROOT / "data" / "forecast_features" / "full_features_1y.parquet"
_CALIB_CACHE   = _ROOT / "data" / "forecast_features" / "calibration_results.parquet"


# ── Outcome computation ───────────────────────────────────────────────────────

_HORIZON_BARS: dict[str, int] = {
    "1h": 12,    # 12 × 5m = 1h
    "4h": 48,    # 48 × 5m = 4h
    "1d": 288,   # 288 × 5m = 1d
}

# Direction threshold: ±0.3% defines up/down vs range.
# At 1% threshold, 96% of 1h moves are "range" — untrainable.
# At 0.3%: 1h ~17% up/17% down, 4h ~30% up/29% down — tractable.
_DIRECTION_THRESHOLD_PCT: float = 0.3


def _compute_outcomes(close: pd.Series) -> pd.DataFrame:
    """Compute actual price direction at each horizon for every bar.

    Returns DataFrame with cols: actual_dir_1h, actual_dir_4h, actual_dir_1d
    actual_dir: +1 (up >1%), -1 (down >-1%), 0 (range ±1%)
    """
    out = pd.DataFrame(index=close.index)
    for horizon, bars in _HORIZON_BARS.items():
        future_close = close.shift(-bars)
        pct_change = (future_close - close) / close * 100
        direction = np.where(
            pct_change > _DIRECTION_THRESHOLD_PCT, 1,
            np.where(pct_change < -_DIRECTION_THRESHOLD_PCT, -1, 0)
        )
        out[f"actual_dir_{horizon}"] = direction
        out[f"actual_pct_{horizon}"] = pct_change
    return out


# ── Fast vectorized signal computation ───────────────────────────────────────

def _compute_signals_batch(features_df: pd.DataFrame) -> pd.DataFrame:
    """Compute signals B/C/D/E for all rows at once (vectorized).

    Phase signal A requires MTFPhaseState (not pre-computed), so we use
    regime_int as proxy for historical phase bias:
      regime_int: 1=bullish, -1=bearish, 0=neutral
    """
    df = features_df.copy()
    n = len(df)

    # Signal A proxy: regime_int from whatif enriched data
    # (1=bullish → macro_bias=+1, -1=bearish → macro_bias=-1, 0=neutral)
    phase_dir = df["regime_int"].values.astype(np.float32)

    # Confidence based on how extreme regime is (not always present)
    phase_conf = np.where(phase_dir != 0, 0.5, 0.3).astype(np.float32)
    phase_mag  = np.abs(phase_dir) * 0.5

    # Signal B: derivatives divergence (vectorized)
    oi_div_z  = df["oi_price_div_4h_z"].values
    taker_1h  = df["taker_imbalance_1h"].values
    funding_z = df["funding_z"].values

    b_dir = np.zeros(n, dtype=np.float32)
    b_mag = np.zeros(n, dtype=np.float32)

    # Significant divergence
    sig_div = np.abs(oi_div_z) >= 0.5
    oi_up   = oi_div_z > 0.5
    taker_b = taker_1h > 0.05
    taker_s = taker_1h < -0.05

    # OI up + buy taker → bullish
    mask = sig_div & oi_up & taker_b
    b_dir[mask] = 1
    b_mag[mask] = np.clip(np.abs(oi_div_z[mask]) * 0.3 + taker_1h[mask] * 0.5, 0, 0.9)

    # OI up + sell taker → bearish divergence
    mask = sig_div & oi_up & taker_s
    b_dir[mask] = -1
    b_mag[mask] = np.clip(np.abs(oi_div_z[mask]) * 0.3 + np.abs(taker_1h[mask]) * 0.5, 0, 0.9)

    # Funding adjustment
    fund_ext = np.abs(funding_z) > 1.5
    fund_dir = np.where(funding_z > 0, -1, 1)  # contrarian
    fund_only = fund_ext & (b_dir == 0)
    b_dir = np.where(fund_only, fund_dir, b_dir)
    b_mag = np.where(fund_only, 0.25, b_mag)

    b_conf = np.clip(0.4 + np.abs(oi_div_z) * 0.1 + np.abs(taker_1h) * 0.3, 0, 0.8)

    # Signal C: positioning extreme (vectorized)
    ls_top = df["ls_top_traders"].values
    ls_long_ext  = df["ls_long_extreme"].values
    ls_short_ext = df["ls_short_extreme"].values

    c_dir = np.zeros(n, dtype=np.float32)
    c_mag = np.zeros(n, dtype=np.float32)

    c_dir = np.where(ls_long_ext == 1, -1.0, c_dir)
    c_mag = np.where(ls_long_ext == 1, np.clip(0.5 + np.where(funding_z > 1.0, 0.2, 0.0), 0, 0.9), c_mag)

    c_dir = np.where(ls_short_ext == 1, 1.0, c_dir)
    c_mag = np.where(ls_short_ext == 1, np.clip(0.5 + np.where(funding_z < -1.0, 0.2, 0.0), 0, 0.9), c_mag)

    # Mild lean
    mild_long  = (ls_long_ext == 0) & (ls_short_ext == 0) & (ls_top > 1.5)
    mild_short = (ls_long_ext == 0) & (ls_short_ext == 0) & (ls_top < 0.67)
    c_dir = np.where(mild_long, -1.0, c_dir)
    c_mag = np.where(mild_long, np.clip((ls_top - 1.5) / (2.33 - 1.5) * 0.3, 0, 0.3), c_mag)
    c_dir = np.where(mild_short, 1.0, c_dir)
    c_mag = np.where(mild_short, np.clip((0.67 - ls_top) / (0.67 - 0.43) * 0.3, 0, 0.3), c_mag)

    c_conf = np.where((ls_long_ext == 1) | (ls_short_ext == 1), 0.6, 0.3)

    # Signal D: structural context (vectorized — key features only)
    in_prem = df["in_premium_zone"].values
    dist_pdh = df["dist_to_pdh_pct"].values
    dist_pdl = df["dist_to_pdl_pct"].values
    dist_nh  = df["dist_to_nearest_unmitigated_high_pct"].values
    dist_nl  = df["dist_to_nearest_unmitigated_low_pct"].values
    nh_age   = df["nearest_unmitigated_high_above_age_h"].values
    nl_age   = df["nearest_unmitigated_low_below_age_h"].values

    bear_score = (
        in_prem.astype(float) * 0.2
        + np.where((dist_pdh >= 0) & (dist_pdh < 0.5), 0.3, np.where((dist_pdh >= 0) & (dist_pdh < 1.5), 0.15, 0.0))
        + np.where((dist_nh < 2.0) & (nh_age < 24), 0.25, 0.0)
    )
    bull_score = (
        np.where((dist_pdl <= 0) & (dist_pdl > -0.5), 0.3, np.where((dist_pdl <= 0) & (dist_pdl > -1.5), 0.15, 0.0))
        + np.where((dist_nl < 2.0) & (nl_age < 24), 0.25, 0.0)
    )
    d_net = bear_score - bull_score
    d_dir = np.sign(d_net)
    d_dir[np.abs(d_net) < 0.1] = 0
    d_mag = np.clip(np.abs(d_net), 0, 0.9)
    d_conf = np.clip(0.3 + np.abs(d_net) * 0.5, 0, 0.7)

    # Signal E: momentum exhaustion (vectorized)
    rsi_14 = df["rsi_14"].values
    rvol   = df["rvol_20"].values
    uw_dom = df["upper_wick_dominance"].values
    lw_dom = df["lower_wick_dominance"].values

    e_dir = np.zeros(n, dtype=np.float32)
    e_mag = np.zeros(n, dtype=np.float32)

    ob = rsi_14 > 75
    os_ = rsi_14 < 25
    e_dir = np.where(ob, -1.0, np.where(os_, 1.0, 0.0))
    e_mag = np.where(ob,
        np.clip(0.3 + np.where(rvol > 1.5, 0.15, 0) + np.where(uw_dom > 0.4, 0.15, 0), 0, 0.9),
        np.where(os_,
            np.clip(0.3 + np.where(rvol > 1.5, 0.15, 0) + np.where(lw_dom > 0.4, 0.15, 0), 0, 0.9),
            0.0
        )
    )
    e_conf = np.where(np.abs(rsi_14 - 50) > 25, 0.5, 0.3)

    # Return signal array: (n, 5_signals × 3_fields)
    signals = pd.DataFrame({
        "a_dir": phase_dir, "a_mag": phase_mag.astype(np.float32), "a_conf": phase_conf,
        "b_dir": b_dir, "b_mag": b_mag.astype(np.float32), "b_conf": b_conf.astype(np.float32),
        "c_dir": c_dir, "c_mag": c_mag.astype(np.float32), "c_conf": c_conf.astype(np.float32),
        "d_dir": d_dir.astype(np.float32), "d_mag": d_mag.astype(np.float32), "d_conf": d_conf.astype(np.float32),
        "e_dir": e_dir, "e_mag": e_mag.astype(np.float32), "e_conf": e_conf.astype(np.float32),
    }, index=features_df.index)

    return signals


def _signals_to_prob_up(signals: pd.DataFrame, weights: list[float]) -> np.ndarray:
    """Convert signal arrays + weights to p_up for each bar (vectorized)."""
    assert len(weights) == 5
    w = np.array(weights, dtype=np.float64)
    total_w = w.sum()

    net = (
        signals["a_dir"].values * signals["a_mag"].values * signals["a_conf"].values * w[0]
        + signals["b_dir"].values * signals["b_mag"].values * signals["b_conf"].values * w[1]
        + signals["c_dir"].values * signals["c_mag"].values * signals["c_conf"].values * w[2]
        + signals["d_dir"].values * signals["d_mag"].values * signals["d_conf"].values * w[3]
        + signals["e_dir"].values * signals["e_mag"].values * signals["e_conf"].values * w[4]
    ) / total_w

    net = np.clip(net, -1.0, 1.0)
    prob_up = 1.0 / (1.0 + np.exp(-net * 4))
    return prob_up


def _brier_score(prob_up: np.ndarray, actual_dir: np.ndarray) -> float:
    """Brier score for binary up prediction. actual_dir: +1=up, else=not-up."""
    actual_bin = (actual_dir == 1).astype(float)
    valid = ~np.isnan(prob_up) & ~np.isnan(actual_bin)
    if valid.sum() < 10:
        return 0.25
    return float(((prob_up[valid] - actual_bin[valid]) ** 2).mean())


# ── Main calibration run ──────────────────────────────────────────────────────

def run_calibration(
    force_rebuild: bool = False,
    train_frac: float = 0.8,
) -> dict:
    """Run full historical calibration. Returns validation results dict.

    CHECKPOINT 3 gate: if test Brier > 0.28 on any horizon → report failure.
    """
    if not _FEATURES_PATH.exists():
        return {"error": "features not built — run build_full_features() first"}

    logger.info("calibration: loading features...")
    features = pd.read_parquet(_FEATURES_PATH)

    logger.info("calibration: computing outcomes...")
    outcomes = _compute_outcomes(features["close"])

    # Trim to rows where all horizons have valid outcomes (drop last ~288 bars)
    valid_mask = outcomes.notna().all(axis=1)
    features = features[valid_mask]
    outcomes = outcomes[valid_mask]

    n = len(features)
    split = int(n * train_frac)
    train_feat, test_feat = features.iloc[:split], features.iloc[split:]
    train_out,  test_out  = outcomes.iloc[:split], outcomes.iloc[split:]

    logger.info("calibration: train=%d test=%d", split, n - split)

    # Compute signals for both sets
    logger.info("calibration: computing signals (batch)...")
    train_signals = _compute_signals_batch(train_feat)
    test_signals  = _compute_signals_batch(test_feat)

    results = {}

    from .projection_v2 import _HORIZON_WEIGHTS

    for horizon in ["1h", "4h", "1d"]:
        logger.info("calibration: optimizing weights for %s horizon...", horizon)
        actual_col = f"actual_dir_{horizon}"
        if actual_col not in train_out.columns:
            continue

        train_actual = train_out[actual_col].values
        test_actual  = test_out[actual_col].values

        # Baseline weights (from _HORIZON_WEIGHTS)
        base_weights = _HORIZON_WEIGHTS.get(horizon, [0.2, 0.2, 0.2, 0.2, 0.2])

        # Grid search over weight perturbations
        best_weights = list(base_weights)
        best_train_brier = _brier_score(
            _signals_to_prob_up(train_signals, base_weights), train_actual
        )

        # Search: vary each weight by ±0.1 in steps of 0.05
        for delta_set in _weight_perturbations(base_weights, n_trials=200):
            prob_up = _signals_to_prob_up(train_signals, delta_set)
            bs = _brier_score(prob_up, train_actual)
            if bs < best_train_brier:
                best_train_brier = bs
                best_weights = delta_set

        # Evaluate best weights on test set
        test_prob_up = _signals_to_prob_up(test_signals, best_weights)
        test_brier = _brier_score(test_prob_up, test_actual)

        # Reliability: per decile of predicted prob_up, what fraction actually went up?
        reliability = _reliability_curve(test_prob_up, test_actual)

        # Sharpness: std of predicted probs (>0.1 = not trivially flat)
        sharpness = float(test_prob_up.std())

        # Baseline: predict always 0.5 → Brier = 0.25
        baseline_brier = 0.25

        results[horizon] = {
            "test_brier": round(test_brier, 4),
            "baseline_brier": baseline_brier,
            "improvement_vs_baseline": round(baseline_brier - test_brier, 4),
            "better_than_random": test_brier < baseline_brier,
            "target_met": test_brier <= 0.22,
            "sharpness": round(sharpness, 4),
            "best_weights": [round(w, 3) for w in best_weights],
            "reliability": reliability,
            "train_size": split,
            "test_size": n - split,
        }

        logger.info("calibration: %s brier=%.4f (baseline=0.25, improvement=%.4f)",
                    horizon, test_brier, baseline_brier - test_brier)

    # GO/NO-GO gate
    all_briers = [v["test_brier"] for v in results.values() if "test_brier" in v]
    best_brier = min(all_briers) if all_briers else 1.0
    worst_brier = max(all_briers) if all_briers else 1.0

    results["_summary"] = {
        "best_brier": round(best_brier, 4),
        "worst_brier": round(worst_brier, 4),
        "go_no_go": "GO" if worst_brier <= 0.28 else "NO-GO",
        "target_achieved": worst_brier <= 0.22,
        "note": (
            "Target ≤0.22 met on all horizons" if worst_brier <= 0.22
            else f"Target not met (worst={worst_brier:.4f}). "
                 + ("Above 0.28 — STOP gate triggered" if worst_brier > 0.28
                    else "Between 0.22-0.28 — marginal, report to operator")
        ),
    }

    return results


def _weight_perturbations(base_weights: list[float], n_trials: int = 200):
    """Generate weight perturbations for grid search. Yields normalized weight lists."""
    rng = np.random.default_rng(42)
    n = len(base_weights)
    for _ in range(n_trials):
        w = np.array(base_weights) + rng.uniform(-0.15, 0.15, n)
        w = np.clip(w, 0.0, 1.0)
        w = (w / w.sum()).tolist()
        yield w


def _reliability_curve(prob_up: np.ndarray, actual_dir: np.ndarray, n_bins: int = 5) -> list[dict]:
    """Compute reliability curve: per prob-decile, actual up fraction."""
    actual_bin = (actual_dir == 1).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    curve = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (prob_up >= lo) & (prob_up < hi)
        if mask.sum() > 0:
            mean_pred = float(prob_up[mask].mean())
            mean_actual = float(actual_bin[mask].mean())
            curve.append({
                "pred_range": f"{lo:.1f}-{hi:.1f}",
                "mean_pred": round(mean_pred, 3),
                "actual_up_frac": round(mean_actual, 3),
                "n": int(mask.sum()),
                "calibrated": abs(mean_pred - mean_actual) < 0.1,
            })
    return curve


# ── Per-phase calibration ─────────────────────────────────────────────────────

def run_per_phase_calibration(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    best_weights: dict[str, list[float]],
) -> dict:
    """Compute Brier per phase (uses regime_int as phase proxy)."""
    signals = _compute_signals_batch(features)
    phase_map = {1: "markup", -1: "markdown", 0: "range/transition"}

    results = {}
    for phase_val, phase_name in phase_map.items():
        mask = features["regime_int"] == phase_val
        if mask.sum() < 20:
            continue
        phase_signals = signals[mask]
        phase_out = outcomes[mask]
        for horizon in ["1h", "4h", "1d"]:
            actual_col = f"actual_dir_{horizon}"
            if actual_col not in phase_out.columns:
                continue
            w = best_weights.get(horizon, [0.2] * 5)
            prob_up = _signals_to_prob_up(phase_signals, w)
            actual = phase_out[actual_col].values
            bs = _brier_score(prob_up, actual)
            key = f"{phase_name}_{horizon}"
            results[key] = {
                "brier": round(bs, 4),
                "n_bars": int(mask.sum()),
            }

    return results
