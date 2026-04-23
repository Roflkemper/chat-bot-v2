from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _direction(data: Dict[str, Any]) -> str:
    decision = data.get('decision') if isinstance(data.get('decision'), dict) else {}
    raw = decision.get('direction_text') or decision.get('direction') or data.get('final_decision') or data.get('forecast_direction') or 'NEUTRAL'
    raw = str(raw).upper()
    if 'LONG' in raw or 'ЛОНГ' in raw:
        return 'LONG'
    if 'SHORT' in raw or 'ШОРТ' in raw:
        return 'SHORT'
    return 'NEUTRAL'


def _get_targets(data: Dict[str, Any], side: str) -> tuple[float | None, float | None]:
    block = data.get('trade_plan') if isinstance(data.get('trade_plan'), dict) else {}
    tp1 = block.get('tp1') or data.get('tp1')
    tp2 = block.get('tp2') or data.get('tp2')
    def as_num(x):
        try:
            if isinstance(x, str):
                x = x.replace(' ', '').replace(',', '')
            return float(x)
        except Exception:
            return None
    return as_num(tp1), as_num(tp2)


def analyze_move_continuation(data: Dict[str, Any], analysis_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    decision = data.get('decision') if isinstance(data.get('decision'), dict) else {}
    setup = data.get('setup_quality') if isinstance(data.get('setup_quality'), dict) else {}
    structure = data.get('market_structure') if isinstance(data.get('market_structure'), dict) else {}
    confluence = data.get('confluence') if isinstance(data.get('confluence'), dict) else {}

    side = _direction(data)
    confidence = _f(decision.get('final_confidence') or decision.get('confidence_pct') or data.get('forecast_confidence_effective') or data.get('forecast_confidence') or data.get('confidence') or 0.0)
    long_score = _f(data.get('long_score') or decision.get('long_score') or 0.0)
    short_score = _f(data.get('short_score') or decision.get('short_score') or 0.0)
    edge = _f(data.get('edge_score') or decision.get('edge_score') or decision.get('best_trade_score') or confluence.get('score') or 0.0)
    trade_authorized = bool(decision.get('trade_authorized'))
    manager_action = str(decision.get('manager_action') or '').upper()
    trap = str(setup.get('trap_risk') or '').upper()
    late = str(setup.get('late_entry_risk') or '').upper()
    continuation_quality = str(structure.get('continuation_quality') or '').upper()
    status = str(structure.get('status') or '').upper()
    choch = bool(structure.get('choch_risk'))
    structure_break = bool(structure.get('structure_break'))

    score = confidence * 0.45 + max(long_score, short_score) * 0.25 + edge * 0.30
    if not trade_authorized:
        score -= 18
    if manager_action in {'ЛУЧШЕ ЗАКРЫТЬ', 'ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ'}:
        score -= 22
    if continuation_quality == 'HIGH':
        score += 8
    elif continuation_quality == 'LOW':
        score -= 8
    if status in {'TREND_UP', 'TREND_DOWN', 'CONTINUATION'}:
        score += 5
    if trap == 'HIGH':
        score -= 12
    elif trap == 'MEDIUM':
        score -= 5
    if late == 'HIGH':
        score -= 15
    elif late == 'MEDIUM':
        score -= 6
    if choch:
        score -= 12
    if structure_break:
        score -= 14
    score = max(0.0, min(100.0, score))

    if side == 'NEUTRAL' or score < 28:
        state = 'EXHAUSTED'
        mgmt = 'WATCH FOR REVERSAL'
        comment = 'движение не выглядит здоровым для удержания как базовый сценарий'
    elif structure_break or choch or trap == 'HIGH':
        state = 'POSSIBLE_FALSE_BREAK'
        mgmt = 'EXIT ON WEAKNESS'
        comment = 'есть риск, что импульс уже не подтверждается и может перейти в ложный вынос'
    elif late == 'HIGH' or score < 48:
        state = 'FADING'
        mgmt = 'HOLD CAREFULLY'
        comment = 'движение еще может идти по инерции, но оно уже не свежее'
    elif late == 'MEDIUM' or score < 68:
        state = 'ALIVE_BUT_LATE'
        mgmt = 'PARTIAL TAKE'
        comment = 'движение еще живо, но лучше вести его осторожно и без погони за ценой'
    else:
        state = 'ALIVE'
        mgmt = 'HOLD STRONG'
        comment = 'импульс выглядит достаточно живым, удержание пока оправдано'

    if manager_action in {'ЛУЧШЕ ЗАКРЫТЬ', 'ЛУЧШЕ ФИНАЛЬНО ЗАКРЫТЬ'} or (not trade_authorized and edge <= 0.0):
        state = 'FADING' if state == 'ALIVE' else state
        mgmt = 'EXIT ON WEAKNESS'
        comment = 'контекст уже не поддерживает агрессивное удержание; приоритет — защита капитала'

    path = 'добой ближайшей цели' if state in {'ALIVE_BUT_LATE', 'FADING'} else 'продолжение по текущей стороне' if state == 'ALIVE' else 'искать реакцию и возможный разворот'
    return {
        'side': side,
        'continuation_state': state,
        'continuation_score': round(score, 1),
        'management_state': mgmt,
        'movement_comment': comment,
        'likely_path': path,
        'late_entry_risk': late or 'UNKNOWN',
        'trap_risk': trap or 'UNKNOWN',
    }


def build_target_map(data: Dict[str, Any], analysis_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    side = _direction(data)
    price = _f(data.get('price') or data.get('last_price') or data.get('close') or 0.0)
    range_low = _f(data.get('range_low') or data.get('low') or data.get('support') or 0.0)
    range_mid = _f(data.get('range_mid') or data.get('mid') or 0.0)
    range_high = _f(data.get('range_high') or data.get('high') or data.get('resistance') or 0.0)
    tp1, tp2 = _get_targets(data, side)
    atr = _f(data.get('atr') or data.get('atr_14') or 0.0)
    if atr <= 0 and price > 0:
        atr = price * 0.006

    if side == 'LONG':
        nearest = tp1 or (range_mid if range_mid > price else price + atr)
        main = tp2 or (range_high if range_high > nearest else nearest + atr)
        ext = main + atr if main else None
        reaction = f"{round((main or nearest) - atr * 0.35, 2)}–{round((main or nearest) + atr * 0.35, 2)}" if (main or nearest) else 'нет данных'
        invalidation = range_low if range_low > 0 else price - atr
    elif side == 'SHORT':
        nearest = tp1 or (range_mid if 0 < range_mid < price else price - atr)
        main = tp2 or (range_low if 0 < range_low < nearest else nearest - atr)
        ext = main - atr if main else None
        reaction = f"{round((main or nearest) - atr * 0.35, 2)}–{round((main or nearest) + atr * 0.35, 2)}" if (main or nearest) else 'нет данных'
        invalidation = range_high if range_high > 0 else price + atr
    else:
        nearest = main = ext = None
        reaction = 'нет данных'
        invalidation = None

    return {
        'nearest_target': nearest,
        'main_target': main,
        'extension_target': ext,
        'reaction_zone': reaction,
        'invalidation_level': invalidation,
    }


def find_reversal_zones(data: Dict[str, Any], analysis_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    flow = analyze_move_continuation(data, analysis_snapshot)
    target_map = build_target_map(data, analysis_snapshot)
    state = flow['continuation_state']
    zone = target_map['reaction_zone']
    if state == 'ALIVE':
        trigger = 'искать разворот только если после выноса пропадет follow-through и сломается локальная структура'
    elif state in {'ALIVE_BUT_LATE', 'FADING'}:
        trigger = 'у зоны реакции смотреть вынос без продолжения, резкий rejection и возврат под/над локальный уровень'
    else:
        trigger = 'первое подтверждение разворота уже допустимо искать по rejection и микрослому структуры'
    return {
        'reversal_watch_zone': zone,
        'reversal_confirm_zone': zone,
        'reversal_triggers': trigger,
        'reversal_comment': 'контртренд только после подтверждения' if state != 'EXHAUSTED' else 'контртренд становится интереснее, но нужен триггер',
    }


def build_trade_flow_summary(data: Dict[str, Any], analysis_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    flow = analyze_move_continuation(data, analysis_snapshot)
    target_map = build_target_map(data, analysis_snapshot)
    reversal = find_reversal_zones(data, analysis_snapshot)
    return {
        **flow,
        **target_map,
        **reversal,
    }
