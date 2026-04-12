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


def _sign(x: float) -> str:
    if x > 0:
        return 'UP'
    if x < 0:
        return 'DOWN'
    return 'NONE'


def build_impulse_character_context(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload or {}
    volatility = payload.get('volatility_impulse') if isinstance(payload.get('volatility_impulse'), dict) else {}
    micro = payload.get('microstructure') if isinstance(payload.get('microstructure'), dict) else {}
    orderflow = payload.get('orderflow_context') if isinstance(payload.get('orderflow_context'), dict) else {}
    fast = payload.get('fast_move_context') if isinstance(payload.get('fast_move_context'), dict) else {}
    move_projection = payload.get('move_projection') if isinstance(payload.get('move_projection'), dict) else {}

    move_5 = _f(volatility.get('move_5'))
    stretch = abs(_f(volatility.get('stretch_pct') or volatility.get('atr_stretch_pct') or volatility.get('move_vs_atr_pct')))
    vol_ratio = _f(orderflow.get('volume_ratio') or orderflow.get('relative_volume') or micro.get('volume_ratio'), 1.0)
    body_ratio = _f(micro.get('body_ratio') or micro.get('body_dominance') or fast.get('body_ratio'), 0.0)
    wick_ratio = _f(micro.get('wick_ratio') or micro.get('wick_dominance') or fast.get('wick_ratio'), 0.0)
    follow = _u(fast.get('follow_through') or fast.get('continuation_quality') or move_projection.get('follow_through'))
    classification = _u(fast.get('classification') or fast.get('type'))
    bias = _u(move_projection.get('bias') or fast.get('bias') or payload.get('direction'))
    location_state = _u(fast.get('location_state') or payload.get('location_state'))

    candles = payload.get('recent_candles') if isinstance(payload.get('recent_candles'), list) else []
    if candles and abs(move_5) <= 1e-9:
        closes = [_f(c.get('close')) for c in candles[-6:]]
        if len(closes) >= 2:
            move_5 = closes[-1] - closes[0]
    if candles and vol_ratio <= 1.0:
        vols = [_f(c.get('volume')) for c in candles[-8:]]
        if len(vols) >= 4:
            base = sum(vols[:-1]) / max(len(vols)-1, 1)
            if base > 0:
                vol_ratio = max(vol_ratio, vols[-1] / base)

    direction = _sign(move_5)
    if direction == 'NONE' and bias in {'LONG', 'UP', 'BULL', 'BULLISH'}:
        direction = 'UP'
    elif direction == 'NONE' and bias in {'SHORT', 'DOWN', 'BEAR', 'BEARISH'}:
        direction = 'DOWN'

    strength_score = stretch * 18.0 + max(0.0, vol_ratio - 1.0) * 22.0 + body_ratio * 35.0
    if classification in {'CONTINUATION_UP', 'CONTINUATION_DOWN'}:
        strength_score += 10.0
    if follow in {'STRONG', 'CLEAN', 'GOOD', 'YES'}:
        strength_score += 8.0
    strength = 'LOW'
    if strength_score >= 62:
        strength = 'HIGH'
    elif strength_score >= 32:
        strength = 'MEDIUM'

    quality = 'CHOPPY'
    if body_ratio >= 0.58 and wick_ratio <= 0.28 and vol_ratio >= 1.05:
        quality = 'CLEAN'
    elif wick_ratio >= 0.45 or classification in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN', 'WEAK_CONTINUATION_UP', 'WEAK_CONTINUATION_DOWN'}:
        quality = 'EXHAUSTING'

    acceptance = 'UNCONFIRMED'
    if classification in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} or follow in {'STRONG', 'CLEAN', 'GOOD'}:
        acceptance = 'ACCEPTED'
    elif classification in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN', 'FAKE_UP', 'FAKE_DOWN'} or follow in {'WEAK', 'NONE', 'FAIL'}:
        acceptance = 'REJECTED'

    state = 'NO_CLEAR_IMPULSE'
    if direction == 'UP' and quality == 'CLEAN' and acceptance == 'ACCEPTED' and strength in {'MEDIUM', 'HIGH'}:
        state = 'CONTINUATION_UP'
    elif direction == 'DOWN' and quality == 'CLEAN' and acceptance == 'ACCEPTED' and strength in {'MEDIUM', 'HIGH'}:
        state = 'CONTINUATION_DOWN'
    elif direction == 'UP' and quality == 'EXHAUSTING':
        state = 'EXHAUSTION_UP'
    elif direction == 'DOWN' and quality == 'EXHAUSTING':
        state = 'EXHAUSTION_DOWN'
    elif direction == 'UP' and acceptance == 'REJECTED':
        state = 'TRAP_CANDIDATE_UP'
    elif direction == 'DOWN' and acceptance == 'REJECTED':
        state = 'TRAP_CANDIDATE_DOWN'
    elif strength == 'LOW':
        state = 'CHOP'

    comment = 'движение без чистого преимущества, но характер всё равно читается'
    if state == 'CONTINUATION_UP':
        comment = 'импульс вверх чистый, без потери удержания'
    elif state == 'CONTINUATION_DOWN':
        comment = 'импульс вниз чистый, без потери удержания'
    elif state == 'EXHAUSTION_UP':
        comment = 'рост есть, но характер движения ближе к затуханию / ловушке'
    elif state == 'EXHAUSTION_DOWN':
        comment = 'падение есть, но характер движения ближе к затуханию / ловушке'
    elif state == 'TRAP_CANDIDATE_UP':
        comment = 'вынос вверх не принят рынком, возможен short после confirm'
    elif state == 'TRAP_CANDIDATE_DOWN':
        comment = 'пролив вниз не принят рынком, возможен long после confirm'
    elif state == 'CHOP':
        comment = 'движение рваное, лучше не форсировать вход'

    if location_state == 'MID' and state.startswith('CONTINUATION_'):
        comment += '; но цена в середине диапазона, chase запрещён'

    score = max(0.0, min(100.0, round(strength_score, 1)))
    return {
        'direction': direction,
        'strength': strength,
        'quality': quality,
        'acceptance': acceptance,
        'state': state,
        'score': score,
        'comment': comment,
        'can_enter_with_trend': state in {'CONTINUATION_UP', 'CONTINUATION_DOWN'} and location_state != 'MID',
        'allow_countertrend': state in {'EXHAUSTION_UP', 'EXHAUSTION_DOWN', 'TRAP_CANDIDATE_UP', 'TRAP_CANDIDATE_DOWN'},
        'watch_conditions': [
            'удержание уровня' if acceptance == 'ACCEPTED' else 'reclaim / возврат за уровень',
            'follow-through следующей свечой',
            'объём подтверждает движение' if vol_ratio >= 1.0 else 'без подтверждения объёмом лучше не форсировать',
        ],
    }


__all__ = ['build_impulse_character_context']
