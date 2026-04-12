from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class OrderflowSnapshot:
    aggressive_buy_volume: float = 0.0
    aggressive_sell_volume: float = 0.0
    delta_volume: float = 0.0
    cumulative_delta: float = 0.0
    buy_imbalance: float = 0.5
    sell_imbalance: float = 0.5
    absorption_at_high: bool = False
    absorption_at_low: bool = False
    exhaustion_up: bool = False
    exhaustion_down: bool = False


def build_orderflow_context(snapshot: Optional[OrderflowSnapshot] = None) -> Dict:
    snapshot = snapshot or OrderflowSnapshot()
    total_aggr = snapshot.aggressive_buy_volume + snapshot.aggressive_sell_volume
    if total_aggr > 0:
        buy_ratio = snapshot.aggressive_buy_volume / total_aggr
        sell_ratio = snapshot.aggressive_sell_volume / total_aggr
    else:
        buy_ratio = 0.5
        sell_ratio = 0.5

    bias = 'NEUTRAL'
    if buy_ratio >= 0.58 and snapshot.delta_volume > 0:
        bias = 'LONG'
    elif sell_ratio >= 0.58 and snapshot.delta_volume < 0:
        bias = 'SHORT'

    exhaustion = 'NONE'
    if snapshot.exhaustion_up:
        exhaustion = 'UP'
    elif snapshot.exhaustion_down:
        exhaustion = 'DOWN'

    confidence = 50.0 + abs(buy_ratio - sell_ratio) * 70.0
    confidence = max(0.0, min(100.0, confidence))

    summary = (
        f"orderflow_bias={bias}, buy_ratio={buy_ratio:.2f}, "
        f"delta={snapshot.delta_volume:.2f}, exhaustion={exhaustion}"
    )

    return {
        'bias': bias,
        'buy_ratio': float(buy_ratio),
        'sell_ratio': float(sell_ratio),
        'delta_volume': float(snapshot.delta_volume),
        'cumulative_delta': float(snapshot.cumulative_delta),
        'buy_imbalance': float(snapshot.buy_imbalance),
        'sell_imbalance': float(snapshot.sell_imbalance),
        'absorption_at_high': bool(snapshot.absorption_at_high),
        'absorption_at_low': bool(snapshot.absorption_at_low),
        'exhaustion': exhaustion,
        'confidence': float(confidence),
        'summary': summary,
    }
