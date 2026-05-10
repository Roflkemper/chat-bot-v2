"""Pipeline observability for setup detector.

Records every stage transition (detector run → strength check → combo
filter → semantic dedup → type/pair dedup → GC confirmation → MTF check
→ emit) so we can build a daily funnel and catch silent-drop bugs.

Background: 2026-05-10 audit found 48 P-15 emits combo_blocked over 2
days because P-15 used strength=8 while combo_filter required >=9. The
bug sat unnoticed because each drop-stage only wrote a single log line
with no aggregate. This module gives us a structured drop record.

File: state/pipeline_metrics.jsonl  (one line per dropped/emitted setup)
Schema:
  {ts, pair, setup_type, side, regime, session, strength, confidence,
   stage_outcome, drop_reason}
where stage_outcome ∈ {
   "detector_failed", "below_strength", "combo_blocked",
   "semantic_dedup_skip", "type_pair_dedup_skip",
   "gc_blocked", "gc_boost", "gc_penalty", "gc_neutral",
   "mtf_aligned", "mtf_conflict", "mtf_neutral",
   "emitted"
}

Design notes:
- One file, append-only. Rotated by date in scripts/daily_kpi_report.py.
- ensure_ascii=False to keep Cyrillic/labels readable.
- All writes are best-effort; failures swallow to never block the loop.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_METRICS_PATH = _ROOT / "state" / "pipeline_metrics.jsonl"


def record(
    *,
    pair: str | None = None,
    setup_type: str | None = None,
    side: str | None = None,
    regime: str | None = None,
    session: str | None = None,
    strength: int | None = None,
    confidence: float | None = None,
    stage_outcome: str,
    drop_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one structured record to pipeline_metrics.jsonl. Never raises."""
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage_outcome": stage_outcome,
    }
    if pair is not None: payload["pair"] = pair
    if setup_type is not None: payload["setup_type"] = setup_type
    if side is not None: payload["side"] = side
    if regime is not None: payload["regime"] = regime
    if session is not None: payload["session"] = session
    if strength is not None: payload["strength"] = strength
    if confidence is not None: payload["confidence"] = round(float(confidence), 1)
    if drop_reason is not None: payload["drop_reason"] = drop_reason
    if extra:
        payload.update(extra)

    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _METRICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except OSError:
        logger.exception("pipeline_metrics.write_failed")


def _setup_side(setup_type_value: str) -> str:
    return "long" if "long" in setup_type_value.lower() else "short"


def record_setup(setup, stage_outcome: str, *, drop_reason: str | None = None,
                 extra: dict[str, Any] | None = None) -> None:
    """Convenience wrapper: extracts common fields from a Setup object."""
    try:
        st = setup.setup_type.value
    except AttributeError:
        st = "?"
    record(
        pair=getattr(setup, "pair", None),
        setup_type=st,
        side=_setup_side(st),
        regime=getattr(setup, "regime_label", None),
        session=getattr(setup, "session_label", None),
        strength=getattr(setup, "strength", None),
        confidence=getattr(setup, "confidence_pct", None),
        stage_outcome=stage_outcome,
        drop_reason=drop_reason,
        extra=extra,
    )
