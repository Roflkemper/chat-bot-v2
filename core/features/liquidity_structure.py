from __future__ import annotations

from statistics import mean
from typing import Iterable, List, Dict, Any


LOOKBACK = 48
STRUCTURE_WINDOW = 24
VOLUME_WINDOW = 20
SWING_WINDOW = 18
SWEEP_WINDOW = 8
CLUSTER_TOLERANCE_PCT = 0.35
LEVEL_TOLERANCE_PCT = 0.30


def _safe_mean(values: Iterable[float], default: float = 0.0) -> float:
    values = list(values)
    return mean(values) if values else default


def _pct_diff(a: float, b: float) -> float:
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base * 100.0


def _is_upper_rejection(bar: Dict[str, Any], avg_range_20: float) -> tuple[bool, bool, bool]:
    high = float(bar['high'])
    low = float(bar['low'])
    open_ = float(bar['open'])
    close = float(bar['close'])
    candle_range = max(high - low, 1e-9)
    upper_wick = high - max(open_, close)
    body = abs(close - open_)
    upper_wick_ratio = upper_wick / candle_range
    body_ratio = body / candle_range
    candidate = upper_wick_ratio >= 0.50 and body_ratio <= 0.45 and candle_range >= avg_range_20 * 0.9
    strong = candidate and upper_wick_ratio >= 0.60
    return candidate, strong, upper_wick_ratio >= 0.60


def _is_lower_rejection(bar: Dict[str, Any], avg_range_20: float) -> tuple[bool, bool, bool]:
    high = float(bar['high'])
    low = float(bar['low'])
    open_ = float(bar['open'])
    close = float(bar['close'])
    candle_range = max(high - low, 1e-9)
    lower_wick = min(open_, close) - low
    body = abs(close - open_)
    lower_wick_ratio = lower_wick / candle_range
    body_ratio = body / candle_range
    candidate = lower_wick_ratio >= 0.50 and body_ratio <= 0.45 and candle_range >= avg_range_20 * 0.9
    strong = candidate and lower_wick_ratio >= 0.60
    return candidate, strong, lower_wick_ratio >= 0.60


def _find_swing_highs(candles: List[Dict[str, Any]]) -> List[float]:
    highs: List[float] = []
    for i in range(1, len(candles) - 1):
        cur = float(candles[i]['high'])
        if cur >= float(candles[i - 1]['high']) and cur >= float(candles[i + 1]['high']):
            highs.append(cur)
    return highs


def _find_swing_lows(candles: List[Dict[str, Any]]) -> List[float]:
    lows: List[float] = []
    for i in range(1, len(candles) - 1):
        cur = float(candles[i]['low'])
        if cur <= float(candles[i - 1]['low']) and cur <= float(candles[i + 1]['low']):
            lows.append(cur)
    return lows


def _has_cluster(levels: List[float], tolerance_pct: float, min_count: int = 2) -> bool:
    if len(levels) < min_count:
        return False
    for i, level in enumerate(levels):
        count = 1
        for j, other in enumerate(levels):
            if i == j:
                continue
            if _pct_diff(level, other) <= tolerance_pct:
                count += 1
        if count >= min_count:
            return True
    return False


