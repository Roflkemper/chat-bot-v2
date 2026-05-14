from __future__ import annotations

from typing import Any, Dict


def _depth_label(depth_pct: float) -> str:
    if depth_pct < 15:
        return "EARLY"
    if depth_pct < 50:
        return "WORK"
    if depth_pct < 85:
        return "RISK"
    return "DEEP"


def build_execution_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    price = float(payload.get('price', 0.0))
    range_low = float(payload.get('range_low', 0.0))
    range_mid = float(payload.get('range_mid', 0.0))
    range_high = float(payload.get('range_high', 0.0))

    if price >= range_mid:
        side = active_block = 'SHORT'
        block_low = float(payload.get('upper_block_low', range_mid))
        block_high = float(payload.get('upper_block_high', range_high))
        consensus_direction = 'SHORT'
    else:
        side = active_block = 'LONG'
        block_low = float(payload.get('lower_block_low', range_low))
        block_high = float(payload.get('lower_block_high', range_mid))
        consensus_direction = 'LONG'

    block_size = max(block_high - block_low, 1e-9)
    block_depth_pct = ((price - block_low) / block_size) * 100.0
    overrun_threshold = 97.0
    state = 'OVERRUN' if block_depth_pct >= overrun_threshold else 'SEARCH_TRIGGER'

    pattern_avg_move_pct = abs(float(payload.get('pattern_avg_move_pct', 0.0) or 0.0))
    pattern_direction = str(payload.get('pattern_direction') or 'NEUTRAL').upper()
    pattern_visible = bool(pattern_avg_move_pct >= 0.25 and pattern_direction in {'LONG', 'SHORT'})

    return {
        'price': round(price, 2),
        'range_low': round(range_low, 2),
        'range_mid': round(range_mid, 2),
        'range_high': round(range_high, 2),
        'active_block': active_block,
        'side': side,
        'block_low': round(block_low, 2),
        'block_high': round(block_high, 2),
        'block_depth_pct': round(block_depth_pct, 2),
        'depth_label': _depth_label(block_depth_pct),
        'state': state,
        'consensus_direction': consensus_direction,
        'consensus_confidence': 'LOW',
        'pattern_visible': pattern_visible,
    }


execution_snapshot = build_execution_snapshot
