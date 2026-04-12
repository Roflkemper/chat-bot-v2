from __future__ import annotations

from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _s(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def _symbol(payload: Dict[str, Any], view: Dict[str, Any]) -> str:
    symbol = _s(payload.get('symbol') or payload.get('instrument') or view.get('symbol') or '')
    return symbol.upper()


def _classify_delta(score: float) -> str:
    if score >= 0.82:
        return 'CRITICAL'
    if score >= 0.62:
        return 'HEAVY'
    if score >= 0.35:
        return 'RISING'
    return 'LOW'


def _classify_stress(score: float) -> str:
    if score >= 0.82:
        return 'CRITICAL'
    if score >= 0.60:
        return 'HIGH'
    if score >= 0.35:
        return 'MEDIUM'
    return 'LOW'


def evaluate_hedge_action(
    payload: Dict[str, Any],
    view: Dict[str, Any] | None = None,
    execution_plan: Dict[str, Any] | None = None,
    consensus: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    view = view if isinstance(view, dict) else {}
    execution_plan = execution_plan if isinstance(execution_plan, dict) else {}
    consensus = consensus if isinstance(consensus, dict) else {}

    symbol = _symbol(payload, view)
    side = _s(execution_plan.get('side') or view.get('side') or 'NEUTRAL').upper()
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    derivatives = payload.get('derivatives_context') if isinstance(payload.get('derivatives_context'), dict) else {}

    long_layers = _f(payload.get('long_layers_active') or payload.get('active_long_layers') or payload.get('long_layers') or 0.0)
    short_layers = _f(payload.get('short_layers_active') or payload.get('active_short_layers') or payload.get('short_layers') or 0.0)
    layers = long_layers if side == 'LONG' else short_layers if side == 'SHORT' else 0.0

    position_load = _f(payload.get('position_load') or payload.get('grid_load') or payload.get('active_position_load') or 0.0)
    adverse_move = abs(_f(payload.get('adverse_excursion_pct') or payload.get('grid_drawdown_pct') or payload.get('unrealized_pressure_pct') or 0.0))
    distance_from_avg = abs(_f(payload.get('distance_from_avg_entry_pct') or payload.get('distance_from_average_pct') or 0.0))
    confidence = _f(view.get('scenario_confidence') or payload.get('scenario_confidence') or decision.get('confidence_pct') or 0.0)
    trend_pressure = _s(consensus.get('trend_pressure') or '').upper()
    leader_pressure = _s(consensus.get('leader_pressure') or '').upper()
    hedge_pressure = _s(consensus.get('hedge_pressure_modifier') or 'NORMAL').upper()
    blocked_side = _s(consensus.get('blocked_side') or 'NONE').upper()
    no_add = 'НЕ ДОБИРАТЬ' in _s(execution_plan.get('no_add_text')).upper()
    no_entry = 'НЕ ВХОДИТЬ' in _s(execution_plan.get('no_entry_text')).upper()

    effective_delta_score = 0.0
    effective_delta_score += min(0.45, layers * 0.12)
    effective_delta_score += min(0.25, position_load * 0.25)
    effective_delta_score += min(0.20, adverse_move / 3.5)
    effective_delta_score += min(0.15, distance_from_avg / 2.5)
    if confidence < 45:
        effective_delta_score += 0.12
    elif confidence < 58:
        effective_delta_score += 0.06
    if hedge_pressure == 'HIGH':
        effective_delta_score += 0.15
    elif hedge_pressure == 'ELEVATED':
        effective_delta_score += 0.08
    effective_delta_score = max(0.0, min(1.0, effective_delta_score))
    effective_delta = _classify_delta(effective_delta_score)

    stress_score = 0.0
    stress_score += min(0.35, layers * 0.10)
    stress_score += min(0.25, adverse_move / 3.0)
    stress_score += min(0.15, distance_from_avg / 2.2)
    if no_add:
        stress_score += 0.10
    if trend_pressure == 'RISK_OFF_GRID':
        stress_score += 0.18
    elif trend_pressure.startswith('TRENDING'):
        stress_score += 0.10
    if side == blocked_side:
        stress_score += 0.16
    if confidence < 40:
        stress_score += 0.14
    elif confidence < 55:
        stress_score += 0.07
    stress_score = max(0.0, min(1.0, stress_score))
    grid_stress = _classify_stress(stress_score)

    if side == 'NEUTRAL' or no_entry and layers <= 0 and position_load <= 0:
        return {
            'mode': 'OFF',
            'hedge_state': 'HEDGE_OFF',
            'effective_delta': 'LOW',
            'grid_stress': 'LOW',
            'hedge_type': 'NONE',
            'size_hint': 'NONE',
            'reason': 'нет активной нагрузки',
            'action_text': 'ХЕДЖ НЕ НУЖЕН: нет активной нагрузки',
            'forbidden_text': 'НЕ ХЕДЖИРОВАТЬ НА ВСЯКИЙ СЛУЧАЙ',
            'escalation_text': 'что усилит защиту: набор активной позиции + рост перекоса + ухудшение сценария',
            'release_text': 'что снимет защиту: активная защита не включена',
        }

    coin = 'BTC' if 'BTC' in symbol else 'ETH' if 'ETH' in symbol else 'XRP' if 'XRP' in symbol else 'ALT'
    hedge_type = 'LOCK'
    if coin == 'XRP':
        hedge_type = 'PARTIAL_DEFENSE'
    elif coin == 'ETH' and leader_pressure in {'BTC_DOWN_HARD', 'BTC_DOWN'} and side == 'LONG':
        hedge_type = 'CROSS_HEDGE_ADVISORY'
    elif confidence < 40 and grid_stress in {'HIGH', 'CRITICAL'}:
        hedge_type = 'TRAILING_DEFENSE'

    size_hint = 'LIGHT'
    if effective_delta in {'HEAVY', 'CRITICAL'} or grid_stress in {'HIGH', 'CRITICAL'}:
        size_hint = 'MEDIUM'
    if effective_delta == 'CRITICAL' or grid_stress == 'CRITICAL':
        size_hint = 'HEAVY'

    mode = 'WATCH'
    hedge_state = 'HEDGE_WATCH'
    reason = 'перекос растёт'
    action_text = 'ПОДГОТОВИТЬ ХЕДЖ: перекос растёт, но защита ещё не обязательна'
    forbidden_text = 'НЕ ДОБИРАТЬ В УХУДШЕНИЕ СРЕДНЕЙ И НЕ ВКЛЮЧАТЬ FULL HEDGE ПО ОДНОЙ СВЕЧЕ'

    if grid_stress == 'LOW' and effective_delta == 'LOW':
        mode = 'OFF'
        hedge_state = 'HEDGE_OFF'
        reason = 'сетка под контролем'
        action_text = 'ХЕДЖ НЕ НУЖЕН: сетка под контролем'
        forbidden_text = 'НЕ ХЕДЖИРОВАТЬ: давление ещё не критично'
    elif grid_stress == 'MEDIUM' or effective_delta == 'RISING':
        mode = 'WATCH'
        hedge_state = 'HEDGE_WATCH'
        reason = 'перекос растёт / добор уже надо ограничивать'
        action_text = 'ГОТОВИТЬ ХЕДЖ: риск для сетки повышается'
    elif grid_stress == 'HIGH' or effective_delta == 'HEAVY':
        mode = 'ARM'
        hedge_state = 'HEDGE_ARMED'
        reason = 'сетка теряет контроль, partial defense в приоритете'
        action_text = 'ЧАСТИЧНАЯ ЗАЩИТА ПРИОРИТЕТНЕЕ ПОЛНОГО ХЕДЖА'
        if hedge_type == 'LOCK':
            hedge_type = 'PARTIAL_DEFENSE' if coin in {'XRP', 'ALT'} else 'LOCK'
        size_hint = 'MEDIUM' if size_hint == 'LIGHT' else size_hint
    if grid_stress == 'CRITICAL' or effective_delta == 'CRITICAL' or (trend_pressure == 'RISK_OFF_GRID' and side == blocked_side and confidence < 45):
        mode = 'READY'
        hedge_state = 'HEDGE_READY'
        reason = 'сетку опасно досиживать без защиты'
        action_text = 'ХЕДЖ РАЗРЕШЁН: сетка перегружена и рынок давит против позиции'
        forbidden_text = 'НЕ ДОСИЖИВАТЬ БЕЗ ЗАЩИТЫ И НЕ ДОБИРАТЬ ПРОТИВ ДАВЛЕНИЯ'
    if confidence >= 62 and grid_stress in {'LOW', 'MEDIUM'} and hedge_pressure == 'NORMAL' and side != blocked_side and adverse_move < 1.0:
        mode = 'REDUCE'
        hedge_state = 'HEDGE_REDUCE'
        reason = 'давление ослабло'
        action_text = 'СНИЖАТЬ ЗАЩИТУ: рынок возвращает контроль'
        forbidden_text = 'НЕ ДЕРЖАТЬ ПОЛНЫЙ ХЕДЖ, ЕСЛИ УГРОЗА ОСЛАБЛА'
    if confidence >= 70 and grid_stress == 'LOW' and effective_delta == 'LOW' and side != blocked_side and adverse_move < 0.6:
        mode = 'EXIT'
        hedge_state = 'HEDGE_EXIT'
        reason = 'угроза снята'
        action_text = 'СНИМАТЬ ХЕДЖ: сценарий восстановился'
        forbidden_text = 'НЕ ДЕРЖАТЬ ЗАЩИТУ БЕЗ АКТИВНОЙ УГРОЗЫ'

    escalation_text = 'что усилит защиту: новый набор слоёв, рост перекоса, продолжение движения против сетки'
    if leader_pressure in {'BTC_DOWN_HARD', 'BTC_UP_HARD'}:
        escalation_text = 'что усилит защиту: сильное движение BTC-поводыря подтвердит защитный сценарий'
    if hedge_type == 'CROSS_HEDGE_ADVISORY':
        action_text = 'РАССМОТРЕТЬ ЗАЩИТУ ЧЕРЕЗ BTC: ETH-перекос под давлением лидера рынка'
        reason = 'ETH под риском, BTC даёт лучший защитный контекст'

    release_text = 'что снимет защиту: ослабление давления, восстановление сценария, нормализация перекоса'

    return {
        'mode': mode,
        'hedge_state': hedge_state,
        'effective_delta': effective_delta,
        'effective_delta_score': round(effective_delta_score, 3),
        'grid_stress': grid_stress,
        'grid_stress_score': round(stress_score, 3),
        'hedge_type': hedge_type,
        'size_hint': size_hint,
        'reason': reason,
        'action_text': action_text,
        'forbidden_text': forbidden_text,
        'escalation_text': escalation_text,
        'release_text': release_text,
    }
