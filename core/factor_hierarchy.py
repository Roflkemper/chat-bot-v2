
from __future__ import annotations

from typing import Dict, Any, List

BASE_WEIGHTS = {
    'regime': 0.28,
    'liquidity': 0.20,
    'micro': 0.14,
    'impulse': 0.12,
    'range_position': 0.10,
    'pattern': 0.08,
    'orderflow': 0.05,
    'derivatives': 0.03,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _position_scores(range_position: str) -> Dict[str, float]:
    pos = str(range_position or '').lower()
    if any(x in pos for x in ('верх', 'high', 'upper')):
        return {'long': 35.0, 'short': 65.0, 'label': 'upper-edge'}
    if any(x in pos for x in ('ниж', 'low', 'lower')):
        return {'long': 65.0, 'short': 35.0, 'label': 'lower-edge'}
    if any(x in pos for x in ('серед', 'mid', 'middle')):
        return {'long': 48.0, 'short': 48.0, 'label': 'mid'}
    return {'long': 50.0, 'short': 50.0, 'label': 'unknown'}


def _regime_scores(regime_label: str, mean_reversion_bias: float, continuation_bias: float) -> Dict[str, float]:
    label = str(regime_label or '').upper()
    mr = _clamp(mean_reversion_bias)
    cont = _clamp(continuation_bias)
    if 'TREND_IMPULSE_FRESH' in label:
        return {'long': cont, 'short': cont, 'state': 'trend-impulse'}
    if 'TREND_EXHAUSTION' in label:
        return {'long': mr, 'short': mr, 'state': 'trend-exhaustion'}
    if 'RANGE' in label:
        return {'long': mr * 0.92 + 4, 'short': mr * 0.92 + 4, 'state': 'range'}
    return {'long': 50.0, 'short': 50.0, 'state': 'unknown'}


def _liquidity_scores(liquidity_state: str) -> Dict[str, float]:
    state = str(liquidity_state or 'NEUTRAL').upper()
    if state == 'BUY_SIDE_SWEEP_REJECTED':
        return {'long': 32.0, 'short': 68.0}
    if state == 'SELL_SIDE_SWEEP_REJECTED':
        return {'long': 68.0, 'short': 32.0}
    if state in {'UP_MAGNET', 'BUY_SIDE_PRESSURE'}:
        return {'long': 58.0, 'short': 42.0}
    if state in {'DOWN_MAGNET', 'SELL_SIDE_PRESSURE'}:
        return {'long': 42.0, 'short': 58.0}
    return {'long': 50.0, 'short': 50.0}


def _micro_scores(micro_bias: str, confidence: float) -> Dict[str, float]:
    bias = str(micro_bias or 'NEUTRAL').upper()
    conf = _clamp(confidence)
    strength = (conf - 50.0) * 0.9
    if bias == 'LONG':
        return {'long': 50.0 + strength, 'short': 50.0 - strength}
    if bias == 'SHORT':
        return {'long': 50.0 - strength, 'short': 50.0 + strength}
    return {'long': 50.0, 'short': 50.0}


def _pattern_scores(long_prob: float, short_prob: float) -> Dict[str, float]:
    return {'long': _clamp(long_prob), 'short': _clamp(short_prob)}


def _impulse_scores(direction: str, continuation_prob: float) -> Dict[str, float]:
    d = str(direction or 'NEUTRAL').upper()
    p = _clamp(continuation_prob)
    if d == 'UP':
        return {'long': p, 'short': 100.0 - p}
    if d == 'DOWN':
        return {'long': 100.0 - p, 'short': p}
    return {'long': 50.0, 'short': 50.0}


def _orderflow_scores(bias: str, confidence: float) -> Dict[str, float]:
    b = str(bias or 'NEUTRAL').upper()
    conf = _clamp(confidence)
    if b == 'LONG':
        return {'long': conf, 'short': 100.0 - conf}
    if b == 'SHORT':
        return {'long': 100.0 - conf, 'short': conf}
    return {'long': 50.0, 'short': 50.0}


def _derivatives_scores(price_oi_regime: str, magnet_side: str) -> Dict[str, float]:
    score = {'long': 50.0, 'short': 50.0}
    poi = str(price_oi_regime or 'NEUTRAL').upper()
    if poi == 'BULLISH_BUILDUP':
        score['long'] += 10.0; score['short'] -= 10.0
    elif poi == 'BEARISH_BUILDUP':
        score['long'] -= 10.0; score['short'] += 10.0
    mag = str(magnet_side or 'NEUTRAL').upper()
    if mag == 'UP':
        score['long'] += 5.0; score['short'] -= 5.0
    elif mag == 'DOWN':
        score['long'] -= 5.0; score['short'] += 5.0
    return {'long': _clamp(score['long']), 'short': _clamp(score['short'])}


def build_factor_breakdown(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    regime = payload.get('regime_v2') or {}
    liquidity = payload.get('liquidity_map') or {}
    micro = payload.get('microstructure') or {}
    pattern = payload.get('pattern_memory_v2') or {}
    vol = payload.get('volatility_impulse') or {}
    orderflow = payload.get('orderflow_context') or {}
    liq_ctx = payload.get('liquidation_context') or {}
    deriv = payload.get('derivatives_context') or {}

    weights = dict(BASE_WEIGHTS)
    adaptive = payload.get('adaptive_weights') or {}
    weights['regime'] *= float(adaptive.get('regime', 1.0) or 1.0)
    weights['liquidity'] *= float(adaptive.get('liquidity', 1.0) or 1.0)
    weights['pattern'] *= float(adaptive.get('pattern', 1.0) or 1.0)
    weights['micro'] *= float(adaptive.get('micro', 1.0) or 1.0)
    weights['derivatives'] *= float(adaptive.get('derivatives', 1.0) or 1.0)

    components = {
        'regime': _regime_scores(regime.get('regime_label'), regime.get('mean_reversion_bias', 50.0), regime.get('continuation_bias', 50.0)),
        'liquidity': _liquidity_scores(liquidity.get('liquidity_state')),
        'micro': _micro_scores(micro.get('micro_bias'), micro.get('confidence', 50.0)),
        'impulse': _impulse_scores(vol.get('impulse_direction', 'NEUTRAL'), vol.get('continuation_probability', 50.0)),
        'range_position': _position_scores(payload.get('range_position') or decision.get('range_position')),
        'pattern': _pattern_scores(pattern.get('long_prob', 50.0), pattern.get('short_prob', 50.0)),
        'orderflow': _orderflow_scores(orderflow.get('bias'), orderflow.get('confidence', 50.0)),
        'derivatives': _derivatives_scores(deriv.get('price_oi_regime'), liq_ctx.get('magnet_side')),
    }

    total_weight = sum(weights.values()) or 1.0
    long_total = 0.0
    short_total = 0.0
    breakdown_long: List[Dict[str, Any]] = []
    breakdown_short: List[Dict[str, Any]] = []
    for name, vals in components.items():
        w = weights.get(name, 0.0)
        ls = _clamp(vals.get('long', 50.0))
        ss = _clamp(vals.get('short', 50.0))
        long_total += ls * w
        short_total += ss * w
        breakdown_long.append({'factor': name, 'score': round(ls, 1), 'weight': round(w, 3)})
        breakdown_short.append({'factor': name, 'score': round(ss, 1), 'weight': round(w, 3)})
    long_total = long_total / total_weight
    short_total = short_total / total_weight
    diff = short_total - long_total
    if abs(diff) < 4.0:
        dominance = 'NEUTRAL'
        edge_stage = 'NO_EDGE' if max(long_total, short_total) < 54 else 'BUILDING'
    else:
        dominance = 'SHORT' if diff > 0 else 'LONG'
        absd = abs(diff)
        edge_stage = 'PREPARE' if absd < 7 else 'BUILDING' if absd < 12 else 'READY'
    return {
        'long_total': round(_clamp(long_total), 1),
        'short_total': round(_clamp(short_total), 1),
        'dominance': dominance,
        'dominance_diff': round(diff, 1),
        'edge_stage': edge_stage,
        'weights': {k: round(v, 3) for k, v in weights.items()},
        'long_breakdown': sorted(breakdown_long, key=lambda x: x['score'], reverse=True),
        'short_breakdown': sorted(breakdown_short, key=lambda x: x['score'], reverse=True),
        'position_label': components['range_position'].get('label', 'unknown'),
    }
