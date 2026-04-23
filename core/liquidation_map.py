
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LiquidationSnapshot:
    nearest_long_liq_price: float = 0.0
    nearest_short_liq_price: float = 0.0
    current_price: float = 0.0
    long_cluster_strength: float = 0.0
    short_cluster_strength: float = 0.0


def build_liquidation_context(snapshot: Optional[LiquidationSnapshot] = None) -> Dict:
    snapshot = snapshot or LiquidationSnapshot()

    cp = float(snapshot.current_price or 0.0)
    long_liq = float(snapshot.nearest_long_liq_price or 0.0)
    short_liq = float(snapshot.nearest_short_liq_price or 0.0)

    dist_to_long = abs(cp - long_liq) / cp * 100.0 if cp > 0 and long_liq > 0 else 999.0
    dist_to_short = abs(cp - short_liq) / cp * 100.0 if cp > 0 and short_liq > 0 else 999.0

    if dist_to_short < dist_to_long:
        magnet_side = 'UP'
    elif dist_to_long < dist_to_short:
        magnet_side = 'DOWN'
    else:
        magnet_side = 'NEUTRAL'

    nearest_dist = min(dist_to_long, dist_to_short)
    cascade_risk = 'LOW'
    if nearest_dist < 0.8:
        cascade_risk = 'MEDIUM'
    if nearest_dist < 0.4:
        cascade_risk = 'HIGH'

    up_cluster = float(snapshot.short_cluster_strength or 0.0)
    down_cluster = float(snapshot.long_cluster_strength or 0.0)
    if magnet_side == 'UP' and dist_to_short < 0.35:
        liquidity_state = 'UP_MAGNET'
    elif magnet_side == 'DOWN' and dist_to_long < 0.35:
        liquidity_state = 'DOWN_MAGNET'
    else:
        liquidity_state = 'NEUTRAL'

    if short_liq > 0 and cp >= short_liq * 0.998 and up_cluster >= down_cluster:
        liquidity_state = 'BUY_SIDE_SWEEP_REJECTED' if dist_to_short < 0.18 else 'UP_MAGNET'
    if long_liq > 0 and cp <= long_liq * 1.002 and down_cluster >= up_cluster:
        liquidity_state = 'SELL_SIDE_SWEEP_REJECTED' if dist_to_long < 0.18 else 'DOWN_MAGNET'

    summary = (
        f"магнит={magnet_side}, верхняя ликвидность {dist_to_short:.2f}%, "
        f"нижняя ликвидность {dist_to_long:.2f}%, cascade_risk={cascade_risk}"
    )

    return {
        'dist_to_long_liq_pct': float(dist_to_long),
        'dist_to_short_liq_pct': float(dist_to_short),
        'long_cluster_strength': down_cluster,
        'short_cluster_strength': up_cluster,
        'magnet_side': magnet_side,
        'cascade_risk': cascade_risk,
        'liquidity_state': liquidity_state,
        'upper_cluster_price': short_liq,
        'lower_cluster_price': long_liq,
        'summary': summary,
    }
