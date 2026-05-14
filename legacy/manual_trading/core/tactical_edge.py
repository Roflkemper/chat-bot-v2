from __future__ import annotations

from typing import Any, Dict


def _u(value: Any) -> str:
    return str(value or '').upper()


def build_tactical_edge(payload: Dict[str, Any], execution: Dict[str, Any] | None = None,
                        fast_move: Dict[str, Any] | None = None,
                        fake: Dict[str, Any] | None = None,
                        proj: Dict[str, Any] | None = None,
                        trade_flow: Dict[str, Any] | None = None) -> Dict[str, Any]:
    execution = execution or {}
    fast_move = fast_move or {}
    fake = fake or {}
    proj = proj or {}
    trade_flow = trade_flow or {}

    range_pos = _u(payload.get('range_position'))
    action_now = str(execution.get('action_now') or payload.get('action_text') or 'ЖДАТЬ')
    trigger = execution.get('confirm_trigger') or 'ждать подтверждение'
    invalidation = execution.get('invalidation') or proj.get('invalidation') or 'нет данных'
    zone = execution.get('entry_zone') or proj.get('target_zone') or 'нет данных'

    fm_class = _u(fast_move.get('classification'))
    acceptance = _u(fast_move.get('acceptance_state'))
    fake_type = _u(fake.get('type'))
    flow_state = _u(trade_flow.get('continuation_state'))
    mgmt_state = _u(trade_flow.get('management_state'))
    proj_side = _u(proj.get('side'))

    posture = 'WAIT'
    entry = 'ждать край или retest'
    risk = 'не гнаться за свечой'
    next_trigger = trigger
    note = execution.get('comment') or fast_move.get('tactical_plan') or fake.get('action') or 'нет данных'

    if 'FAKE' in fake_type or 'EARLY_FAKE' in fm_class or 'POSSIBLE_FALSE_BREAK' in flow_state:
        posture = 'FADE_SETUP'
        if 'UP' in fake_type or 'UP' in fm_class:
            entry = 'шорт только после слабого возврата под зону выноса'
            risk = 'не шортить первую сильную свечу вверх'
        elif 'DOWN' in fake_type or 'DOWN' in fm_class:
            entry = 'лонг только после reclaim обратно над зону выноса'
            risk = 'не ловить нож на первой красной свече'
        next_trigger = fake.get('action') or trigger
    elif 'ACCEPTED' in acceptance or 'ACCEPTANCE' in fm_class or 'CONTINUATION' in fm_class or flow_state in {'ALIVE', 'ALIVE_BUT_LATE'}:
        posture = 'CONTINUATION'
        if proj_side == 'SHORT' or 'DOWN' in fm_class:
            entry = 'приоритет вниз, вход только на retest'
            risk = 'не добирать шорт внизу без отката'
        else:
            entry = 'приоритет вверх, вход только на retest'
            risk = 'лонг в догонку плохой'
        next_trigger = fast_move.get('watch_text') or trigger
    elif 'EXHAUST' in fm_class or flow_state == 'FADING' or mgmt_state in {'REDUCE', 'PROTECT', 'EXIT'}:
        posture = 'EXHAUSTION'
        entry = 'скорее partial / reduce, чем новый вход'
        risk = 'не расширять риск на уставшем движении'
        next_trigger = trade_flow.get('reversal_triggers') or trigger
    elif range_pos == 'MID' or 'ЖДАТЬ' in action_now.upper():
        posture = 'NO_CHASE'
        entry = 'из середины диапазона лучше не входить'
        risk = 'шум съедает RR'

    summary_map = {
        'FADE_SETUP': 'похоже на ловушку: работаем только после подтверждённого возврата',
        'CONTINUATION': 'движение ещё живо, но вход только на retest без погони',
        'EXHAUSTION': 'импульс выдыхается: приоритет защита и частичная фиксация',
        'NO_CHASE': 'сейчас нет чистого тактического входа',
        'WAIT': 'нужен более чистый сетап',
    }

    return {
        'posture': posture,
        'summary': summary_map.get(posture, 'нужен более чистый сетап'),
        'entry': entry,
        'risk': risk,
        'next_trigger': next_trigger,
        'invalidation': invalidation,
        'zone': zone,
        'note': note,
    }
