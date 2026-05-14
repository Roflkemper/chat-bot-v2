from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def _u(v: Any, default: str = '') -> str:
    try:
        if v is None:
            return default
        return str(v).strip().upper()
    except Exception:
        return default


def build_fake_move_state(payload: Dict[str, Any], decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    decision = decision if isinstance(decision, dict) else {}
    fast = payload.get('fast_move_context') if isinstance(payload.get('fast_move_context'), dict) else {}
    liq = payload.get('liquidity_decision') if isinstance(payload.get('liquidity_decision'), dict) else {}
    impulse = payload.get('impulse_character') if isinstance(payload.get('impulse_character'), dict) else {}
    price = _f(payload.get('price') or payload.get('last_price') or payload.get('close') or payload.get('current_price'))
    low = _f(payload.get('range_low') or decision.get('range_low'))
    high = _f(payload.get('range_high') or decision.get('range_high'))
    classification = _u(fast.get('classification') or fast.get('type'))
    continuation_risk = _u(fast.get('continuation_risk') or decision.get('continuation_risk'))
    trap_risk = _u(decision.get('trap_risk') or fast.get('trap_risk'))
    impulse_state = _u(impulse.get('state'))
    acceptance = _u(impulse.get('acceptance'))
    liq_pressure = _u(liq.get('liq_side_pressure') or liq.get('pressure'))
    squeeze_risk = _u(liq.get('squeeze_risk'))

    out = {
        'state': 'NO_SWEEP',
        'type': 'NONE',
        'is_fake_move': False,
        'confirmed': False,
        'side_hint': 'NEUTRAL',
        'confidence': 0.0,
        'reclaim_needed': None,
        'invalidation_level': None,
        'execution_mode': 'NONE',
        'summary': 'признаков ложного выноса недостаточно',
        'implication': 'работать по базовой логике режима',
        'action': 'ждать подтверждение',
    }

    up_candidate = classification in {'LIKELY_FAKE_UP', 'FAKE_UP', 'WEAK_CONTINUATION_UP'} or impulse_state in {'EXHAUSTION_UP', 'TRAP_CANDIDATE_UP'}
    down_candidate = classification in {'LIKELY_FAKE_DOWN', 'FAKE_DOWN', 'WEAK_CONTINUATION_DOWN'} or impulse_state in {'EXHAUSTION_DOWN', 'TRAP_CANDIDATE_DOWN'}

    if up_candidate:
        out['state'] = 'SWEEP_UP_DETECTED'
        out['type'] = 'FAKE_UP_RISK'
        out['side_hint'] = 'SHORT'
        out['reclaim_needed'] = round(high, 2) if high > 0 else None
        out['invalidation_level'] = round(high * 1.002, 2) if high > 0 else None
        out['confidence'] = 56.0
        out['summary'] = 'вынос вверх есть, но нужен реальный возврат под уровень'
        out['action'] = 'ждать возврат под верхнюю зону и отсутствие follow-through вверх'
        out['execution_mode'] = 'WAIT_RECLAIM_SHORT'
        if acceptance == 'REJECTED' or classification in {'FAKE_UP', 'LIKELY_FAKE_UP'}:
            out['state'] = 'RECLAIM_PENDING_SHORT'
            out['confidence'] += 10.0
        if continuation_risk in {'LOW', 'MEDIUM'}:
            out['confidence'] += 6.0
        if trap_risk == 'HIGH':
            out['confidence'] += 8.0
        if liq_pressure in {'UP', 'LONG'} and squeeze_risk in {'MEDIUM', 'HIGH'}:
            out['confidence'] += 4.0
        if out['state'] == 'RECLAIM_PENDING_SHORT' and (classification in {'FAKE_UP', 'LIKELY_FAKE_UP'} or impulse_state in {'TRAP_CANDIDATE_UP', 'EXHAUSTION_UP'}):
            out.update({
                'state': 'FAKE_UP_CONFIRMED',
                'type': 'FAKE_UP',
                'is_fake_move': True,
                'confirmed': True,
                'execution_mode': 'WATCH_CONFIRM_SHORT',
                'summary': 'ложный вынос вверх подтверждён: рынок не принял цену выше уровня',
                'implication': 'short допустим только после возврата под уровень / слабого ретеста',
                'action': 'лонги не догонять; short смотреть только после возврата под уровень',
            })
        elif classification == 'CONTINUATION_UP' and acceptance == 'ACCEPTED':
            out.update({
                'state': 'REAL_BREAK_UP_CONFIRMED',
                'type': 'CONTINUATION_UP',
                'side_hint': 'LONG',
                'summary': 'движение вверх пока больше похоже на реальное продолжение, чем на ловушку',
                'action': 'контртренд short избегать до явной потери удержания',
                'execution_mode': 'AVOID_COUNTERTREND_SHORT',
                'confidence': 72.0,
            })
        out['confidence'] = min(float(out['confidence']), 92.0)
        return out

    if down_candidate:
        out['state'] = 'SWEEP_DOWN_DETECTED'
        out['type'] = 'FAKE_DOWN_RISK'
        out['side_hint'] = 'LONG'
        out['reclaim_needed'] = round(low, 2) if low > 0 else None
        out['invalidation_level'] = round(low * 0.998, 2) if low > 0 else None
        out['confidence'] = 56.0
        out['summary'] = 'пролив вниз есть, но нужен реальный reclaim выше уровня'
        out['action'] = 'ждать возврат выше нижней зоны и отсутствие follow-through вниз'
        out['execution_mode'] = 'WAIT_RECLAIM_LONG'
        if acceptance == 'REJECTED' or classification in {'FAKE_DOWN', 'LIKELY_FAKE_DOWN'}:
            out['state'] = 'RECLAIM_PENDING_LONG'
            out['confidence'] += 10.0
        if continuation_risk in {'LOW', 'MEDIUM'}:
            out['confidence'] += 6.0
        if trap_risk == 'HIGH':
            out['confidence'] += 8.0
        if liq_pressure in {'DOWN', 'SHORT'} and squeeze_risk in {'MEDIUM', 'HIGH'}:
            out['confidence'] += 4.0
        if out['state'] == 'RECLAIM_PENDING_LONG' and (classification in {'FAKE_DOWN', 'LIKELY_FAKE_DOWN'} or impulse_state in {'TRAP_CANDIDATE_DOWN', 'EXHAUSTION_DOWN'}):
            out.update({
                'state': 'FAKE_DOWN_CONFIRMED',
                'type': 'FAKE_DOWN',
                'is_fake_move': True,
                'confirmed': True,
                'execution_mode': 'WATCH_CONFIRM_LONG',
                'summary': 'ложный вынос вниз подтверждён: рынок не принял цену ниже уровня',
                'implication': 'long допустим только после reclaim выше уровня / слабого ретеста',
                'action': 'шорты не догонять; long смотреть только после reclaim выше уровня',
            })
        elif classification == 'CONTINUATION_DOWN' and acceptance == 'ACCEPTED':
            out.update({
                'state': 'REAL_BREAK_DOWN_CONFIRMED',
                'type': 'CONTINUATION_DOWN',
                'side_hint': 'SHORT',
                'summary': 'движение вниз пока больше похоже на реальное продолжение, чем на ловушку',
                'action': 'контртренд long избегать до явного reclaim вверх',
                'execution_mode': 'AVOID_COUNTERTREND_LONG',
                'confidence': 72.0,
            })
        out['confidence'] = min(float(out['confidence']), 92.0)
        return out

    return out


__all__ = ['build_fake_move_state']
