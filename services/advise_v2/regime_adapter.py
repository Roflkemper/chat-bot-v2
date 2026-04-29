from __future__ import annotations

from core.orchestrator.regime_classifier import (
    PRIMARY_CASCADE_DOWN,
    PRIMARY_CASCADE_UP,
    PRIMARY_COMPRESSION,
    PRIMARY_RANGE,
    PRIMARY_TREND_DOWN,
    PRIMARY_TREND_UP,
    RegimeSnapshot,
)

_VALID_ADVISE_LABELS = {
    "impulse_up",
    "impulse_down",
    "impulse_up_exhausting",
    "impulse_down_exhausting",
    "range_tight",
    "range_wide",
    "trend_up",
    "trend_down",
    "consolidation",
    "unknown",
}


def map_regime_to_advise_label(snapshot: RegimeSnapshot) -> str:
    """
    Map active RegimeSnapshot output into advise_v2 MarketContext.regime_label values.

    Defaults to "unknown" for unsupported primary labels.
    """
    primary = getattr(snapshot, "primary_regime", None)
    metrics = getattr(snapshot, "metrics", None)

    if primary == PRIMARY_TREND_UP:
        return "trend_up"
    if primary == PRIMARY_TREND_DOWN:
        return "trend_down"
    if primary == PRIMARY_COMPRESSION:
        return "consolidation"
    if primary == PRIMARY_RANGE:
        bb_width = float(getattr(metrics, "bb_width_pct_1h", 0.0) or 0.0)
        return "range_tight" if bb_width < 3.0 else "range_wide"
    if primary == PRIMARY_CASCADE_UP:
        adx = float(getattr(metrics, "adx_1h", 0.0) or 0.0)
        adx_slope = float(getattr(metrics, "adx_slope_1h", 0.0) or 0.0)
        return "impulse_up_exhausting" if adx > 40.0 and adx_slope < 0.0 else "impulse_up"
    if primary == PRIMARY_CASCADE_DOWN:
        adx = float(getattr(metrics, "adx_1h", 0.0) or 0.0)
        adx_slope = float(getattr(metrics, "adx_slope_1h", 0.0) or 0.0)
        return "impulse_down_exhausting" if adx > 40.0 and adx_slope < 0.0 else "impulse_down"
    return "unknown"


def is_valid_advise_regime_label(value: str) -> bool:
    """Return True when the mapped regime label is valid for advise_v2 schema."""
    return value in _VALID_ADVISE_LABELS
