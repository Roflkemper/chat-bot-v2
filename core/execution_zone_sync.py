from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Literal, Optional

Direction = Literal["LONG", "SHORT", "NEUTRAL"]
State = Literal["MID_RANGE", "SEARCH_TRIGGER", "PRE_ACTIVATION", "CONFIRMED", "OVERRUN", "WAIT_RECLAIM", "PAUSE"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class BlockMetrics:
    active_side: Direction
    in_active_block: bool
    block_depth_pct: float
    range_position_pct: float
    distance_to_upper: float
    distance_to_lower: float
    near_edge: bool

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ExecutionZoneState:
    state: State
    action_side: Direction
    confidence_label: str
    aggressiveness: str
    metrics: BlockMetrics
    trigger_text: str
    invalidation_text: str
    hedge_arm_text: str
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["metrics"] = self.metrics.to_dict()
        return payload


def choose_active_side(price: float, range_mid: float) -> Direction:
    if not range_mid:
        return "NEUTRAL"
    if price > range_mid:
        return "SHORT"
    if price < range_mid:
        return "LONG"
    return "NEUTRAL"


def compute_block_metrics(
    *,
    price: float,
    range_low: float,
    range_mid: float,
    range_high: float,
    zone_enter_buffer: float = 0.0,
    active_side: Optional[Direction] = None,
) -> BlockMetrics:
    active_side = active_side or choose_active_side(price, range_mid)

    width = max(range_high - range_low, 1e-9)
    range_position_pct = _clamp((price - range_low) / width * 100.0, 0.0, 100.0)
    distance_to_upper = max(range_high - price, 0.0)
    distance_to_lower = max(price - range_low, 0.0)
    near_edge = min(distance_to_upper, distance_to_lower) / max(price, 1e-9) < 0.005

    in_active_block = False
    block_depth_pct = 0.0

    if active_side == "SHORT" and range_high > range_mid:
        block_low = range_mid + zone_enter_buffer
        block_high = range_high
        in_active_block = price >= block_low and price <= block_high
        block_width = max(block_high - block_low, 1e-9)
        block_depth_pct = _clamp((price - block_low) / block_width * 100.0, 0.0, 100.0) if in_active_block else 0.0
    elif active_side == "LONG" and range_mid > range_low:
        block_low = range_low
        block_high = range_mid - zone_enter_buffer
        in_active_block = price >= block_low and price <= block_high
        block_width = max(block_high - block_low, 1e-9)
        block_depth_pct = _clamp((block_high - price) / block_width * 100.0, 0.0, 100.0) if in_active_block else 0.0

    return BlockMetrics(
        active_side=active_side,
        in_active_block=in_active_block,
        block_depth_pct=round(block_depth_pct, 2),
        range_position_pct=round(range_position_pct, 2),
        distance_to_upper=round(distance_to_upper, 2),
        distance_to_lower=round(distance_to_lower, 2),
        near_edge=near_edge,
    )


def normalize_consensus(action_side: Direction, consensus_direction: Direction, agreement: str) -> str:
    if action_side in {"LONG", "SHORT"}:
        if consensus_direction == action_side:
            if agreement in {"HIGH", "MID", "LOW"}:
                return f"{action_side} | {agreement}"
            return f"{action_side} | LOW"
        if consensus_direction in {"LONG", "SHORT"} and consensus_direction != action_side:
            return "CONFLICTED"
        return f"{action_side} | LOW"
    return "NEUTRAL"


def build_execution_zone_state(
    *,
    price: float,
    range_low: float,
    range_mid: float,
    range_high: float,
    stable_pattern_direction: Direction,
    consensus_direction: Direction,
    consensus_agreement: str,
    zone_enter_buffer: float = 0.0,
    hedge_buffer: float = 0.0,
) -> ExecutionZoneState:
    active_side = choose_active_side(price, range_mid)
    metrics = compute_block_metrics(
        price=price,
        range_low=range_low,
        range_mid=range_mid,
        range_high=range_high,
        zone_enter_buffer=zone_enter_buffer,
        active_side=active_side,
    )

    state: State = "MID_RANGE"
    confidence_label = "NONE"
    aggressiveness = "LOW"
    note = ""

    if metrics.in_active_block:
        state = "SEARCH_TRIGGER"
        confidence_label = "LOW"
        note = "price inside active block"
        if metrics.block_depth_pct > 85:
            state = "OVERRUN"
            confidence_label = "NONE"
            aggressiveness = "OFF"
            note = "deep penetration; breakout/overrun risk"
        elif metrics.block_depth_pct > 50:
            confidence_label = "LOW"
            aggressiveness = "REDUCED"
            note = "inside active block; penetration already deep"
    else:
        state = "MID_RANGE"
        confidence_label = "NONE"
        aggressiveness = "LOW"
        note = "outside active block"

    if stable_pattern_direction in {"LONG", "SHORT"} and stable_pattern_direction != active_side and state == "SEARCH_TRIGGER":
        confidence_label = "LOW"
        aggressiveness = "REDUCED"
        note += "; stable pattern conflicts with zone side"

    consensus_text = normalize_consensus(active_side if state != "MID_RANGE" else "NEUTRAL", consensus_direction, consensus_agreement)

    trigger_text = (
        "ложный вынос + быстрый возврат обратно в диапазон"
        if state in {"SEARCH_TRIGGER", "PRE_ACTIVATION"}
        else "ждать подход к активному блоку"
    )
    invalidation_text = (
        f"закрепление выше {range_high:.2f}" if active_side == "SHORT"
        else f"закрепление ниже {range_low:.2f}" if active_side == "LONG"
        else "нет активной стороны"
    )

    if active_side == "SHORT":
        hedge_arm = range_high + hedge_buffer
        hedge_arm_text = f"ARM UP: {hedge_arm:.2f}"
    elif active_side == "LONG":
        hedge_arm = range_low - hedge_buffer
        hedge_arm_text = f"ARM DOWN: {hedge_arm:.2f}"
    else:
        hedge_arm_text = "NOT ACTIVE"

    note = f"{note}; consensus={consensus_text}"

    return ExecutionZoneState(
        state=state,
        action_side=active_side if state != "MID_RANGE" else "NEUTRAL",
        confidence_label=confidence_label,
        aggressiveness=aggressiveness,
        metrics=metrics,
        trigger_text=trigger_text,
        invalidation_text=invalidation_text,
        hedge_arm_text=hedge_arm_text,
        note=note,
    )
