"""Bridge between setup_detector and RegimeForecastSwitcher.

The two systems speak different languages:
  - setup_detector wants DetectionContext (pair, OHLCV, ICT, etc) and emits Setup
  - regime_switcher wants a feature-row and emits ForecastResult per horizon

This module owns the merge: run setup_detector, attach the best-matching setup
to the relevant horizon's ForecastResult.

Why bridge instead of import-into-switcher:
  1. Switcher stays pure: features → forecast. No OHLCV dependency.
  2. setup_detector heavy (14 detectors, ICT context). Lazy import here.
  3. Easy to disable: pass `attach_setups=False` to skip the merge path.

Direction → horizon mapping:
  LONG_*  setups   → attach to 1h forecast (entry-timing signal)
  SHORT_* setups   → attach to 1h forecast
  GRID_*  setups   → attach to 4h forecast (slower management actions)
  DEFENSIVE_*      → attach to 1h forecast (urgent)

Conflict resolution: highest strength wins per horizon. Ties broken by
confidence_pct.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from .regime_switcher import ForecastResult


_HORIZON_BY_PREFIX: dict[str, str] = {
    "long_":      "1h",
    "short_":     "1h",
    "grid_":      "4h",
    "def_":       "1h",
    "defensive_": "1h",
}


def _setup_to_context(setup) -> dict:
    """Compact dict suitable for ForecastResult.setup_context."""
    direction = "long" if setup.setup_type.value.startswith("long") else (
        "short" if setup.setup_type.value.startswith("short") else "grid"
    )
    basis_summary = ", ".join(b.label for b in setup.basis[:4]) if setup.basis else ""
    return {
        "setup_id": setup.setup_id,
        "setup_type": setup.setup_type.value,
        "direction": direction,
        "strength": setup.strength,
        "confidence_pct": setup.confidence_pct,
        "entry": setup.entry_price,
        "sl": setup.stop_price,
        "tp1": setup.tp1_price,
        "tp2": setup.tp2_price,
        "rr": setup.risk_reward,
        "basis_summary": basis_summary,
        "regime_at_detection": setup.regime_label,
    }


def _horizon_for_setup_type(setup_type_value: str) -> str:
    for prefix, hz in _HORIZON_BY_PREFIX.items():
        if setup_type_value.startswith(prefix):
            return hz
    return "1h"


def _select_best_per_horizon(setups: list) -> dict[str, "object"]:
    """Pick highest-strength setup for each horizon. Ties → confidence_pct."""
    best: dict[str, object] = {}
    for s in setups:
        hz = _horizon_for_setup_type(s.setup_type.value)
        cur = best.get(hz)
        if cur is None:
            best[hz] = s
            continue
        if (s.strength, s.confidence_pct) > (cur.strength, cur.confidence_pct):
            best[hz] = s
    return best


def attach_setups(
    forecasts: dict[str, ForecastResult],
    setups: list,
) -> dict[str, ForecastResult]:
    """Attach matching setups to forecast results.

    forecasts: per-horizon ForecastResult dict (output of switcher.forecast()).
    setups:    list of Setup instances (output of running setup_detector).

    Returns a NEW dict — does not mutate the input. Horizons with no matching
    setup get setup_context=None.
    """
    if not setups:
        return {hz: dataclasses.replace(fr, setup_context=None) for hz, fr in forecasts.items()}

    best_per_horizon = _select_best_per_horizon(setups)
    out: dict[str, ForecastResult] = {}
    for hz, fr in forecasts.items():
        s = best_per_horizon.get(hz)
        ctx = _setup_to_context(s) if s is not None else None
        out[hz] = dataclasses.replace(fr, setup_context=ctx)
    return out


def detect_and_attach(
    forecasts: dict[str, ForecastResult],
    detection_ctx,
    detector_registry: Optional[tuple] = None,
) -> dict[str, ForecastResult]:
    """Run setup_detector against `detection_ctx`, attach results to `forecasts`.

    Returns a new forecasts dict with setup_context populated where a setup matches.
    Detection failures are non-fatal: returns forecasts with None setup_context.
    """
    if detection_ctx is None:
        return attach_setups(forecasts, [])

    if detector_registry is None:
        from services.setup_detector.setup_types import DETECTOR_REGISTRY
        detector_registry = DETECTOR_REGISTRY

    candidates: list = []
    for detector in detector_registry:
        try:
            setup = detector(detection_ctx)
            if setup is not None:
                candidates.append(setup)
        except Exception:
            # Single-detector failure shouldn't break the chain
            continue
    return attach_setups(forecasts, candidates)
