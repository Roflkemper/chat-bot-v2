
from __future__ import annotations

from typing import Dict, Any, List


def build_bot_authority(decision: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    factor = payload.get('factor_breakdown') or {}
    grid = payload.get('grid_cmd') or {}
    liq = (payload.get('liquidity_map') or {}).get('liquidity_state', 'NEUTRAL')
    dominance = str(factor.get('dominance', 'NEUTRAL')).upper()
    stage = str(factor.get('edge_stage', 'NO_EDGE')).upper()
    long_score = float(factor.get('long_total', 50.0) or 50.0)
    short_score = float(factor.get('short_total', 50.0) or 50.0)
    range_volume = decision.get('range_volume_bot') if isinstance(decision.get('range_volume_bot'), dict) else {}
    location = str(range_volume.get('location_state') or '').upper()
    decision_action = str(decision.get('action') or '').upper()
    decision_execution = str(decision.get('execution') or '').upper()
    breakout_risk = str(range_volume.get('breakout_risk') or decision.get('trap_risk') or 'HIGH').upper()

    cards: List[Dict[str, Any]] = []
    def add(label: str, status: str, score: float, note: str):
        cards.append({'bot': label, 'status': status, 'score': round(score,1), 'note': note})

    if dominance == 'SHORT':
        add('CT SHORT', 'PREPARE' if stage in {'PREPARE', 'BUILDING'} else 'READY', short_score, 'продавец получает перевес, ждать реакцию у верхней зоны')
        add('CT LONG', 'REDUCED', long_score, 'контртренд против доминирующей стороны только малым размером')
    elif dominance == 'LONG':
        add('CT LONG', 'PREPARE' if stage in {'PREPARE', 'BUILDING'} else 'READY', long_score, 'покупатель получает перевес, ждать реакцию у нижней зоны')
        add('CT SHORT', 'REDUCED', short_score, 'контртренд против доминирующей стороны только малым размером')
    else:
        add('CT LONG', 'WAIT', long_score, 'нет чистого directional edge')
        add('CT SHORT', 'WAIT', short_score, 'нет чистого directional edge')

    grid_long = str(grid.get('long_grid') or 'HOLD').upper()
    grid_short = str(grid.get('short_grid') or 'HOLD').upper()
    grid_note = 'середина диапазона: без форсирования'
    if location == 'EDGE':
        grid_note = 'цена у края диапазона: можно готовить мягкий запуск'
    elif location == 'MID':
        grid_note = 'середина диапазона: только reduced / small'
    if breakout_risk == 'HIGH':
        grid_note += '; высокий breakout risk — без adds'

    allow_soft_range = decision_execution == 'PROBE_ALLOWED' or decision_action in {'ENTER','ВХОДИТЬ','PROBE'}
    add('RANGE LONG', 'SMALL ONLY' if (grid_long in {'ENABLE', 'DEFENSIVE'} or (allow_soft_range and dominance == 'LONG' and location == 'EDGE')) else 'OFF', long_score, grid_note)
    add('RANGE SHORT', 'SMALL ONLY' if (grid_short in {'ENABLE', 'DEFENSIVE'} or (allow_soft_range and dominance == 'SHORT' and location == 'EDGE')) else 'OFF', short_score, grid_note)

    if allow_soft_range and dominance == 'SHORT' and location == 'EDGE':
        master = 'PROBE SHORT GRID'
        auth = 'SOFT_AUTHORIZED'
    elif allow_soft_range and dominance == 'LONG' and location == 'EDGE':
        master = 'PROBE LONG GRID'
        auth = 'SOFT_AUTHORIZED'
    elif dominance == 'SHORT' and stage in {'PREPARE', 'BUILDING', 'READY'}:
        master = 'PREPARE SHORT GRID' if liq != 'SELL_SIDE_SWEEP_REJECTED' else 'SHORT GRID READY'
        auth = 'SOFT_AUTHORIZED' if stage != 'READY' else 'AUTHORIZED'
    elif dominance == 'LONG' and stage in {'PREPARE', 'BUILDING', 'READY'}:
        master = 'PREPARE LONG GRID' if liq != 'BUY_SIDE_SWEEP_REJECTED' else 'LONG GRID READY'
        auth = 'SOFT_AUTHORIZED' if stage != 'READY' else 'AUTHORIZED'
    else:
        master = 'WAIT'
        auth = 'NOT_AUTHORIZED'

    return {
        'master_mode': master,
        'authority': auth,
        'cards': cards,
    }
