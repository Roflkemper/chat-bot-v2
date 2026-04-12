from __future__ import annotations

from typing import Any, Dict


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _dist_pct(price: float, level: float) -> float:
    if price <= 0 or level <= 0:
        return 999.0
    return abs(price - level) / price * 100.0


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace('%', '').replace(',', '.')
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def _s(value: Any, default: str = '') -> str:
    try:
        if value is None:
            return default
        return str(value).strip()
    except Exception:
        return default


def _u(value: Any, default: str = '') -> str:
    return _s(value, default).upper()


def _pct01(value: Any, default: float = 0.0) -> float:
    x = _f(value, default)
    if 0.0 <= x <= 1.0:
        x *= 100.0
    return max(0.0, min(100.0, x))


def _pick(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _range_pct(price: float, low: float, high: float) -> float:
    if price <= 0 or high <= low:
        return 50.0
    return max(0.0, min(100.0, (price - low) / (high - low) * 100.0))


def _fmt_price(v: float) -> str:
    return f'{v:.2f}' if v > 0 else 'нет данных'


def _side_ru(side: str) -> str:
    side = _u(side)
    if side == 'LONG':
        return 'ЛОНГ'
    if side == 'SHORT':
        return 'ШОРТ'
    return 'НЕЙТРАЛЬНО'


def _extract_ohlc(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, float]:
    def pick(*vals: Any) -> float:
        for v in vals:
            x = _f(v, 0.0)
            if x > 0:
                return x
        return 0.0

    candle = _pick(payload.get('last_candle'), payload.get('current_candle'), decision.get('last_candle'))
    candles = payload.get('candles') if isinstance(payload.get('candles'), list) else []
    prev = candles[-2] if len(candles) >= 2 and isinstance(candles[-2], dict) else {}
    last = candles[-1] if len(candles) >= 1 and isinstance(candles[-1], dict) else {}
    open_ = pick(payload.get('open'), payload.get('last_open'), decision.get('open'), candle.get('open'), last.get('open'))
    high_ = pick(payload.get('high'), payload.get('last_high'), decision.get('high'), candle.get('high'), last.get('high'))
    low_ = pick(payload.get('low'), payload.get('last_low'), decision.get('low'), candle.get('low'), last.get('low'))
    close_ = pick(payload.get('close'), payload.get('last_price'), payload.get('price'), decision.get('close'), candle.get('close'), last.get('close'))
    prev_open = pick(payload.get('prev_open'), prev.get('open'))
    prev_high = pick(payload.get('prev_high'), prev.get('high'))
    prev_low = pick(payload.get('prev_low'), prev.get('low'))
    prev_close = pick(payload.get('prev_close'), prev.get('close'))
    return {
        'open': open_,
        'high': max(high_, open_, close_),
        'low': low_ if low_ > 0 else min(v for v in [open_, close_, high_] if v > 0) if any(v > 0 for v in [open_, close_, high_]) else 0.0,
        'close': close_,
        'prev_open': prev_open,
        'prev_high': prev_high,
        'prev_low': prev_low,
        'prev_close': prev_close,
    }


def _candle_metrics(ohlc: Dict[str, float]) -> Dict[str, float]:
    o = _f(ohlc.get('open'), 0.0)
    h = _f(ohlc.get('high'), 0.0)
    l = _f(ohlc.get('low'), 0.0)
    c = _f(ohlc.get('close'), 0.0)
    if h <= 0 or l <= 0 or h < l:
        return {'range': 0.0, 'body': 0.0, 'upper_wick': 0.0, 'lower_wick': 0.0, 'body_pct': 0.0, 'upper_wick_pct': 0.0, 'lower_wick_pct': 0.0}
    rng = max(1e-9, h - l)
    body = abs(c - o)
    upper = max(0.0, h - max(o, c))
    lower = max(0.0, min(o, c) - l)
    return {
        'range': rng,
        'body': body,
        'upper_wick': upper,
        'lower_wick': lower,
        'body_pct': body / rng * 100.0,
        'upper_wick_pct': upper / rng * 100.0,
        'lower_wick_pct': lower / rng * 100.0,
    }


def _zone_state(price: float, low: float, high: float, inner_low: float, inner_high: float) -> str:
    if price <= 0:
        return 'UNKNOWN'
    if low <= price <= high:
        return 'EDGE'
    if inner_low <= price <= inner_high:
        return 'MID'
    return 'OUTSIDE'


def build_v13_trade_fix_context(payload: Dict[str, Any], *, side: str = 'NEUTRAL') -> Dict[str, Any]:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    price = _f(payload.get('price') or payload.get('last_price') or payload.get('close'), 0.0)
    low = _f(payload.get('range_low') or decision.get('range_low') or ((payload.get('range') or {}).get('low')), 0.0)
    mid = _f(payload.get('range_mid') or decision.get('range_mid') or ((payload.get('range') or {}).get('mid')), 0.0)
    high = _f(payload.get('range_high') or decision.get('range_high') or ((payload.get('range') or {}).get('high')), 0.0)
    width = max(0.0, high - low)
    rpct = _range_pct(price, low, high)

    vol = _pick(payload.get('volatility_impulse'), decision.get('volatility_impulse'))
    fast = _pick(payload.get('fast_move_context'), decision.get('fast_move_context'))
    fake = _pick(payload.get('fake_move_detector'), decision.get('fake_move_detector'))
    liq = _pick(payload.get('liquidation_context'), decision.get('liquidation_context'))
    proj = _pick(payload.get('move_projection'), decision.get('move_projection'))

    move_5_pct = _f(vol.get('move_5_pct'), 0.0)
    atr_pct = _f(vol.get('atr_pct'), 0.0)
    vol_strength = _u(vol.get('impulse_strength'), 'LOW')
    stretch_state = _u(vol.get('stretch_state'), 'NORMAL')
    ct_risk = _u(vol.get('countertrend_risk'), 'LOW')

    fast_cls = _u(fast.get('classification'))
    fast_conf = _pct01(fast.get('confidence'), 0.0)
    acceptance = _u(fast.get('acceptance_state'), 'UNDEFINED')
    continuation_target = _s(fast.get('continuation_target'), '')

    fake_type = _u(fake.get('type'))
    fake_conf = _pct01(fake.get('confidence'), 0.0)
    fake_action = _s(fake.get('action'))
    reclaim_needed = _f(fake.get('reclaim_needed'), 0.0)
    fake_invalidation = _f(fake.get('invalidation_level'), 0.0)
    fake_execution_mode = _u(fake.get('execution_mode'))

    recent_events = int(_f(liq.get('recent_liquidation_events'), 0))
    recent_notional = _f(liq.get('recent_liquidation_notional_usd'), 0.0)
    liq_state = _u(liq.get('liquidity_state'), 'NEUTRAL')
    magnet_side = _u(liq.get('magnet_side'), 'NEUTRAL')
    cascade_risk = _u(liq.get('cascade_risk'), 'LOW')
    upper_cluster = _f(liq.get('upper_cluster_price'), 0.0)
    lower_cluster = _f(liq.get('lower_cluster_price'), 0.0)
    feed_health = _u(liq.get('feed_health'), '')
    fallback_active = bool(liq.get('fallback_active'))

    projection_bias = _u(proj.get('bias') or proj.get('direction'), 'NEUTRAL')
    projection_conf = _pct01(proj.get('confidence'), 0.0)

    ohlc = _extract_ohlc(payload, decision)
    cm = _candle_metrics(ohlc)
    close_price = _f(ohlc.get('close'), price)

    impulse_score = 0.0
    impulse_score += min(18.0, abs(move_5_pct) * 12.0)
    impulse_score += min(16.0, atr_pct * 18.0)
    impulse_score += {'LOW': 8.0, 'MEDIUM': 16.0, 'HIGH': 24.0}.get(vol_strength, 0.0)
    impulse_score += {'NORMAL': 2.0, 'STRETCHED': 6.0, 'EXTREME': 8.0}.get(stretch_state, 0.0)
    impulse_score += min(18.0, fast_conf * 0.22)
    impulse_score += 8.0 if fast_cls in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} else 0.0
    impulse_score += 4.0 if fast_cls in {'WEAK_CONTINUATION_UP', 'WEAK_CONTINUATION_DOWN'} else 0.0
    impulse_score += 6.0 if recent_events >= 3 and recent_notional > 0 else 0.0
    if fast_cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN', 'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'}:
        impulse_score -= 12.0
    if fake_type in {'FAKE_UP', 'FAKE_DOWN'}:
        impulse_score -= 18.0
    if acceptance in {'FAILED_UP_ACCEPTANCE', 'FAILED_DOWN_ACCEPTANCE', 'EXHAUSTION'}:
        impulse_score -= 10.0
    if ct_risk == 'HIGH':
        impulse_score -= 4.0
    impulse_score = max(0.0, min(100.0, impulse_score))

    if impulse_score >= 70.0:
        impulse_label = 'STRONG'
    elif impulse_score >= 48.0:
        impulse_label = 'ACTIVE'
    elif impulse_score >= 26.0:
        impulse_label = 'WEAK'
    else:
        impulse_label = 'DEAD'

    continuation_score = impulse_score * 0.48
    continuation_score += 12.0 if fast_cls in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} else 0.0
    continuation_score += 6.0 if fast_cls in {'WEAK_CONTINUATION_UP', 'WEAK_CONTINUATION_DOWN'} else 0.0
    continuation_score += 8.0 if acceptance in {'UP_ACCEPTANCE_CONFIRMED', 'DOWN_ACCEPTANCE_CONFIRMED'} else 0.0
    continuation_score += 4.0 if acceptance in {'UP_ACCEPTANCE_PROBING', 'DOWN_ACCEPTANCE_PROBING'} else 0.0
    continuation_score += 5.0 if recent_events >= 3 and recent_notional > 0 else 0.0
    continuation_score += 4.0 if projection_bias in {'LONG', 'SHORT', 'UP', 'DOWN'} and projection_conf >= 55.0 else 0.0
    if fake_type in {'FAKE_UP', 'FAKE_DOWN'}:
        continuation_score -= 22.0
    if fast_cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN', 'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'}:
        continuation_score -= 14.0
    if acceptance in {'FAILED_UP_ACCEPTANCE', 'FAILED_DOWN_ACCEPTANCE', 'EXHAUSTION'}:
        continuation_score -= 10.0
    continuation_score = max(0.0, min(100.0, continuation_score))
    continuation_label = 'HIGH' if continuation_score >= 62.0 else 'MEDIUM' if continuation_score >= 38.0 else 'LOW'

    trend_dir = 'NEUTRAL'
    if fast_cls.endswith('_UP') or projection_bias in {'LONG', 'UP'}:
        trend_dir = 'UP'
    elif fast_cls.endswith('_DOWN') or projection_bias in {'SHORT', 'DOWN'}:
        trend_dir = 'DOWN'

    outer_edge = width * 0.16 if width > 0 else 0.0
    inner_mid = width * 0.12 if width > 0 else 0.0

    short_low = max(low, high - outer_edge) if width > 0 else 0.0
    short_high = high if high > 0 else 0.0
    long_low = low if low > 0 else 0.0
    long_high = min(high, low + outer_edge) if width > 0 else 0.0
    mid_low = max(low, mid - inner_mid) if width > 0 else 0.0
    mid_high = min(high, mid + inner_mid) if width > 0 else 0.0

    liq_quality = 'NONE'
    if upper_cluster > 0 or lower_cluster > 0 or recent_events > 0:
        liq_quality = 'LIVE' if (recent_events > 0 and not fallback_active and feed_health in {'LIVE', 'METRICS_ONLY', ''}) else 'FALLBACK'

    if upper_cluster > 0 and width > 0 and upper_cluster >= mid:
        zone_half = width * 0.05
        short_low = max(mid, upper_cluster - zone_half)
        short_high = min(high, upper_cluster + zone_half)
    if lower_cluster > 0 and width > 0 and lower_cluster <= mid:
        zone_half = width * 0.05
        long_low = max(low, lower_cluster - zone_half)
        long_high = min(mid, lower_cluster + zone_half)

    short_prox_pct = _dist_pct(price, short_low) if short_low > 0 else 999.0
    long_prox_pct = _dist_pct(price, long_high) if long_high > 0 else 999.0
    zone_touch_pct = max(0.22, width / price * 0.06) if price > 0 and width > 0 else 0.35
    zone_near_pct = max(0.38, width / price * 0.11) if price > 0 and width > 0 else 0.60

    active_zone = 'MID'
    if short_low <= price <= short_high and short_high > short_low:
        active_zone = 'SHORT_ZONE'
    elif long_low <= price <= long_high and long_high > long_low:
        active_zone = 'LONG_ZONE'
    elif mid_low <= price <= mid_high and mid_high > mid_low:
        active_zone = 'NO_TRADE_MID'

    proximity_side = 'NEUTRAL'
    proximity_state = 'FAR'
    reversal_side = 'NEUTRAL'
    reversal_conf = 0.0
    reversal_reason = 'цена не в рабочей зоне'
    if short_high > short_low and short_prox_pct <= zone_touch_pct and price <= short_low:
        proximity_side = 'SHORT'
        proximity_state = 'TOUCH'
    elif long_high > long_low and long_prox_pct <= zone_touch_pct and price >= long_high:
        proximity_side = 'LONG'
        proximity_state = 'TOUCH'
    elif short_high > short_low and short_prox_pct <= zone_near_pct and price <= short_low:
        proximity_side = 'SHORT'
        proximity_state = 'NEAR'
    elif long_high > long_low and long_prox_pct <= zone_near_pct and price >= long_high:
        proximity_side = 'LONG'
        proximity_state = 'NEAR'

    reaction_score = 0.0
    reaction_state = 'NONE'
    reaction_text = 'нет реакции от зоны'
    if fake_type in {'FAKE_UP', 'FAKE_DOWN'}:
        reaction_score = max(reaction_score, max(fake_conf, 68.0))
        reaction_state = 'REJECT'
        reaction_text = 'ложный вынос уже подтверждён'
    elif fast_cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN'}:
        reaction_score = max(reaction_score, max(fast_conf, 56.0))
        reaction_state = 'READY_RECLAIM'
        reaction_text = 'рынок даёт вероятность ловушки, ждём reclaim'
    elif fast_cls in {'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'}:
        reaction_score = max(reaction_score, max(fast_conf, 48.0))
        reaction_state = 'EARLY_RISK'
        reaction_text = 'есть ранний риск ложного выноса'

    if active_zone == 'SHORT_ZONE':
        zone_bonus = 16.0 if impulse_label in {'DEAD', 'WEAK'} else 8.0
        reaction_score = max(reaction_score, reversal_conf + zone_bonus)
        if reaction_state == 'NONE':
            reaction_state = 'IN_ZONE_SHORT'
            reaction_text = 'цена в верхней зоне, нужна реакция продавца'
    elif active_zone == 'LONG_ZONE':
        zone_bonus = 16.0 if impulse_label in {'DEAD', 'WEAK'} else 8.0
        reaction_score = max(reaction_score, reversal_conf + zone_bonus)
        if reaction_state == 'NONE':
            reaction_state = 'IN_ZONE_LONG'
            reaction_text = 'цена в нижней зоне, нужен выкуп'
    elif proximity_state == 'TOUCH':
        near_bonus = 14.0 if impulse_label in {'DEAD', 'WEAK'} else 8.0
        reaction_score = max(reaction_score, reversal_conf + near_bonus)
        if reaction_state == 'NONE':
            reaction_state = 'TOUCH'
            reaction_text = 'касание рабочей зоны, жди первую реакцию'
    elif proximity_state == 'NEAR':
        near_bonus = 8.0 if impulse_label in {'DEAD', 'WEAK'} else 4.0
        reaction_score = max(reaction_score, reversal_conf + near_bonus)
        if reaction_state == 'NONE':
            reaction_state = 'NEAR'
            reaction_text = 'цена подходит к рабочей зоне'

    if acceptance in {'FAILED_UP_ACCEPTANCE', 'FAILED_DOWN_ACCEPTANCE', 'EXHAUSTION'}:
        reaction_score += 8.0
        if reaction_state in {'NONE', 'NEAR'}:
            reaction_state = 'REJECT'
            reaction_text = 'принятие цены провалилось, есть реакция против движения'
    if continuation_label == 'LOW' and impulse_label == 'DEAD' and proximity_state in {'NEAR', 'TOUCH'}:
        reaction_score += 6.0
    reaction_score = _clamp(reaction_score, 0.0, 100.0)

    if price > 0 and short_high > short_low and price >= short_low:
        reversal_side = 'SHORT'
        reversal_conf = max(reversal_conf, 34.0 + max(0.0, (rpct - 58.0)) * 1.1)
        reversal_reason = 'верхняя зона продавца / возврат в диапазон'
    if price > 0 and long_high > long_low and price <= long_high:
        long_conf = 34.0 + max(0.0, (42.0 - rpct)) * 1.1
        if long_conf >= reversal_conf:
            reversal_side = 'LONG'
            reversal_conf = long_conf
            reversal_reason = 'нижняя зона покупателя / возврат в диапазон'

    if fake_type == 'FAKE_UP' or fast_cls in {'LIKELY_FAKE_UP', 'EARLY_FAKE_UP_RISK'}:
        reversal_side = 'SHORT'
        reversal_conf = max(reversal_conf, fake_conf or fast_conf or 58.0)
        reversal_reason = 'ложный вынос вверх / слабое принятие цены'
    elif fake_type == 'FAKE_DOWN' or fast_cls in {'LIKELY_FAKE_DOWN', 'EARLY_FAKE_DOWN_RISK'}:
        reversal_side = 'LONG'
        reversal_conf = max(reversal_conf, fake_conf or fast_conf or 58.0)
        reversal_reason = 'ложный пролив вниз / reclaim вверх'
    elif fast_cls in {'CONTINUATION_UP', 'CONTINUATION_DOWN'}:
        reversal_conf = min(reversal_conf, 28.0)
        reversal_reason = 'идёт continuation, разворот слабый'

    if recent_events >= 3 and recent_notional > 0:
        if liq_state == 'BUY_SIDE_SWEEP_REJECTED':
            reversal_side = 'SHORT'
            reversal_conf = max(reversal_conf, 62.0)
            reversal_reason = 'сверху сняли ликвидность и получили rejection'
        elif liq_state == 'SELL_SIDE_SWEEP_REJECTED':
            reversal_side = 'LONG'
            reversal_conf = max(reversal_conf, 62.0)
            reversal_reason = 'снизу сняли ликвидность и получили reclaim'

    entry_side = 'NEUTRAL'
    action_code = 'WAIT'
    action_text = 'ЖДАТЬ: нет преимущества для входа'
    action_reason = 'цена вне рабочей зоны или движение не даёт edge'

    lifecycle_state = 'NOT_READY'
    lifecycle_state_ru = 'НЕ ГОТОВО'
    lifecycle_reason = 'цена далеко от рабочей зоны'
    if proximity_state == 'NEAR':
        lifecycle_state = 'READY'
        lifecycle_state_ru = 'ГОТОВИТЬ'
        lifecycle_reason = 'цена подходит к рабочей зоне'
    if proximity_state == 'TOUCH' or active_zone in {'SHORT_ZONE', 'LONG_ZONE'}:
        lifecycle_state = 'WATCH'
        lifecycle_state_ru = 'СМОТРЕТЬ РЕАКЦИЮ'
        lifecycle_reason = 'цена коснулась рабочей зоны'
    if reaction_state in {'REJECT', 'READY_RECLAIM'} and reaction_score >= 56.0:
        lifecycle_state = 'ACTIVE'
        lifecycle_state_ru = 'АКТИВНЫЙ ТРИГГЕР'
        lifecycle_reason = reaction_text

    # V13.3 entry lifecycle + reaction engine
    reclaim_side = 'NEUTRAL'
    reclaim_text = 'нет reclaim-триггера'
    trigger_strength = 0.0
    entry_state = 'NOT_READY'
    entry_state_ru = 'НЕ ГОТОВО'
    trigger_reason = 'условия входа не собраны'
    entry_trigger_text = 'ждать рабочую зону и подтверждение'
    confirm_text = 'нужен возврат в диапазон и отсутствие follow-through'
    cancel_text = ''

    if fake_type == 'FAKE_UP' or fast_cls in {'LIKELY_FAKE_UP', 'EARLY_FAKE_UP_RISK'}:
        reclaim_side = 'SHORT'
        reclaim_price = reclaim_needed if reclaim_needed > 0 else (short_low if short_low > 0 else high)
        reclaim_text = f'возврат ниже {_fmt_price(reclaim_price)}'
        trigger_strength = max(fake_conf, fast_conf, reversal_conf)
        entry_trigger_text = f'SHORT trigger: {reclaim_text} и слабая следующая свеча'
        confirm_text = 'после возврата под зону выноса следующая свеча не должна дать follow-through вверх'
        cancel_text = f'отмена short-идеи: принятие цены выше {_fmt_price(fake_invalidation or short_high or high)}'
    elif fake_type == 'FAKE_DOWN' or fast_cls in {'LIKELY_FAKE_DOWN', 'EARLY_FAKE_DOWN_RISK'}:
        reclaim_side = 'LONG'
        reclaim_price = reclaim_needed if reclaim_needed > 0 else (long_high if long_high > 0 else low)
        reclaim_text = f'возврат выше {_fmt_price(reclaim_price)}'
        trigger_strength = max(fake_conf, fast_conf, reversal_conf)
        entry_trigger_text = f'LONG trigger: {reclaim_text} и удержание возврата'
        confirm_text = 'после reclaim вверх следующая свеча не должна дать follow-through вниз'
        cancel_text = f'отмена long-идеи: принятие цены ниже {_fmt_price(fake_invalidation or long_low or low)}'
    elif fast_cls == 'CONTINUATION_UP' and continuation_score >= 55.0:
        reclaim_side = 'LONG'
        reclaim_text = f'retest выше {_fmt_price(short_low or mid)}'
        trigger_strength = continuation_score
        entry_trigger_text = f'LONG continuation: {reclaim_text}'
        confirm_text = 'вход только после retest и удержания над зоной'
        cancel_text = f'отмена continuation: возврат ниже {_fmt_price(short_low or mid)}'
    elif fast_cls == 'CONTINUATION_DOWN' and continuation_score >= 55.0:
        reclaim_side = 'SHORT'
        reclaim_text = f'retest ниже {_fmt_price(long_high or mid)}'
        trigger_strength = continuation_score
        entry_trigger_text = f'SHORT continuation: {reclaim_text}'
        confirm_text = 'вход только после retest и удержания под зоной'
        cancel_text = f'отмена continuation: возврат выше {_fmt_price(long_high or mid)}'
    elif reversal_side == 'SHORT' and short_high > short_low:
        reclaim_side = 'SHORT'
        reclaim_text = f'реакция продавца в зоне {_fmt_price(short_low)}–{_fmt_price(short_high)}'
        trigger_strength = reversal_conf
        entry_trigger_text = f'SHORT edge: {reclaim_text}'
        confirm_text = 'нужна слабая реакция покупателя и отсутствие принятия выше high зоны'
        cancel_text = f'отмена short-идеи: принятие цены выше {_fmt_price(short_high)}'
    elif reversal_side == 'LONG' and long_high > long_low:
        reclaim_side = 'LONG'
        reclaim_text = f'выкуп в зоне {_fmt_price(long_low)}–{_fmt_price(long_high)}'
        trigger_strength = reversal_conf
        entry_trigger_text = f'LONG edge: {reclaim_text}'
        confirm_text = 'нужен reclaim вверх и отсутствие follow-through вниз'
        cancel_text = f'отмена long-идеи: принятие цены ниже {_fmt_price(long_low)}'

    if active_zone == 'NO_TRADE_MID':
        entry_state = 'NOT_READY'
        entry_state_ru = 'НЕ ГОТОВО'
        trigger_reason = 'середина диапазона: location плохая'
    elif fake_type in {'FAKE_UP', 'FAKE_DOWN'} and trigger_strength >= 66.0:
        entry_state = 'ACTIVE'
        entry_state_ru = 'АКТИВНО'
        trigger_reason = 'ложный вынос подтверждён'
    elif fast_cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN'} and trigger_strength >= 58.0:
        entry_state = 'READY'
        entry_state_ru = 'ГОТОВО'
        trigger_reason = 'есть готовый fake move сценарий, ждём reclaim'
    elif fast_cls in {'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'} and trigger_strength >= 52.0:
        entry_state = 'READY'
        entry_state_ru = 'ГОТОВО'
        trigger_reason = 'ранний fake-риск есть, но нужен confirm'
    elif fast_cls in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} and continuation_score >= 62.0:
        entry_state = 'ACTIVE'
        entry_state_ru = 'АКТИВНО'
        trigger_reason = 'continuation подтверждён удержанием'
    elif reaction_state in {'REJECT', 'READY_RECLAIM'} and reaction_score >= 56.0:
        entry_state = 'ACTIVE'
        entry_state_ru = 'АКТИВНО'
        trigger_reason = reaction_text
    elif active_zone in {'SHORT_ZONE', 'LONG_ZONE'} and reaction_score >= 46.0:
        entry_state = 'READY'
        entry_state_ru = 'ГОТОВО'
        trigger_reason = 'локация рабочая, есть первая реакция'
    elif active_zone in {'SHORT_ZONE', 'LONG_ZONE'}:
        entry_state = 'WATCH'
        entry_state_ru = 'НАБЛЮДАТЬ'
        trigger_reason = 'цена в зоне, ждём подтверждение'
    elif proximity_state == 'TOUCH':
        entry_state = 'WATCH'
        entry_state_ru = 'НАБЛЮДАТЬ'
        trigger_reason = 'касание рабочей зоны: нужна реакция'
    elif proximity_state == 'NEAR':
        entry_state = 'READY'
        entry_state_ru = 'ГОТОВО'
        trigger_reason = 'цена подходит к зоне: можно готовить сценарий'

    if active_zone == 'NO_TRADE_MID':
        action_code = 'NO_TRADE_MID'
        action_text = 'НЕ ЛЕЗТЬ: середина диапазона'
        action_reason = 'в середине нет edge, нужен подход к краю'
    elif fast_cls in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} and continuation_score >= 62.0 and acceptance in {'UP_ACCEPTANCE_CONFIRMED', 'DOWN_ACCEPTANCE_CONFIRMED', 'UP_ACCEPTANCE_PROBING', 'DOWN_ACCEPTANCE_PROBING'}:
        entry_side = 'LONG' if trend_dir == 'UP' or fast_cls == 'CONTINUATION_UP' else 'SHORT'
        action_code = 'FOLLOW_THROUGH'
        action_text = f'НЕ КОНТРИТЬ: движение {"вверх" if entry_side == "LONG" else "вниз"} ещё живое'
        action_reason = 'импульс жив и принятие цены подтверждено'
    elif entry_state == 'ACTIVE' and reclaim_side == 'SHORT':
        entry_side = 'SHORT'
        action_code = 'ENTRY_ACTIVE_SHORT'
        action_text = 'ВХОД SHORT АКТИВЕН: small/probe по триггеру'
        action_reason = trigger_reason
    elif entry_state == 'ACTIVE' and reclaim_side == 'LONG':
        entry_side = 'LONG'
        action_code = 'ENTRY_ACTIVE_LONG'
        action_text = 'ВХОД LONG АКТИВЕН: small/probe по триггеру'
        action_reason = trigger_reason
    elif entry_state == 'READY' and reclaim_side == 'SHORT':
        entry_side = 'SHORT'
        action_code = 'ENTRY_READY_SHORT'
        action_text = 'ГОТОВИТЬ SHORT: ждать reclaim и слабую реакцию'
        action_reason = trigger_reason
    elif entry_state == 'READY' and reclaim_side == 'LONG':
        entry_side = 'LONG'
        action_code = 'ENTRY_READY_LONG'
        action_text = 'ГОТОВИТЬ LONG: ждать reclaim и удержание возврата'
        action_reason = trigger_reason
    elif reversal_side == 'SHORT' and reversal_conf >= 52.0 and short_high > short_low:
        entry_side = 'SHORT'
        action_code = 'LOOK_SHORT_ZONE'
        action_text = 'ИСКАТЬ ШОРТ В ВЕРХНЕЙ ЗОНЕ'
        action_reason = reversal_reason
    elif reversal_side == 'LONG' and reversal_conf >= 52.0 and long_high > long_low:
        entry_side = 'LONG'
        action_code = 'LOOK_LONG_ZONE'
        action_text = 'ИСКАТЬ ЛОНГ В НИЖНЕЙ ЗОНЕ'
        action_reason = reversal_reason
    elif active_zone in {'SHORT_ZONE', 'LONG_ZONE'}:
        entry_side = 'SHORT' if active_zone == 'SHORT_ZONE' else 'LONG'
        action_code = 'ARM_EDGE'
        action_text = f'НАБЛЮДАТЬ {"ШОРТ" if entry_side == "SHORT" else "ЛОНГ"}: зона близко, жди confirm'
        action_reason = 'локация уже рабочая, но подтверждения мало'

    confirmation_state = 'NONE'
    confirmation_state_ru = 'НЕТ'
    confirmation_score = 0.0
    confirmation_reason = 'нет подтверждающей свечной реакции'
    if entry_side == 'LONG' or reversal_side == 'LONG' or active_zone == 'LONG_ZONE':
        zone_ref = long_high if long_high > 0 else low
        reclaim_ok = close_price >= zone_ref and zone_ref > 0
        bounce_pct = ((close_price - low) / max(1e-9, high - low) * 100.0) if high > low else 0.0
        wick_ok = cm.get('lower_wick_pct', 0.0) >= 28.0
        fail_accept = acceptance in {'FAILED_DOWN_ACCEPTANCE', 'EXHAUSTION'}
        if active_zone == 'LONG_ZONE' and (wick_ok or fail_accept or reclaim_ok):
            confirmation_score = max(confirmation_score, 42.0 + reaction_score * 0.35 + (18.0 if reclaim_ok else 0.0) + (10.0 if wick_ok else 0.0) + (8.0 if fail_accept else 0.0) + max(0.0, bounce_pct - 45.0) * 0.35)
            confirmation_reason = 'нижнюю зону выкупают, возврат внутрь диапазона подтверждается'
        if fake_type == 'FAKE_DOWN':
            confirmation_score = max(confirmation_score, max(fake_conf, 62.0) + (8.0 if reclaim_ok else 0.0))
            confirmation_reason = 'ложный пролив вниз подтверждён reclaim вверх'
    if entry_side == 'SHORT' or reversal_side == 'SHORT' or active_zone == 'SHORT_ZONE':
        zone_ref = short_low if short_low > 0 else high
        reclaim_ok = 0 < close_price <= zone_ref if zone_ref > 0 else False
        fade_pct = ((high - close_price) / max(1e-9, high - low) * 100.0) if high > low else 0.0
        wick_ok = cm.get('upper_wick_pct', 0.0) >= 28.0
        fail_accept = acceptance in {'FAILED_UP_ACCEPTANCE', 'EXHAUSTION'}
        if active_zone == 'SHORT_ZONE' and (wick_ok or fail_accept or reclaim_ok):
            confirmation_score = max(confirmation_score, 42.0 + reaction_score * 0.35 + (18.0 if reclaim_ok else 0.0) + (10.0 if wick_ok else 0.0) + (8.0 if fail_accept else 0.0) + max(0.0, fade_pct - 45.0) * 0.35)
            confirmation_reason = 'верхнюю зону продают, возврат внутрь диапазона подтверждается'
        if fake_type == 'FAKE_UP':
            confirmation_score = max(confirmation_score, max(fake_conf, 62.0) + (8.0 if reclaim_ok else 0.0))
            confirmation_reason = 'ложный вынос вверх подтверждён возвратом вниз'

    confirmation_score = _clamp(confirmation_score, 0.0, 100.0)
    if confirmation_score >= 72.0:
        confirmation_state = 'CONFIRMED'
        confirmation_state_ru = 'ПОДТВЕРЖДЁН'
    elif confirmation_score >= 54.0:
        confirmation_state = 'EARLY'
        confirmation_state_ru = 'РАННИЙ'

    if confirmation_state == 'CONFIRMED' and (reclaim_side in {'LONG', 'SHORT'} or entry_side in {'LONG', 'SHORT'}):
        entry_state = 'ACTIVE'
        entry_state_ru = 'АКТИВНО'
        lifecycle_state = 'ACTIVE'
        lifecycle_state_ru = 'АКТИВНЫЙ ТРИГГЕР'
        lifecycle_reason = confirmation_reason
        trigger_reason = confirmation_reason
        trigger_strength = max(trigger_strength, confirmation_score)
        if entry_side == 'NEUTRAL':
            entry_side = reclaim_side if reclaim_side in {'LONG', 'SHORT'} else reversal_side
        action_code = 'ENTRY_ACTIVE_LONG' if entry_side == 'LONG' else 'ENTRY_ACTIVE_SHORT'
        action_text = f'ВХОД {_side_ru(entry_side)} АКТИВЕН: small/probe после подтверждения зоны'
        action_reason = confirmation_reason
    elif confirmation_state == 'EARLY' and active_zone in {'LONG_ZONE', 'SHORT_ZONE'}:
        entry_state = 'READY'
        entry_state_ru = 'ГОТОВО'
        lifecycle_state = 'WATCH'
        lifecycle_state_ru = 'СМОТРЕТЬ РЕАКЦИЮ'
        lifecycle_reason = confirmation_reason
        trigger_reason = confirmation_reason
        trigger_strength = max(trigger_strength, confirmation_score)
        if entry_side == 'NEUTRAL':
            entry_side = 'LONG' if active_zone == 'LONG_ZONE' else 'SHORT'
        action_code = 'ENTRY_READY_LONG' if entry_side == 'LONG' else 'ENTRY_READY_SHORT'
        action_text = f'ГОТОВИТЬ {_side_ru(entry_side)}: реакция появилась, жди удержание'
        action_reason = confirmation_reason

    short_zone_text = f'{_fmt_price(short_low)}–{_fmt_price(short_high)}' if short_high > short_low else 'нет данных'
    long_zone_text = f'{_fmt_price(long_low)}–{_fmt_price(long_high)}' if long_high > long_low else 'нет данных'
    no_trade_text = f'{_fmt_price(mid_low)}–{_fmt_price(mid_high)}' if mid_high > mid_low else 'нет данных'

    invalidation_text = 'нет данных'
    if entry_side == 'SHORT' and short_high > 0:
        invalidation_text = f'принятие цены выше {_fmt_price(fake_invalidation or short_high)} и follow-through вверх'
    elif entry_side == 'LONG' and long_low > 0:
        invalidation_text = f'принятие цены ниже {_fmt_price(fake_invalidation or long_low)} и follow-through вниз'
    elif high > 0 and low > 0:
        invalidation_text = f'выход из диапазона {_fmt_price(low)}–{_fmt_price(high)} с удержанием за границей'

    liquidity_text = 'нет реальной ликвидационной зоны'
    if liq_quality != 'NONE':
        if upper_cluster > 0 and lower_cluster > 0:
            liquidity_text = f'верх {upper_cluster:.2f} / низ {lower_cluster:.2f} ({liq_quality})'
        elif upper_cluster > 0:
            liquidity_text = f'верх {upper_cluster:.2f} ({liq_quality})'
        elif lower_cluster > 0:
            liquidity_text = f'низ {lower_cluster:.2f} ({liq_quality})'
        elif magnet_side in {'UP', 'DOWN'}:
            liquidity_text = f'магнит {magnet_side} ({liq_quality})'

    impulse_note = 'движение шумовое'
    if impulse_label == 'STRONG':
        impulse_note = 'импульс сильный, рынок ещё может тащить дальше'
    elif impulse_label == 'ACTIVE':
        impulse_note = 'импульс живой, но уже не безусловный'
    elif impulse_label == 'WEAK':
        impulse_note = 'есть движение, но без права гнаться'

    if fake_type in {'FAKE_UP', 'FAKE_DOWN'} or fast_cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN', 'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'}:
        impulse_note += '; есть риск ловушки'
    if cascade_risk == 'HIGH':
        impulse_note += '; рядом каскадная ликвидность'

    fake_label_out = fake_type or fast_cls or 'NONE'
    fake_conf_out = round(max(fake_conf, fast_conf if 'FAKE' in fast_cls else 0.0), 1)

    return {
        'proximity_side': proximity_side,
        'proximity_state': proximity_state,
        'short_prox_pct': round(short_prox_pct, 3) if short_prox_pct < 999 else 999.0,
        'long_prox_pct': round(long_prox_pct, 3) if long_prox_pct < 999 else 999.0,
        'reaction_state': reaction_state,
        'reaction_score': round(reaction_score, 1),
        'reaction_text': reaction_text,
        'lifecycle_state': lifecycle_state,
        'lifecycle_state_ru': lifecycle_state_ru,
        'lifecycle_reason': lifecycle_reason,
        'impulse_score': round(impulse_score, 1),
        'impulse_label': impulse_label,
        'impulse_note': impulse_note,
        'continuation_score': round(continuation_score, 1),
        'continuation_label': continuation_label,
        'trend_dir': trend_dir,
        'active_zone': active_zone,
        'short_zone_low': round(short_low, 2),
        'short_zone_high': round(short_high, 2),
        'short_zone_text': short_zone_text,
        'long_zone_low': round(long_low, 2),
        'long_zone_high': round(long_high, 2),
        'long_zone_text': long_zone_text,
        'no_trade_low': round(mid_low, 2),
        'no_trade_high': round(mid_high, 2),
        'no_trade_text': no_trade_text,
        'reversal_side': reversal_side,
        'reversal_side_ru': _side_ru(reversal_side),
        'reversal_conf': round(reversal_conf, 1),
        'reversal_reason': reversal_reason,
        'entry_side': entry_side,
        'entry_side_ru': _side_ru(entry_side),
        'action_code': action_code,
        'action_text': action_text,
        'action_reason': action_reason,
        'entry_state': entry_state,
        'entry_state_ru': entry_state_ru,
        'entry_trigger_text': entry_trigger_text,
        'trigger_reason': trigger_reason,
        'confirm_text': confirm_text,
        'cancel_text': cancel_text or invalidation_text,
        'confirmation_state': confirmation_state,
        'confirmation_state_ru': confirmation_state_ru,
        'confirmation_score': round(confirmation_score, 1),
        'confirmation_reason': confirmation_reason,
        'reclaim_side': reclaim_side,
        'reclaim_text': reclaim_text,
        'trigger_strength': round(trigger_strength, 1),
        'fake_action': fake_action or 'нет данных',
        'fake_execution_mode': fake_execution_mode or 'NONE',
        'invalidation_text': invalidation_text,
        'liquidity_quality': liq_quality,
        'liquidity_text': liquidity_text,
        'fake_type': fake_label_out,
        'fake_conf': fake_conf_out,
        'continuation_target': continuation_target or 'нет данных',
        'magnet_side': magnet_side or 'NEUTRAL',
        'feed_health': feed_health or ('FALLBACK' if fallback_active else 'NONE'),
        'recent_events': recent_events,
        'recent_notional_usd': round(recent_notional, 2),
        'zone_state_short': _zone_state(price, short_low, short_high, mid_low, mid_high),
        'zone_state_long': _zone_state(price, long_low, long_high, mid_low, mid_high),
    }


__all__ = ['build_v13_trade_fix_context']
