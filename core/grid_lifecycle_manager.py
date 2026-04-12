from __future__ import annotations

from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _s(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def evaluate_grid_lifecycle(
    payload: Dict[str, Any],
    view: Dict[str, Any] | None = None,
    consensus: Dict[str, Any] | None = None,
    hedge: Dict[str, Any] | None = None,
    execution_plan: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    view = view if isinstance(view, dict) else {}
    consensus = consensus if isinstance(consensus, dict) else {}
    hedge = hedge if isinstance(hedge, dict) else {}
    execution_plan = execution_plan if isinstance(execution_plan, dict) else {}

    ctx = view.get('ctx') if isinstance(view.get('ctx'), dict) else {}
    range_state = _s(ctx.get('range_state')).upper()
    at_mid = bool(ctx.get('at_mid')) or range_state == 'MID RANGE'

    long_grid = _s(view.get('long_grid') or payload.get('long_grid') or 'PAUSE').upper()
    short_grid = _s(view.get('short_grid') or payload.get('short_grid') or 'PAUSE').upper()
    confidence = _f(view.get('scenario_confidence') or payload.get('scenario_confidence'))
    impulse_text = _s(view.get('impulse_text') or payload.get('impulse_text')).upper()
    scenario_text = _s(view.get('scenario_text') or payload.get('scenario_text')).upper()
    blocked_side = _s(consensus.get('blocked_side') or 'NONE').upper()
    consensus_state = _s(consensus.get('consensus_state') or '').upper()
    aggression_modifier = _s(consensus.get('aggression_modifier') or '').upper()
    hedge_mode = _s(hedge.get('mode') or execution_plan.get('hedge_mode') or 'OFF').upper()
    grid_stress = _s(hedge.get('grid_stress') or execution_plan.get('grid_stress') or 'LOW').upper()
    effective_delta = _s(hedge.get('effective_delta') or execution_plan.get('effective_delta') or 'LOW').upper()
    entry_mode = _s(execution_plan.get('entry_mode') or 'NO_ENTRY').upper()
    side = _s(execution_plan.get('side') or 'NEUTRAL').upper()
    no_add_text = _s(execution_plan.get('no_add_text') or '').upper()
    no_entry_text = _s(execution_plan.get('no_entry_text') or '').upper()

    active_side = 'NEUTRAL'
    if side in {'LONG', 'SHORT'}:
        active_side = side
    elif long_grid in {'RUN', 'REDUCE', 'ARM'} and short_grid == 'PAUSE':
        active_side = 'LONG'
    elif short_grid in {'RUN', 'REDUCE', 'ARM'} and long_grid == 'PAUSE':
        active_side = 'SHORT'

    phase = 'IDLE'
    authority = 'NO_GRID'
    meaning = 'сетка не активна и не должна готовиться'
    action_text = 'не включать сетку'
    forbidden_text = 'не активировать сетку заранее'
    next_text = 'что переведёт фазу: подход к рабочему краю без блокировки контекстом'
    break_text = 'что ломает фазу: рынок остаётся вне рабочего grid-контекста'

    if at_mid and long_grid == 'PAUSE' and short_grid == 'PAUSE':
        phase = 'IDLE'
        authority = 'NO_GRID'
        meaning = 'середина диапазона; сетку рано даже готовить'
        action_text = 'ждать край диапазона'
        forbidden_text = 'не включать и не добирать из середины'
        next_text = 'что переведёт фазу: подход к рабочему краю + реакция без конфликта с master decision'
        break_text = 'что ломает фазу: дальнейшая жизнь в середине диапазона или trend pressure'
    elif entry_mode == 'NO_ENTRY' and active_side == 'NEUTRAL':
        phase = 'IDLE'
        authority = 'NO_GRID'
        meaning = 'сторона не разрешена; сетка не готовится'
        action_text = 'не включать сетку'
        forbidden_text = 'не открывать сетку без разрешённой стороны'
        next_text = 'что переведёт фазу: появление разрешённой стороны у рабочего края'
        break_text = 'что ломает фазу: block by consensus / отсутствие рабочего края'
    else:
        if long_grid == 'ARM' or short_grid == 'ARM' or (entry_mode in {'PROBE', 'CONFIRMED'} and not at_mid and active_side != 'NEUTRAL' and confidence >= 52):
            phase = 'ARM'
            authority = 'ARM_GRID'
            meaning = 'сетка у рабочего края и почти готова к активации'
            action_text = 'ждать подтверждающий триггер и включать только по рабочей реакции'
            forbidden_text = 'не форсировать сетку без реакции у края'
            next_text = 'что переведёт фазу: подтверждение реакции и разрешённый execution'
            break_text = 'что ломает фазу: уход от края, consensus block или потеря реакции'
        if active_side != 'NEUTRAL' and (long_grid == 'RUN' or short_grid == 'RUN'):
            phase = 'ACTIVE'
            authority = 'RUN_GRID'
            meaning = 'сетка разрешена и сопровождается как рабочая'
            action_text = 'вести сетку по сценарию'
            forbidden_text = 'не форсировать лишний добор без улучшения позиции'
            next_text = 'что переведёт фазу: рост стресса / запрет добора / ухудшение recovery'
            break_text = 'что ломает фазу: потеря сценария или подтверждённый слом структуры'
        if active_side != 'NEUTRAL' and (long_grid == 'REDUCE' or short_grid == 'REDUCE'):
            phase = 'REDUCE'
            authority = 'REDUCE_GRID'
            meaning = 'нагрузку сетки надо разгружать; приоритет снять часть риска'
            action_text = 'разгружать сетку и не возвращаться к агрессии'
            forbidden_text = 'не добирать и не возвращать старую агрессию без reset'
            next_text = 'что переведёт фазу: частичная разгрузка + стабилизация давления'
            break_text = 'что ломает фазу: продолжение давления и дальнейшая потеря контроля'

    if phase in {'ACTIVE', 'ARM'} and (('НЕ ДОБИРАТЬ' in no_add_text and confidence < 64) or aggression_modifier in {'REDUCE', 'LIGHT_REDUCE'}):
        phase = 'HOLD_ACTIVE'
        authority = 'HOLD_GRID'
        meaning = 'сетка ещё жива, но расширение уже надо ограничивать'
        action_text = 'держать рабочую сетку аккуратно, без свободного расширения'
        forbidden_text = 'не ухудшать среднюю и не набирать по инерции'
        next_text = 'что переведёт фазу: новое подтверждение удержания или возврат контроля'
        break_text = 'что ломает фазу: рост стресса, consensus pressure, ухудшение recovery'

    defend_trigger = (
        hedge_mode in {'WATCH', 'ARM', 'READY', 'ACTIVE_ADVISORY'}
        or grid_stress in {'HIGH', 'CRITICAL'}
        or effective_delta in {'HEAVY', 'CRITICAL'}
    )
    if phase in {'ACTIVE', 'HOLD_ACTIVE', 'ARM'} and defend_trigger:
        phase = 'DEFEND'
        authority = 'DEFEND_GRID'
        meaning = 'сетка под давлением; приоритет защиты выше расширения'
        action_text = 'не добирать, готовить защиту и следить за разгрузкой'
        forbidden_text = 'не усреднять ухудшение и не делать вид, что всё спокойно'
        next_text = 'что переведёт фазу: partial defense / снижение стресса / ослабление давления'
        break_text = 'что ломает фазу: дальнейший рост давления без recovery'

    if phase == 'DEFEND' and (hedge_mode == 'READY' or grid_stress == 'CRITICAL' or effective_delta == 'CRITICAL' or long_grid == 'REDUCE' or short_grid == 'REDUCE'):
        phase = 'REDUCE'
        authority = 'REDUCE_GRID'
        meaning = 'удержание как есть хуже, чем разгрузка части риска'
        action_text = 'снимать часть нагрузки, а не досиживать вслепую'
        forbidden_text = 'не возвращать add до восстановления контроля'
        next_text = 'что переведёт фазу: стабилизация после разгрузки и ослабление угрозы'
        break_text = 'что ломает фазу: сценарий окончательно ломается'

    exit_trigger = (
        _s(execution_plan.get('full_exit_text')).strip() not in {'', 'не применяется'}
        and hedge_mode in {'READY', 'ACTIVE_ADVISORY'}
        and grid_stress == 'CRITICAL'
        and confidence < 45
    )
    if exit_trigger or consensus_state == 'CONSENSUS_RISK_OFF' and confidence < 45 and active_side != 'NEUTRAL':
        phase = 'EXIT'
        authority = 'EXIT_GRID'
        meaning = 'сценарий потерял рабочее качество; сетку надо выводить из игры'
        action_text = 'выключать сетку / завершать сценарий'
        forbidden_text = 'не продолжать сопровождение как рабочее'
        next_text = 'что переведёт фазу: выход завершён, рынок сбрасывает токсичность'
        break_text = 'что ломает фазу: повторный запуск без reset'

    rearm_wait_trigger = phase == 'EXIT' or (phase == 'REDUCE' and confidence < 50 and blocked_side == active_side and active_side != 'NEUTRAL')
    if rearm_wait_trigger:
        phase = 'REARM_WAIT'
        authority = 'WAIT_REARM'
        meaning = 'после стресса или выхода повторно включать сетку рано'
        action_text = 'ждать reset рынка и не перезапускать сетку из упрямства'
        forbidden_text = 'не перезаходить сразу после срыва сценария'
        next_text = 'что переведёт фазу: стабилизация давления и возврат разрешённой стороны'
        break_text = 'что ломает фазу: новый токсичный импульс против сетки'

    if phase == 'REARM_WAIT' and hedge_mode in {'OFF', 'REDUCE', 'EXIT'} and grid_stress in {'LOW', 'MEDIUM'} and effective_delta in {'LOW', 'RISING'} and confidence >= 55 and blocked_side not in {active_side, 'BOTH'}:
        phase = 'REARM_READY'
        authority = 'REARM_ALLOWED'
        meaning = 'рынок reset-нулся достаточно, чтобы снова разрешить подготовку'
        action_text = 'разрешить новый prepare, но не форсировать активацию'
        forbidden_text = 'не считать это автоматическим новым входом'
        next_text = 'что переведёт фазу: новый подход к рабочему краю и новая реакция'
        break_text = 'что ломает фазу: возврат давления или новый consensus block'

    return {
        'phase': phase,
        'lifecycle_authority': authority,
        'active_side': active_side,
        'meaning_text': meaning,
        'action_text': action_text,
        'forbidden_text': forbidden_text,
        'next_text': next_text,
        'break_text': break_text,
        'grid_stress': grid_stress,
        'effective_delta': effective_delta,
        'hedge_mode': hedge_mode,
    }
