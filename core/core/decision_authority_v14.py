from __future__ import annotations

from typing import Any, Dict, List

from core.output_contract_v14 import build_location_state


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


def _direction_from_pattern(pattern: Dict[str, Any]) -> str:
    raw = _u(pattern.get('direction') or pattern.get('direction_bias') or pattern.get('pattern_bias'))
    if raw in {'UP', 'LONG', 'BULL', 'BULLISH'}:
        return 'LONG'
    if raw in {'DOWN', 'SHORT', 'BEAR', 'BEARISH'}:
        return 'SHORT'
    return 'NEUTRAL'


def _fmt_price(v: Any) -> str:
    x = _f(v)
    return f"{x:.2f}" if x > 0 else 'нет данных'


def build_decision_authority_v14(payload: Dict[str, Any], legacy_decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    legacy = legacy_decision if isinstance(legacy_decision, dict) else {}
    loc = build_location_state(payload)
    impulse = payload.get('impulse_character') if isinstance(payload.get('impulse_character'), dict) else {}
    fake = payload.get('fake_move_detector') if isinstance(payload.get('fake_move_detector'), dict) else {}
    liq = payload.get('liquidity_decision') if isinstance(payload.get('liquidity_decision'), dict) else {}
    pattern = payload.get('pattern_memory_v2') if isinstance(payload.get('pattern_memory_v2'), dict) else {}

    location = _u(loc.get('state') or payload.get('location_state') or legacy.get('range_position') or 'UNKNOWN')
    impulse_state = _u(impulse.get('state') or 'NO_CLEAR_IMPULSE')
    fake_state = _u(fake.get('state') or 'NO_SWEEP')
    liq_pressure = _u(liq.get('liq_side_pressure') or 'NEUTRAL')
    squeeze = _u(liq.get('squeeze_risk') or 'LOW')
    pattern_side = _direction_from_pattern(pattern)

    long_score = 0.0
    short_score = 0.0
    why_long: List[str] = []
    why_short: List[str] = []

    if location == 'LOWER_EDGE':
        long_score += 24.0; why_long.append('цена у нижней рабочей зоны')
    elif location == 'UPPER_EDGE':
        short_score += 24.0; why_short.append('цена у верхней рабочей зоны')
    elif location == 'MID':
        why_long.append('середина диапазона'); why_short.append('середина диапазона')

    if fake_state == 'FAKE_UP_CONFIRMED':
        short_score += 40.0; why_short.append('ложный вынос вверх подтверждён')
    elif fake_state == 'RECLAIM_PENDING_SHORT':
        short_score += 24.0; why_short.append('есть sweep вверх, нужен финальный confirm')
    elif fake_state == 'REAL_BREAK_UP_CONFIRMED':
        long_score += 22.0; why_long.append('рынок принял breakout вверх')

    if fake_state == 'FAKE_DOWN_CONFIRMED':
        long_score += 40.0; why_long.append('ложный вынос вниз подтверждён')
    elif fake_state == 'RECLAIM_PENDING_LONG':
        long_score += 24.0; why_long.append('есть flush вниз, нужен финальный confirm')
    elif fake_state == 'REAL_BREAK_DOWN_CONFIRMED':
        short_score += 22.0; why_short.append('рынок принял breakout вниз')

    if impulse_state == 'EXHAUSTION_UP':
        short_score += 28.0; why_short.append('импульс вверх затухает')
    elif impulse_state == 'EXHAUSTION_DOWN':
        long_score += 28.0; why_long.append('импульс вниз затухает')
    elif impulse_state == 'TRAP_CANDIDATE_UP':
        short_score += 24.0; why_short.append('вынос вверх не принят')
    elif impulse_state == 'TRAP_CANDIDATE_DOWN':
        long_score += 24.0; why_long.append('пролив вниз не принят')
    elif impulse_state == 'CONTINUATION_UP':
        long_score += 18.0; why_long.append('чистое продолжение вверх')
        short_score -= 18.0
    elif impulse_state == 'CONTINUATION_DOWN':
        short_score += 18.0; why_short.append('чистое продолжение вниз')
        long_score -= 18.0

    if liq_pressure == 'UP':
        long_score += 12.0; why_long.append('ликвидность давит вверх')
        if squeeze == 'HIGH': short_score -= 8.0
    elif liq_pressure == 'DOWN':
        short_score += 12.0; why_short.append('ликвидность давит вниз')
        if squeeze == 'HIGH': long_score -= 8.0

    if pattern_side == 'LONG':
        long_score += 10.0; why_long.append('исторический паттерн поддерживает long')
    elif pattern_side == 'SHORT':
        short_score += 10.0; why_short.append('исторический паттерн поддерживает short')

    long_score = max(0.0, long_score)
    short_score = max(0.0, short_score)
    diff = abs(long_score - short_score)

    direction = 'NEUTRAL'
    why: List[str] = []
    dominant_score = max(long_score, short_score)
    if diff >= 8.0:
        if short_score > long_score:
            direction = 'SHORT'; why = why_short
        else:
            direction = 'LONG'; why = why_long

    state = 'WATCH_ZONE'
    action = 'WATCH'
    setup_note = 'ждать рабочую зону и подтверждение'
    summary = 'ситуация ещё не даёт готовый вход'
    entry_hint = ''

    if location == 'MID' and dominant_score < 35.0:
        state = 'WATCH_ZONE'; action = 'WAIT'; summary = 'середина диапазона: не лезть, ждать край и реакцию'; setup_note = 'в середине range edge не реализуется'
    elif direction == 'SHORT' and fake_state == 'FAKE_UP_CONFIRMED':
        state = 'EXECUTE_PROBE_SHORT'; action = 'EXECUTE_PROBE_SHORT'; summary = 'short разрешён: fake up подтверждён'; setup_note = 'допустим probe / small после confirm'; entry_hint = f'после возврата под {_fmt_price(loc.get("high") or payload.get("range_high"))}'
    elif direction == 'LONG' and fake_state == 'FAKE_DOWN_CONFIRMED':
        state = 'EXECUTE_PROBE_LONG'; action = 'EXECUTE_PROBE_LONG'; summary = 'long разрешён: fake down подтверждён'; setup_note = 'допустим probe / small после confirm'; entry_hint = f'после возврата выше {_fmt_price(loc.get("low") or payload.get("range_low"))}'
    elif direction == 'SHORT' and location == 'UPPER_EDGE' and dominant_score >= 40.0:
        state = 'ARM_SHORT'; action = 'ARM_SHORT'; summary = 'short сетап собирается у верхней зоны'; setup_note = 'нужен reclaim / rejection'; entry_hint = f'смотреть отказ от зоны {_fmt_price(payload.get("range_mid"))}–{_fmt_price(payload.get("range_high"))}'
    elif direction == 'LONG' and location == 'LOWER_EDGE' and dominant_score >= 40.0:
        state = 'ARM_LONG'; action = 'ARM_LONG'; summary = 'long сетап собирается у нижней зоны'; setup_note = 'нужен reclaim / rejection'; entry_hint = f'смотреть выкуп зоны {_fmt_price(payload.get("range_low"))}–{_fmt_price(payload.get("range_mid"))}'
    elif direction == 'SHORT' and dominant_score >= 28.0:
        state = 'WATCH_SHORT'; action = 'WATCH'; summary = 'есть short bias, но без точки входа'; setup_note = 'ждать подход к верхней зоне'
    elif direction == 'LONG' and dominant_score >= 28.0:
        state = 'WATCH_LONG'; action = 'WATCH'; summary = 'есть long bias, но без точки входа'; setup_note = 'ждать подход к нижней зоне'
    else:
        direction = 'NEUTRAL'
        state = 'WATCH_ZONE'; action = 'WAIT'; summary = 'направление не созрело: нужен подход к зоне и реакция'; setup_note = 'нет готового directional edge'
        why = ['нет достаточно сильного перевеса']

    effective_edge = min(92.0, round(max(long_score, short_score), 1))
    if action.startswith('EXECUTE_'):
        effective_edge = max(effective_edge, 55.0)
    elif action.startswith('ARM_'):
        effective_edge = max(effective_edge, 38.0)
    elif action == 'WATCH':
        effective_edge = max(effective_edge, 20.0)

    edge_label = 'NO_EDGE'
    if effective_edge >= 66.0:
        edge_label = 'STRONG'
    elif effective_edge >= 45.0:
        edge_label = 'WORKABLE'
    elif effective_edge >= 18.0:
        edge_label = 'WEAK'

    invalidation = ''
    if direction == 'SHORT' and _f(payload.get('range_high')) > 0:
        invalidation = f'закрепление выше {_fmt_price(payload.get("range_high"))} ломает short-сценарий'
    elif direction == 'LONG' and _f(payload.get('range_low')) > 0:
        invalidation = f'закрепление ниже {_fmt_price(payload.get("range_low"))} ломает long-сценарий'
    elif _f(payload.get('range_low')) > 0 and _f(payload.get('range_high')) > 0:
        invalidation = f'выход из диапазона {_fmt_price(payload.get("range_low"))}–{_fmt_price(payload.get("range_high"))} с удержанием за границей'

    return {
        'state': state,
        'action': action,
        'direction': direction,
        'edge_score': round(effective_edge, 1),
        'edge_label': edge_label,
        'summary': summary,
        'setup_note': setup_note,
        'entry_hint': entry_hint,
        'invalidation': invalidation,
        'why': why[:4],
        'scores': {'long': round(long_score, 1), 'short': round(short_score, 1)},
        'location_state': location,
        'impulse_state': impulse_state,
        'fake_move_state': fake_state,
        'liquidity_pressure': liq_pressure,
        'pattern_side': pattern_side,
    }


__all__ = ['build_decision_authority_v14']
