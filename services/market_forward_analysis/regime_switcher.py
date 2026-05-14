"""Regime-conditional forecast switcher.

Routes forecast requests to per-regime calibration models (MARKUP/MARKDOWN/RANGE)
according to the OOS-validated delivery matrix. Applies hysteresis to prevent
thrashing between regimes and gating logic for window-sensitive cells.

Validated delivery matrix (from oos_validation_20260503T222446Z.json):
              1h            4h            1d
  MARKUP      qualitative   numeric       numeric-with-gate (regime_stability)
  MARKDOWN    numeric       numeric       qualitative (variance 0.197)
  RANGE       numeric       numeric       numeric (most stable, var 0.003)
  DISTRIBUTION qualitative  qualitative   qualitative (a priori)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .calibration import _compute_signals_batch, _signals_to_prob_up
from .regime_models.markup   import load_best_weights as load_markup_weights
from .regime_models.markdown import load_best_weights as load_markdown_weights
from .regime_models.range    import load_best_weights as load_range_weights

logger = logging.getLogger(__name__)


# Validated delivery matrix: True = numeric, False = qualitative
# MARKUP-1d uses gating: numeric IF regime_stability > _STABILITY_THRESHOLD
_DELIVERY_MATRIX: dict[str, dict[str, str]] = {
    "MARKUP":       {"1h": "qualitative", "4h": "numeric",     "1d": "gated"},
    "MARKDOWN":     {"1h": "numeric",     "4h": "numeric",     "1d": "qualitative"},
    "RANGE":        {"1h": "numeric",     "4h": "numeric",     "1d": "numeric"},
    "DISTRIBUTION": {"1h": "qualitative", "4h": "qualitative", "1d": "qualitative"},
}

# CV-validated mean Brier per cell — used for numeric output confidence
_CV_BRIER: dict[str, dict[str, float]] = {
    "MARKUP":   {"1h": 0.2733, "4h": 0.2590, "1d": 0.2346},
    "MARKDOWN": {"1h": 0.2042, "4h": 0.2278, "1d": 0.2801},
    "RANGE":    {"1h": 0.2467, "4h": 0.2478, "1d": 0.2502},
}

# Hysteresis: switch only after N consecutive bars of new regime + confidence threshold
_HYSTERESIS_BARS = 12          # 12 × 5m = 1h confirmation
_REGIME_CONF_THRESHOLD = 0.65  # below this → stay in last_regime
_STABILITY_THRESHOLD = 0.70    # MARKUP-1d gate: below this → qualitative fallback


@dataclass
class ForecastResult:
    horizon: str
    mode: str           # "numeric" | "qualitative"
    value: float | str  # prob_up if numeric, label string if qualitative
    confidence: float   # 1 - normalized_brier; 0..1
    caveat: Optional[str] = None
    # Optional setup context attached by setup_bridge.attach_setups().
    # When present: dict with keys {setup_type, direction, strength, confidence_pct,
    # entry, sl, tp1, tp2, basis_summary}. None when no matching setup was detected.
    setup_context: Optional[dict] = None


@dataclass
class SwitcherState:
    """Persistent state across forecast() calls for hysteresis."""
    last_regime: Optional[str] = None
    bars_in_current_regime: int = 0
    candidate_regime: Optional[str] = None
    candidate_bars: int = 0


class RegimeForecastSwitcher:
    """Regime-conditional forecast router with hysteresis and gating.

    Usage:
        sw = RegimeForecastSwitcher()
        result = sw.forecast(bar_features, regime="MARKDOWN",
                             regime_confidence=0.8, regime_stability=0.9)
        # result["1h"].value, result["1h"].mode, ...
    """

    def __init__(self) -> None:
        self.state = SwitcherState()
        self._weights_cache: dict[str, dict[str, list[float]]] = {
            "MARKUP":   {hz: load_markup_weights(hz)   for hz in ("1h", "4h", "1d")},
            "MARKDOWN": {hz: load_markdown_weights(hz) for hz in ("1h", "4h", "1d")},
            "RANGE":    {hz: load_range_weights(hz)    for hz in ("1h", "4h", "1d")},
        }

    # ── Hysteresis logic ──────────────────────────────────────────────────────

    def _resolve_regime(self, current_regime: str, regime_confidence: float) -> str:
        """Apply hysteresis: returns the regime to actually route to.

        First call (no last_regime): direct route to current_regime.
        Subsequent: switch only after confidence > threshold AND N consecutive
        bars of agreement. Otherwise stay in last_regime.
        """
        if self.state.last_regime is None:
            self.state.last_regime = current_regime
            self.state.bars_in_current_regime = 1
            self.state.candidate_regime = None
            self.state.candidate_bars = 0
            return current_regime

        if current_regime == self.state.last_regime:
            self.state.bars_in_current_regime += 1
            self.state.candidate_regime = None
            self.state.candidate_bars = 0
            return current_regime

        # Different regime input — only switch if confident AND sustained
        if regime_confidence < _REGIME_CONF_THRESHOLD:
            return self.state.last_regime  # not confident, stay

        if current_regime == self.state.candidate_regime:
            self.state.candidate_bars += 1
        else:
            self.state.candidate_regime = current_regime
            self.state.candidate_bars = 1

        if self.state.candidate_bars >= _HYSTERESIS_BARS:
            # Promotion: candidate becomes new regime
            self.state.last_regime = current_regime
            self.state.bars_in_current_regime = self.state.candidate_bars
            self.state.candidate_regime = None
            self.state.candidate_bars = 0
            return current_regime

        return self.state.last_regime

    # ── Forecast ──────────────────────────────────────────────────────────────

    def forecast(
        self,
        bar_features: pd.DataFrame,
        current_regime: str,
        regime_confidence: float = 1.0,
        regime_stability: float = 1.0,
    ) -> dict[str, ForecastResult]:
        """Produce per-horizon forecast for the given bar(s) and regime.

        bar_features: DataFrame with a single row (or batch); same schema as
                      regime_split parquets.
        current_regime: 'MARKUP' | 'MARKDOWN' | 'RANGE' | 'DISTRIBUTION'
        regime_confidence: 0..1 — Wyckoff classifier certainty
        regime_stability: 0..1 — proxy for regime-transition risk (higher = stabler)
        """
        effective_regime = self._resolve_regime(current_regime, regime_confidence)

        results: dict[str, ForecastResult] = {}
        for hz in ("1h", "4h", "1d"):
            mode_spec = _DELIVERY_MATRIX[effective_regime][hz]

            # Resolve gated cells
            if mode_spec == "gated":
                mode = "numeric" if regime_stability > _STABILITY_THRESHOLD else "qualitative"
                caveat = None if mode == "numeric" else (
                    f"regime_stability={regime_stability:.2f} below {_STABILITY_THRESHOLD}; "
                    "transition risk — qualitative fallback"
                )
            else:
                mode = mode_spec
                caveat = None

            if mode == "qualitative":
                # Qualitative output: direction-leaning label based on regime
                label = {
                    "MARKUP":       "lean_up",
                    "MARKDOWN":     "lean_down",
                    "RANGE":        "lean_neutral",
                    "DISTRIBUTION": "lean_top_unstable",
                }.get(effective_regime, "uncertain")

                results[hz] = ForecastResult(
                    horizon=hz,
                    mode="qualitative",
                    value=label,
                    confidence=max(0.0, 1.0 - _CV_BRIER.get(effective_regime, {}).get(hz, 0.25) / 0.25),
                    caveat=caveat,
                )
                continue

            # Numeric output: compute prob_up from regime model
            if effective_regime == "DISTRIBUTION":
                # Should not reach here (DISTRIBUTION is all-qualitative) — safety
                results[hz] = ForecastResult(hz, "qualitative", "uncertain", 0.0, caveat)
                continue

            weights = self._weights_cache[effective_regime][hz]
            signals = _compute_signals_batch(bar_features, horizon=hz)
            prob_up = float(_signals_to_prob_up(signals, weights)[-1])

            cv_brier = _CV_BRIER[effective_regime][hz]
            # Confidence: 1 - (Brier - random_baseline) normalized; 0.25 baseline → conf=1 at Brier=0
            confidence = max(0.0, min(1.0, 1.0 - (cv_brier / 0.25)))

            results[hz] = ForecastResult(
                horizon=hz,
                mode="numeric",
                value=prob_up,
                confidence=confidence,
                caveat=caveat,
            )

        return results

    def reset(self) -> None:
        """Clear hysteresis state (for tests or session restart)."""
        self.state = SwitcherState()
