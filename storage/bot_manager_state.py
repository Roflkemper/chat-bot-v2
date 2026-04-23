from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Tuple

from utils.safe_io import atomic_write_json, safe_read_json

BOT_MANAGER_STATE_FILE = "state/bot_manager_state.json"

BOT_KEY_ALIASES = {
    "CT LONG": "ct_long",
    "CT SHORT": "ct_short",
    "RANGE LONG": "range_long",
    "RANGE SHORT": "range_short",
}

MANUAL_ACTION_ALIASES = {
    "ON": "ACTIVE",
    "ACTIVE": "ACTIVE",
    "SMALL": "SMALL",
    "AGGRESSIVE": "AGGRESSIVE",
    "ADD": "ADD",
    "PARTIAL": "PARTIAL",
    "EXIT": "EXIT",
    "CANCEL": "CANCEL",
    "RESET": "RESET",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_manual_state() -> Dict[str, Any]:
    return {
        "override": False,
        "phase": "",
        "action": "",
        "size_hint": "",
        "position_open": False,
        "adds_done": 0,
        "partial_exit_done": False,
        "updated_at": None,
        "note": "",
    }


def _default_bot_state() -> Dict[str, Any]:
    return {
        "phase": "IDLE",
        "last_action": "WAIT",
        "entry_mode": "WAIT",
        "size_hint": "NONE",
        "position_open": False,
        "adds_used": 0,
        "max_adds": 2,
        "updated_at": None,
        "note": "",
        "last_score": 0.0,
        "manual": _default_manual_state(),
    }


def _default_state() -> Dict[str, Any]:
    return {
        "version": 2,
        "updated_at": None,
        "bots": {
            "ct_long": _default_bot_state(),
            "ct_short": _default_bot_state(),
            "range_long": _default_bot_state(),
            "range_short": _default_bot_state(),
        },
    }


def _merge_bot_state(value: Dict[str, Any] | None) -> Dict[str, Any]:
    bot_state = dict(_default_bot_state())
    if isinstance(value, dict):
        bot_state.update({k: v for k, v in value.items() if k != 'manual'})
        manual = dict(_default_manual_state())
        if isinstance(value.get('manual'), dict):
            manual.update(value['manual'])
        bot_state['manual'] = manual
    return bot_state


def load_bot_manager_state() -> Dict[str, Any]:
    state = safe_read_json(BOT_MANAGER_STATE_FILE, _default_state())
    bots = state.get("bots")
    if not isinstance(bots, dict):
        bots = {}
    merged_bots: Dict[str, Any] = {}
    for key in _default_state()["bots"].keys():
        merged_bots[key] = _merge_bot_state(bots.get(key))
    state["bots"] = merged_bots
    return state


def save_bot_manager_state(state: Dict[str, Any]) -> None:
    payload = _default_state()
    if isinstance(state, dict):
        payload.update({k: v for k, v in state.items() if k != "bots"})
        incoming_bots = state.get("bots") if isinstance(state.get("bots"), dict) else {}
        payload["bots"] = {}
        for key in _default_state()["bots"].keys():
            payload["bots"][key] = _merge_bot_state(incoming_bots.get(key))
    payload["updated_at"] = _now()
    atomic_write_json(BOT_MANAGER_STATE_FILE, payload)


def _phase_from_action(action: str, is_active: bool, adds_used: int, score: float) -> str:
    a = str(action or "WAIT").upper()
    if a == "CANCEL SCENARIO":
        return "WATCH" if not is_active and score >= 0.20 else "CANCELLED"
    if a == "CAUTIOUS EXIT":
        return "CAUTIOUS_EXIT"
    if a == "WAIT EDGE":
        return "WAIT_EDGE"
    if a in {"ENABLE SMALL SIZE", "ENABLE SMALL SIZE REDUCED"}:
        return "SOFT_READY" if not is_active else "ACTIVE"
    if a in {"AGGRESSIVE ENTRY", "ENABLE / CAN ADD"}:
        if not is_active:
            return "ACTIVE"
        if a == "ENABLE / CAN ADD" and adds_used < 2:
            return "ADD_READY"
        return "ACTIVE"
    if score >= 0.45:
        return "WATCH"
    return "IDLE"


def _size_hint(plan_state: str, action: str) -> str:
    p = str(plan_state or "WAIT").upper()
    a = str(action or "WAIT").upper()
    if a == "AGGRESSIVE ENTRY" or p == "AGGRESSIVE ENTRY":
        return "AGGRESSIVE"
    if a in {"ENABLE / CAN ADD", "CAN ADD"} or p == "CAN ADD":
        return "ADD"
    if a in {"ENABLE SMALL SIZE", "ENABLE SMALL SIZE REDUCED"} or p in {"SMALL ENTRY", "READY_SMALL", "READY_SMALL_REDUCED"}:
        return "SMALL_REDUCED" if a == "ENABLE SMALL SIZE REDUCED" or p == "READY_SMALL_REDUCED" else "SMALL"
    if a == "CAUTIOUS EXIT":
        return "REDUCE"
    return "NONE"


def _apply_manual_overlay(updated: Dict[str, Any]) -> Dict[str, Any]:
    manual = updated.get('manual') if isinstance(updated.get('manual'), dict) else _default_manual_state()
    if not manual.get('override'):
        return updated
    if manual.get('phase'):
        updated['phase'] = manual.get('phase')
    if manual.get('action'):
        updated['last_action'] = manual.get('action')
    if manual.get('size_hint'):
        updated['size_hint'] = manual.get('size_hint')
    updated['position_open'] = bool(manual.get('position_open'))
    updated['adds_used'] = max(int(updated.get('adds_used') or 0), int(manual.get('adds_done') or 0))
    if manual.get('note'):
        updated['note'] = str(manual.get('note'))
    updated['manual_override'] = True
    return updated


def sync_bot_manager(bot_cards: list[dict[str, Any]]) -> Dict[str, Any]:
    state = load_bot_manager_state()
    bots = state.get("bots") or {}

    for card in bot_cards:
        key = str(card.get("bot_key") or "").strip()
        if not key:
            continue
        current = _merge_bot_state(bots.get(key))
        score = float(card.get("score") or 0.0)
        action = str(card.get("management_action") or "WAIT")
        plan_state = str(card.get("plan_state") or "WAIT")
        status = str(card.get("status") or "OFF").upper()
        is_active = bool(current.get("position_open"))
        adds_used = int(current.get("adds_used") or 0)

        if action == "CANCEL SCENARIO" and status == "OFF" and plan_state not in {"READY_SMALL", "READY_SMALL_REDUCED"}:
            updated = _default_bot_state()
            updated['manual'] = current.get('manual') if isinstance(current.get('manual'), dict) else _default_manual_state()
            updated.update({
                "phase": "WATCH" if action == "CANCEL SCENARIO" else "IDLE",
                "last_action": action if action != "WAIT" else "WAIT",
                "entry_mode": plan_state,
                "size_hint": _size_hint(plan_state, action),
                "position_open": False,
                "adds_used": 0,
                "updated_at": _now(),
                "note": str(card.get("exit_instruction") or card.get("note") or "").strip(),
                "last_score": round(score, 3),
            })
            updated = _apply_manual_overlay(updated)
            bots[key] = updated
            card["manager_state"] = updated
            continue

        updated = _default_bot_state()
        updated.update({k: v for k, v in current.items() if k != 'manual'})
        updated['manual'] = current.get('manual') if isinstance(current.get('manual'), dict) else _default_manual_state()
        next_phase = _phase_from_action(action, is_active, adds_used, score)
        size_hint = _size_hint(plan_state, action)

        if next_phase == "ACTIVE" and not is_active:
            updated["position_open"] = True
        elif next_phase in {"CAUTIOUS_EXIT", "WAIT_EDGE", "SOFT_READY", "WATCH"}:
            updated["position_open"] = bool(current.get("position_open"))
        elif next_phase == "CANCELLED":
            updated["position_open"] = False
            updated["adds_used"] = 0

        if next_phase == "ADD_READY" and updated.get("position_open"):
            updated["adds_used"] = min(int(updated.get("adds_used") or 0) + 1, int(updated.get("max_adds") or 2))
        elif next_phase == "ACTIVE" and not current.get("position_open"):
            updated["adds_used"] = 0

        updated.update({
            "phase": next_phase,
            "last_action": action,
            "entry_mode": plan_state,
            "size_hint": size_hint,
            "updated_at": _now(),
            "note": str(card.get("entry_instruction") or card.get("exit_instruction") or card.get("note") or "").strip(),
            "last_score": round(score, 3),
        })
        updated = _apply_manual_overlay(updated)
        bots[key] = updated
        card["manager_state"] = updated

    state["bots"] = bots
    save_bot_manager_state(state)
    return state


def parse_manual_bot_command(text: str) -> Tuple[str | None, str | None]:
    normalized = ' '.join(str(text or '').strip().upper().split())
    if not normalized.startswith('BOT '):
        return None, None
    rest = normalized[4:]
    action = None
    bot_key = None
    for alias, key in BOT_KEY_ALIASES.items():
        prefix = alias + ' '
        if rest.startswith(prefix):
            bot_key = key
            action = MANUAL_ACTION_ALIASES.get(rest[len(prefix):].strip())
            break
    return bot_key, action


def apply_manual_bot_action(bot_key: str, action: str) -> Dict[str, Any]:
    state = load_bot_manager_state()
    bots = state.get('bots') or {}
    current = _merge_bot_state(bots.get(bot_key))
    manual = dict(current.get('manual') or _default_manual_state())
    action = str(action or '').upper()

    if action == 'RESET':
        manual = _default_manual_state()
    elif action == 'CANCEL':
        manual.update({'override': True, 'phase': 'CANCELLED', 'action': 'CANCEL SCENARIO', 'size_hint': 'NONE', 'position_open': False, 'adds_done': 0, 'partial_exit_done': False, 'note': 'сценарий отменён вручную', 'updated_at': _now()})
    elif action == 'EXIT':
        manual.update({'override': True, 'phase': 'CAUTIOUS_EXIT', 'action': 'CAUTIOUS EXIT', 'size_hint': 'REDUCE', 'position_open': True, 'note': 'осторожный выход / сопровождение включён вручную', 'updated_at': _now()})
    elif action == 'PARTIAL':
        manual.update({'override': True, 'phase': 'CAUTIOUS_EXIT', 'action': 'PARTIAL EXIT', 'size_hint': 'REDUCE', 'position_open': True, 'partial_exit_done': True, 'note': 'частичный выход отмечен вручную', 'updated_at': _now()})
    elif action == 'ADD':
        manual.update({'override': True, 'phase': 'ADD_READY', 'action': 'CAN ADD', 'size_hint': 'ADD', 'position_open': True, 'adds_done': int(manual.get('adds_done') or 0) + 1, 'note': 'добор подтверждён вручную', 'updated_at': _now()})
    elif action == 'AGGRESSIVE':
        manual.update({'override': True, 'phase': 'ACTIVE', 'action': 'AGGRESSIVE ENTRY', 'size_hint': 'AGGRESSIVE', 'position_open': True, 'note': 'агрессивный вход подтверждён вручную', 'updated_at': _now()})
    elif action == 'SMALL':
        manual.update({'override': True, 'phase': 'ACTIVE', 'action': 'SMALL ENTRY', 'size_hint': 'SMALL', 'position_open': True, 'note': 'небольшая позиция открыта вручную', 'updated_at': _now()})
    elif action == 'ACTIVE':
        manual.update({'override': True, 'phase': 'ACTIVE', 'action': 'ACTIVE', 'size_hint': manual.get('size_hint') or 'BASE', 'position_open': True, 'note': 'бот включён вручную', 'updated_at': _now()})
    else:
        raise ValueError('unknown manual action')

    current['manual'] = manual
    bots[bot_key] = current
    state['bots'] = bots
    save_bot_manager_state(state)
    return state




def format_bot_manager_status(state: Dict[str, Any] | None = None) -> str:
    state = state or load_bot_manager_state()
    lines = ['🤖 СТАТУС БОТОВ', '']
    for alias, key in BOT_KEY_ALIASES.items():
        bot = _merge_bot_state((state.get('bots') or {}).get(key))
        manual = bot.get('manual') or {}
        phase = str(bot.get('phase') or 'IDLE').upper()
        position_open = bool(bot.get('position_open'))
        display_phase = {
            'SOFT_READY':'НАБЛЮДЕНИЕ', 'WATCH_ONLY':'НЕ АКТИВИРОВАТЬ', 'WAIT_EDGE':'ЖДАТЬ КРАЙ',
            'CANCELLED':'ОТМЕНЁН', 'ACTIVE':'АКТИВЕН', 'ADD_READY':'ГОТОВ ДОБОР',
            'WATCH':'НАБЛЮДЕНИЕ', 'IDLE':'НЕ АКТИВИРОВАТЬ', 'CAUTIOUS_EXIT':'ВЫХОД / СОПРОВОЖДЕНИЕ'
        }.get(phase, phase)
        if not position_open and display_phase in {'АКТИВЕН', 'ГОТОВ ДОБОР'}:
            display_phase = 'НАБЛЮДЕНИЕ'
        lines.append(f'• {alias}: {display_phase}')
        if manual.get('override'):
            lines.append(f'  - ручной режим: {manual.get("action") or manual.get("phase") or "override"}')
        note = str(bot.get('note') or '').strip()
        if note:
            lowered = note.lower()
            if any(x in lowered for x in ['none', 'открыта нет', 'размер none']):
                note = ''
        if note:
            lines.append(f'  - {note}')
    lines.extend(['', 'Команды для ручного ведения:', '• BOT CT LONG ACTIVE / SMALL / AGGRESSIVE / ADD / PARTIAL / EXIT / CANCEL / RESET', '• BOT CT SHORT ACTIVE / SMALL / AGGRESSIVE / ADD / PARTIAL / EXIT / CANCEL / RESET', '• BOT RANGE LONG ACTIVE / SMALL / AGGRESSIVE / ADD / PARTIAL / EXIT / CANCEL / RESET', '• BOT RANGE SHORT ACTIVE / SMALL / AGGRESSIVE / ADD / PARTIAL / EXIT / CANCEL / RESET'])
    return '\n'.join(lines)