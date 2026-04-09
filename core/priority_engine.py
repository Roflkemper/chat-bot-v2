
from __future__ import annotations

from typing import Any, Dict, List


def _u(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip().upper()
    except Exception:
        return default


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def build_priority_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    execution = payload.get('execution') if isinstance(payload.get('execution'), dict) else {}
    setup = payload.get('setup_quality') if isinstance(payload.get('setup_quality'), dict) else {}
    range_bot = payload.get('range_volume_bot') if isinstance(payload.get('range_volume_bot'), dict) else {}
    trade_flow = payload.get('trade_flow') if isinstance(payload.get('trade_flow'), dict) else {}
    action = _u(decision.get('action_text') or decision.get('action') or payload.get('action_now') or 'WAIT', 'WAIT')
    direction = _u(decision.get('direction_text') or decision.get('direction') or payload.get('final_decision') or 'NEUTRAL', 'NEUTRAL')
    edge = _f(payload.get('edge_score') or decision.get('edge_score') or 0.0)
    setup_grade = _u(setup.get('grade') or payload.get('grade') or '')
    setup_status = _u(setup.get('setup_status_text') or payload.get('setup_status_text') or '')
    vr_status = _u(range_bot.get('status') or '')
    execution_state = _u(execution.get('permission') or execution.get('state') or payload.get('execution_state') or '')
    move_state = _u(trade_flow.get('status') or payload.get('trade_flow_status') or '')

    blocked = (
        edge <= 0.05
        or 'NO TRADE' in setup_grade
        or 'ПРОПУСТИТЬ' in setup_status
        or action in {'WAIT', 'ЖДАТЬ', 'WAIT_CONFIRMATION', 'ЖДАТЬ ПОДТВЕРЖДЕНИЕ'}
    )

    candidates: List[Dict[str, Any]] = []
    if blocked:
        candidates.append({'key': 'WAIT', 'score': 1.0, 'label': 'WAIT', 'reason': 'вход не авторизован'})
    else:
        candidates.append({'key': direction or 'NEUTRAL', 'score': max(0.2, edge), 'label': direction or 'NEUTRAL', 'reason': 'основной directional сценарий'})

    if vr_status in {'READY_SMALL', 'READY_SMALL_REDUCED', 'READY_NORMAL'} and not blocked:
        candidates.append({'key': 'RANGE_BOT', 'score': 0.75, 'label': 'RANGE BOT', 'reason': 'range-бот авторизован'})
    elif vr_status in {'WATCH_ONLY', 'WATCH', 'ARMING'}:
        candidates.append({'key': 'WATCH_RANGE', 'score': 0.45, 'label': 'WATCH RANGE', 'reason': 'наблюдать край диапазона'})

    if move_state in {'PARTIAL_NOW', 'EXIT ON WEAKNESS', 'FULL_EXIT_NOW'}:
        candidates.append({'key': 'MANAGE_POSITION', 'score': 0.95, 'label': 'MANAGE POSITION', 'reason': 'приоритет ведения позиции выше нового входа'})

    candidates.sort(key=lambda x: x.get('score', 0.0), reverse=True)
    top = candidates[0] if candidates else {'key': 'WAIT', 'score': 1.0, 'label': 'WAIT', 'reason': 'нет рабочего сценария'}
    return {
        'main_priority': top.get('key', 'WAIT'),
        'main_label': top.get('label', 'WAIT'),
        'main_reason': top.get('reason', 'нет рабочего сценария'),
        'blocked': blocked,
        'candidates': candidates[:5],
        'execution_state': execution_state or ('BLOCKED' if blocked else 'ACTIVE'),
    }
