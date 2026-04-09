from __future__ import annotations

from typing import Any, Dict


def build_reversal_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    reaction = payload.get('liquidation_reaction') if isinstance(payload.get('liquidation_reaction'), dict) else {}
    move = payload.get('impulse_character') if isinstance(payload.get('impulse_character'), dict) else {}
    pin = payload.get('pinbar_context') if isinstance(payload.get('pinbar_context'), dict) else {}
    volume = payload.get('volume_confirmation') if isinstance(payload.get('volume_confirmation'), dict) else {}
    blocks = payload.get('liquidity_blocks') if isinstance(payload.get('liquidity_blocks'), dict) else {}
    state = 'NO_REVERSAL'
    conf = 0.0
    summary = 'разворот не подтверждён'
    if reaction.get('trap_side') == 'SHORT' and move.get('state') in {'EXHAUSTION_UP','TRAP_CANDIDATE_UP'}:
        state='EARLY_REVERSAL_DOWN'; conf=58.0; summary='верхний вынос не принят, возможен разворот вниз'
    if reaction.get('trap_side') == 'LONG' and move.get('state') in {'EXHAUSTION_DOWN','TRAP_CANDIDATE_DOWN'}:
        state='EARLY_REVERSAL_UP'; conf=58.0; summary='нижний пролив не принят, возможен разворот вверх'
    if pin.get('pinbar_valid') and pin.get('pinbar_confirmed'):
        if pin.get('side') == 'SHORT':
            state='CONFIRMED_REVERSAL_DOWN'; conf=max(conf,74.0); summary='разворот вниз подтверждён пинбаром в верхнем блоке'
        elif pin.get('side') == 'LONG':
            state='CONFIRMED_REVERSAL_UP'; conf=max(conf,74.0); summary='разворот вверх подтверждён пинбаром в нижнем блоке'
    if volume.get('state') == 'WEAK' and conf > 0:
        conf += 5.0
    if reaction.get('acceptance') == 'ACCEPTED_ABOVE' and blocks.get('upper_state') == 'ACCEPTED_BREAK':
        state='PULLBACK_ONLY'; conf=max(conf,40.0); summary='пока это больше похоже на pullback внутри продолжения вверх'
    if reaction.get('acceptance') == 'ACCEPTED_BELOW' and blocks.get('lower_state') == 'ACCEPTED_BREAK':
        state='PULLBACK_ONLY'; conf=max(conf,40.0); summary='пока это больше похоже на pullback внутри продолжения вниз'
    return {'state': state, 'confidence': round(min(conf, 90.0),1), 'summary': summary}
