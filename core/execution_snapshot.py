from __future__ import annotations

from typing import Any, Dict

from core.pipeline_integration_fix import build_pipeline_fields


def build_execution_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    price = float(payload['price'])
    range_low = float(payload['range_low'])
    range_mid = float(payload['range_mid'])
    range_high = float(payload['range_high'])

    if price >= range_mid:
        side = 'SHORT'
        active_block_low = float(payload.get('upper_block_low', range_mid))
        active_block_high = float(payload.get('upper_block_high', range_high))
        distance_to_active_edge = max(0.0, active_block_high - price)
    else:
        side = 'LONG'
        active_block_low = float(payload.get('lower_block_low', range_low))
        active_block_high = float(payload.get('lower_block_high', range_mid))
        distance_to_active_edge = max(0.0, price - active_block_low)

    block_size = max(active_block_high - active_block_low, 1e-9)
    block_depth_pct = ((price - active_block_low) / block_size) * 100.0
    overrun_flag = block_depth_pct >= 97.0 or price > range_high or price < range_low

    state = 'OVERRUN' if overrun_flag else 'MID_RANGE'
    result = build_pipeline_fields(
        price=price,
        existing_state=state,
        execution_side=side,
        state_machine_snapshot={
            'state': state,
            'active_block_side': side,
            'active_block_low': active_block_low,
            'active_block_high': active_block_high,
            'block_depth_pct': block_depth_pct,
            'distance_to_active_edge': distance_to_active_edge,
            'distance_to_upper_edge': max(0.0, range_high - price),
            'distance_to_lower_edge': max(0.0, price - range_low),
            'overrun_flag': overrun_flag,
        },
        pattern_snapshot={
            'avg_move_pct': payload.get('pattern_avg_move_pct'),
            'sample_count': payload.get('pattern_sample_count', 12),
        },
        consensus_snapshot={
            'direction': payload.get('pattern_direction'),
            'confidence': payload.get('consensus_confidence'),
        },
    )
    out = result.to_dict()
    out['side'] = side
    return out
