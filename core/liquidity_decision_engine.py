from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def _u(v: Any, default: str = '') -> str:
    try:
        if v is None:
            return default
        return str(v).strip().upper()
    except Exception:
        return default


def build_liquidity_decision_context(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload or {}
    ctx = payload.get('coinglass_context') if isinstance(payload.get('coinglass_context'), dict) else {}
    liq = payload.get('liquidation_context') if isinstance(payload.get('liquidation_context'), dict) else {}
    feed_health = _u(ctx.get('feed_health') or liq.get('feed_health') or 'UNKNOWN')
    price_oi_regime = _u(ctx.get('price_oi_regime') or liq.get('price_oi_regime'))
    funding_state = _u(ctx.get('funding_state') or liq.get('funding_state'))
    events = int(ctx.get('recent_liquidation_events') or liq.get('recent_liquidation_events') or 0)
    notional = _f(ctx.get('recent_liquidation_notional_usd') or liq.get('recent_liquidation_notional_usd'))
    burst_up = bool(ctx.get('event_burst_up'))
    burst_down = bool(ctx.get('event_burst_down'))
    above = _f(ctx.get('nearest_above_strength') or ctx.get('recent_cluster_above_strength'))
    below = _f(ctx.get('nearest_below_strength') or ctx.get('recent_cluster_below_strength'))

    pressure = 'NEUTRAL'
    crowding = 'NONE'
    squeeze = 'LOW'
    unwind = 'NONE'
    summary = 'ликвидность не даёт явного преимущества'

    if price_oi_regime == 'UP_OI_UP':
        pressure = 'UP'
        crowding = 'LONG'
        squeeze = 'MEDIUM'
        summary = 'цена и OI растут: рынок набирает плечо вверх, контртренд short опасен без потери удержания'
    elif price_oi_regime == 'DOWN_OI_UP':
        pressure = 'DOWN'
        crowding = 'SHORT'
        squeeze = 'MEDIUM'
        summary = 'цена падает при росте OI: рынок набирает давление вниз, long без flush/reclaim опасен'
    elif price_oi_regime == 'UP_OI_DOWN':
        pressure = 'UP'
        unwind = 'SHORT_COVER'
        summary = 'рост идёт на сбросе OI: похоже на закрытие шортов, а не на новый устойчивый тренд'
    elif price_oi_regime == 'DOWN_OI_DOWN':
        pressure = 'DOWN'
        unwind = 'LONG_UNWIND'
        summary = 'падение идёт на сбросе OI: похоже на long unwind, после flush возможен отскок'

    if funding_state in {'POSITIVE', 'CROWDED_LONG', 'LONGS_CROWDED'}:
        crowding = 'LONG'
    elif funding_state in {'NEGATIVE', 'CROWDED_SHORT', 'SHORTS_CROWDED'}:
        crowding = 'SHORT'

    if burst_up or above > below * 1.35:
        pressure = 'UP'
        squeeze = 'HIGH' if events >= 3 or notional >= 100000 else max(squeeze, 'MEDIUM')
    if burst_down or below > above * 1.35:
        pressure = 'DOWN'
        squeeze = 'HIGH' if events >= 3 or notional >= 100000 else max(squeeze, 'MEDIUM')

    if feed_health in {'DEGRADED', 'UNKNOWN'} and events <= 0:
        summary = 'feed неполный: использовать ликвидность только как слабый контекст, не как триггер'
    elif burst_up and unwind == 'SHORT_COVER':
        summary = 'сверху был выброс ликвидаций и рост идёт на short cover: после потери удержания возможен fake up'
    elif burst_down and unwind == 'LONG_UNWIND':
        summary = 'снизу был выброс ликвидаций и падение идёт на long unwind: после reclaim возможен fake down'

    return {
        'feed_health': feed_health,
        'price_oi_regime': price_oi_regime or 'NEUTRAL',
        'funding_state': funding_state or 'NEUTRAL',
        'liq_side_pressure': pressure,
        'crowding': crowding,
        'squeeze_risk': squeeze,
        'unwind_state': unwind,
        'recent_events': events,
        'recent_notional_usd': round(notional, 2),
        'summary': summary,
    }


__all__ = ['build_liquidity_decision_context']
