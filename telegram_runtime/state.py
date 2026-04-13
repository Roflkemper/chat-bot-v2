from __future__ import annotations

from typing import Any, Dict

from utils.safe_io import atomic_write_json, safe_read_json

STATE_FILE = 'state/telegram_runtime_state.json'


def _default_state() -> Dict[str, Any]:
    return {
        'subscribed_chat_ids': [],
        'alerts_enabled_by_chat': {},
        'last_alert_text_by_chat': {},
    }


def load_runtime_state() -> Dict[str, Any]:
    return safe_read_json(STATE_FILE, _default_state())


def save_runtime_state(state: Dict[str, Any]) -> None:
    base = _default_state()
    if isinstance(state, dict):
        base.update(state)
    atomic_write_json(STATE_FILE, base)


def ensure_chat_registered(chat_id: int, *, default_alerts_enabled: bool = True) -> Dict[str, Any]:
    state = load_runtime_state()
    subs = {str(v) for v in state.get('subscribed_chat_ids') or []}
    sid = str(int(chat_id))
    subs.add(sid)
    state['subscribed_chat_ids'] = sorted(subs)
    flags = state.get('alerts_enabled_by_chat') or {}
    flags.setdefault(sid, bool(default_alerts_enabled))
    state['alerts_enabled_by_chat'] = flags
    save_runtime_state(state)
    return state


def set_alerts_enabled(chat_id: int, enabled: bool) -> Dict[str, Any]:
    state = ensure_chat_registered(chat_id)
    flags = state.get('alerts_enabled_by_chat') or {}
    flags[str(int(chat_id))] = bool(enabled)
    state['alerts_enabled_by_chat'] = flags
    save_runtime_state(state)
    return state


def alerts_enabled(chat_id: int) -> bool:
    state = ensure_chat_registered(chat_id)
    flags = state.get('alerts_enabled_by_chat') or {}
    return bool(flags.get(str(int(chat_id)), True))


def iter_alert_chat_ids() -> list[int]:
    state = load_runtime_state()
    subs = state.get('subscribed_chat_ids') or []
    flags = state.get('alerts_enabled_by_chat') or {}
    out: list[int] = []
    for raw in subs:
        sid = str(raw)
        if not flags.get(sid, True):
            continue
        try:
            out.append(int(sid))
        except Exception:
            continue
    return out


def last_alert_text(chat_id: int) -> str:
    state = load_runtime_state()
    bag = state.get('last_alert_text_by_chat') or {}
    return str(bag.get(str(int(chat_id))) or '')


def set_last_alert_text(chat_id: int, text: str) -> None:
    state = load_runtime_state()
    bag = state.get('last_alert_text_by_chat') or {}
    bag[str(int(chat_id))] = str(text or '')
    state['last_alert_text_by_chat'] = bag
    save_runtime_state(state)
