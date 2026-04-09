from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
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


def build_location_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    price = _f(payload.get('price') or payload.get('last_price') or payload.get('current_price') or payload.get('close'))
    low = _f(payload.get('range_low'))
    mid = _f(payload.get('range_mid'))
    high = _f(payload.get('range_high'))
    if price <= 0 or high <= low:
        state = _u(payload.get('location_state') or payload.get('range_position') or 'UNKNOWN')
        return {'state': state or 'UNKNOWN', 'price': price, 'low': low, 'mid': mid, 'high': high, 'position_pct': 50.0}
    band = max(high - low, 1e-9)
    pct = max(0.0, min(100.0, (price - low) / band * 100.0))
    if pct >= 82.0:
        state = 'UPPER_EDGE'
    elif pct <= 18.0:
        state = 'LOWER_EDGE'
    elif 38.0 <= pct <= 62.0:
        state = 'MID'
    elif pct > 62.0:
        state = 'UPPER_PART'
    else:
        state = 'LOWER_PART'
    return {'state': state, 'price': price, 'low': low, 'mid': mid, 'high': high, 'position_pct': round(pct, 1)}


def build_v14_output_contract(payload: Dict[str, Any], decision: Dict[str, Any], authority: Dict[str, Any]) -> Dict[str, Any]:
    loc = build_location_state(payload)
    impulse = payload.get('impulse_character') if isinstance(payload.get('impulse_character'), dict) else {}
    fake = payload.get('fake_move_detector') if isinstance(payload.get('fake_move_detector'), dict) else {}
    liq = payload.get('liquidity_decision') if isinstance(payload.get('liquidity_decision'), dict) else {}
    pattern = payload.get('pattern_memory_v2') if isinstance(payload.get('pattern_memory_v2'), dict) else {}
    return {
        'location_state': loc.get('state', 'UNKNOWN'),
        'range_position_pct': loc.get('position_pct', 50.0),
        'price': loc.get('price'),
        'range_low': loc.get('low'),
        'range_mid': loc.get('mid'),
        'range_high': loc.get('high'),
        'impulse_state': _u(impulse.get('state') or 'NO_CLEAR_IMPULSE'),
        'fake_move_state': _u(fake.get('state') or 'NO_SWEEP'),
        'liquidity_state': _u(liq.get('liq_side_pressure') or 'NEUTRAL'),
        'pattern_bias': _u(pattern.get('direction') or pattern.get('direction_bias') or pattern.get('pattern_bias') or 'NEUTRAL'),
        'decision_state': _u(authority.get('state') or decision.get('action') or 'WAIT'),
        'decision_action': _u(authority.get('action') or decision.get('action') or 'WAIT'),
        'direction': _u(authority.get('direction') or decision.get('direction') or 'NEUTRAL'),
        'summary': str(authority.get('summary') or decision.get('summary') or '').strip(),
        'setup_note': str(authority.get('setup_note') or '').strip(),
        'invalidation': str(authority.get('invalidation') or decision.get('invalidation') or '').strip(),
        'entry_hint': str(authority.get('entry_hint') or '').strip(),
        'why': list(authority.get('why') or []),
    }


__all__ = ['build_location_state', 'build_v14_output_contract']
