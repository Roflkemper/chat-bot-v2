from __future__ import annotations

from datetime import datetime
from typing import Mapping


def build_execution_snapshot(payload: Mapping[str, float]):
    price = float(payload.get('price', 0.0))
    range_low = float(payload.get('range_low', 0.0))
    range_mid = float(payload.get('range_mid', (range_low + float(payload.get('range_high', 0.0))) / 2.0))
    range_high = float(payload.get('range_high', 0.0))

    if price > range_mid:
        side = 'SHORT'
        active_block = 'SHORT'
        block_low = float(payload.get('upper_block_low', range_mid))
        block_high = float(payload.get('upper_block_high', range_high))
    else:
        side = 'LONG'
        active_block = 'LONG'
        block_low = float(payload.get('lower_block_low', range_low))
        block_high = float(payload.get('lower_block_high', range_mid))

    block_size = max(block_high - block_low, 1e-9)
    range_size = max(range_high - range_low, 1e-9)
    block_depth_pct = ((price - block_low) / block_size) * 100.0
    range_position_pct = ((price - range_low) / range_size) * 100.0

    if block_depth_pct < 15:
        depth_label = 'EARLY'
    elif block_depth_pct < 50:
        depth_label = 'WORK'
    elif block_depth_pct < 85:
        depth_label = 'RISK'
    else:
        depth_label = 'DEEP'

    state = 'OVERRUN' if block_depth_pct >= 85 else 'SEARCH_TRIGGER'
    pattern_avg_move_pct = float(payload.get('pattern_avg_move_pct', 0.0) or 0.0)
    pattern_direction = str(payload.get('pattern_direction', 'NEUTRAL') or 'NEUTRAL')

    return {
        'timestamp': datetime.now().strftime('%H:%M'),
        'tf': '1h',
        'price': round(price, 2),
        'state': state,
        'side': side,
        'active_block': active_block,
        'block_depth_pct': round(block_depth_pct, 2),
        'depth_label': depth_label,
        'range_position_pct': round(range_position_pct, 2),
        'consensus_direction': side,
        'consensus_confidence': 'LOW',
        'consensus_votes': '1/3',
        'pattern_visible': abs(pattern_avg_move_pct) >= 0.2 and pattern_direction in {'LONG', 'SHORT'},
    }
