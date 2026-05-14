"""Tests for scripts/setup_precision_tracker statistical functions."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "setup_precision_tracker",
        ROOT / "scripts" / "setup_precision_tracker.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["setup_precision_tracker"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bootstrap_ci_handles_empty():
    mod = _load_module()
    assert mod._bootstrap_ci([], lambda x: 0) == (0.0, 0.0)


def test_bootstrap_ci_handles_too_few():
    mod = _load_module()
    assert mod._bootstrap_ci([0.1, 0.2], lambda x: sum(x)/len(x)) == (0.0, 0.0)


def test_bootstrap_ci_for_positive_distribution():
    mod = _load_module()
    # 100 samples around 0.5 ± 0.1 → CI should hug 0.5 and exclude 0
    import random
    random.seed(42)
    samples = [0.5 + random.gauss(0, 0.1) for _ in range(100)]
    lo, hi = mod._bootstrap_ci(samples, lambda x: sum(x)/len(x), n_resamples=500)
    assert lo > 0.4
    assert hi < 0.6
    assert lo > 0  # excludes zero


def test_status_insufficient_below_30():
    mod = _load_module()
    assert mod._status(20, 0, 0, 0, 0) == "INSUFFICIENT"
    assert mod._status(0, 0, 0, 0, 0) == "INSUFFICIENT"


def test_status_evaluating_30_to_99_positive_ci():
    mod = _load_module()
    # CI entirely positive, N=50
    assert mod._status(50, 0.05, 0.20, 0.10, 0.001) == "EVALUATING"


def test_status_stable_n100_positive_ci():
    mod = _load_module()
    assert mod._status(150, 0.05, 0.20, 0.10, 0.001) == "STABLE"


def test_status_degraded_negative_ci():
    mod = _load_module()
    # CI entirely negative
    assert mod._status(50, -0.30, -0.05, -0.15, 0.005) == "DEGRADED"


def test_status_marginal_straddling_zero():
    mod = _load_module()
    # CI straddles 0 with no big drift from backtest
    assert mod._status(50, -0.05, 0.10, 0.02, 0.005) == "MARGINAL"


def test_status_degraded_drift_vs_backtest():
    mod = _load_module()
    # CI straddles 0, but live way below backtest exp → DEGRADED
    # backtest=0.50, live=-0.30, CI=[-0.40, 0.20] → sigma~0.15, z=(0.50-(-0.30))/0.15=5.3
    assert mod._status(50, -0.40, 0.20, -0.30, 0.50) == "DEGRADED"
