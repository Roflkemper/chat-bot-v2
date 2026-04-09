from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


PATTERN_MOVE_THRESHOLD_PCT = 0.20


@dataclass
class ExecutionSnapshot:
    symbol: str = 'BTC'
    timeframe: str = '1h'
    price: float = 0.0
    structure: str = 'CHOP'
    position: str = 'MID_RANGE'
    side: str = 'NONE'
    state: str = 'MID_RANGE'
    active_block: str = 'NONE'
    block_depth_pct: float = 0.0
    distance_to_active_edge: Optional[float] = None
    distance_to_upper_edge: Optional[float] = None
    distance_to_lower_edge: Optional[float] = None
    consensus_direction: str = 'NONE'
    consensus_confidence: str = 'NONE'
    pattern_visible: bool = False
    pattern_label: Optional[str] = None
    pattern_avg_move_pct: Optional[float] = None
    trigger: str = ''
    invalidation: str = ''
    hedge_arm_up: Optional[float] = None
    hedge_arm_down: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _inside(price: float, low: float, high: float) -> bool:
    return low <= price <= high


def _depth_for_side(price: float, low: float, high: float, side: str) -> float:
    width = max(high - low, 1e-9)
    if side == 'SHORT':
        depth = (price - low) / width * 100.0
    elif side == 'LONG':
        depth = (high - price) / width * 100.0
    else:
        return 0.0
    return _clamp(depth, 0.0, 100.0)


def build_execution_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    symbol = payload.get('symbol', 'BTC')
    timeframe = payload.get('timeframe', '1h')
    price = float(payload['price'])
    range_low = float(payload['range_low'])
    range_mid = float(payload['range_mid'])
    range_high = float(payload['range_high'])
    upper_low = float(payload.get('upper_block_low', range_mid))
    upper_high = float(payload.get('upper_block_high', range_high))
    lower_low = float(payload.get('lower_block_low', range_low))
    lower_high = float(payload.get('lower_block_high', range_mid))
    side_hint = payload.get('side_hint')
    pattern_avg_move_pct = payload.get('pattern_avg_move_pct')
    pattern_direction = payload.get('pattern_direction')
    hedge_buffer = float(payload.get('hedge_buffer', 0.0))

    if price > range_mid:
        side = 'SHORT'
        active_block = 'SHORT_BLOCK'
        block_low, block_high = upper_low, upper_high
    elif price < range_mid:
        side = 'LONG'
        active_block = 'LONG_BLOCK'
        block_low, block_high = lower_low, lower_high
    else:
        side = side_hint or 'NONE'
        active_block = 'NONE'
        block_low, block_high = range_mid, range_mid

    in_active_block = active_block != 'NONE' and _inside(price, block_low, block_high)
    depth = _depth_for_side(price, block_low, block_high, side) if in_active_block else 0.0

    if in_active_block:
        if depth >= 85.0:
            state = 'OVERRUN'
        else:
            state = 'SEARCH_TRIGGER'
    else:
        state = 'MID_RANGE'

    distance_to_upper = max(range_high - price, 0.0)
    distance_to_lower = max(price - range_low, 0.0)
    if side == 'SHORT':
        distance_to_active = distance_to_upper
    elif side == 'LONG':
        distance_to_active = max(price - range_low, 0.0)
    else:
        distance_to_active = None

    pattern_visible = (
        pattern_avg_move_pct is not None and abs(float(pattern_avg_move_pct)) >= PATTERN_MOVE_THRESHOLD_PCT
    )

    if side == 'NONE':
        consensus_direction = 'NONE'
        consensus_confidence = 'NONE'
    elif state == 'OVERRUN':
        consensus_direction = side
        consensus_confidence = 'LOW'
    elif state == 'SEARCH_TRIGGER':
        consensus_direction = side
        consensus_confidence = 'LOW'
    else:
        consensus_direction = side
        consensus_confidence = 'MID'

    snap = ExecutionSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        price=price,
        structure=payload.get('structure', 'CHOP'),
        position=payload.get('position', 'MID_RANGE'),
        side=side,
        state=state,
        active_block=active_block,
        block_depth_pct=depth,
        distance_to_active_edge=distance_to_active,
        distance_to_upper_edge=distance_to_upper,
        distance_to_lower_edge=distance_to_lower,
        consensus_direction=consensus_direction,
        consensus_confidence=consensus_confidence,
        pattern_visible=pattern_visible,
        pattern_label=pattern_direction if pattern_visible else None,
        pattern_avg_move_pct=pattern_avg_move_pct if pattern_visible else None,
        trigger=payload.get('trigger', 'касание края + ложный вынос + возврат'),
        invalidation=payload.get('invalidation', f'закрепление вне диапазона {range_low:.2f}-{range_high:.2f}'),
        hedge_arm_up=range_high + hedge_buffer if hedge_buffer else None,
        hedge_arm_down=range_low - hedge_buffer if hedge_buffer else None,
    )
    return snap.to_dict()
