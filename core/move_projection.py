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


def _direction(payload: Dict[str, Any]) -> str:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    raw = str(
        decision.get('direction_text')
        or decision.get('direction')
        or payload.get('final_decision')
        or payload.get('forecast_direction')
        or 'НЕЙТРАЛЬНО'
    ).upper()
    if 'LONG' in raw or 'ЛОНГ' in raw or 'ВВЕРХ' in raw or raw == 'UP':
        return 'LONG'
    if 'SHORT' in raw or 'ШОРТ' in raw or 'ВНИЗ' in raw or raw == 'DOWN':
        return 'SHORT'
    return 'NEUTRAL'


def build_move_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    fast_move = payload.get('fast_move_context') if isinstance(payload.get('fast_move_context'), dict) else {}
    flow = payload.get('trade_flow') if isinstance(payload.get('trade_flow'), dict) else {}
    fake = payload.get('fake_move_detector') if isinstance(payload.get('fake_move_detector'), dict) else {}

    side = _direction(payload)
    price = _f(payload.get('price') or payload.get('last_price') or payload.get('close'))
    low = _f(payload.get('range_low'))
    mid = _f(payload.get('range_mid'))
    high = _f(payload.get('range_high'))
    conf = _f(decision.get('confidence_pct') or decision.get('confidence') or payload.get('forecast_confidence'))
    edge = _f(decision.get('best_trade_score') or decision.get('edge_score') or payload.get('edge_score'))
    impulse_move = _f(payload.get('impulse_move_pct') or payload.get('move_pct') or payload.get('volatility_pct'))
    atr = _f(payload.get('atr') or payload.get('atr_14'))
    if atr <= 0 and price > 0:
        atr = price * 0.006

    fast_cls = str(fast_move.get('classification') or fake.get('type') or '').upper()
    mode = 'NO_EDGE'
    target_side = side

    if fast_cls in {'LIKELY_FAKE_UP', 'EARLY_FAKE_UP_RISK'}:
        mode = 'MEAN_REVERT' if fast_cls == 'LIKELY_FAKE_UP' else 'SOFT_PROJECTION'
        target_side = 'SHORT'
    elif fast_cls in {'LIKELY_FAKE_DOWN', 'EARLY_FAKE_DOWN_RISK'}:
        mode = 'MEAN_REVERT' if fast_cls == 'LIKELY_FAKE_DOWN' else 'SOFT_PROJECTION'
        target_side = 'LONG'
    elif fast_cls in {'CONTINUATION_UP', 'WEAK_CONTINUATION_UP'}:
        mode = 'CONTINUATION' if fast_cls == 'CONTINUATION_UP' else 'SOFT_PROJECTION'
        target_side = 'LONG'
    elif fast_cls in {'CONTINUATION_DOWN', 'WEAK_CONTINUATION_DOWN'}:
        mode = 'CONTINUATION' if fast_cls == 'CONTINUATION_DOWN' else 'SOFT_PROJECTION'
        target_side = 'SHORT'
    elif side in {'LONG', 'SHORT'} and conf >= 45:
        mode = 'CONTINUATION'
    elif conf >= 40:
        mode = 'SOFT_SIGNAL'
    else:
        width = max(high - low, 0.0)
        pos = ((price - low) / width) if price > 0 and width > 0 else 0.5
        if price > 0 and width > 0:
            if pos >= 0.66:
                mode = 'SOFT_PROJECTION'
                target_side = 'SHORT'
            elif pos <= 0.34:
                mode = 'SOFT_PROJECTION'
                target_side = 'LONG'
            else:
                target_side = 'NEUTRAL'
        else:
            target_side = 'NEUTRAL'

    expected_move_pct = 0.0
    if mode == 'CONTINUATION':
        expected_move_pct = max(0.35, min(1.80, 0.35 + (conf - 45.0) * 0.018 + max(edge - 50.0, 0.0) * 0.01 + impulse_move * 0.30))
    elif mode == 'MEAN_REVERT':
        expected_move_pct = max(0.40, min(1.40, 0.45 + max(0.0, impulse_move) * 0.35 + max(conf - 50.0, 0.0) * 0.012))
    elif mode == 'SOFT_SIGNAL':
        expected_move_pct = max(0.25, min(0.90, 0.25 + max(conf - 40.0, 0.0) * 0.02))
    elif mode == 'SOFT_PROJECTION':
        expected_move_pct = max(0.20, min(0.85, 0.22 + max(conf - 45.0, 0.0) * 0.015 + max(impulse_move, 0.0) * 0.18))

    target_price = None
    target_zone = 'нет данных'
    invalidation = None
    summary = 'движение недостаточно чистое для проекции'

    if price > 0 and target_side == 'LONG':
        target_price = price * (1.0 + expected_move_pct / 100.0)
        if mode == 'MEAN_REVERT':
            target_zone = f"{mid:.2f}" if mid > 0 else f"{target_price:.2f}"
            summary = 'после ложного пролива вероятен возврат к середине диапазона / ближайшему сопротивлению'
        elif mode == 'SOFT_PROJECTION':
            anchor = mid if mid > price else (high if high > price else target_price)
            target_zone = f"{anchor:.2f}"
            summary = 'мягкая проекция вверх: сначала нужен reclaim / удержание локального low, базовая цель — середина диапазона или ближайшая реакция'
        else:
            anchor = high if high > price else target_price
            target_zone = f"{anchor:.2f}"
            summary = 'если покупатель удержит структуру, вероятен добой вверх до ближайшей верхней зоны'
        invalidation = low if low > 0 else price - atr
    elif price > 0 and target_side == 'SHORT':
        target_price = price * (1.0 - expected_move_pct / 100.0)
        if mode == 'MEAN_REVERT':
            target_zone = f"{mid:.2f}" if mid > 0 else f"{target_price:.2f}"
            summary = 'после ложного выноса вверх вероятен возврат к середине диапазона / ближайшей поддержке'
        elif mode == 'SOFT_PROJECTION':
            anchor = mid if 0 < mid < price else (low if 0 < low < price else target_price)
            target_zone = f"{anchor:.2f}"
            summary = 'мягкая проекция вниз: сначала нужен возврат под локальный high, базовая цель — середина диапазона или ближайшая реакция'
        else:
            anchor = low if 0 < low < price else target_price
            target_zone = f"{anchor:.2f}"
            summary = 'если продавец удержит локальный high, вероятен добой вниз до ближайшей нижней зоны'
        invalidation = high if high > 0 else price + atr

    if mode == 'SOFT_SIGNAL' and target_side in {'LONG', 'SHORT'}:
        summary = 'это мягкий сигнал: движение есть, но вход только после дополнительного подтверждения'
    if target_side == 'NEUTRAL':
        summary = 'направленного преимущества нет, лучше ждать край диапазона или новый импульс'

    return {
        'mode': mode,
        'side': target_side,
        'expected_move_pct': round(expected_move_pct, 2),
        'target_price': round(target_price, 2) if target_price is not None else None,
        'target_zone': target_zone,
        'invalidation': round(invalidation, 2) if invalidation is not None else None,
        'summary': summary,
        'continuation_target': flow.get('main_target') or fast_move.get('continuation_target') or 'нет данных',
    }


__all__ = ['build_move_projection']
