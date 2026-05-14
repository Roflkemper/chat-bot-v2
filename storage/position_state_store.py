from __future__ import annotations

import json
import os
from typing import Any, Dict

DEFAULT_POSITION_STATE: Dict[str, Any] = {
    'active': False,
    'side': 'NONE',
    'stage': 'FLAT',
    'entry_price': None,
    'size': 0.0,
    'source': 'none',
    'updated_at': '',
}


def load_position_state(path: str = 'storage/position_state.json') -> Dict[str, Any]:
    if not os.path.exists(path):
        return dict(DEFAULT_POSITION_STATE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_POSITION_STATE)
        state = dict(DEFAULT_POSITION_STATE)
        state.update(data)
        return state
    except Exception:
        return dict(DEFAULT_POSITION_STATE)


def save_position_state(state: Dict[str, Any], path: str = 'storage/position_state.json') -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
