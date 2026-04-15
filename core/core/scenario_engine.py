from __future__ import annotations

from typing import Dict, Any


def _zone(low, high):
    if low is None and high is None:
        return 'нет данных'
    if low is None:
        return f'{high:.2f}'
    if high is None:
        return f'{low:.2f}'
    return f'{low:.2f}–{high:.2f}'


def _scenario_status(probability: float, dominance_diff: float, edge_stage: str) -> str:
    stage = str(edge_stage or 'NO_EDGE').upper()
    diff = abs(float(dominance_diff or 0.0))
    prob = float(probability or 0.0)
    if stage == 'READY' or prob >= 64.0 or diff >= 12.0:
        return 'READY'
    if stage in {'BUILDING', 'PREPARE'} or prob >= 56.0 or diff >= 7.0:
        return 'BUILDING'
    if prob >= 52.0 or diff >= 4.0:
        return 'PREPARE'
    return 'NO_EDGE'


def build_scenarios(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    factor = payload.get('factor_breakdown') or {}
    liquidity = payload.get('liquidity_map') or {}
    micro = payload.get('microstructure') or {}
    vol = payload.get('volatility_impulse') or {}
    regime = payload.get('regime_v2') or {}
    fast_move = payload.get('fast_move_context') or {}
    low = payload.get('range_low')
    mid = payload.get('range_mid')
    high = payload.get('range_high')

    long_p = float(factor.get('long_total', 50.0) or 50.0)
    short_p = float(factor.get('short_total', 50.0) or 50.0)
    dominance_diff = float(factor.get('dominance_diff', 0.0) or 0.0)
    dominant = 'LONG' if long_p > short_p else 'SHORT' if short_p > long_p else 'NEUTRAL'
    trigger_zone = _zone(mid, high) if dominant == 'SHORT' else _zone(low, mid) if dominant == 'LONG' else _zone(low, high)
    alt_zone = _zone(low, mid) if dominant == 'SHORT' else _zone(mid, high) if dominant == 'LONG' else _zone(low, high)

    primary_probability = round(max(long_p, short_p), 1)
    alt_probability = round(min(long_p, short_p), 1)
    primary_status = _scenario_status(primary_probability, dominance_diff, factor.get('edge_stage', 'NO_EDGE'))
    readiness = max(0.0, min(100.0, round(abs(dominance_diff) * 7.5 + max(primary_probability - 50.0, 0.0) * 1.6, 1)))

    primary = {
        'side': dominant,
        'probability': primary_probability,
        'zone': trigger_zone,
        'status': primary_status,
        'trigger': 'реакция от зоны + подтверждение' if dominant != 'NEUTRAL' else 'ждать смещение к краю диапазона',
        'target': _zone(low, low) if dominant == 'SHORT' else _zone(high, high) if dominant == 'LONG' else 'нет данных',
        'readiness': readiness,
    }
    alternative = {
        'side': 'LONG' if dominant == 'SHORT' else 'SHORT' if dominant == 'LONG' else 'NEUTRAL',
        'probability': alt_probability,
        'zone': alt_zone,
        'status': 'ALT',
        'trigger': 'закрепление против основного сценария',
        'target': _zone(high, high) if dominant == 'SHORT' else _zone(low, low) if dominant == 'LONG' else 'нет данных',
        'readiness': round(max(0.0, min(100.0, readiness * 0.65)), 1),
    }

    reasons = []
    liq = str(liquidity.get('liquidity_state') or 'NEUTRAL').upper()
    if liq == 'BUY_SIDE_SWEEP_REJECTED':
        reasons.append('сверху был вынос ликвидности с отказом')
    elif liq == 'SELL_SIDE_SWEEP_REJECTED':
        reasons.append('снизу был вынос ликвидности с отказом')
    elif liq == 'UP_MAGNET':
        reasons.append('сверху есть магнит ликвидности')
    elif liq == 'DOWN_MAGNET':
        reasons.append('снизу есть магнит ликвидности')
    micro_bias = str(micro.get('micro_bias') or 'NEUTRAL').upper()
    if micro_bias == 'SHORT':
        reasons.append('микроструктура склоняется к продавцу')
    elif micro_bias == 'LONG':
        reasons.append('микроструктура склоняется к покупателю')
    impulse_state = str(vol.get('impulse_state') or '').upper()
    if impulse_state == 'NO_CLEAR_IMPULSE':
        reasons.append('чистый импульс не собран — вход только по подтверждению')
    elif impulse_state:
        reasons.append(f'состояние импульса: {impulse_state}')
    if 'RANGE' in str(regime.get('regime_label') or '').upper():
        reasons.append('рынок остаётся в диапазоне')

    fm_class = str(fast_move.get('classification') or '').upper()
    if fm_class == 'LIKELY_FAKE_UP':
        reasons.append('быстрый вынос вверх пока похож на ловушку')
    elif fm_class == 'LIKELY_FAKE_DOWN':
        reasons.append('быстрый пролив вниз пока похож на ловушку')
    elif fm_class == 'CONTINUATION_UP':
        reasons.append('быстрое движение вверх пока принимается рынком')
    elif fm_class == 'CONTINUATION_DOWN':
        reasons.append('быстрое движение вниз пока принимается рынком')

    invalidation = 'пробой и закреп против основной стороны отменяет базовый сценарий'
    pretrade = 'WAIT'
    if dominant != 'NEUTRAL':
        pretrade = f'PREPARE {dominant}'
        if primary_status == 'BUILDING':
            pretrade = f'BUILDING {dominant}'
        elif primary_status == 'READY':
            pretrade = f'READY {dominant}'

    fm_action = str(fast_move.get('action') or '').strip()
    if dominant == 'SHORT':
        action_now = 'не входить из середины; ждать вынос вверх / реакцию от верхней зоны'
    elif dominant == 'LONG':
        action_now = 'не входить из середины; ждать вынос вниз / реакцию от нижней зоны'
    else:
        action_now = 'ждать смещение к краю диапазона и появление активной стороны'
    if fm_action:
        action_now = fm_action

    return {
        'primary': primary,
        'alternative': alternative,
        'dominant_side': dominant,
        'invalidation': invalidation,
        'pretrade_signal': pretrade,
        'reasons': reasons[:5],
        'trigger_readiness': readiness,
        'action_now_hint': action_now,
    }
