from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Literal

Side = Literal["LONG", "SHORT", "NONE"]


class ExecutionState(str, Enum):
    MID_RANGE = "MID_RANGE"
    SEARCH_TRIGGER = "SEARCH_TRIGGER"
    PRE_ACTIVATION = "PRE_ACTIVATION"
    CONFIRMED = "CONFIRMED"
    OVERRUN = "OVERRUN"


@dataclass(frozen=True)
class RangeLevels:
    low: float
    mid: float
    high: float


@dataclass(frozen=True)
class StateMachineConfig:
    zone_enter_buffer: float = 80.0
    zone_exit_buffer: float = 150.0
    pre_activation_pct: float = 0.15
    overrun_pct: float = 0.85
    risk_pct: float = 0.50
    near_edge_pct: float = 0.005  # 0.5%
    distance_alert_usd: float = 500.0


@dataclass
class StateMachineResult:
    active_side: Side
    active_block_low: Optional[float]
    active_block_high: Optional[float]
    state: ExecutionState
    depth_pct: float
    distance_to_upper_edge: float
    distance_to_lower_edge: float
    distance_to_active_edge: Optional[float]
    near_edge: bool
    confidence_penalty: int
    entry_blocked: bool
    risk_label: str



def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))



def determine_active_side(price: float, levels: RangeLevels) -> Side:
    if price > levels.mid:
        return "SHORT"
    if price < levels.mid:
        return "LONG"
    return "NONE"



def _block_for_side(levels: RangeLevels, side: Side) -> tuple[Optional[float], Optional[float]]:
    if side == "SHORT":
        return levels.mid, levels.high
    if side == "LONG":
        return levels.low, levels.mid
    return None, None



def _inside_active_block(price: float, block_low: float, block_high: float, enter_buffer: float, exit_buffer: float, previous_state: Optional[ExecutionState]) -> bool:
    # asymmetric hysteresis: easier to enter than to exit
    if previous_state in {ExecutionState.SEARCH_TRIGGER, ExecutionState.PRE_ACTIVATION, ExecutionState.CONFIRMED}:
        return (block_low - enter_buffer) <= price <= (block_high + exit_buffer)
    return (block_low - enter_buffer) <= price <= (block_high + enter_buffer)



def _depth_pct(price: float, block_low: float, block_high: float, side: Side) -> float:
    width = max(block_high - block_low, 1e-9)
    if side == "SHORT":
        depth = (price - block_low) / width
    elif side == "LONG":
        depth = (block_high - price) / width
    else:
        return 0.0
    return round(_clamp(depth, 0.0, 1.2) * 100.0, 2)



def _distance_to_active_edge(price: float, block_low: float, block_high: float, side: Side) -> float:
    return max(0.0, (block_high - price) if side == "SHORT" else (price - block_low))



def evaluate_state(
    price: float,
    levels: RangeLevels,
    *,
    early_reaction: bool = False,
    confirm_count_2of3: int = 0,
    previous_state: Optional[ExecutionState] = None,
    config: Optional[StateMachineConfig] = None,
) -> StateMachineResult:
    cfg = config or StateMachineConfig()
    active_side = determine_active_side(price, levels)
    block_low, block_high = _block_for_side(levels, active_side)

    distance_to_upper_edge = round(max(0.0, levels.high - price), 2)
    distance_to_lower_edge = round(max(0.0, price - levels.low), 2)

    if active_side == "NONE" or block_low is None or block_high is None:
        return StateMachineResult(
            active_side="NONE",
            active_block_low=None,
            active_block_high=None,
            state=ExecutionState.MID_RANGE,
            depth_pct=0.0,
            distance_to_upper_edge=distance_to_upper_edge,
            distance_to_lower_edge=distance_to_lower_edge,
            distance_to_active_edge=None,
            near_edge=False,
            confidence_penalty=0,
            entry_blocked=False,
            risk_label="MID_RANGE",
        )

    inside = _inside_active_block(price, block_low, block_high, cfg.zone_enter_buffer, cfg.zone_exit_buffer, previous_state)
    depth_pct = _depth_pct(price, block_low, block_high, active_side)
    distance_to_active_edge = round(_distance_to_active_edge(price, block_low, block_high, active_side), 2)
    width = max(block_high - block_low, 1e-9)
    near_edge = (distance_to_active_edge / width) <= cfg.near_edge_pct or distance_to_active_edge <= cfg.distance_alert_usd

    if not inside:
        state = ExecutionState.MID_RANGE
    else:
        if depth_pct >= cfg.overrun_pct * 100.0:
            state = ExecutionState.OVERRUN
        elif confirm_count_2of3 >= 2:
            state = ExecutionState.CONFIRMED
        elif early_reaction or depth_pct >= cfg.pre_activation_pct * 100.0:
            state = ExecutionState.PRE_ACTIVATION
        else:
            state = ExecutionState.SEARCH_TRIGGER

    confidence_penalty = 0
    entry_blocked = False
    risk_label = "EARLY"

    if depth_pct >= cfg.overrun_pct * 100.0:
        confidence_penalty = 2
        entry_blocked = True
        risk_label = "OVERRUN"
    elif depth_pct >= cfg.risk_pct * 100.0:
        confidence_penalty = 1
        risk_label = "RISK_OF_THROUGH"
    elif depth_pct >= cfg.pre_activation_pct * 100.0:
        risk_label = "WORKING_ZONE"

    return StateMachineResult(
        active_side=active_side,
        active_block_low=block_low,
        active_block_high=block_high,
        state=state,
        depth_pct=depth_pct,
        distance_to_upper_edge=distance_to_upper_edge,
        distance_to_lower_edge=distance_to_lower_edge,
        distance_to_active_edge=distance_to_active_edge,
        near_edge=near_edge,
        confidence_penalty=confidence_penalty,
        entry_blocked=entry_blocked,
        risk_label=risk_label,
    )
