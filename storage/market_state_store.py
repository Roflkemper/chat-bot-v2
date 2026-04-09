from __future__ import annotations

import json
import os
from typing import Any, Dict

DEFAULT_MARKET_STATE: Dict[str, Any] = {
    'flip_prep_active': False,
    'flip_prep_side': 'NONE',
    'flip_prep_reason': '',
    'flip_prep_level': None,
    'flip_prep_confirm_bars_needed': 2,
    'flip_prep_progress_bars': 0,
    'flip_prep_status': 'IDLE',
    'flip_prep_cooldown_bars': 0,
    'candidate_side': 'NONE',
    'candidate_status': 'NONE',
    'candidate_reason': '',
}


def load_market_state(path: str = 'storage/market_state.json') -> Dict[str, Any]:
    if not os.path.exists(path):
        return dict(DEFAULT_MARKET_STATE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_MARKET_STATE)
        state = dict(DEFAULT_MARKET_STATE)
        state.update(data)
        return state
    except Exception:
        return dict(DEFAULT_MARKET_STATE)


def save_market_state(state: Dict[str, Any], path: str = 'storage/market_state.json') -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
