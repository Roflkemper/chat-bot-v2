from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class PipelineIntegrationResult:
    state: str
    active_block_side: Optional[str]
    block_depth_pct: Optional[float]
    distance_to_active_edge: Optional[float]
    distance_to_upper_edge: Optional[float]
    distance_to_lower_edge: Optional[float]
    overrun_flag: bool
    consensus_direction: Optional[str]
    consensus_confidence: Optional[str]
    consensus_label: str
    pattern_visible: bool
    pattern_reason_hidden: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_confidence(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().upper()
    if v in {"LOW", "MID", "HIGH", "NONE"}:
        return v
    if "LOW" in v:
        return "LOW"
    if "MID" in v or "MED" in v:
        return "MID"
    if "HIGH" in v:
        return "HIGH"
    return None


def _normalize_direction(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().upper()
    if v in {"LONG", "SHORT", "CONFLICTED", "NONE", "NEUTRAL"}:
        return v
    if "LONG" in v:
        return "LONG"
    if "SHORT" in v:
        return "SHORT"
    if "CONFLICT" in v:
        return "CONFLICTED"
    if "NEUTRAL" in v:
        return "NEUTRAL"
    return None


def normalize_pattern_visibility(
    pattern_snapshot: Dict[str, Any],
    min_abs_avg_move_pct: float = 0.20,
    min_samples: int = 10,
) -> Dict[str, Any]:
    avg_move = _safe_float(pattern_snapshot.get("avg_move_pct"))
    samples = pattern_snapshot.get("sample_count")
    try:
        samples = int(samples) if samples is not None else None
    except Exception:
        samples = None

    visible = True
    hidden_reason = None

    if avg_move is not None and abs(avg_move) < min_abs_avg_move_pct:
        visible = False
        hidden_reason = "avg_move_below_threshold"
    if samples is not None and samples < min_samples:
        visible = False
        hidden_reason = hidden_reason or "sample_count_below_threshold"

    pattern_snapshot = dict(pattern_snapshot)
    pattern_snapshot["visible"] = visible
    pattern_snapshot["hidden_reason"] = hidden_reason
    return pattern_snapshot


def normalize_consensus(
    execution_side: Optional[str],
    consensus_direction: Optional[str],
    consensus_confidence: Optional[str],
) -> Dict[str, Any]:
    side = _normalize_direction(execution_side)
    direction = _normalize_direction(consensus_direction)
    confidence = _normalize_confidence(consensus_confidence)

    if side in {"LONG", "SHORT"} and direction in {None, "NEUTRAL", "NONE"}:
        direction = side
        confidence = confidence or "LOW"

    if direction == "CONFLICTED":
        label = "CONFLICTED"
    elif direction in {"LONG", "SHORT"}:
        label = f"{direction} | {confidence or 'LOW'}"
    else:
        label = "NONE"

    return {
        "consensus_direction": direction,
        "consensus_confidence": confidence,
        "consensus_label": label,
    }


def enforce_state_inside_active_block(
    state: Optional[str],
    price: float,
    active_block_low: Optional[float],
    active_block_high: Optional[float],
    active_block_side: Optional[str],
) -> str:
    normalized_state = (state or "MID_RANGE").strip().upper()
    if (
        active_block_low is not None
        and active_block_high is not None
        and active_block_low <= price <= active_block_high
        and active_block_side in {"LONG", "SHORT"}
    ):
        if normalized_state == "MID_RANGE":
            return "SEARCH_TRIGGER"
    return normalized_state


def build_pipeline_fields(
    *,
    price: float,
    existing_state: Optional[str],
    execution_side: Optional[str],
    state_machine_snapshot: Dict[str, Any],
    pattern_snapshot: Optional[Dict[str, Any]] = None,
    consensus_snapshot: Optional[Dict[str, Any]] = None,
) -> PipelineIntegrationResult:
    pattern_snapshot = pattern_snapshot or {}
    consensus_snapshot = consensus_snapshot or {}

    active_block_low = _safe_float(state_machine_snapshot.get("active_block_low"))
    active_block_high = _safe_float(state_machine_snapshot.get("active_block_high"))

    state = enforce_state_inside_active_block(
        state=state_machine_snapshot.get("state") or existing_state,
        price=float(price),
        active_block_low=active_block_low,
        active_block_high=active_block_high,
        active_block_side=_normalize_direction(state_machine_snapshot.get("active_block_side")),
    )

    pattern_norm = normalize_pattern_visibility(pattern_snapshot)
    consensus_norm = normalize_consensus(
        execution_side=execution_side,
        consensus_direction=consensus_snapshot.get("direction"),
        consensus_confidence=consensus_snapshot.get("confidence"),
    )

    return PipelineIntegrationResult(
        state=state,
        active_block_side=_normalize_direction(state_machine_snapshot.get("active_block_side")),
        block_depth_pct=_safe_float(state_machine_snapshot.get("block_depth_pct")),
        distance_to_active_edge=_safe_float(state_machine_snapshot.get("distance_to_active_edge")),
        distance_to_upper_edge=_safe_float(state_machine_snapshot.get("distance_to_upper_edge")),
        distance_to_lower_edge=_safe_float(state_machine_snapshot.get("distance_to_lower_edge")),
        overrun_flag=bool(state_machine_snapshot.get("overrun_flag", False)),
        consensus_direction=consensus_norm["consensus_direction"],
        consensus_confidence=consensus_norm["consensus_confidence"],
        consensus_label=consensus_norm["consensus_label"],
        pattern_visible=bool(pattern_norm.get("visible", True)),
        pattern_reason_hidden=pattern_norm.get("hidden_reason"),
    )


def merge_into_decision_snapshot(
    decision_snapshot: Dict[str, Any],
    integration_result: PipelineIntegrationResult,
) -> Dict[str, Any]:
    out = dict(decision_snapshot)
    out.update({
        "state": integration_result.state,
        "active_block_side": integration_result.active_block_side,
        "block_depth_pct": integration_result.block_depth_pct,
        "distance_to_active_edge": integration_result.distance_to_active_edge,
        "distance_to_upper_edge": integration_result.distance_to_upper_edge,
        "distance_to_lower_edge": integration_result.distance_to_lower_edge,
        "overrun_flag": integration_result.overrun_flag,
        "consensus_direction": integration_result.consensus_direction,
        "consensus_confidence": integration_result.consensus_confidence,
        "consensus_label": integration_result.consensus_label,
        "pattern_visible": integration_result.pattern_visible,
        "pattern_reason_hidden": integration_result.pattern_reason_hidden,
    })
    return out
