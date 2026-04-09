from __future__ import annotations

from typing import Any, Dict


def _u(v: Any, default: str = '') -> str:
    return str(v or default).strip().upper()


def build_grid_execution_authority_v15(payload: Dict[str, Any], authority: Dict[str, Any] | None = None) -> Dict[str, Any]:
    auth = authority if isinstance(authority, dict) else {}
    reaction = payload.get('liquidation_reaction') if isinstance(payload.get('liquidation_reaction'), dict) else {}
    blocks = payload.get('liquidity_blocks') if isinstance(payload.get('liquidity_blocks'), dict) else {}
    reversal = payload.get('reversal_v15') if isinstance(payload.get('reversal_v15'), dict) else {}
    volume = payload.get('volume_confirmation') if isinstance(payload.get('volume_confirmation'), dict) else {}
    action = _u(auth.get('action'), 'WATCH')
    direction = _u(auth.get('direction'), 'NEUTRAL')
    reaction_state = _u(reaction.get('acceptance'), 'NONE')
    trap = _u(reaction.get('trap_side'), 'NONE')
    volume_state = _u(volume.get('state'), 'NEUTRAL')
    reversal_state = _u(reversal.get('state'), 'NO_REVERSAL')
    upper_reaction = _u(blocks.get('upper_reaction'), 'NONE')
    lower_reaction = _u(blocks.get('lower_reaction'), 'NONE')

    grid_strategy = payload.get('grid_strategy') if isinstance(payload.get('grid_strategy'), dict) else {}
    active_bots = list(grid_strategy.get('active_bots') or [])
    strongest_bot = str(grid_strategy.get('strongest_bot') or 'NONE')

    result = {
        'status': 'WATCH',
        'long_grid': 'HOLD',
        'short_grid': 'HOLD',
        'reason': 'ждать подтверждение у блока',
    }

    if action == 'EXECUTE_PROBE_LONG':
        result.update({'status': 'ENABLE_SMALL', 'long_grid': 'ENABLE_SMALL', 'short_grid': 'HOLD', 'reason': 'нижний блок удержан, допустим small long-grid'})
    elif action == 'EXECUTE_PROBE_SHORT':
        result.update({'status': 'ENABLE_SMALL', 'long_grid': 'HOLD', 'short_grid': 'ENABLE_SMALL', 'reason': 'верхний блок удержан, допустим small short-grid'})
    elif action == 'EXECUTE_LONG':
        result.update({'status': 'HOLD_LONG', 'long_grid': 'HOLD', 'short_grid': 'REDUCE', 'reason': 'движение вверх принято, short-grid лучше сокращать'})
    elif action == 'EXECUTE_SHORT':
        result.update({'status': 'HOLD_SHORT', 'long_grid': 'REDUCE', 'short_grid': 'HOLD', 'reason': 'движение вниз принято, long-grid лучше сокращать'})
    elif action == 'ARM_LONG':
        result.update({'status': 'ARM_LONG', 'long_grid': 'ARM', 'short_grid': 'HOLD', 'reason': 'нижний блок в работе, ждём reclaim / разворот'})
    elif action == 'ARM_SHORT':
        result.update({'status': 'ARM_SHORT', 'long_grid': 'HOLD', 'short_grid': 'ARM', 'reason': 'верхний блок в работе, ждём rejection / разворот'})

    if trap == 'LONG' and reversal_state.endswith('_UP') and volume_state != 'CONFIRMED':
        result['reason'] += '; без агрессии, объём пока не идеален'
    if trap == 'SHORT' and reversal_state.endswith('_DOWN') and volume_state != 'CONFIRMED':
        result['reason'] += '; без агрессии, объём пока не идеален'
    if reaction_state == 'ACCEPTED_ABOVE':
        result.update({'short_grid': 'EXIT', 'reason': 'рынок принял цену выше верхнего блока, short-идея ослабла'})
    elif reaction_state == 'ACCEPTED_BELOW':
        result.update({'long_grid': 'EXIT', 'reason': 'рынок принял цену ниже нижнего блока, long-идея ослабла'})
    if upper_reaction == 'REJECTED_FROM_BLOCK' and direction == 'SHORT' and result['short_grid'] == 'HOLD':
        result['short_grid'] = 'ARM'
    if lower_reaction == 'BOUNCED_FROM_BLOCK' and direction == 'LONG' and result['long_grid'] == 'HOLD':
        result['long_grid'] = 'ARM'

    # V16.5: allow visible grid pre-activation even before full block acceptance
    if result['status'] == 'WATCH' and active_bots:
        if direction == 'LONG':
            result.update({
                'status': 'PREPARE_LONG',
                'long_grid': 'PREPARE',
                'short_grid': 'HOLD',
                'reason': f'3-bot grid engine already sees deviation; prepare long grid ({strongest_bot})',
            })
        elif direction == 'SHORT':
            result.update({
                'status': 'PREPARE_SHORT',
                'long_grid': 'HOLD',
                'short_grid': 'PREPARE',
                'reason': f'3-bot grid engine already sees deviation; prepare short grid ({strongest_bot})',
            })
    return result
