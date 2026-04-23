from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def build_liquidation_reaction_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    candles = payload.get('recent_candles') if isinstance(payload.get('recent_candles'), list) else []
    if len(candles) < 5:
        return {'sweep_detected': False, 'reclaim': False, 'acceptance': 'UNKNOWN', 'trap_side': 'NONE', 'reaction_strength': 0.0, 'summary': 'недостаточно свечей для реакции'}
    blocks = payload.get('liquidity_blocks') if isinstance(payload.get('liquidity_blocks'), dict) else {}
    upper = blocks.get('upper_block') if isinstance(blocks.get('upper_block'), dict) else {}
    lower = blocks.get('lower_block') if isinstance(blocks.get('lower_block'), dict) else {}
    recent = candles[-5:]
    highs = [_f(c.get('high')) for c in recent]
    lows = [_f(c.get('low')) for c in recent]
    closes = [_f(c.get('close')) for c in recent]
    opens = [_f(c.get('open')) for c in recent]
    uh, ul = _f(upper.get('high')), _f(upper.get('low'))
    ll, lh = _f(lower.get('low')), _f(lower.get('high'))
    vol = [max(_f(c.get('volume')), 0.0) for c in recent]
    avg_vol = sum(vol) / max(len(vol), 1)
    last_vol = vol[-1]

    sweep_up = uh > 0 and max(highs) > uh
    sweep_down = ll > 0 and min(lows) < ll
    reclaim_short = sweep_up and closes[-1] < uh and closes[-2] < uh and max(closes[-3:]) < max(highs[-3:]) and closes[-1] < opens[-1]
    reclaim_long = sweep_down and closes[-1] > ll and closes[-2] > ll and min(closes[-3:]) > min(lows[-3:]) and closes[-1] > opens[-1]
    accepted_above = sweep_up and closes[-1] > uh and closes[-2] > ul and min(closes[-3:]) > ul
    accepted_below = sweep_down and closes[-1] < ll and closes[-2] < lh and max(closes[-3:]) < lh

    acceptance = 'NONE'
    trap_side = 'NONE'
    strength = 0.0
    summary = 'реакция на блок слабая / неочевидная'
    if reclaim_short:
        acceptance = 'REJECTED_ABOVE'
        trap_side = 'SHORT'
        strength = 70.0 + (8.0 if last_vol >= avg_vol else 0.0)
        summary = 'верхний блок вынесли и затем потеряли удержание: это похоже на ложный вынос вверх'
    elif reclaim_long:
        acceptance = 'REJECTED_BELOW'
        trap_side = 'LONG'
        strength = 70.0 + (8.0 if last_vol >= avg_vol else 0.0)
        summary = 'нижний блок вынесли и быстро вернули назад: это похоже на ложный пролив вниз'
    elif accepted_above:
        acceptance = 'ACCEPTED_ABOVE'
        strength = 66.0 + (6.0 if last_vol >= avg_vol else 0.0)
        summary = 'цена удерживается выше верхнего блока: продолжение вверх выглядит рабочим'
    elif accepted_below:
        acceptance = 'ACCEPTED_BELOW'
        strength = 66.0 + (6.0 if last_vol >= avg_vol else 0.0)
        summary = 'цена удерживается ниже нижнего блока: продолжение вниз выглядит рабочим'

    return {
        'sweep_detected': bool(sweep_up or sweep_down),
        'sweep_side': 'UP' if sweep_up else 'DOWN' if sweep_down else 'NONE',
        'reclaim': bool(reclaim_short or reclaim_long),
        'acceptance': acceptance,
        'trap_side': trap_side,
        'reaction_strength': round(min(strength, 92.0), 1),
        'summary': summary,
    }
