"""Integration with setup_bridge — optional wrapper that attaches SizingDecision.

Usage:
    forecasts = switcher.forecast(bar, regime, ...)
    forecasts = attach_setups(forecasts, setups)
    forecasts = attach_sizing(forecasts, regime, wr_history)
    # Now forecasts["1h"].sizing_decision is populated.

Anti-drift: ForecastResult dataclass is frozen → we add the sizing as a
separate dict keyed by horizon. Callers read it via the helper, not via
mutation. This keeps the `SizingDecision` schema small ({multiplier, reasoning,
inputs_snapshot}) and avoids extending ForecastResult.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from services.market_forward_analysis.regime_switcher import ForecastResult
from .multiplier import compute_sizing, SizingDecision


def attach_sizing(
    forecasts: dict[str, ForecastResult],
    regime: str,
    wr_history: Optional[dict] = None,
) -> dict[str, dict]:
    """Compute sizing for the 1h horizon (the only one v0.1 sizes).

    Returns a NEW dict shaped as:
        {hz: {"forecast": ForecastResult, "sizing": SizingDecision | None}}

    Why not mutate ForecastResult: the dataclass is intentionally minimal
    and was extended once already (setup_context). Further extensions would
    create coupling between the switcher contract and downstream concerns.
    A side-by-side dict is cleaner for v0.1.
    """
    out: dict[str, dict] = {}
    for hz, fr in forecasts.items():
        sizing: Optional[SizingDecision] = None
        if hz == "1h":
            setup_ctx = fr.setup_context if fr.setup_context else None
            sizing = compute_sizing(
                regime=regime,
                forecast_1h=_forecast_to_dict(fr),
                setup_context=setup_ctx,
                wr_history=wr_history,
            )
        out[hz] = {"forecast": fr, "sizing": sizing}
    return out


def _forecast_to_dict(fr: ForecastResult) -> dict:
    """Render ForecastResult for compute_sizing()'s dict-form input."""
    # Brier is not on ForecastResult; we infer from confidence (1 - brier/0.25)
    # confidence = max(0, 1 - brier/0.25) → brier = 0.25 * (1 - confidence)
    brier = max(0.0, 0.25 * (1.0 - fr.confidence)) if fr.confidence else None
    return {
        "mode": fr.mode,
        "value": fr.value,
        "brier": brier,
    }
