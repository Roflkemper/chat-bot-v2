from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _direction(value: Any) -> str:
    s = str(value or '').upper()
    if 'LONG' in s or 'ЛОНГ' in s or 'ВВЕРХ' in s or s == 'UP':
        return 'LONG'
    if 'SHORT' in s or 'ШОРТ' in s or 'ВНИЗ' in s or s == 'DOWN':
        return 'SHORT'
    return 'NEUTRAL'


def build_soft_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    factor = payload.get('factor_breakdown') if isinstance(payload.get('factor_breakdown'), dict) else {}
    fast_move = payload.get('fast_move_context') if isinstance(payload.get('fast_move_context'), dict) else {}

    conf = _f(decision.get('confidence_pct') or decision.get('confidence') or payload.get('forecast_confidence'))
    long_total = _f(factor.get('long_total') or decision.get('long_score'))
    short_total = _f(factor.get('short_total') or decision.get('short_score'))
    dominance = _direction(factor.get('dominance') or decision.get('direction_text') or payload.get('forecast_direction'))
    diff = abs(long_total - short_total)
    fast_cls = str(fast_move.get('classification') or '').upper()

    active = False
    status = 'OFF'
    side = dominance if dominance in {'LONG', 'SHORT'} else 'NEUTRAL'
    summary = 'мягкого сигнала нет'
    trigger = 'ждать'

    if 40.0 <= conf < 55.0 and side in {'LONG', 'SHORT'}:
        active = True
        status = 'SOFT_SIGNAL'
        summary = 'есть предварительный directional перекос, но без права на форсированный вход'
        trigger = 'только retest / reclaim / confirm'
    if fast_cls in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN'}:
        active = True
        status = 'SOFT_SIGNAL_TRAP'
        side = 'SHORT' if fast_cls == 'LIKELY_FAKE_UP' else 'LONG'
        summary = 'быстрый вынос дал мягкий контртрендовый сигнал, но без подтверждения это только наблюдение'
        trigger = 'ждать возврат под/над зону выноса'
    elif not active and diff >= 4.0 and side in {'LONG', 'SHORT'} and conf >= 38.0:
        active = True
        status = 'SOFT_SIGNAL_BUILDING'
        summary = 'перевес начинает строиться, но edge ещё не готов для нормального входа'
        trigger = 'нужна следующая свеча в сторону сценария'

    score = round(min(100.0, max(conf, diff * 7.5 if diff else 0.0)), 1) if active else 0.0
    return {
        'active': active,
        'status': status,
        'side': side,
        'score': score,
        'summary': summary,
        'trigger': trigger,
    }


__all__ = ['build_soft_signal']
