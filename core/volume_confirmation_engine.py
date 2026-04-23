from __future__ import annotations

from typing import Any, Dict, List


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def _candle_stats(candles: List[Dict[str, Any]]) -> Dict[str, float]:
    if not candles:
        return {
            'last_volume': 0.0,
            'avg_volume': 0.0,
            'relative_volume': 1.0,
            'body_ratio': 0.0,
            'close_pos': 0.5,
            'last_range': 0.0,
            'avg_range': 0.0,
            'range_expansion': 1.0,
            'direction': 0.0,
            'up_vol_3': 0.0,
            'down_vol_3': 0.0,
        }
    vols = [_f(c.get('volume')) for c in candles]
    ranges = [max(_f(c.get('high')) - _f(c.get('low')), 0.0) for c in candles]
    last = candles[-1]
    lo = _f(last.get('low'))
    hi = _f(last.get('high'))
    op = _f(last.get('open'))
    cl = _f(last.get('close'))
    body = abs(cl - op)
    rng = max(hi - lo, 1e-9)
    close_pos = (cl - lo) / rng if rng > 0 else 0.5
    avg_volume = sum(vols[:-1]) / max(len(vols) - 1, 1) if len(vols) > 1 else (vols[-1] if vols else 0.0)
    avg_range = sum(ranges[:-1]) / max(len(ranges) - 1, 1) if len(ranges) > 1 else (ranges[-1] if ranges else 0.0)
    up_vol_3 = 0.0
    down_vol_3 = 0.0
    for c in candles[-3:]:
        v = _f(c.get('volume'))
        if _f(c.get('close')) >= _f(c.get('open')):
            up_vol_3 += v
        else:
            down_vol_3 += v
    return {
        'last_volume': vols[-1] if vols else 0.0,
        'avg_volume': avg_volume,
        'relative_volume': (vols[-1] / max(avg_volume, 1e-9)) if vols else 1.0,
        'body_ratio': body / rng,
        'close_pos': close_pos,
        'last_range': ranges[-1] if ranges else 0.0,
        'avg_range': avg_range,
        'range_expansion': (ranges[-1] / max(avg_range, 1e-9)) if ranges else 1.0,
        'direction': 1.0 if cl > op else -1.0 if cl < op else 0.0,
        'up_vol_3': up_vol_3,
        'down_vol_3': down_vol_3,
    }


