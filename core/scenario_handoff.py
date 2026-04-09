from __future__ import annotations

from typing import Any, Dict, List, Tuple

FLIP_PREP_COOLDOWN_BARS = 3
SCENARIO_FLIP_CONFIRM_BARS = 2


def _clamp(v: int, lo: int = 15, hi: int = 85) -> int:
    return max(lo, min(hi, int(v)))


def compute_block_pressure(active_block: str, consensus_side: str, consensus_alignment: int, session_fc: Dict[str, Any], medium_fc: Dict[str, Any]) -> Tuple[str, str, bool, str]:
    if consensus_side not in {'LONG', 'SHORT'} or consensus_side == active_block:
        if consensus_side == active_block and consensus_alignment >= 2:
            return 'WITH', 'MID' if consensus_alignment == 2 else 'HIGH', False, 'большинство ТФ поддерживают активный блок'
        return 'NONE', 'LOW', False, ''

    session_support = str(session_fc.get('strength') or 'LOW').upper() == 'HIGH'
    medium_phase = str(medium_fc.get('phase') or '').upper()
    phase_against = (active_block == 'SHORT' and medium_phase == 'MARKUP') or (active_block == 'LONG' and medium_phase == 'MARKDOWN')

    if consensus_alignment == 3 and (session_support or phase_against):
        return 'AGAINST', 'HIGH', True, 'все ТФ против блока — высокий риск смены структуры'
    if consensus_alignment == 3:
        return 'AGAINST', 'MID', True, 'все ТФ против активного блока — давление на смену зоны'
    if consensus_alignment == 2 and phase_against:
        return 'AGAINST', 'LOW', True, 'среднесрок и большинство ТФ против блока'
    return 'NONE', 'LOW', False, ''


def compute_scenario_weights(snapshot: Dict[str, Any]) -> Tuple[int, int, List[str], List[str]]:
    base_prob = 50
    base_reasons: List[str] = []
    alt_reasons: List[str] = []

    pressure = str(snapshot.get('block_pressure') or 'NONE').upper()
    pressure_strength = str(snapshot.get('block_pressure_strength') or 'LOW').upper()
    consensus_side = str(snapshot.get('consensus_direction') or 'NONE').upper()
    active_block = str(snapshot.get('active_block') or 'NONE').upper()
    consensus_alignment = int(snapshot.get('consensus_alignment_count') or 0)
    depth_label = str(snapshot.get('depth_label') or '').upper()
    depth_pct = float(snapshot.get('block_depth_pct') or 0.0)
    range_position = float(snapshot.get('range_position_pct') or 0.0)
    medium_phase = str((snapshot.get('forecast') or {}).get('medium', {}).get('phase') or '').upper()
    scalp_dir = str((snapshot.get('forecast') or {}).get('short', {}).get('direction') or 'NEUTRAL').upper()
    hedge_state = str(snapshot.get('hedge_state') or 'OFF').upper()
    trigger_type = str(snapshot.get('trigger_type') or '').upper()
    flip_status = str(snapshot.get('flip_prep_status') or 'IDLE').upper()

    if pressure == 'AGAINST':
        delta = {'HIGH': 15, 'MID': 10, 'LOW': 5}.get(pressure_strength, 0)
        base_prob -= delta
        alt_reasons.append(f'давление против блока {pressure_strength.lower()}')
    if consensus_side in {'LONG', 'SHORT'} and consensus_side != active_block:
        if consensus_alignment == 3:
            base_prob -= 10
            alt_reasons.append('консенсус 3/3 против блока')
        elif consensus_alignment == 2:
            base_prob -= 5
            alt_reasons.append('консенсус 2/3 против блока')
    if depth_label in {'RISK', 'DEEP'}:
        base_prob -= 5
        alt_reasons.append('глубоко в зоне — выше риск прошивки')
    if depth_pct > 70:
        base_prob -= 5
        alt_reasons.append('глубина блока выше 70%')
    if (active_block == 'SHORT' and medium_phase == 'MARKUP') or (active_block == 'LONG' and medium_phase == 'MARKDOWN'):
        base_prob -= 10
        alt_reasons.append('среднесрок в фазе против блока')
    if consensus_side in {'LONG', 'SHORT'} and scalp_dir == consensus_side and consensus_side != active_block:
        base_prob -= 5
        alt_reasons.append('скальп уже в сторону пробоя')

    if active_block == 'SHORT' and range_position > 85:
        base_prob += 10
        base_reasons.append('цена у верхнего края — возможен резкий отбой')
    elif active_block == 'LONG' and range_position < 15:
        base_prob += 10
        base_reasons.append('цена у нижнего края — возможен резкий отбой')
    if hedge_state == 'PRE-TRIGGER':
        base_prob += 5
        base_reasons.append('hedge PRE-TRIGGER поддерживает осторожный отбой')
    if trigger_type == 'RECLAIM':
        base_prob += 5
        base_reasons.append('reclaim у края сохраняет шанс отбоя')
    if scalp_dir == 'NEUTRAL':
        base_prob += 5
        base_reasons.append('скальп не подтверждает пробой')

    if flip_status == 'WATCHING':
        base_prob -= 10
        alt_reasons.append('flip prep watching усиливает альтернативный сценарий')
    elif flip_status == 'ARMED':
        base_prob -= 20
        alt_reasons.append('flip prep armed усиливает вероятность пробоя')
    elif flip_status == 'CONFIRMED':
        base_prob -= 30
        alt_reasons.append('flip prep confirmed почти подготовил handoff')

    base_prob = _clamp(base_prob)
    alt_prob = 100 - base_prob
    return base_prob, alt_prob, base_reasons[:4], alt_reasons[:5]


