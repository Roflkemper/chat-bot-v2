"""Sizing multiplier v0.1 — rule-based.

Spec: docs/DESIGN/SIZING_MULTIPLIER_v0_1.md (frozen params 2026-05-05).

Core function:
    compute_sizing(regime, forecast_1h, setup_context, wr_history) -> SizingDecision

Inputs:
    regime:         "MARKUP" | "MARKDOWN" | "RANGE" | "DISTRIBUTION"
    forecast_1h:    dict with keys {mode, value (prob_up if numeric), brier (CV)}
                    OR a ForecastResult-like object with .mode / .value / attrs
    setup_context:  dict (output of setup_bridge._setup_to_context) or None
    wr_history:     dict {"win_rate_pct": float|None, "decided_trades": int}
                    or None

Output:
    SizingDecision dataclass with multiplier, reasoning (Russian), inputs_snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Frozen v0.1 parameters (per design doc Decisions section) ─────────────────

_BASE_TABLE: dict[tuple[str, str], tuple[float, str]] = {
    # (regime, band) -> (base_mult, reasoning_fragment)
    ("MARKDOWN", "green"):       (1.4, "MARKDOWN с надёжным 1h (GREEN)"),
    ("MARKDOWN", "yellow"):      (1.0, "MARKDOWN, 1h в YELLOW"),
    ("MARKDOWN", "red"):         (0.6, "MARKDOWN, но 1h не numeric"),
    ("MARKDOWN", "qualitative"): (0.6, "MARKDOWN, 1h только качественный"),

    ("MARKUP", "green"):         (1.4, "MARKUP с надёжным 1h (GREEN)"),
    ("MARKUP", "yellow"):        (1.0, "MARKUP, 1h в YELLOW"),
    ("MARKUP", "red"):           (0.4, "MARKUP, 1h не numeric"),
    ("MARKUP", "qualitative"):   (0.4, "MARKUP, 1h только качественный"),

    ("RANGE", "green"):          (1.0, "RANGE с надёжным 1h"),
    ("RANGE", "yellow"):         (0.8, "RANGE, mean reversion — скромный размер"),
    ("RANGE", "red"):            (0.5, "RANGE без надёжного прогноза"),
    ("RANGE", "qualitative"):    (0.5, "RANGE без надёжного прогноза"),
}

_SETUP_DELTA: list[tuple[int, float, str]] = [
    # (min_strength, delta, fragment) — first match wins, ordered high-to-low
    (9,  +0.4, "strength-9+ сетап усиливает"),
    (7,  +0.2, "strength-7+ сетап подтверждает"),
    (1,   0.0, "сетап слабый"),
]
_NO_SETUP_DELTA: tuple[float, str] = (-0.2, "нет сетапа — отступление от модельного триггера")

_WR_MIN_TRADES = 10
_WR_TABLE: list[tuple[float, float, str]] = [
    # (min_wr_pct, multiplier, fragment) — ordered high-to-low
    (60.0, 1.1, "недельная статистика подтверждает (WR ≥60%)"),
    (40.0, 1.0, "недельная статистика нейтральна"),
    (0.0,  0.7, "недельная статистика против — снижаем"),
]
_WR_INSUFFICIENT = (1.0, "недельной статистики недостаточно")

_DIRECTION_CONFLICT_CAP = 0.5
_FORECAST_LONG_THRESHOLD = 0.55   # prob_up >= → long bias
_FORECAST_SHORT_THRESHOLD = 0.45  # prob_up <= → short bias

_FINAL_MIN, _FINAL_MAX = 0.0, 2.0

# Direction-aware workflow (block 4, locked 2026-05-05):
# Applied AFTER base × WR × conflict_cap × clamp. Promotes setups aligned with
# regime direction, dampens contrarian. RANGE/DISTRIBUTION untouched.
_DIRECTION_PROMOTE = 1.1
_DIRECTION_DAMP = 0.9


# ── Output dataclass ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SizingDecision:
    """Sizing decision with audit trail.

    Frozen fields (no extending in v0.1 per anti-drift) — multiplier, reasoning,
    inputs_snapshot. Migration to richer schema requires explicit operator approval.
    """
    multiplier: float            # final multiplier in [0.0, 2.0], 1 dp
    reasoning: str               # Russian, 1-2 sentences
    inputs_snapshot: dict        # frozen copy of inputs for audit


# ── Helpers ──────────────────────────────────────────────────────────────────

def _brier_band(brier: Optional[float]) -> str:
    """GREEN ≤0.22 / YELLOW 0.22-0.265 / RED >0.265 / qualitative for None."""
    if brier is None:
        return "qualitative"
    if brier <= 0.22:
        return "green"
    if brier <= 0.265:
        return "yellow"
    return "red"


def _extract_forecast_attrs(forecast_1h: Any) -> tuple[str, Optional[float], Optional[float]]:
    """Read mode / value / brier from dict or object-like input.

    Returns (mode, prob_up, brier). prob_up is None when mode != 'numeric'.
    """
    if forecast_1h is None:
        return ("qualitative", None, None)
    if isinstance(forecast_1h, dict):
        mode = forecast_1h.get("mode", "qualitative")
        value = forecast_1h.get("value")
        brier = forecast_1h.get("brier")
    else:
        mode = getattr(forecast_1h, "mode", "qualitative")
        value = getattr(forecast_1h, "value", None)
        brier = getattr(forecast_1h, "brier", None)
        if brier is None:
            # ForecastResult derives confidence from CV brier; reverse if needed
            conf = getattr(forecast_1h, "confidence", None)
            if conf is not None:
                brier = max(0.0, 0.25 * (1.0 - conf))

    prob_up: Optional[float] = None
    if mode == "numeric" and isinstance(value, (int, float)):
        prob_up = float(value)
    return (str(mode), prob_up, float(brier) if brier is not None else None)


def _forecast_direction(prob_up: Optional[float]) -> str:
    """Returns 'long' / 'short' / 'neutral' from prob_up, or 'unknown' if None."""
    if prob_up is None:
        return "unknown"
    if prob_up >= _FORECAST_LONG_THRESHOLD:
        return "long"
    if prob_up <= _FORECAST_SHORT_THRESHOLD:
        return "short"
    return "neutral"


def _setup_adjustment(
    setup_context: Optional[dict],
    forecast_direction: str,
) -> tuple[float, str, bool]:
    """Returns (delta, fragment, conflict_flag).

    conflict_flag: True if setup direction contradicts forecast direction.
    """
    if not setup_context:
        delta, frag = _NO_SETUP_DELTA
        return delta, frag, False

    strength = int(setup_context.get("strength") or 0)
    setup_dir = str(setup_context.get("direction") or "")

    delta = 0.0
    frag = "сетап слабый"
    for min_str, d, f in _SETUP_DELTA:
        if strength >= min_str:
            delta, frag = d, f
            break

    # Direction conflict only meaningful when both sides are directional
    conflict = False
    if forecast_direction in ("long", "short") and setup_dir in ("long", "short"):
        if forecast_direction != setup_dir:
            conflict = True
            frag = f"{frag}, но направление setup={setup_dir} против прогноза={forecast_direction}"

    return delta, frag, conflict


def _wr_adjustment(wr_history: Optional[dict]) -> tuple[float, str]:
    """Returns (multiplier, fragment) per WR table."""
    if not wr_history:
        return _WR_INSUFFICIENT
    decided = int(wr_history.get("decided_trades") or 0)
    wr_pct = wr_history.get("win_rate_pct")
    if decided < _WR_MIN_TRADES or wr_pct is None:
        return _WR_INSUFFICIENT
    wr_pct = float(wr_pct)
    for min_wr, mult, frag in _WR_TABLE:
        if wr_pct >= min_wr:
            return mult, f"{frag} (WR {wr_pct:.0f}%, n={decided})"
    return _WR_INSUFFICIENT


def apply_direction_workflow(
    sizing: "SizingDecision",
    regime: str,
    setup_direction: Optional[str],
) -> "SizingDecision":
    """Direction-aware promotion/dampening layer (block 4).

    Applied AFTER `compute_sizing()` clamp. Returns a NEW SizingDecision.

    Rules:
        MARKUP   × long  → ×1.1 (promote)
        MARKUP   × short → ×0.9 (damp)
        MARKDOWN × short → ×1.1 (promote)
        MARKDOWN × long  → ×0.9 (damp)
        RANGE / DISTRIBUTION × any → unchanged
        unknown setup_direction → unchanged

    Final clamp [0, 2] re-applied after factor.
    """
    if regime not in {"MARKUP", "MARKDOWN"}:
        return sizing
    if setup_direction not in {"long", "short"}:
        return sizing

    if (regime == "MARKUP" and setup_direction == "long") or \
       (regime == "MARKDOWN" and setup_direction == "short"):
        factor, frag = _DIRECTION_PROMOTE, f"{regime} режим → {setup_direction.upper()} promoted ×{_DIRECTION_PROMOTE}"
    else:
        factor, frag = _DIRECTION_DAMP, f"{regime} режим → {setup_direction.upper()} damped ×{_DIRECTION_DAMP}"

    new_mult = max(_FINAL_MIN, min(_FINAL_MAX, round(sizing.multiplier * factor, 1)))
    new_reasoning = f"{sizing.reasoning.rstrip('.×')} → {frag}, итог {new_mult}×."
    new_snapshot = dict(sizing.inputs_snapshot)
    new_snapshot["direction_workflow"] = {
        "regime": regime,
        "setup_direction": setup_direction,
        "factor": factor,
        "before": sizing.multiplier,
        "after": new_mult,
    }
    return SizingDecision(
        multiplier=new_mult,
        reasoning=new_reasoning,
        inputs_snapshot=new_snapshot,
    )


# ── Public entry point ───────────────────────────────────────────────────────

def compute_sizing(
    regime: str,
    forecast_1h: Any,
    setup_context: Optional[dict],
    wr_history: Optional[dict] = None,
    apply_workflow: bool = True,
) -> SizingDecision:
    """Compute sizing multiplier v0.1.

    See docs/DESIGN/SIZING_MULTIPLIER_v0_1.md for full spec.

    apply_workflow: when True (default), applies direction-aware workflow layer
    after the clamp (block 4). Set False to disable for backward-compat
    or A/B comparison.
    """
    snapshot = {
        "regime": regime,
        "forecast_1h": (
            {"mode": getattr(forecast_1h, "mode", None) or (forecast_1h or {}).get("mode") if forecast_1h else None,
             "value": getattr(forecast_1h, "value", None) or (forecast_1h or {}).get("value") if forecast_1h else None,
             "brier": getattr(forecast_1h, "brier", None) or (forecast_1h or {}).get("brier") if forecast_1h else None}
            if forecast_1h is not None else None
        ),
        "setup_context": dict(setup_context) if setup_context else None,
        "wr_history": dict(wr_history) if wr_history else None,
    }

    # Step 0: DISTRIBUTION short-circuit
    if regime == "DISTRIBUTION":
        return SizingDecision(
            multiplier=0.0,
            reasoning="DISTRIBUTION-режим — модель не выдаёт numeric edge; не торгуем по модели, флэт.",
            inputs_snapshot=snapshot,
        )

    mode, prob_up, brier = _extract_forecast_attrs(forecast_1h)
    band = _brier_band(brier)
    if mode != "numeric":
        band = "qualitative"

    # Step 1: base from regime + band
    base_entry = _BASE_TABLE.get((regime, band))
    if base_entry is None:
        # Unknown regime: refuse to size
        return SizingDecision(
            multiplier=0.0,
            reasoning=f"Неизвестный режим {regime!r} — не торгуем по модели, флэт.",
            inputs_snapshot=snapshot,
        )
    base, base_frag = base_entry

    # Step 2: setup delta + direction conflict
    forecast_dir = _forecast_direction(prob_up)
    setup_delta, setup_frag, conflict = _setup_adjustment(setup_context, forecast_dir)
    pre = base + setup_delta
    if conflict:
        pre = min(pre, _DIRECTION_CONFLICT_CAP)

    # Step 3: WR multiplier
    wr_mult, wr_frag = _wr_adjustment(wr_history)
    final = pre * wr_mult

    # Final clamp + round
    final = max(_FINAL_MIN, min(_FINAL_MAX, round(final, 1)))

    reasoning = f"{base_frag}, {setup_frag}, {wr_frag} — размер {final}×."
    decision = SizingDecision(
        multiplier=final,
        reasoning=reasoning,
        inputs_snapshot=snapshot,
    )

    # Block 4 — direction-aware workflow layer (after clamp)
    if apply_workflow and setup_context:
        setup_dir = setup_context.get("direction") if isinstance(setup_context, dict) else None
        decision = apply_direction_workflow(decision, regime, setup_dir)

    return decision