def detect_liquidity_structure(candles: List[Dict[str, Any]]) -> Dict[str, bool]:
    window = candles[-LOOKBACK:] if len(candles) >= LOOKBACK else candles[:]
    if len(window) < 6:
        return {
            'repeated_upper_rejection': False,
            'repeated_lower_rejection': False,
            'upper_sweep': False,
            'lower_sweep': False,
            'distribution': False,
            'accumulation': False,
            'equal_highs': False,
            'equal_lows': False,
            'volume_rejection_up': False,
            'volume_rejection_down': False,
        }

    vol_window = window[-VOLUME_WINDOW:] if len(window) >= VOLUME_WINDOW else window
    avg_volume_20 = _safe_mean(float(x['volume']) for x in vol_window)
    avg_range_20 = _safe_mean(float(x['high']) - float(x['low']) for x in vol_window)

    structure_window = window[-STRUCTURE_WINDOW:] if len(window) >= STRUCTURE_WINDOW else window

    upper_candidates: List[Dict[str, Any]] = []
    lower_candidates: List[Dict[str, Any]] = []

    volume_rejection_up = False
    volume_rejection_down = False

    for bar in structure_window:
        vol = float(bar['volume'])
        upper_candidate, upper_strong, _ = _is_upper_rejection(bar, avg_range_20)
        lower_candidate, lower_strong, _ = _is_lower_rejection(bar, avg_range_20)

        if upper_candidate:
            upper_candidates.append({'high': float(bar['high']), 'volume': vol, 'strong': upper_strong})
            if vol >= avg_volume_20 * 1.25:
                volume_rejection_up = True
        if lower_candidate:
            lower_candidates.append({'low': float(bar['low']), 'volume': vol, 'strong': lower_strong})
            if vol >= avg_volume_20 * 1.25:
                volume_rejection_down = True

    repeated_upper_rejection = False
    repeated_lower_rejection = False

    if len(upper_candidates) >= 2:
        highs = [x['high'] for x in upper_candidates]
        repeated_upper_rejection = _has_cluster(highs, CLUSTER_TOLERANCE_PCT, 2) and any(
            x['strong'] or x['volume'] >= avg_volume_20 * 1.20 for x in upper_candidates
        )
    if len(lower_candidates) >= 2:
        lows = [x['low'] for x in lower_candidates]
        repeated_lower_rejection = _has_cluster(lows, CLUSTER_TOLERANCE_PCT, 2) and any(
            x['strong'] or x['volume'] >= avg_volume_20 * 1.20 for x in lower_candidates
        )

    swing_window = window[-SWING_WINDOW:] if len(window) >= SWING_WINDOW else window
    equal_highs = _has_cluster(_find_swing_highs(swing_window), LEVEL_TOLERANCE_PCT, 2)
    equal_lows = _has_cluster(_find_swing_lows(swing_window), LEVEL_TOLERANCE_PCT, 2)

    upper_sweep = False
    lower_sweep = False
    sweep_window = window[-SWEEP_WINDOW:] if len(window) >= SWEEP_WINDOW else window
    for i in range(1, len(sweep_window)):
        prev = sweep_window[i - 1]
        cur = sweep_window[i]
        prev_high = float(prev['high'])
        prev_low = float(prev['low'])
        cur_high = float(cur['high'])
        cur_low = float(cur['low'])
        cur_close = float(cur['close'])
        cur_open = float(cur['open'])
        cur_range = max(cur_high - cur_low, 1e-9)
        upper_wick_ratio = (cur_high - max(cur_open, cur_close)) / cur_range
        lower_wick_ratio = (min(cur_open, cur_close) - cur_low) / cur_range
        if cur_high > prev_high and cur_close < prev_high and _pct_diff(cur_close, prev_high) > 0.15:
            if upper_wick_ratio >= 0.50 or float(cur['volume']) >= avg_volume_20 * 1.15:
                upper_sweep = True
        if cur_low < prev_low and cur_close > prev_low and _pct_diff(cur_close, prev_low) > 0.15:
            if lower_wick_ratio >= 0.50 or float(cur['volume']) >= avg_volume_20 * 1.15:
                lower_sweep = True

    distribution = (
        (repeated_upper_rejection and upper_sweep)
        or (repeated_upper_rejection and equal_highs)
        or (upper_sweep and volume_rejection_up)
        or (
            len(upper_candidates) >= 3
            and _has_cluster([x['high'] for x in upper_candidates], CLUSTER_TOLERANCE_PCT, 3)
            and any(x['volume'] >= avg_volume_20 * 1.20 for x in upper_candidates)
        )
    )
    accumulation = (
        (repeated_lower_rejection and lower_sweep)
        or (repeated_lower_rejection and equal_lows)
        or (lower_sweep and volume_rejection_down)
        or (
            len(lower_candidates) >= 3
            and _has_cluster([x['low'] for x in lower_candidates], CLUSTER_TOLERANCE_PCT, 3)
            and any(x['volume'] >= avg_volume_20 * 1.20 for x in lower_candidates)
        )
    )

    return {
        'repeated_upper_rejection': repeated_upper_rejection,
        'repeated_lower_rejection': repeated_lower_rejection,
        'upper_sweep': upper_sweep,
        'lower_sweep': lower_sweep,
        'distribution': distribution,
        'accumulation': accumulation,
        'equal_highs': equal_highs,
        'equal_lows': equal_lows,
        'volume_rejection_up': volume_rejection_up,
        'volume_rejection_down': volume_rejection_down,
    }
