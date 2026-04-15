from __future__ import annotations

from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _s(value: Any, default: str = '') -> str:
    return str(value if value is not None else default).strip()


def _pick(mapping: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if isinstance(mapping, dict) and mapping.get(key) not in (None, ''):
            return mapping.get(key)
    return default


def evaluate_external_market_bias(payload: Dict[str, Any], view: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    view = view if isinstance(view, dict) else {}
    btc_ctx = payload.get('btc_context') if isinstance(payload.get('btc_context'), dict) else {}

    dxy = _f(_pick(payload, 'dxy_change_pct', 'dxy_move_pct', default=0.0))
    spy = _f(_pick(payload, 'spy_change_pct', 'spx_change_pct', 'es_change_pct', default=0.0))
    dominance = _f(_pick(payload, 'btc_dominance_change_pct', 'dominance_change_pct', default=0.0))
    btc_5m = _f(_pick(btc_ctx, 'change_5m_pct', 'move_5m_pct', default=_pick(payload, 'btc_change_5m_pct', default=0.0)))
    btc_15m = _f(_pick(btc_ctx, 'change_15m_pct', 'move_15m_pct', default=_pick(payload, 'btc_change_15m_pct', default=0.0)))
    htf = _s(_pick(payload, 'htf_trend', 'trend_4h', 'trend_1d', default='')).upper()

    score = 0.0
    drivers: list[str] = []
    if dxy >= 0.30:
        score -= 0.35
        drivers.append('DXY вверх')
    elif dxy <= -0.30:
        score += 0.35
        drivers.append('DXY вниз')
    if spy <= -0.50:
        score -= 0.35
        drivers.append('SPX/US risk-off')
    elif spy >= 0.50:
        score += 0.35
        drivers.append('SPX/US risk-on')
    if dominance >= 0.20:
        score -= 0.20
        drivers.append('доминация BTC растёт')
    elif dominance <= -0.20:
        score += 0.15
        drivers.append('доминация BTC снижается')
    if btc_5m <= -0.8 or btc_15m <= -1.6:
        score -= 0.30
        drivers.append('BTC поводырь давит вниз')
    elif btc_5m >= 0.8 or btc_15m >= 1.6:
        score += 0.30
        drivers.append('BTC поводырь поддерживает рост')
    if 'BEAR' in htf or 'DOWN' in htf:
        score -= 0.10
    elif 'BULL' in htf or 'UP' in htf:
        score += 0.10

    if score <= -0.55:
        state = 'RISK_OFF'
        blocked_side = 'LONG'
    elif score >= 0.55:
        state = 'RISK_ON'
        blocked_side = 'SHORT'
    elif score <= -0.20:
        state = 'BEARISH_SUPPORT'
        blocked_side = 'NONE'
    elif score >= 0.20:
        state = 'BULLISH_SUPPORT'
        blocked_side = 'NONE'
    else:
        state = 'NEUTRAL_EXTERN'
        blocked_side = 'NONE'

    driver = drivers[0] if drivers else 'внешний фон нейтрален'
    if state == 'RISK_OFF':
        long_text = 'лонг ослаблен; нижние блоки считать менее надёжными'
        short_text = 'шорт поддержан внешним risk-off'
    elif state == 'RISK_ON':
        long_text = 'лонг поддержан внешним risk-on'
        short_text = 'шорт ослаблен; верхние блоки менее надёжны'
    elif state == 'BEARISH_SUPPORT':
        long_text = 'лонг слабее обычного'
        short_text = 'шорт получает внешний плюс'
    elif state == 'BULLISH_SUPPORT':
        long_text = 'лонг получает внешний плюс'
        short_text = 'шорт слабее обычного'
    else:
        long_text = 'лонг без внешнего блока'
        short_text = 'шорт без внешнего блока'

    return {
        'state': state,
        'score': round(score, 3),
        'driver': driver,
        'drivers': drivers,
        'blocked_side': blocked_side,
        'long_text': long_text,
        'short_text': short_text,
    }


def evaluate_flow_pressure(payload: Dict[str, Any], view: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    view = view if isinstance(view, dict) else {}
    deriv = payload.get('derivatives_context') if isinstance(payload.get('derivatives_context'), dict) else {}

    buy_vol = _f(_pick(payload, 'taker_buy_volume_15m', 'buy_volume_15m', default=_pick(deriv, 'taker_buy_volume_15m', default=0.0)))
    sell_vol = _f(_pick(payload, 'taker_sell_volume_15m', 'sell_volume_15m', default=_pick(deriv, 'taker_sell_volume_15m', default=0.0)))
    delta_5m = _f(_pick(payload, 'delta_5m', 'orderflow_delta_5m', default=0.0))
    delta_15m = _f(_pick(payload, 'delta_15m', 'orderflow_delta_15m', default=0.0))
    cvd = _f(_pick(payload, 'cvd_proxy', 'cumulative_delta_proxy', default=delta_5m + delta_15m))
    price_5m = _f(_pick(payload, 'price_change_5m_pct', 'change_5m_pct', default=0.0))
    oi = _f(_pick(deriv, 'open_interest_change_pct', 'oi_change_pct', default=_pick(payload, 'oi_change_pct', default=0.0)))
    wick_top = _f(_pick(payload, 'upper_wick_ratio', default=0.0))
    wick_bottom = _f(_pick(payload, 'lower_wick_ratio', default=0.0))

    total = max(buy_vol + sell_vol, 1e-9)
    taker_skew = (buy_vol - sell_vol) / total
    net = (taker_skew * 0.40) + (delta_5m * 0.30) + (delta_15m * 0.20) + (cvd * 0.10)

    state = 'BALANCED_FLOW'
    summary = 'поток сбалансирован'
    add_risk_modifier = 'NORMAL'
    absorption_flag = False
    fake_risk = False

    if net >= 0.25 and price_5m < 0.10:
        state = 'ABSORBED_BUYING'
        summary = 'покупки идут, но цена не продвигается вверх — вероятен лимитный продавец'
        add_risk_modifier = 'REDUCE_LONG'
        absorption_flag = True
    elif net <= -0.25 and price_5m > -0.10:
        state = 'ABSORBED_SELLING'
        summary = 'продажи идут, но цену не продавливают — снизу есть поглощение'
        add_risk_modifier = 'REDUCE_SHORT'
        absorption_flag = True
    elif net >= 0.30 and price_5m > 0.20:
        state = 'BUY_PRESSURE'
        summary = 'поток подтверждает давление вверх'
    elif net <= -0.30 and price_5m < -0.20:
        state = 'SELL_PRESSURE'
        summary = 'поток подтверждает давление вниз'
    elif abs(net) >= 0.18:
        state = 'PRESSURE_BUILDING'
        summary = 'внутри диапазона копится скрытое одностороннее давление'

    if abs(oi) >= 6.0 and abs(price_5m) < 0.15:
        fake_risk = True
        if state in {'BUY_PRESSURE', 'SELL_PRESSURE', 'PRESSURE_BUILDING'}:
            state = 'FAKE_EXPANSION'
            summary = 'OI растёт без нормального продвижения цены — риск ловушки / squeeze'

    if price_5m > 0 and wick_top >= 0.45 and net > 0.15:
        state = 'ABSORBED_BUYING'
        summary = 'агрессивные покупки встречают поглощение сверху'
        add_risk_modifier = 'REDUCE_LONG'
        absorption_flag = True
    elif price_5m < 0 and wick_bottom >= 0.45 and net < -0.15:
        state = 'ABSORBED_SELLING'
        summary = 'агрессивные продажи встречают поглощение снизу'
        add_risk_modifier = 'REDUCE_SHORT'
        absorption_flag = True

    return {
        'state': state,
        'summary': summary,
        'net_score': round(net, 3),
        'taker_skew': round(taker_skew, 3),
        'delta_5m': round(delta_5m, 3),
        'delta_15m': round(delta_15m, 3),
        'cvd_proxy': round(cvd, 3),
        'price_change_5m_pct': round(price_5m, 3),
        'oi_change_pct': round(oi, 3),
        'add_risk_modifier': add_risk_modifier,
        'absorption_flag': absorption_flag,
        'fake_risk': fake_risk,
    }


def evaluate_pre_hedge_warning(payload: Dict[str, Any], view: Dict[str, Any] | None, consensus: Dict[str, Any], external_bias: Dict[str, Any], flow_pressure: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    view = view if isinstance(view, dict) else {}
    ctx = view.get('ctx') if isinstance(view.get('ctx'), dict) else {}
    side = _s(view.get('side') or payload.get('side') or 'NEUTRAL').upper()
    confidence = _f(view.get('scenario_confidence') or payload.get('scenario_confidence') or 0.0)
    near_edge = bool(ctx.get('at_lower_edge') or ctx.get('at_upper_edge') or ctx.get('at_edge'))
    range_state = _s(ctx.get('range_state') or '').upper()
    extern_state = _s(external_bias.get('state') or '').upper()
    flow_state = _s(flow_pressure.get('state') or '').upper()
    blocked = _s(consensus.get('blocked_side') or 'NONE').upper()

    status = 'PRE_HEDGE_OFF'
    reason = 'ранней угрозы нет'
    action = 'pre-hedge не нужен'

    if extern_state in {'RISK_OFF', 'BEARISH_SUPPORT'} and flow_state in {'SELL_PRESSURE', 'ABSORBED_BUYING', 'PRESSURE_BUILDING', 'FAKE_EXPANSION'}:
        status = 'PRE_HEDGE_WATCH'
        reason = 'внешний фон и поток ухудшают long-side'
        action = 'не расширять добор и заранее готовить защитный сценарий'
    if near_edge and status == 'PRE_HEDGE_WATCH':
        status = 'PRE_HEDGE_ARMED'
        reason = 'у края диапазона давление может перейти в пробой без возврата'
        action = 'при пробое края без быстрого возврата сразу переходить в DEFEND'
    if near_edge and blocked == 'LONG' and flow_state in {'SELL_PRESSURE', 'ABSORBED_BUYING', 'FAKE_EXPANSION'} and confidence < 60:
        status = 'PRE_HEDGE_TRIGGER_ZONE'
        reason = 'нижний край под риском; long-side ослаблен ещё до перегруза'
        action = 'пробой без reclaim = защита / hedge watch без новых доборов'
    if side == 'SHORT' and extern_state in {'RISK_ON', 'BULLISH_SUPPORT'} and flow_state in {'BUY_PRESSURE', 'ABSORBED_SELLING', 'PRESSURE_BUILDING', 'FAKE_EXPANSION'}:
        status = 'PRE_HEDGE_WATCH' if status == 'PRE_HEDGE_OFF' else status
        reason = 'внешний фон и поток ухудшают short-side'
        action = 'не расширять добор против роста и держать защитный сценарий рядом'

    return {
        'status': status,
        'reason': reason,
        'action': action,
    }
