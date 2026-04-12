from __future__ import annotations

from typing import Any, Dict

from core.impulse_character_engine import build_impulse_character_context


def analyze_impulse(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ctx = build_impulse_character_context(data or {})
    state = str(ctx.get('state') or 'NO_CLEAR_IMPULSE')
    can_enter = bool(ctx.get('can_enter_with_trend'))
    comment = str(ctx.get('comment') or '')
    legacy_state = 'IMPULSE_UNCERTAIN'
    if state in {'CONTINUATION_UP', 'CONTINUATION_DOWN'}:
        legacy_state = 'IMPULSE_CONTINUES'
    elif state in {'EXHAUSTION_UP', 'EXHAUSTION_DOWN', 'TRAP_CANDIDATE_UP', 'TRAP_CANDIDATE_DOWN', 'CHOP'}:
        legacy_state = 'IMPULSE_EXHAUSTING'
    return {
        'state': legacy_state,
        'score': float(ctx.get('score') or 0.0),
        'can_enter': can_enter,
        'comment': comment,
        'watch_conditions': list(ctx.get('watch_conditions') or []),
        'v14': ctx,
    }