def update_flip_prep(prev_state: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    state = {
        'flip_prep_active': False,
        'flip_prep_side': 'NONE',
        'flip_prep_reason': '',
        'flip_prep_level': None,
        'flip_prep_confirm_bars_needed': SCENARIO_FLIP_CONFIRM_BARS,
        'flip_prep_progress_bars': 0,
        'flip_prep_status': 'IDLE',
        'flip_prep_cooldown_bars': max(int(prev_state.get('flip_prep_cooldown_bars') or 0) - 1, 0),
        'candidate_side': 'NONE',
        'candidate_status': 'NONE',
        'candidate_reason': '',
    }

    active_block = str(snapshot.get('active_block') or 'NONE').upper()
    watch_side = str(snapshot.get('watch_side') or 'NONE').upper()
    consensus_side = str(snapshot.get('consensus_direction') or 'NONE').upper()
    consensus_alignment = int(snapshot.get('consensus_alignment_count') or 0)
    pressure = str(snapshot.get('block_pressure') or 'NONE').upper()
    pressure_strength = str(snapshot.get('block_pressure_strength') or 'LOW').upper()
    range_position = float(snapshot.get('range_position_pct') or 0.0)

    if active_block == 'SHORT':
        trigger_level = float(snapshot.get('range_high') or 0.0)
        outside = float(snapshot.get('price') or 0.0) > trigger_level
    elif active_block == 'LONG':
        trigger_level = float(snapshot.get('range_low') or 0.0)
        outside = float(snapshot.get('price') or 0.0) < trigger_level
    else:
        trigger_level = 0.0
        outside = False

    eligible = (
        active_block in {'SHORT', 'LONG'}
        and watch_side in {'LONG', 'SHORT'}
        and watch_side != active_block
        and consensus_side == watch_side
        and consensus_alignment >= 2
        and pressure == 'AGAINST'
        and pressure_strength in {'MID', 'HIGH'}
        and ((active_block == 'SHORT' and range_position >= 80.0) or (active_block == 'LONG' and range_position <= 20.0))
    )

    prev_status = str(prev_state.get('flip_prep_status') or 'IDLE').upper()
    prev_side = str(prev_state.get('flip_prep_side') or 'NONE').upper()
    prev_progress = int(prev_state.get('flip_prep_progress_bars') or 0)

    if state['flip_prep_cooldown_bars'] > 0 and prev_status in {'FAILED', 'IDLE'}:
        return state

    if not eligible:
        return state

    if prev_status in {'WATCHING', 'ARMED', 'CONFIRMED'} and prev_side not in {'NONE', watch_side}:
        # do not allow competing prep while one is active
        return {
            **state,
            'flip_prep_active': True,
            'flip_prep_side': prev_side,
            'flip_prep_status': prev_status,
            'flip_prep_progress_bars': prev_progress,
            'flip_prep_level': prev_state.get('flip_prep_level'),
            'flip_prep_reason': str(prev_state.get('flip_prep_reason') or ''),
            'candidate_side': prev_state.get('candidate_side', 'NONE'),
            'candidate_status': prev_state.get('candidate_status', 'NONE'),
            'candidate_reason': prev_state.get('candidate_reason', ''),
        }

    if prev_status in {'WATCHING', 'ARMED', 'CONFIRMED'} and prev_side == watch_side:
        if outside:
            progress = prev_progress + 1 if prev_status in {'ARMED', 'CONFIRMED'} else max(prev_progress, 0) + 1
            progress = min(progress, SCENARIO_FLIP_CONFIRM_BARS)
            status = 'ARMED' if progress < SCENARIO_FLIP_CONFIRM_BARS else 'CONFIRMED'
            candidate_status = 'PREPARED' if status == 'CONFIRMED' else 'WATCH'
            return {
                **state,
                'flip_prep_active': True,
                'flip_prep_side': watch_side,
                'flip_prep_reason': 'цена вышла за сценарный уровень и удерживается за ним',
                'flip_prep_level': trigger_level,
                'flip_prep_progress_bars': progress,
                'flip_prep_status': status,
                'candidate_side': watch_side,
                'candidate_status': candidate_status,
                'candidate_reason': 'сценарный handoff усиливается' if status != 'CONFIRMED' else 'сценарий новой стороны подготовлен',
            }
        # failed reset + cooldown
        return {
            **state,
            'flip_prep_cooldown_bars': FLIP_PREP_COOLDOWN_BARS,
        }

    if outside:
        return {
            **state,
            'flip_prep_active': True,
            'flip_prep_side': watch_side,
            'flip_prep_reason': 'цена начала выход за сценарный уровень',
            'flip_prep_level': trigger_level,
            'flip_prep_progress_bars': 1,
            'flip_prep_status': 'ARMED',
            'candidate_side': watch_side,
            'candidate_status': 'WATCH',
            'candidate_reason': 'новая сторона получает подготовку через пробой',
        }

    return {
        **state,
        'flip_prep_active': True,
        'flip_prep_side': watch_side,
        'flip_prep_reason': 'рынок под давлением против блока — наблюдаем handoff',
        'flip_prep_level': trigger_level,
        'flip_prep_progress_bars': 0,
        'flip_prep_status': 'WATCHING',
        'candidate_side': watch_side,
        'candidate_status': 'WATCH',
        'candidate_reason': 'новая сторона пока только в watch-режиме',
    }
