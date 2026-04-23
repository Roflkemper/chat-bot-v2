
from __future__ import annotations

from typing import Any, Dict


def _u(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value).strip().upper()
    except Exception:
        return default


def classify_market_phase(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    regime = _u(payload.get('market_mode') or payload.get('regime') or decision.get('mode') or decision.get('regime') or '')
    fast = _u(payload.get('fast_move_classification') or '')
    trade_flow = payload.get('trade_flow') if isinstance(payload.get('trade_flow'), dict) else {}
    tf_status = _u(trade_flow.get('status') or '')
    if 'RANGE' in regime and 'EXHAUST' in tf_status:
        phase = 'ROTATION'
        note = 'рынок вращается внутри диапазона, продолжение ослабевает'
    elif 'RANGE' in regime:
        phase = 'RANGE'
        note = 'рабочая логика — край диапазона и подтверждение'
    elif fast in {'LIKELY_FAKE_UP', 'LIKELY_FAKE_DOWN', 'EARLY_FAKE_UP_RISK', 'EARLY_FAKE_DOWN_RISK'}:
        phase = 'FAKE_EXPANSION'
        note = 'идёт риск ложного расширения / ловушки'
    elif fast in {'CONTINUATION_UP', 'CONTINUATION_DOWN'}:
        phase = 'TREND_CONTINUATION'
        note = 'движение принимают, continuation жив'
    elif fast == 'POST_LIQUIDATION_EXHAUSTION' or 'EXHAUST' in tf_status:
        phase = 'EXHAUSTION'
        note = 'импульс выдыхается, приоритет — защита'
    else:
        phase = 'MIXED'
        note = 'фаза рынка смешанная, нужен аккуратный execution'
    return {'phase': phase, 'note': note}
