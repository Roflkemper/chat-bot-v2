from __future__ import annotations

from typing import Any, Dict, Iterable


def _d(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _pick(payload: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in payload and payload.get(k) is not None:
            return payload.get(k)
        if '.' in k:
            cur: Any = payload
            ok = True
            for part in k.split('.'):
                if isinstance(cur, dict) and part in cur and cur.get(part) is not None:
                    cur = cur.get(part)
                else:
                    ok = False
                    break
            if ok:
                return cur
    return default


def derive_range_quality(payload: Dict[str, Any]) -> Dict[str, Any]:
    impulse = _d(payload.get('impulse_character'))
    volume = _d(payload.get('volume_context') or payload.get('volume_confirmation'))
    decision = _d(payload.get('decision'))
    structure = str(impulse.get('state') or payload.get('structure') or 'CHOP').upper()
    volume_quality = str(volume.get('quality') or volume.get('volume_quality') or 'MIXED').upper()
    breakout = str(volume.get('breakout_state') or volume.get('breakout_quality') or 'UNCONFIRMED').upper()
    accel = str(volume.get('accel') or volume.get('acceleration_state') or 'NORMAL').upper()
    range_state = str(decision.get('range_position') or payload.get('range_position') or payload.get('range_position_zone') or '').upper()
    if range_state in {'MID', 'MID_RANGE', 'CENTER', 'MIDDLE'}:
        location = 'MID RANGE'
    elif range_state in {'UPPER', 'UPPER_RANGE', 'UPPER_PART', 'HIGH_EDGE'}:
        location = 'UPPER RANGE'
    elif range_state in {'LOWER', 'LOWER_RANGE', 'LOWER_PART', 'LOW_EDGE'}:
        location = 'LOWER RANGE'
    else:
        location = 'MID RANGE'

    if structure == 'CHOP' and breakout == 'UNCONFIRMED' and volume_quality in {'MIXED','THIN','REJECTION','BALANCED'}:
        label = 'RANGE HEALTHY'
        tradable = True
        risk = 'LOW'
        note = 'диапазон живой, сетки можно держать только по режиму края'
    elif breakout in {'WEAK','FAILED'} or volume_quality in {'MIXED','THIN','REJECTION'}:
        label = 'RANGE NOISY'
        tradable = True
        risk = 'MEDIUM'
        note = 'диапазон грязный, агрессию лучше снизить'
    else:
        label = 'RANGE BREAK RISK'
        tradable = False
        risk = 'HIGH'
        note = 'диапазон может ломаться, форсировать сетки нельзя'
    return {
        'label': label,
        'tradable': tradable,
        'risk': risk,
        'note': note,
        'structure': structure,
        'volume_quality': volume_quality,
        'breakout': breakout,
        'accel': accel,
        'location': location,
    }


def derive_reclaim_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    fake = _d(payload.get('fake_move_v14') or payload.get('fake_move') or payload.get('fake_context'))
    reaction = _d(payload.get('liquidation_reaction') or payload.get('reaction_to_blocks'))
    decision = _d(payload.get('decision'))
    side = str(fake.get('trap_side') or reaction.get('trap_side') or decision.get('direction') or 'NONE').upper()
    reclaim = bool(fake.get('reclaim_needed') or reaction.get('reclaim'))
    acceptance = str(reaction.get('acceptance') or fake.get('acceptance') or 'UNKNOWN').upper()
    summary = str(fake.get('summary') or reaction.get('summary') or '').strip()

    if reclaim and acceptance in {'FAILED', 'REJECTED'}:
        state = 'RECLAIM FAILED'
        action = 'не форсировать вход против failed reclaim'
    elif reclaim and acceptance in {'ACCEPTED', 'CONFIRMED'}:
        state = 'RECLAIM CONFIRMED'
        action = 'reclaim удержан, сценарий у края сильнее'
    elif reclaim:
        state = 'RECLAIM READY'
        action = 'ждать возврат и удержание уровня'
    else:
        state = 'NO RECLAIM'
        action = ''
    return {
        'state': state,
        'side': side,
        'summary': summary,
        'action': action,
        'visible': state != 'NO RECLAIM',
    }


def derive_divergence_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = _d(payload.get('decision'))
    pattern = _d(payload.get('pattern_memory_v2') or payload.get('pattern_memory'))
    volume = _d(payload.get('volume_context') or payload.get('volume_confirmation'))
    market_regime = _d(payload.get('market_regime'))
    rsi = _f(_pick(payload, ['rsi14', 'features.rsi14', 'market_regime.features.rsi14', 'market_regime.rsi14'], None), -1.0)
    prev_rsi = _f(_pick(payload, ['prev_rsi14', 'features.prev_rsi14'], None), -1.0)
    price = _f(_pick(payload, ['price', 'current_price', 'last_price', 'close'], None), 0.0)
    prev_price = _f(_pick(payload, ['prev_close', 'previous_close', 'features.prev_close'], None), 0.0)
    direction = str(pattern.get('direction_bias') or pattern.get('direction') or decision.get('direction') or 'NEUTRAL').upper()
    breakout = str(volume.get('breakout_state') or volume.get('breakout_quality') or 'UNCONFIRMED').upper()
    volume_quality = str(volume.get('quality') or volume.get('volume_quality') or 'MIXED').upper()
    range_state = str(decision.get('range_position') or payload.get('range_position') or payload.get('range_position_zone') or '').upper()

    state = 'NONE'
    strength = 'LOW'
    note = ''
    if rsi >= 0 and prev_rsi >= 0 and price > 0 and prev_price > 0:
        if price >= prev_price and rsi < prev_rsi and rsi >= 60:
            state = 'BEARISH'
            note = 'цена обновляет/держит high, RSI слабее'
        elif price <= prev_price and rsi > prev_rsi and rsi <= 40:
            state = 'BULLISH'
            note = 'цена обновляет/держит low, RSI сильнее'
    elif direction == 'SHORT' and range_state in {'UPPER','UPPER_RANGE','UPPER_PART','HIGH_EDGE'} and breakout == 'UNCONFIRMED' and volume_quality in {'MIXED','THIN','REJECTION'}:
        state = 'BEARISH_HINT'
        note = 'верхний край без подтверждённого breakout'
    elif direction == 'LONG' and range_state in {'LOWER','LOWER_RANGE','LOWER_PART','LOW_EDGE'} and breakout == 'UNCONFIRMED' and volume_quality in {'MIXED','THIN','REJECTION'}:
        state = 'BULLISH_HINT'
        note = 'нижний край без подтверждённого breakout'

    if state in {'BEARISH','BULLISH'}:
        strength = 'MEDIUM' if breakout == 'UNCONFIRMED' else 'LOW'
    elif state.endswith('_HINT'):
        strength = 'SOFT'

    return {
        'state': state,
        'strength': strength,
        'note': note,
        'visible': state != 'NONE',
    }


def derive_v1689_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    rq = derive_range_quality(payload)
    reclaim = derive_reclaim_signal(payload)
    div = derive_divergence_signal(payload)
    return {
        'range_quality': rq,
        'reclaim': reclaim,
        'divergence': div,
    }
