from __future__ import annotations

from typing import Any, Dict

from core.fake_move_engine_v14 import build_fake_move_state


def build_fake_move_detector(payload: Dict[str, Any], decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    result = build_fake_move_state(payload or {}, decision if isinstance(decision, dict) else {})
    # backward-compatible aliases used around the project
    result.setdefault('execution_mode', 'NONE')
    result.setdefault('side_hint', 'NEUTRAL')
    result.setdefault('confirmed', False)
    result.setdefault('confidence', 0.0)
    result['v14_state'] = result.get('state')
    return result


__all__ = ['build_fake_move_detector']
