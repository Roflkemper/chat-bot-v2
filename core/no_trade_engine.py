from __future__ import annotations

from typing import Dict, List


def build_no_trade_context(regime_v2: Dict, liquidity_map: Dict, expectancy_ctx: Dict, volatility_ctx: Dict, orderflow_ctx: Dict) -> Dict:
    reasons: List[str] = []
    submode = regime_v2.get('regime_label', 'UNKNOWN')
    liquidity_state = liquidity_map.get('liquidity_state', 'NEUTRAL')
    exp_long = float(expectancy_ctx.get('exp_long', 0.0))
    exp_short = float(expectancy_ctx.get('exp_short', 0.0))
    impulse = volatility_ctx.get('impulse_strength', 'LOW')
    orderflow_bias = orderflow_ctx.get('bias', 'NEUTRAL')

    best_exp = max(exp_long, exp_short)
    if best_exp <= 0.05:
        reasons.append('expectancy too low')
    if submode == 'RANGE_DIRTY' and liquidity_state == 'NEUTRAL':
        reasons.append('dirty range without clear liquidity edge')
    if impulse == 'LOW' and liquidity_state == 'NEUTRAL':
        reasons.append('low impulse and no clear trigger')
    if orderflow_bias == 'NEUTRAL' and best_exp <= 0.12:
        reasons.append('orderflow neutral')

    is_no_trade = len(reasons) > 0
    level = 'LOW'
    if len(reasons) >= 2:
        level = 'MEDIUM'
    if len(reasons) >= 3:
        level = 'HIGH'
    return {'is_no_trade': is_no_trade, 'level': level, 'reasons': reasons, 'summary': ', '.join(reasons) if reasons else 'trade allowed'}
