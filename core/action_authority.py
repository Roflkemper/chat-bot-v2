from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


def _u(value: Any) -> str:
    return str(value or '').strip().upper()


def _s(value: Any, default: str = '') -> str:
    text = str(value or '').strip()
    return text or default


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except Exception:
        return default


BLOCK_ACTIONS = {'WAIT', 'NO_TRADE', 'WATCH', 'WAIT_CONFIRM', 'WAIT_CONFIRMATION', 'WAIT_PULLBACK', 'WAIT_RANGE_EDGE'}
BLOCK_ENTRY_TYPES = {'NO ENTRY', 'БЕЗ ВХОДА', 'NO_TRADE', 'WAIT_CONFIRM'}


@dataclass
class ActionAuthority:
    direction: str = 'NEUTRAL'
    direction_text: str = 'НЕЙТРАЛЬНО'
    bias_confidence: float = 0.0
    edge_score: float = 0.0
    entry_allowed: bool = False
    executable: bool = False
    state: str = 'WAIT'
    state_text: str = 'ЖДАТЬ'
    entry_type: str = 'БЕЗ ВХОДА'
    setup_status: str = 'WAIT'
    setup_grade: str = 'NO TRADE'
    manager_action: str = 'WAIT'
    manager_action_text: str = 'ЖДАТЬ'
    invalidation: str = 'нет данных'
    reason: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'direction': self.direction,
            'direction_text': self.direction_text,
            'bias_confidence': self.bias_confidence,
            'edge_score': self.edge_score,
            'entry_allowed': self.entry_allowed,
            'executable': self.executable,
            'state': self.state,
            'state_text': self.state_text,
            'entry_type': self.entry_type,
            'setup_status': self.setup_status,
            'setup_grade': self.setup_grade,
            'manager_action': self.manager_action,
            'manager_action_text': self.manager_action_text,
            'invalidation': self.invalidation,
            'reason': self.reason,
        }


def build_action_authority(data: Dict[str, Any] | None, journal: Dict[str, Any] | None = None) -> ActionAuthority:
    payload = data if isinstance(data, dict) else {}
    journal = journal if isinstance(journal, dict) else {}
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    setup = payload.get('setup_quality') if isinstance(payload.get('setup_quality'), dict) else {}
    execution_verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else {}

    direction = _u(decision.get('direction') or payload.get('final_decision') or payload.get('forecast_direction')) or 'NEUTRAL'
    direction_text = _s(decision.get('direction_text') or direction, 'НЕЙТРАЛЬНО')
    bias_confidence = max(
        _f(decision.get('confidence_pct')),
        _f(decision.get('confidence')),
        _f(payload.get('bias_confidence')),
    )
    edge_score = max(
        _f(decision.get('edge_score')),
        _f(execution_verdict.get('entry_score')),
        _f(payload.get('entry_score')),
    )

    setup_grade = _s(setup.get('grade') or execution_verdict.get('setup_grade') or decision.get('setup_status') or 'NO TRADE', 'NO TRADE')
    setup_status = _s(setup.get('setup_status_text') or decision.get('setup_status_text') or decision.get('action_text') or 'ЖДАТЬ', 'ЖДАТЬ')
    entry_type = _s(
        setup.get('entry_type')
        or execution_verdict.get('entry_type')
        or decision.get('entry_type')
        or payload.get('entry_type')
        or 'БЕЗ ВХОДА',
        'БЕЗ ВХОДА',
    )
    decision_action = _u(decision.get('action') or '')
    decision_action_text = _s(decision.get('action_text') or 'ЖДАТЬ', 'ЖДАТЬ')
    manager_action = _u(decision.get('manager_action') or decision_action or 'WAIT')
    manager_action_text = _s(decision.get('manager_action_text') or decision_action_text or 'ЖДАТЬ', 'ЖДАТЬ')
    invalidation = _s(setup.get('invalidation') or decision.get('invalidation') or payload.get('invalidation') or 'нет данных', 'нет данных')

    setup_valid = bool(
        setup.get('setup_valid')
        if setup.get('setup_valid') is not None else execution_verdict.get('setup_valid')
    )
    trade_authorized = bool(
        payload.get('trade_authorized')
        if payload.get('trade_authorized') is not None else decision.get('trade_authorized')
    )
    has_open_trade = bool(journal.get('has_active_trade') or journal.get('active') or journal.get('trade_id'))

    entry_allowed = (
        direction not in {'NEUTRAL', 'NONE', ''}
        and trade_authorized
        and setup_valid
        and _u(entry_type) not in BLOCK_ENTRY_TYPES
        and decision_action not in BLOCK_ACTIONS
    )
    executable = entry_allowed and not has_open_trade

    if has_open_trade:
        state = 'MANAGE'
        state_text = manager_action_text or 'ВЕСТИ ПОЗИЦИЮ'
        reason = 'есть активная сделка — приоритет ведение, а не новый вход'
    elif executable:
        state = 'EXECUTABLE'
        state_text = decision_action_text or 'ВХОДИТЬ'
        reason = 'сетап подтверждён и вход разрешён'
    elif direction not in {'NEUTRAL', 'NONE', ''} and bias_confidence >= 55.0:
        state = 'PRE_SETUP'
        state_text = 'ЖДАТЬ ПОДТВЕРЖДЕНИЕ'
        reason = 'направление есть, но execution ещё не разрешён'
    else:
        state = 'WAIT'
        state_text = 'ЖДАТЬ'
        reason = 'чистого edge нет'

    return ActionAuthority(
        direction=direction,
        direction_text=direction_text,
        bias_confidence=bias_confidence,
        edge_score=edge_score,
        entry_allowed=entry_allowed,
        executable=executable,
        state=state,
        state_text=state_text,
        entry_type=entry_type,
        setup_status=setup_status,
        setup_grade=setup_grade,
        manager_action=manager_action,
        manager_action_text=manager_action_text,
        invalidation=invalidation,
        reason=reason,
    )
