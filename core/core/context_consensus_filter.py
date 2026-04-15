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
        if key in mapping and mapping.get(key) not in (None, ''):
            return mapping.get(key)
    return default


def _score_to_bias(score: float) -> str:
    if score >= 0.60:
        return 'STRONG_BULL'
    if score >= 0.20:
        return 'BULL'
    if score <= -0.60:
        return 'STRONG_BEAR'
    if score <= -0.20:
        return 'BEAR'
    return 'NEUTRAL'


def _blocked_side(bias: str, trend_pressure: str, leader_pressure: str) -> str:
    if bias == 'STRONG_BEAR':
        return 'LONG'
    if bias == 'STRONG_BULL':
        return 'SHORT'
    if bias == 'BEAR' and leader_pressure in {'BTC_DOWN_HARD', 'BTC_DOWN'} and trend_pressure in {'TRENDING_DOWN', 'TRENDING_UP', 'RISK_OFF_GRID'}:
        return 'LONG'
    if bias == 'BULL' and leader_pressure in {'BTC_UP_HARD', 'BTC_UP'} and trend_pressure in {'TRENDING_UP', 'TRENDING_DOWN', 'RISK_OFF_GRID'}:
        return 'SHORT'
    return 'NONE'




def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _funding_regime(funding: float) -> str:
    if funding >= 0.01:
        return 'HIGH_POSITIVE'
    if funding <= -0.005:
        return 'NEGATIVE'
    return 'NORMAL'


def _flow_proxy_score(payload: Dict[str, Any], derivatives: Dict[str, Any]) -> tuple[float, float, float]:
    buy = _f(_pick(derivatives, 'taker_buy_volume', 'buy_volume', default=_pick(payload, 'taker_buy_volume', default=0.0)))
    sell = _f(_pick(derivatives, 'taker_sell_volume', 'sell_volume', default=_pick(payload, 'taker_sell_volume', default=0.0)))
    total = abs(buy) + abs(sell)
    delta_ratio = 0.0 if total <= 0 else (buy - sell) / (total + 1e-9)
    price_change = _f(_pick(payload, 'price_change_1h_pct', 'change_1h_pct', default=0.0)) / 100.0
    atr_pct = abs(_f(_pick(payload, 'atr_pct_1h', 'atr_pct', default=1.0))) / 100.0
    if atr_pct <= 1e-9:
        atr_pct = 0.01
    import math
    price_norm = math.tanh(price_change / atr_pct)
    absorption = _clamp(delta_ratio - price_norm, -1.0, 1.0)
    flow_score = _clamp(delta_ratio * 0.6 - absorption * 0.4, -1.0, 1.0)
    return round(delta_ratio, 4), round(absorption, 4), round(flow_score, 4)

