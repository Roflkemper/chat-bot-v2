from __future__ import annotations

from typing import Any, Dict, List


def _fmt_price(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return "n/a"


def _current_context(snapshot: Dict[str, Any]) -> str:
    parts: List[str] = []
    context_label = str(snapshot.get('context_label') or '').upper()
    context_score = int(snapshot.get('context_score') or 0)
    if context_label:
        parts.append(f"контекст {context_label} ({context_score}/3)")

    trigger_blocked = bool(snapshot.get('trigger_blocked'))
    if trigger_blocked:
        reason = str(snapshot.get('trigger_block_reason') or 'сигнал заблокирован')
        parts.append(f"trigger заблокирован: {reason}")
    else:
        trigger_type = str(snapshot.get('trigger_type') or 'NONE').upper()
        if trigger_type not in {'', 'NONE'}:
            parts.append(f"trigger {trigger_type} подтверждён")
        else:
            parts.append("trigger не подтверждён")

    block_pressure = str(snapshot.get('block_pressure') or 'NONE').upper()
    pressure_strength = str(snapshot.get('block_pressure_strength') or 'LOW').upper()
    if block_pressure == 'AGAINST':
        parts.append(f"давление против блока ({pressure_strength})")
    elif block_pressure == 'WITH':
        parts.append(f"блок поддержан локальным флоу ({pressure_strength})")

    return '; '.join(parts[:3]) if parts else 'контекст уточняется'


def _fallback_text(snapshot: Dict[str, Any], action: str, side: str) -> str:
    trigger_blocked = bool(snapshot.get('trigger_blocked'))
    if action == 'WAIT':
        if trigger_blocked:
            return 'оставаться в WAIT, не форсировать вход и ждать новый trigger'
        return 'сохранить режим наблюдения и дождаться подтверждения сценария'
    if action == 'PREPARE':
        return 'если вход не подтверждается, откатиться в WAIT и не усиливать позицию'
    if action == 'ENTER':
        return f'если после входа нет продолжения в сторону {side}, перейти к защите/частичному выходу'
    if action == 'EXIT':
        return 'после выхода не переоткрываться до нового чистого сценария'
    return 'ждать пересборку контекста без догонки'



def _primary_action(snapshot: Dict[str, Any]) -> str:
    action = str(snapshot.get('action') or 'WAIT').upper()
    if action in {'WAIT', 'PREPARE', 'ENTER', 'EXIT', 'PROTECT'}:
        return 'EXIT' if action == 'PROTECT' else action
    return 'WAIT'



def _primary_entry(snapshot: Dict[str, Any], side: str) -> str:
    break_level = snapshot.get('break_level')
    price = snapshot.get('price')
    range_mid = snapshot.get('range_mid')
    action = _primary_action(snapshot)
    if action == 'ENTER':
        if price is not None:
            return f"вход по рынку рядом с {_fmt_price(price)}"
        return 'вход по рынку после подтверждения'
    if action == 'PREPARE':
        return f"подготовить вход у уровня {_fmt_price(break_level if side != snapshot.get('active_block') else price)}"
    if action == 'EXIT':
        return f"выход/сокращение при потере {_fmt_price(break_level)}"
    if range_mid is not None:
        return f"вход не разрешён; следить за реакцией вокруг {_fmt_price(range_mid)}"
    return 'вход не разрешён'



def _primary_invalidation(snapshot: Dict[str, Any], side: str) -> str:
    active_block = str(snapshot.get('active_block') or 'NONE').upper()
    range_low = snapshot.get('range_low')
    range_high = snapshot.get('range_high')
    trigger_blocked = bool(snapshot.get('trigger_blocked'))
    if trigger_blocked:
        reason = str(snapshot.get('trigger_block_reason') or 'контекст не собран')
        return f"сценарий не активен: {reason}"
    if side == 'LONG' and range_low is not None:
        return f"закрепление ниже {_fmt_price(range_low)} ломает long-сценарий"
    if side == 'SHORT' and range_high is not None:
        return f"закрепление выше {_fmt_price(range_high)} ломает short-сценарий"
    if active_block == 'SHORT' and range_high is not None:
        return f"закрепление выше {_fmt_price(range_high)} ломает блок отбоя"
    if active_block == 'LONG' and range_low is not None:
        return f"закрепление ниже {_fmt_price(range_low)} ломает блок отбоя"
    return 'без активной стороны нет рабочей invalidation-зоны'



def _build_primary_scenario(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    action = _primary_action(snapshot)
    active_block = str(snapshot.get('active_block') or 'NONE').upper()
    execution_side = str(snapshot.get('execution_side') or active_block or 'NONE').upper()
    side = execution_side if execution_side in {'LONG', 'SHORT'} else active_block

    if action == 'WAIT':
        side = active_block if active_block in {'LONG', 'SHORT'} else side
    elif action == 'EXIT':
        side = execution_side if execution_side in {'LONG', 'SHORT'} else active_block

    zone_text = (
        f"цена в зоне {_fmt_price(snapshot.get('range_low'))}–{_fmt_price(snapshot.get('range_high'))}"
        if snapshot.get('range_low') is not None and snapshot.get('range_high') is not None
        else 'цена в рабочей зоне'
    )

    trigger_type = str(snapshot.get('trigger_type') or 'NONE').upper()
    trigger_text = 'есть подтверждённый trigger' if trigger_type not in {'', 'NONE'} and not snapshot.get('trigger_blocked') else 'нет рабочего trigger'
    if action == 'PREPARE':
        trigger_text = f"есть {trigger_type} и вход ещё не подтверждён" if trigger_type not in {'', 'NONE'} else 'нужен trigger'
    elif action == 'ENTER':
        trigger_text = f"есть {trigger_type} и условия входа собраны" if trigger_type not in {'', 'NONE'} else 'условия входа собраны'
    elif action == 'EXIT':
        trigger_text = 'потерян рабочий импульс / нужен защитный выход'

    return {
        'name': 'PRIMARY',
        'side': side if side in {'LONG', 'SHORT'} else 'NONE',
        'if_zone': zone_text,
        'if_trigger': trigger_text,
        'if_context': _current_context(snapshot),
        'then_action': action,
        'then_entry': _primary_entry(snapshot, side),
        'then_invalidation': _primary_invalidation(snapshot, side),
        'then_fallback': _fallback_text(snapshot, action, side),
    }



def _build_flip_scenario(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    active_block = str(snapshot.get('active_block') or 'NONE').upper()
    watch_side = str(snapshot.get('watch_side') or 'NONE').upper()
    if watch_side not in {'LONG', 'SHORT'}:
        watch_side = 'LONG' if active_block == 'SHORT' else 'SHORT' if active_block == 'LONG' else 'NONE'

    break_level = snapshot.get('break_level')
    confirm_bars = int(snapshot.get('flip_prep_confirm_bars_needed') or 2)
    status = str(snapshot.get('flip_prep_status') or 'IDLE').upper()
    pressure = str(snapshot.get('block_pressure') or 'NONE').upper()
    pressure_strength = str(snapshot.get('block_pressure_strength') or 'LOW').upper()

    if active_block == 'SHORT':
        zone_text = f"цена подходит к верхней границе {_fmt_price(break_level)}"
        trigger_text = f"закрытие выше {_fmt_price(break_level)} ({confirm_bars} бара)"
        invalidation_text = f"возврат обратно под {_fmt_price(break_level)} отменяет flip в LONG"
    elif active_block == 'LONG':
        zone_text = f"цена подходит к нижней границе {_fmt_price(break_level)}"
        trigger_text = f"закрытие ниже {_fmt_price(break_level)} ({confirm_bars} бара)"
        invalidation_text = f"возврат обратно выше {_fmt_price(break_level)} отменяет flip в SHORT"
    else:
        zone_text = 'цена у граничного уровня'
        trigger_text = 'нужен пробой и удержание'
        invalidation_text = 'возврат в диапазон отменяет flip'

    context_bits = [f"flip status: {status}"]
    if pressure == 'AGAINST':
        context_bits.append(f"давление против блока ({pressure_strength})")
    consensus_direction = str(snapshot.get('consensus_direction') or 'NONE').upper()
    if consensus_direction == watch_side:
        context_bits.append(f"consensus поддерживает {watch_side}")

    return {
        'name': 'FLIP',
        'side': watch_side,
        'if_zone': zone_text,
        'if_trigger': trigger_text,
        'if_context': '; '.join(context_bits[:3]),
        'then_action': 'PREPARE' if status in {'WATCHING', 'ARMED', 'IDLE'} else 'ENTER',
        'then_entry': f"вход по стороне {watch_side} только после удержания за {_fmt_price(break_level)}",
        'then_invalidation': invalidation_text,
        'then_fallback': 'если пробой не удержался, вернуть сценарий в WAIT и работать от текущего блока',
    }



def _scenario_to_lines(scenario: Dict[str, Any]) -> List[str]:
    name = str(scenario.get('name') or 'SCENARIO').upper()
    return [
        f"• {name}",
        f"  IF: {scenario.get('if_zone')}",
        f"  IF: {scenario.get('if_trigger')}",
        f"  IF: {scenario.get('if_context')}",
        f"  THEN: действие {scenario.get('then_action')}",
        f"  THEN: вход {scenario.get('then_entry')}",
        f"  THEN: invalidation {scenario.get('then_invalidation')}",
        f"  THEN: если не реализовалось — {scenario.get('then_fallback')}",
    ]



def build_if_then_plan(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    primary = _build_primary_scenario(snapshot)
    flip = _build_flip_scenario(snapshot)
    scenarios = [primary, flip]
    lines: List[str] = []
    for idx, scenario in enumerate(scenarios):
        if idx:
            lines.append('')
        lines.extend(_scenario_to_lines(scenario))

    return {
        'layer': 'IF_THEN_PLAN',
        'scenarios': scenarios,
        'lines': lines,
    }
