"""Regime adapter — projects Classifier A live output to Decision Layer schema.

Read-only thin shim between two systems:

  Producer:  core/orchestrator/regime_classifier.py (Classifier A per
             docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md §1).
             Writes state/regime_state.json every ~5 min via app_runner →
             core/pipeline.py (atomic write through utils.safe_io).

  Consumer:  services/decision_layer/decision_layer.py (Decision Layer
             R-* / D-2 rules) and services/dashboard/state_builder.py
             (regulation_action_card).
             Both expect a dict with the 3-state taxonomy
             {MARKUP, MARKDOWN, RANGE} plus regime_confidence /
             regime_stability scalars in [0.0, 1.0].

Why this adapter exists:
  Decision Layer was originally wired against
  data/regime/switcher_state.json, which was populated by the manual
  one-shot scaffold scripts/dashboard_bootstrap_state.py reading frozen
  forecast-pipeline parquets. That pipeline was decommissioned per
  FORECAST_DECOMMISSION; the bootstrap script kept dashboards "looking
  alive" but its output was permanently frozen at bar_time 2026-05-01.
  Meanwhile Classifier A has been live the whole time, writing to
  state/regime_state.json on every snapshot cycle. This adapter routes
  Decision Layer / state_builder to that live source.

Projection rules (from docs/DESIGN/CLASSIFIER_AUTHORITY_v1.md §1):

  Classifier A primary    → 3-state alignment
  --------------------------------------------
  TREND_UP, CASCADE_UP    → MARKUP
  TREND_DOWN, CASCADE_DOWN → MARKDOWN
  RANGE, COMPRESSION      → RANGE

The same projection applies to pending_primary → candidate_regime.

Computed scalars (Classifier A does not emit numeric confidence —
see CLASSIFIER_AUTHORITY_v1 §1 row "Confidence: Implicit"):

  regime_confidence = min(1.0, hysteresis_counter / HYSTERESIS_THRESHOLD)
    HYSTERESIS_THRESHOLD = 2  (per core/orchestrator/regime_classifier.py
    apply_hysteresis line 420: `if new_counter >= 2: ...`).
    Semantics: confidence = "how close are we to confirming a regime
    transition". When counter=0 (no pending change), confidence in the
    *current* regime is anchored by stability instead. To preserve
    R-1 ("stable + confident → INFO") meaningfulness when there is no
    pending transition, we report confidence = 1.0 in that case
    (the current regime is fully confirmed; no challenger).

  regime_stability = min(1.0, regime_age_bars / STABILITY_SATURATION)
    STABILITY_SATURATION = 12  (matches HYSTERESIS_CALIBRATION_v1 H=1
    12-bar window that the Decision Layer §3 thresholds are anchored
    to: HYSTERESIS_BARS_FULL = 12).
    Semantics: a regime that has held for ≥12 bars saturates at full
    stability; younger regimes scale linearly.

These formulas are operator-tunable in a future
TZ-DECISION-LAYER-CONFIG and are flagged as v1 defaults.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_REGIME_STATE_PATH = Path("state/regime_state.json")

# Per core/orchestrator/regime_classifier.py apply_hysteresis line 420.
HYSTERESIS_THRESHOLD: int = 2

# Saturation period for stability — matches Decision Layer's
# HYSTERESIS_BARS_FULL (12) which is the §3 threshold for confirmed transitions.
STABILITY_SATURATION: int = 12

# Projection table per CLASSIFIER_AUTHORITY_v1 §1.
_PRIMARY_TO_3STATE: dict[str, str] = {
    "TREND_UP": "MARKUP",
    "CASCADE_UP": "MARKUP",
    "TREND_DOWN": "MARKDOWN",
    "CASCADE_DOWN": "MARKDOWN",
    "RANGE": "RANGE",
    "COMPRESSION": "RANGE",
}


def _project_primary(primary: Optional[str]) -> Optional[str]:
    if primary is None:
        return None
    return _PRIMARY_TO_3STATE.get(primary)


def _compute_confidence(hysteresis_counter: int, pending_primary: Optional[str]) -> float:
    """Confidence = how confirmed is the current regime label.

    No pending transition → fully confirmed (1.0). Pending transition →
    fraction of the way through the 2-bar confirmation window.
    """
    if pending_primary is None:
        return 1.0
    if hysteresis_counter <= 0:
        return 0.0
    return min(1.0, hysteresis_counter / HYSTERESIS_THRESHOLD)


def _compute_stability(regime_age_bars: int) -> float:
    """Stability = saturating monotonic of regime_age_bars."""
    if regime_age_bars <= 0:
        return 0.0
    return min(1.0, regime_age_bars / STABILITY_SATURATION)


def _file_mtime_iso(path: Path) -> Optional[str]:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return mtime.strftime("%Y-%m-%dT%H:%M:%SZ")


def _newer_iso(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the lexicographically newer ISO8601 timestamp (Z-suffixed UTC)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a > b else b


def _normalize_iso(s: Optional[str]) -> Optional[str]:
    """Normalize an ISO timestamp to '%Y-%m-%dT%H:%M:%SZ' UTC form."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, AttributeError):
        return None


def adapt_regime_state(
    *,
    path: Path = DEFAULT_REGIME_STATE_PATH,
    symbol: str = "BTCUSDT",
) -> Optional[dict[str, Any]]:
    """Read state/regime_state.json and return a Decision Layer-shaped dict.

    Returns None if the file is missing, unreadable, or the requested
    symbol is not present. Decision Layer treats None as "no regime
    state available" — D-2 (regime_stale) rule will fire on file age
    via state_builder freshness block.

    Output schema (Decision Layer DecisionInputs / state_builder _build_regime):
      {
        "regime":                    str,            # MARKUP|MARKDOWN|RANGE
        "regime_confidence":         float in [0,1],
        "regime_stability":          float in [0,1],
        "bars_in_current_regime":    int,
        "candidate_regime":          str | None,     # MARKUP|MARKDOWN|RANGE
        "candidate_bars":            int,
        "bar_time":                  str (ISO8601 UTC),
        "updated_at":                str (ISO8601 UTC),
      }
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("regime_adapter: cannot read %s: %s", path, exc)
        return None

    symbols = raw.get("symbols") or {}
    sym_state = symbols.get(symbol)
    if not isinstance(sym_state, dict):
        return None

    primary = sym_state.get("current_primary")
    pending = sym_state.get("pending_primary")
    age_bars = int(sym_state.get("regime_age_bars") or 0)
    counter = int(sym_state.get("hysteresis_counter") or 0)
    primary_since = _normalize_iso(sym_state.get("primary_since"))

    projected = _project_primary(primary) if primary else None
    if projected is None:
        # Unknown primary state — refuse to project (don't silently
        # mislabel something we don't have a rule for).
        logger.warning(
            "regime_adapter: no projection rule for primary=%r; returning None",
            primary,
        )
        return None
    candidate = _project_primary(pending)

    confidence = _compute_confidence(counter, pending)
    stability = _compute_stability(age_bars)

    file_iso = _file_mtime_iso(path)
    updated_at = _newer_iso(primary_since, file_iso) or primary_since or file_iso

    return {
        "regime": projected,
        "regime_confidence": confidence,
        "regime_stability": stability,
        "bars_in_current_regime": age_bars,
        "candidate_regime": candidate,
        "candidate_bars": counter,
        "bar_time": primary_since,
        "updated_at": updated_at,
    }