def evaluate_context_consensus(payload: Dict[str, Any], view: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    view = view if isinstance(view, dict) else {}
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    derivatives = payload.get('derivatives_context') if isinstance(payload.get('derivatives_context'), dict) else {}
    btc_ctx = payload.get('btc_context') if isinstance(payload.get('btc_context'), dict) else {}
    eth_ctx = payload.get('eth_context') if isinstance(payload.get('eth_context'), dict) else {}

    htf_price_above = bool(_pick(payload, 'htf_price_above_ema200', 'price_above_ema200_4h', default=False))
    htf_price_below = bool(_pick(payload, 'htf_price_below_ema200', 'price_below_ema200_4h', default=False))
    htf_rsi = _f(_pick(payload, 'htf_rsi', 'rsi_4h', 'rsi_1d', 'htf_rsi_4h', default=50.0), 50.0)
    htf_trend = _s(_pick(payload, 'htf_trend', 'trend_4h', 'trend_1d', default='')).upper()

    htf_score = 0.0
    if htf_price_above or 'BULL' in htf_trend or 'UP' in htf_trend:
        htf_score += 0.55
    if htf_price_below or 'BEAR' in htf_trend or 'DOWN' in htf_trend:
        htf_score -= 0.55
    if htf_rsi > 54:
        htf_score += 0.35
    elif htf_rsi < 46:
        htf_score -= 0.35
    htf_score = max(-1.0, min(1.0, htf_score))
    if htf_score >= 0.45:
        htf_state = 'BULLISH_HTF'
    elif htf_score <= -0.45:
        htf_state = 'BEARISH_HTF'
    else:
        htf_state = 'MIXED_HTF'

    adx = _f(_pick(payload, 'adx_14', 'adx', 'trend_adx', default=0.0))
    trend_strength = _f(_pick(payload, 'trend_strength', default=0.0))
    breakout = _s(_pick(payload, 'breakout_state', default=view.get('ctx', {}).get('breakout', ''))).upper()
    trend_pressure_score = 0.0
    if adx >= 30:
        trend_pressure_score = 0.75
    elif adx >= 25:
        trend_pressure_score = 0.5
    elif adx >= 18:
        trend_pressure_score = 0.2
    if abs(trend_strength) >= 0.9:
        trend_pressure_score = max(trend_pressure_score, 0.6)
    if 'CONFIRMED' in breakout:
        trend_pressure_score = max(trend_pressure_score, 0.7)
    if trend_pressure_score >= 0.7:
        trend_pressure = 'RISK_OFF_GRID'
    elif trend_pressure_score >= 0.45:
        trend_pressure = 'TRENDING_UP' if htf_score >= 0 else 'TRENDING_DOWN'
    else:
        trend_pressure = 'RANGE_OK'

    btc_5m = _f(_pick(btc_ctx, 'change_5m_pct', 'move_5m_pct', default=_pick(payload, 'btc_change_5m_pct', default=0.0)))
    btc_15m = _f(_pick(btc_ctx, 'change_15m_pct', 'move_15m_pct', default=_pick(payload, 'btc_change_15m_pct', default=0.0)))
    eth_5m = _f(_pick(eth_ctx, 'change_5m_pct', 'move_5m_pct', default=_pick(payload, 'eth_change_5m_pct', default=0.0)))
    leader_score = 0.0
    if btc_5m <= -1.0 or btc_15m <= -2.0:
        leader_score = -1.0
        leader_pressure = 'BTC_DOWN_HARD'
    elif btc_5m <= -0.45 or btc_15m <= -0.9:
        leader_score = -0.65
        leader_pressure = 'BTC_DOWN'
    elif btc_5m >= 1.0 or btc_15m >= 2.0:
        leader_score = 1.0
        leader_pressure = 'BTC_UP_HARD'
    elif btc_5m >= 0.45 or btc_15m >= 0.9:
        leader_score = 0.65
        leader_pressure = 'BTC_UP'
    else:
        leader_pressure = 'BTC_NEUTRAL'
        if eth_5m <= -0.8:
            leader_score = -0.3
        elif eth_5m >= 0.8:
            leader_score = 0.3

    funding = _f(_pick(derivatives, 'funding_rate', default=_pick(payload, 'funding_rate', default=0.0)))
    ls_ratio = _f(_pick(derivatives, 'long_short_ratio', 'global_long_short_ratio', default=_pick(payload, 'long_short_ratio', default=1.0)), 1.0)
    top_ratio = _f(_pick(derivatives, 'top_trader_long_short_ratio', default=_pick(payload, 'top_trader_long_short_ratio', default=1.0)), 1.0)
    oi_change = _f(_pick(derivatives, 'open_interest_change_pct', 'oi_change_pct', default=_pick(payload, 'oi_change_pct', default=0.0)))
    sentiment_score = 0.0
    sentiment_label = 'NEUTRAL_SENTIMENT'
    funding_regime = _funding_regime(funding)
    delta_ratio, absorption_score, flow_proxy_score = _flow_proxy_score(payload, derivatives)
    if funding >= 0.01 or ls_ratio >= 1.4:
        sentiment_score -= 0.25
        sentiment_label = 'LONG_CRODED'
    elif funding <= -0.005 or ls_ratio <= 0.72:
        sentiment_score += 0.25
        sentiment_label = 'SHORT_CROWDED'
    if top_ratio <= 0.8 and ls_ratio > 1.1:
        sentiment_score -= 0.15
        sentiment_label = 'TOP_TRADERS_LEAN_SHORT'
    elif top_ratio >= 1.2 and ls_ratio < 0.95:
        sentiment_score += 0.15
        sentiment_label = 'TOP_TRADERS_LEAN_LONG'
    if abs(oi_change) >= 6.0:
        sentiment_score += 0.10 if leader_score > 0 else -0.10 if leader_score < 0 else 0.0

    score = htf_score * 0.40 + flow_proxy_score * 0.30 + sentiment_score * 0.20 + leader_score * 0.10
    if trend_pressure_score >= 0.45:
        score += 0.10 if htf_score > 0 else -0.10 if htf_score < 0 else 0.0
    score = max(-1.0, min(1.0, score))
    overall_bias = _score_to_bias(score)
    blocked_side = _blocked_side(overall_bias, trend_pressure, leader_pressure)

    if blocked_side != 'NONE' and trend_pressure == 'RISK_OFF_GRID':
        consensus_state = 'CONSENSUS_RISK_OFF'
    elif blocked_side == 'LONG':
        consensus_state = 'CONSENSUS_BLOCKS_LONG'
    elif blocked_side == 'SHORT':
        consensus_state = 'CONSENSUS_BLOCKS_SHORT'
    elif overall_bias in {'STRONG_BULL', 'BULL'}:
        consensus_state = 'CONSENSUS_SUPPORTS_LONG'
    elif overall_bias in {'STRONG_BEAR', 'BEAR'}:
        consensus_state = 'CONSENSUS_SUPPORTS_SHORT'
    else:
        consensus_state = 'CONSENSUS_NEUTRAL'

    aggression_modifier = 'NORMAL'
    if trend_pressure == 'RISK_OFF_GRID' or blocked_side != 'NONE':
        aggression_modifier = 'REDUCE'
    elif overall_bias in {'BULL', 'BEAR'}:
        aggression_modifier = 'LIGHT_REDUCE'

    hedge_pressure_modifier = 'NORMAL'
    if trend_pressure == 'RISK_OFF_GRID' and blocked_side != 'NONE':
        hedge_pressure_modifier = 'HIGH'
    elif leader_pressure in {'BTC_DOWN_HARD', 'BTC_UP_HARD'}:
        hedge_pressure_modifier = 'ELEVATED'

    summary = {
        'STRONG_BULL': 'сильный бычий контекст',
        'BULL': 'умеренно бычий контекст',
        'NEUTRAL': 'нейтральный контекст',
        'BEAR': 'умеренно медвежий контекст',
        'STRONG_BEAR': 'сильный медвежий контекст',
    }[overall_bias]
    permission = 'обе стороны без блокировки'
    if blocked_side == 'LONG':
        permission = 'лонг-сетка ослаблена / может быть заблокирована'
    elif blocked_side == 'SHORT':
        permission = 'шорт-сетка ослаблена / может быть заблокирована'

    return {
        'htf_state': htf_state,
        'htf_rsi': round(htf_rsi, 2),
        'trend_pressure': trend_pressure,
        'adx': round(adx, 2),
        'leader_pressure': leader_pressure,
        'btc_change_5m_pct': round(btc_5m, 2),
        'btc_change_15m_pct': round(btc_15m, 2),
        'eth_change_5m_pct': round(eth_5m, 2),
        'sentiment_label': sentiment_label,
        'funding_regime': funding_regime,
        'delta_ratio': delta_ratio,
        'absorption_score': absorption_score,
        'flow_proxy_score': flow_proxy_score,
        'funding_rate': funding,
        'long_short_ratio': round(ls_ratio, 3),
        'top_trader_long_short_ratio': round(top_ratio, 3),
        'oi_change_pct': round(oi_change, 2),
        'overall_bias': overall_bias,
        'bias_score': round(score, 3),
        'consensus_state': consensus_state,
        'blocked_side': blocked_side,
        'aggression_modifier': aggression_modifier,
        'hedge_pressure_modifier': hedge_pressure_modifier,
        'summary': summary,
        'permission_text': permission,
        'risk_off_grid': trend_pressure == 'RISK_OFF_GRID',
    }
