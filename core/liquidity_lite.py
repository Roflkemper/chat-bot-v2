from __future__ import annotations

from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _s(value: Any, default: str = "") -> str:
    return str(value or default)


def build_liquidity_lite_context(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = data or {}
    price = _f(data.get('price') or data.get('current_price') or 0.0)
    low = _f(data.get('range_low') or 0.0)
    mid = _f(data.get('range_mid') or 0.0)
    high = _f(data.get('range_high') or 0.0)

    liq = data.get('liquidation_context') if isinstance(data.get('liquidation_context'), dict) else {}
    deriv = data.get('derivatives_context') if isinstance(data.get('derivatives_context'), dict) else {}
    fast = data.get('fast_move') if isinstance(data.get('fast_move'), dict) else data.get('fast_move_context') if isinstance(data.get('fast_move_context'), dict) else {}
    fake = data.get('fake_move_detector') if isinstance(data.get('fake_move_detector'), dict) else {}
    soft = data.get('soft_signal') if isinstance(data.get('soft_signal'), dict) else {}

    width = max(high - low, 0.0)
    pos_pct = ((price - low) / width * 100.0) if price > 0 and width > 0 else 50.0
    if pos_pct >= 70:
        location_state = 'UPPER_EDGE'
    elif pos_pct <= 30:
        location_state = 'LOWER_EDGE'
    else:
        location_state = 'MID'

    distance_up_pct = ((high - price) / price * 100.0) if price > 0 and high > 0 else 0.0
    distance_down_pct = ((price - low) / price * 100.0) if price > 0 and low > 0 else 0.0
    wick_signal = 'NEUTRAL'
    magnet_side = _s(liq.get('magnet_side'), 'NEUTRAL').upper()
    liquidity_state = _s(liq.get('liquidity_state'), 'NEUTRAL').upper()
    cascade_risk = _s(liq.get('cascade_risk'), 'LOW').upper()
    squeeze_risk = _s(deriv.get('squeeze_risk'), 'LOW').upper()
    fast_class = _s(fast.get('classification') or fake.get('type'), 'BALANCED').upper()

    if liquidity_state == 'BUY_SIDE_SWEEP_REJECTED' or fast_class == 'LIKELY_FAKE_UP':
        wick_signal = 'UP_SWEEP_REJECTED'
    elif liquidity_state == 'SELL_SIDE_SWEEP_REJECTED' or fast_class == 'LIKELY_FAKE_DOWN':
        wick_signal = 'DOWN_SWEEP_REJECTED'
    elif location_state == 'UPPER_EDGE' and squeeze_risk in {'MEDIUM', 'HIGH'}:
        wick_signal = 'UPPER_LIQUIDITY_NEAR'
    elif location_state == 'LOWER_EDGE' and squeeze_risk in {'MEDIUM', 'HIGH'}:
        wick_signal = 'LOWER_LIQUIDITY_NEAR'

    setup_bias = 'NEUTRAL'
    action_hint = 'ждать смещение к краю диапазона'
    trap_side = 'NONE'
    confidence = 48.0

    if wick_signal == 'UP_SWEEP_REJECTED':
        setup_bias = 'SHORT_AFTER_FAKE_UP'
        trap_side = 'UP'
        confidence = 67.0
        action_hint = 'ждать возврат под зону выноса и искать аккуратный шорт'
    elif wick_signal == 'DOWN_SWEEP_REJECTED':
        setup_bias = 'LONG_AFTER_FAKE_DOWN'
        trap_side = 'DOWN'
        confidence = 67.0
        action_hint = 'ждать возврат выше зоны пролива и искать аккуратный лонг'
    elif location_state == 'UPPER_EDGE' and magnet_side in {'DOWN', 'NEUTRAL'}:
        setup_bias = 'SHORT_ZONE_WATCH'
        confidence = 58.0
        action_hint = 'верх диапазона рядом: без пробоя и принятия можно ждать реакцию вниз'
    elif location_state == 'LOWER_EDGE' and magnet_side in {'UP', 'NEUTRAL'}:
        setup_bias = 'LONG_ZONE_WATCH'
        confidence = 58.0
        action_hint = 'низ диапазона рядом: без пролива и принятия можно ждать реакцию вверх'
    elif location_state == 'MID' and soft.get('active'):
        setup_bias = 'SOFT_INTRADAY'
        confidence = 54.0
        action_hint = 'середина диапазона: только reduced size и только по подтверждению'

    next_magnet = 'нет данных'
    if high > 0 and low > 0:
        if magnet_side == 'UP':
            next_magnet = f'верх диапазона {high:.2f}'
        elif magnet_side == 'DOWN':
            next_magnet = f'низ диапазона {low:.2f}'
        elif location_state == 'UPPER_EDGE':
            next_magnet = f'верх диапазона {high:.2f}'
        elif location_state == 'LOWER_EDGE':
            next_magnet = f'низ диапазона {low:.2f}'
        else:
            next_magnet = f'середина/края {mid:.2f} / {high:.2f} / {low:.2f}'

    summary = (
        f'lite liquidity: {location_state}, bias={setup_bias}, magnet={magnet_side}, '
        f'wick={wick_signal}, squeeze={squeeze_risk}, cascade={cascade_risk}'
    )

    return {
        'location_state': location_state,
        'position_in_range_pct': round(pos_pct, 1),
        'distance_up_pct': round(distance_up_pct, 2),
        'distance_down_pct': round(distance_down_pct, 2),
        'wick_signal': wick_signal,
        'setup_bias': setup_bias,
        'trap_side': trap_side,
        'confidence': confidence,
        'action_hint': action_hint,
        'next_magnet': next_magnet,
        'summary': summary,
    }
