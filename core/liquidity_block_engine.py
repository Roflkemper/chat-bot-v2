from __future__ import annotations

from typing import Any, Dict, List


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == '':
            return default
        if isinstance(v, str):
            v = v.replace(' ', '').replace(',', '')
        return float(v)
    except Exception:
        return default


def _touches(candles: List[Dict[str, float]], low: float, high: float) -> int:
    cnt = 0
    for c in candles:
        hi = _f(c.get('high')); lo = _f(c.get('low'))
        if hi >= low and lo <= high:
            cnt += 1
    return cnt


def _last_touch_bars_ago(candles: List[Dict[str, float]], low: float, high: float) -> int:
    for i, c in enumerate(reversed(candles)):
        hi = _f(c.get('high')); lo = _f(c.get('low'))
        if hi >= low and lo <= high:
            return i
    return 999


def _last_reaction(candles: List[Dict[str, float]], low: float, high: float) -> str:
    if not candles:
        return 'NONE'
    c = candles[-1]
    close = _f(c.get('close')); open_ = _f(c.get('open')); hi = _f(c.get('high')); lo = _f(c.get('low'))
    if hi >= low and close < high and close < open_:
        return 'REJECTED_FROM_BLOCK'
    if lo <= high and close > low and close > open_:
        return 'BOUNCED_FROM_BLOCK'
    if close > high:
        return 'ACCEPTED_ABOVE'
    if close < low:
        return 'ACCEPTED_BELOW'
    return 'INSIDE_BLOCK'


def _freshness_score(bars_ago: int) -> float:
    if bars_ago <= 1:
        return 100.0
    if bars_ago <= 3:
        return 82.0
    if bars_ago <= 6:
        return 65.0
    if bars_ago <= 12:
        return 45.0
    return 20.0


def _block_state(reaction: str, tests: int, freshness: float) -> str:
    if reaction in {'REJECTED_FROM_BLOCK', 'BOUNCED_FROM_BLOCK'}:
        return 'ACTIVE_REACTION'
    if reaction in {'ACCEPTED_ABOVE', 'ACCEPTED_BELOW'}:
        return 'ACCEPTED_BREAK'
    if tests >= 4 and freshness < 45:
        return 'WEAKENING'
    return 'WATCH'


def build_liquidity_block_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    candles = payload.get('recent_candles') if isinstance(payload.get('recent_candles'), list) else []
    low = _f(payload.get('range_low')); mid = _f(payload.get('range_mid')); high = _f(payload.get('range_high'))
    co = payload.get('coinglass_context') if isinstance(payload.get('coinglass_context'), dict) else {}
    upper_strength = max(_f(co.get('nearest_above_strength')), _f(co.get('recent_cluster_above_strength')))
    lower_strength = max(_f(co.get('nearest_below_strength')), _f(co.get('recent_cluster_below_strength')))
    # Use narrower actionable liquidity blocks rather than half-range slabs
    span = max(high - low, 0.0)
    width = span * 0.34 if span > 0 else 0.0
    upper_block = {'low': max(mid if mid > 0 else high - width, high - width), 'high': high if high > 0 else 0.0}
    lower_block = {'low': low if low > 0 else 0.0, 'high': min(mid if mid > 0 else low + width, low + width)}
    recent = candles[-48:]
    upper_tests = _touches(recent, upper_block['low'], upper_block['high']) if upper_block['high'] > upper_block['low'] else 0
    lower_tests = _touches(recent, lower_block['low'], lower_block['high']) if lower_block['high'] > lower_block['low'] else 0
    upper_reaction = _last_reaction(candles[-4:], upper_block['low'], upper_block['high']) if upper_block['high'] > upper_block['low'] else 'NONE'
    lower_reaction = _last_reaction(candles[-4:], lower_block['low'], lower_block['high']) if lower_block['high'] > lower_block['low'] else 'NONE'
    upper_bars_ago = _last_touch_bars_ago(recent, upper_block['low'], upper_block['high']) if upper_tests else 999
    lower_bars_ago = _last_touch_bars_ago(recent, lower_block['low'], lower_block['high']) if lower_tests else 999
    upper_fresh = _freshness_score(upper_bars_ago)
    lower_fresh = _freshness_score(lower_bars_ago)
    return {
        'upper_block': upper_block,
        'lower_block': lower_block,
        'upper_block_strength': round(max(upper_strength, upper_tests * 7.0) * (0.7 + upper_fresh / 380.0) * (1.0 if upper_tests < 3 else 0.82 if upper_tests < 5 else 0.68), 1),
        'lower_block_strength': round(max(lower_strength, lower_tests * 7.0) * (0.7 + lower_fresh / 380.0) * (1.0 if lower_tests < 3 else 0.82 if lower_tests < 5 else 0.68), 1),
        'upper_tests': upper_tests,
        'lower_tests': lower_tests,
        'upper_reaction': upper_reaction,
        'lower_reaction': lower_reaction,
        'upper_last_touch_bars_ago': upper_bars_ago,
        'lower_last_touch_bars_ago': lower_bars_ago,
        'upper_freshness': round(upper_fresh, 1),
        'lower_freshness': round(lower_fresh, 1),
        'upper_state': _block_state(upper_reaction, upper_tests, upper_fresh),
        'lower_state': _block_state(lower_reaction, lower_tests, lower_fresh),
    }
