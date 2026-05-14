
from __future__ import annotations

from typing import Dict, Any


def grid_decision(regime: Dict[str, Any], liquidity: Dict[str, Any], ml: Dict[str, Any], factor_breakdown: Dict[str, Any] | None = None) -> Dict[str, str]:
    sub = str((regime or {}).get('regime_label') or '')
    decision = {'long_grid':'HOLD','short_grid':'HOLD'}
    if sub == 'RANGE_CLEAN':
        decision = {'long_grid':'ENABLE','short_grid':'ENABLE'}
    elif sub == 'RANGE_DIRTY':
        decision = {'long_grid':'DEFENSIVE','short_grid':'DEFENSIVE'}
    elif sub == 'TREND_IMPULSE_FRESH':
        decision = {'long_grid':'DISABLE','short_grid':'DISABLE'}
    elif sub == 'TREND_EXHAUSTION':
        decision = {'long_grid':'DEFENSIVE','short_grid':'DEFENSIVE'}
    liq = str((liquidity or {}).get('liquidity_state') or 'NEUTRAL').upper()
    if liq == 'BUY_SIDE_SWEEP_REJECTED':
        decision['short_grid'] = 'PREPARE'; decision['long_grid'] = 'REDUCED'
    elif liq == 'SELL_SIDE_SWEEP_REJECTED':
        decision['long_grid'] = 'PREPARE'; decision['short_grid'] = 'REDUCED'
    factor_breakdown = factor_breakdown or {}
    dom = str(factor_breakdown.get('dominance') or 'NEUTRAL').upper()
    stage = str(factor_breakdown.get('edge_stage') or 'NO_EDGE').upper()
    if dom == 'LONG' and stage in {'PREPARE', 'BUILDING'}:
        decision['long_grid'] = 'PREPARE'
        if decision['short_grid'] == 'ENABLE':
            decision['short_grid'] = 'REDUCED'
    elif dom == 'SHORT' and stage in {'PREPARE', 'BUILDING'}:
        decision['short_grid'] = 'PREPARE'
        if decision['long_grid'] == 'ENABLE':
            decision['long_grid'] = 'REDUCED'
    return decision
