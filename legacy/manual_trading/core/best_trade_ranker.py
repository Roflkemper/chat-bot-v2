from __future__ import annotations

from typing import Dict, List


def _risk_from_score(score: float) -> str:
    if score >= 78: return 'LOW'
    if score >= 58: return 'MEDIUM'
    return 'HIGH'


def _mk_play(play_id: str, side: str, score: float, reasons: List[str]) -> Dict:
    return {'play_id': play_id, 'side': side, 'score': round(score,1), 'risk': _risk_from_score(score), 'why': reasons[:4]}


def rank_best_plays(regime_v2: Dict, liquidity_map: Dict, derivatives_ctx: Dict, ml_v2: Dict, pattern_ctx: Dict, personal_stats: Dict, grid_cmd: Dict, micro_ctx: Dict, adaptive_weights: Dict, expectancy_ctx: Dict = None, volatility_ctx: Dict = None, orderflow_ctx: Dict = None, liquidation_ctx: Dict = None, no_trade_ctx: Dict = None) -> Dict:
    expectancy_ctx = expectancy_ctx or {}
    volatility_ctx = volatility_ctx or {}
    orderflow_ctx = orderflow_ctx or {}
    liquidation_ctx = liquidation_ctx or {}
    no_trade_ctx = no_trade_ctx or {}
    submode = regime_v2.get('regime_label', 'UNKNOWN')
    liquidity_state = liquidity_map.get('liquidity_state', 'NEUTRAL')
    price_oi_regime = derivatives_ctx.get('price_oi_regime', 'NEUTRAL')
    ml_prob = float(ml_v2.get('probability', 0.5))
    mean_rev_bias = float(regime_v2.get('mean_reversion_bias', 50.0))
    personal_edge = float(personal_stats.get('avg_rr', 0.0))
    long_grid = grid_cmd.get('long_grid', 'HOLD')
    short_grid = grid_cmd.get('short_grid', 'HOLD')
    pattern_long = float(pattern_ctx.get('long_prob', 50.0))
    pattern_short = float(pattern_ctx.get('short_prob', 50.0))
    exp_long = float(expectancy_ctx.get('exp_long', 0.0))
    exp_short = float(expectancy_ctx.get('exp_short', 0.0))
    impulse_strength = volatility_ctx.get('impulse_strength', 'LOW')
    ct_risk = volatility_ctx.get('countertrend_risk', 'LOW')
    orderflow_bias = orderflow_ctx.get('bias', 'NEUTRAL')
    orderflow_conf = float(orderflow_ctx.get('confidence', 50.0))
    liq_magnet = liquidation_ctx.get('magnet_side', 'NEUTRAL')
    is_no_trade = bool(no_trade_ctx.get('is_no_trade', False))
    trend_long = trend_short = ct_long = ct_short = grid_long = grid_short = 50.0
    wait_score = 45.0
    rtl=[]; rts=[]; rcl=[]; rcs=[]; rgl=[]; rgs=[]; rw=['нет достаточно чистого edge']
    if 'TREND_IMPULSE_FRESH' in submode:
        trend_long += 22; trend_short += 22; rtl.append('fresh impulse regime'); rts.append('fresh impulse regime')
    if 'TREND_EXHAUSTION' in submode:
        ct_long += 16; ct_short += 16; rcl.append('trend exhaustion'); rcs.append('trend exhaustion')
    if 'RANGE_CLEAN' in submode:
        grid_long += 18; grid_short += 18; rgl.append('clean range'); rgs.append('clean range')
    if 'RANGE_DIRTY' in submode:
        grid_long += 8; grid_short += 8; wait_score += 6
    if liquidity_state == 'BUY_SIDE_SWEEP_REJECTED':
        ct_short += 18; grid_short += 8; trend_long -= 12; rcs.append('buy-side sweep rejected')
    if liquidity_state == 'SELL_SIDE_SWEEP_REJECTED':
        ct_long += 18; grid_long += 8; trend_short -= 12; rcl.append('sell-side sweep rejected')
    if price_oi_regime == 'BULLISH_BUILDUP': trend_long += 10; rtl.append('bullish price/OI buildup')
    elif price_oi_regime == 'BEARISH_BUILDUP': trend_short += 10; rts.append('bearish price/OI buildup')
    trend_long += (ml_prob - 0.5) * 18
    trend_short += ((1.0 - ml_prob) - 0.5) * 18
    trend_long += (pattern_long - 50.0) * 0.16
    trend_short += (pattern_short - 50.0) * 0.16
    ct_long += (mean_rev_bias - 50.0) * 0.18
    ct_short += (mean_rev_bias - 50.0) * 0.18
    trend_long += exp_long * 18; ct_long += exp_long * 10; trend_short += exp_short * 18; ct_short += exp_short * 10
    if impulse_strength == 'HIGH': trend_long += 6; trend_short += 6; wait_score += 3
    if ct_risk == 'HIGH': ct_long -= 10; ct_short -= 10; rw.append('high countertrend risk')
    if orderflow_bias == 'LONG': trend_long += ((orderflow_conf - 50.0) * 0.20); ct_long += ((orderflow_conf - 50.0) * 0.08); rtl.append('orderflow confirms long')
    elif orderflow_bias == 'SHORT': trend_short += ((orderflow_conf - 50.0) * 0.20); ct_short += ((orderflow_conf - 50.0) * 0.08); rts.append('orderflow confirms short')
    if liq_magnet == 'UP': trend_long += 6; rtl.append('upper liquidation magnet')
    elif liq_magnet == 'DOWN': trend_short += 6; rts.append('lower liquidation magnet')
    trend_long += personal_edge * 4.0; trend_short += personal_edge * 4.0; ct_long += personal_edge * 4.0; ct_short += personal_edge * 4.0
    if long_grid == 'ENABLE': grid_long += 20; rgl.append('long grid enabled')
    elif long_grid == 'DEFENSIVE': grid_long += 10; rgl.append('long grid defensive')
    elif long_grid == 'DISABLE': grid_long -= 18
    if short_grid == 'ENABLE': grid_short += 20; rgs.append('short grid enabled')
    elif short_grid == 'DEFENSIVE': grid_short += 10; rgs.append('short grid defensive')
    elif short_grid == 'DISABLE': grid_short -= 18
    if is_no_trade: trend_long -= 20; trend_short -= 20; ct_long -= 20; ct_short -= 20; grid_long -= 18; grid_short -= 18; wait_score += 22
    plays = [
        _mk_play('trend_long','LONG',trend_long,rtl), _mk_play('trend_short','SHORT',trend_short,rts),
        _mk_play('countertrend_long','LONG',ct_long,rcl), _mk_play('countertrend_short','SHORT',ct_short,rcs),
        _mk_play('long_grid','LONG',grid_long,rgl), _mk_play('short_grid','SHORT',grid_short,rgs), _mk_play('wait','FLAT',wait_score,rw)]
    plays = sorted(plays, key=lambda x: x['score'], reverse=True)
    avoid = [p for p in plays if p['score'] < 45]
    return {'top_plays': plays[:3], 'avoid_plays': avoid[:3], 'best_play': plays[0]['play_id'] if plays else 'wait', 'best_side': plays[0]['side'] if plays else 'FLAT', 'best_score': plays[0]['score'] if plays else 0.0}
