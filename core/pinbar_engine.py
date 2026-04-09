from __future__ import annotations

from typing import Any, Dict


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def build_pinbar_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    candles = payload.get('recent_candles') if isinstance(payload.get('recent_candles'), list) else []
    if len(candles) < 2:
        return {'pinbar_valid': False, 'pinbar_strength': 'NONE', 'pinbar_confirmed': False, 'label': 'нет данных', 'summary': 'нет данных по последней свече'}
    c = candles[-1]; prev = candles[-2]
    o,h,l,cl = _f(c.get('open')), _f(c.get('high')), _f(c.get('low')), _f(c.get('close'))
    po,ph,pl,pcl = _f(prev.get('open')), _f(prev.get('high')), _f(prev.get('low')), _f(prev.get('close'))
    rng = max(h-l, 1e-9)
    body = abs(cl-o)
    upper = h - max(o,cl)
    lower = min(o,cl) - l
    blocks = payload.get('liquidity_blocks') if isinstance(payload.get('liquidity_blocks'), dict) else {}
    ub = blocks.get('upper_block') if isinstance(blocks.get('upper_block'), dict) else {}
    lb = blocks.get('lower_block') if isinstance(blocks.get('lower_block'), dict) else {}
    at_upper = _f(ub.get('low')) > 0 and h >= _f(ub.get('low'))
    at_lower = _f(lb.get('high')) > 0 and l <= _f(lb.get('high'))
    bearish = upper / rng >= 0.55 and body / rng <= 0.3 and at_upper
    bullish = lower / rng >= 0.55 and body / rng <= 0.3 and at_lower
    confirmed = False
    if bearish:
        confirmed = cl < min(pcl, po) and h >= ph
        return {'pinbar_valid': True, 'pinbar_strength': 'STRONG' if confirmed else 'MEDIUM', 'pinbar_confirmed': confirmed, 'side': 'SHORT', 'label': 'bearish pinbar', 'summary': 'верхний хвост у верхнего блока: продавец защищает high'}
    if bullish:
        confirmed = cl > max(pcl, po) and l <= pl
        return {'pinbar_valid': True, 'pinbar_strength': 'STRONG' if confirmed else 'MEDIUM', 'pinbar_confirmed': confirmed, 'side': 'LONG', 'label': 'bullish pinbar', 'summary': 'нижний хвост у нижнего блока: покупатель защищает low'}
    return {'pinbar_valid': False, 'pinbar_strength': 'NONE', 'pinbar_confirmed': False, 'side': 'NONE', 'label': 'нет торгового пинбара', 'summary': 'последняя свеча не даёт чистый пинбар в рабочем блоке'}