def build_volume_confirmation_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    orderflow = payload.get('orderflow_context') if isinstance(payload.get('orderflow_context'), dict) else {}
    micro = payload.get('microstructure') if isinstance(payload.get('microstructure'), dict) else {}
    candles = payload.get('recent_candles') if isinstance(payload.get('recent_candles'), list) else []
    stats = _candle_stats(candles[-12:])

    rel = max(
        _f(orderflow.get('relative_volume') or orderflow.get('volume_ratio') or micro.get('volume_ratio'), 1.0),
        _f(stats.get('relative_volume'), 1.0),
    )
    delta = _f(orderflow.get('delta_volume'), 0.0)
    delta_side = 'BUY' if delta > 0 else 'SELL' if delta < 0 else 'BALANCE'
    body_ratio = _f(stats.get('body_ratio'), 0.0)
    close_pos = _f(stats.get('close_pos'), 0.5)
    range_expansion = _f(stats.get('range_expansion'), 1.0)
    up_vol_3 = _f(stats.get('up_vol_3'), 0.0)
    down_vol_3 = _f(stats.get('down_vol_3'), 0.0)
    pressure_3 = 'BUY' if up_vol_3 > down_vol_3 * 1.1 else 'SELL' if down_vol_3 > up_vol_3 * 1.1 else 'BALANCE'

    state = 'NEUTRAL'
    volume_quality = 'MIXED'
    breakout_quality = 'UNCONFIRMED'
    acceleration_state = 'NORMAL'
    reaction_quality = 'MIXED'
    exhaustion_hint = 'NONE'
    absorption_hint = 'NONE'
    confidence = 48.0

    if rel >= 1.7 and range_expansion >= 1.2:
        acceleration_state = 'ACCELERATION'
        confidence += 10.0
    elif rel <= 0.92 and range_expansion >= 1.1:
        acceleration_state = 'EMPTY_PUSH'
        confidence -= 6.0

    if body_ratio >= 0.62 and rel >= 1.2:
        volume_quality = 'CONFIRMING'
        confidence += 8.0
    elif body_ratio <= 0.35 and rel >= 1.15:
        volume_quality = 'REJECTION'
        confidence += 4.0
    elif rel <= 0.95:
        volume_quality = 'THIN'
        confidence -= 5.0

    if volume_quality == 'CONFIRMING' and ((delta_side == 'BUY' and close_pos >= 0.68) or (delta_side == 'SELL' and close_pos <= 0.32)):
        breakout_quality = 'CONFIRMED'
        state = 'CONFIRMED'
        reaction_quality = 'ACCEPTANCE'
        confidence += 10.0
    elif volume_quality in {'REJECTION', 'THIN'} and rel >= 1.05:
        breakout_quality = 'REJECTED'
        state = 'REJECTION'
        reaction_quality = 'REJECTION'
        confidence += 8.0
    elif acceleration_state == 'EMPTY_PUSH':
        breakout_quality = 'WEAK'
        state = 'WEAK'
        reaction_quality = 'NO_ACCEPTANCE'
        confidence -= 2.0

    if rel >= 1.4 and body_ratio <= 0.28:
        absorption_hint = 'HIGH_VOLUME_STALL'
        if state == 'NEUTRAL':
            state = 'ABSORPTION'
        reaction_quality = 'ABSORPTION'
        confidence += 4.0

    if rel >= 1.25 and range_expansion >= 1.15:
        if delta_side == 'BUY' and close_pos < 0.45:
            exhaustion_hint = 'BUY_EXHAUSTION'
            if state == 'NEUTRAL':
                state = 'EXHAUSTION'
        elif delta_side == 'SELL' and close_pos > 0.55:
            exhaustion_hint = 'SELL_EXHAUSTION'
            if state == 'NEUTRAL':
                state = 'EXHAUSTION'

    if state == 'NEUTRAL':
        if rel >= 1.15:
            state = 'BUILDING'
        elif rel <= 0.95:
            state = 'WEAK'
        else:
            state = 'BALANCED'

    summary = 'объём нейтрален'
    signal_note = 'движение не имеет сильного объёмного подтверждения'
    if state == 'CONFIRMED':
        summary = 'ускорение поддержано объёмом; acceptance выглядит рабочим'
        signal_note = 'объём подтверждает движение и удержание цены ближе к краю свечи'
    elif state == 'REJECTION':
        summary = 'на импульсе пришёл реакционный объём; уровень даёт rejection'
        signal_note = 'объём на зоне есть, но цена не удерживает пробой как полноценное acceptance'
    elif state == 'ABSORPTION':
        summary = 'высокий объём без нормального продвижения — похоже на absorption'
        signal_note = 'движение встречает встречную ликвидность; без follow-through это риск разворота или паузы'
    elif state == 'EXHAUSTION':
        summary = 'ускорение выглядит уставшим: объём высокий, но закрытие/продвижение хуже'
        signal_note = 'после такого ускорения часто нужен либо откат, либо повторная проверка зоны'
    elif state == 'BUILDING':
        summary = 'объём подрастает, но полное подтверждение ещё не собрано'
        signal_note = 'есть ранняя поддержка движения, но для сильного continuation нужен follow-through'
    elif state == 'WEAK':
        summary = 'движение идёт без сильного объёмного подтверждения'
        signal_note = 'такой push легче сломать реакцией от уровня или возвратом в диапазон'
    elif state == 'BALANCED':
        summary = 'объём сбалансирован; явного доминирования нет'
        signal_note = 'рынок скорее в ротации, чем в сильном трендовом проталкивании'

    return {
        'state': state,
        'relative_volume': round(rel, 3),
        'delta_side': delta_side,
        'pressure_3': pressure_3,
        'volume_quality': volume_quality,
        'breakout_quality': breakout_quality,
        'acceleration_state': acceleration_state,
        'reaction_quality': reaction_quality,
        'exhaustion_hint': exhaustion_hint,
        'absorption_hint': absorption_hint,
        'body_ratio': round(body_ratio, 3),
        'close_position': round(close_pos, 3),
        'range_expansion': round(range_expansion, 3),
        'confidence': round(max(5.0, min(95.0, confidence)), 1),
        'summary': summary,
        'signal_note': signal_note,
    }
