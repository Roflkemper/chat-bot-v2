from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List


def _strength_label(score: float) -> str:
    score = abs(score)
    if score >= 0.75:
        return 'HIGH'
    if score >= 0.4:
        return 'MID'
    return 'LOW'


def _cluster_levels(levels: List[float], tolerance_pct: float) -> List[List[float]]:
    if not levels:
        return []
    ordered = sorted(levels)
    clusters: List[List[float]] = [[ordered[0]]]
    for level in ordered[1:]:
        last_cluster = clusters[-1]
        anchor = mean(last_cluster)
        tol = abs(anchor) * tolerance_pct / 100.0
        if abs(level - anchor) <= max(tol, 1e-9):
            last_cluster.append(level)
        else:
            clusters.append([level])
    return clusters


def analyze_structural_context(candles: List[Dict[str, Any]], *, lookback: int = 24, tolerance_pct: float = 0.35) -> Dict[str, Any]:
    bars = candles[-lookback:] if len(candles) >= lookback else candles[:]
    if len(bars) < 6:
        return {
            'bias': 'NEUTRAL',
            'strength': 'LOW',
            'phase': 'UNDEFINED',
            'reason': 'мало данных',
            'upper_rejections_count': 0,
            'lower_rejections_count': 0,
            'upper_cluster_level': None,
            'lower_cluster_level': None,
            'liquidity_above': None,
            'liquidity_below': None,
            'nearest_liquidity_side': 'NONE',
            'nearest_liquidity_distance_pct': None,
            'impulse_up_pct': None,
            'impulse_down_pct': None,
            'grid_trigger_up': 0,
            'grid_trigger_down': 0,
        }

    avg_volume = mean(float(x.get('volume', 0.0) or 0.0) for x in bars)
    upper_levels: List[float] = []
    lower_levels: List[float] = []
    upper_score = 0.0
    lower_score = 0.0

    for c in bars:
        high = float(c['high'])
        low = float(c['low'])
        open_ = float(c['open'])
        close = float(c['close'])
        spread = max(high - low, 1e-9)
        upper_wick = high - max(open_, close)
        lower_wick = min(open_, close) - low
        volume = float(c.get('volume', 0.0) or 0.0)
        volume_factor = volume / max(avg_volume, 1e-9)

        upper_ratio = upper_wick / spread
        lower_ratio = lower_wick / spread
        close_near_low = (close - low) / spread <= 0.35
        close_near_high = (high - close) / spread <= 0.35

        if upper_ratio >= 0.45 and close_near_low and volume_factor >= 1.05:
            upper_levels.append(high)
            upper_score += upper_ratio * min(volume_factor, 2.0)
        if lower_ratio >= 0.45 and close_near_high and volume_factor >= 1.05:
            lower_levels.append(low)
            lower_score += lower_ratio * min(volume_factor, 2.0)

    upper_clusters = _cluster_levels(upper_levels, tolerance_pct)
    lower_clusters = _cluster_levels(lower_levels, tolerance_pct)
    best_upper = max(upper_clusters, key=len, default=[])
    best_lower = max(lower_clusters, key=len, default=[])
    upper_count = len(best_upper)
    lower_count = len(best_lower)
    upper_level = round(mean(best_upper), 2) if best_upper else None
    lower_level = round(mean(best_lower), 2) if best_lower else None

    closes = [float(x['close']) for x in bars]
    current_price = closes[-1]
    recent_move = ((closes[-1] - closes[0]) / max(closes[0], 1e-9)) * 100.0

    upper_pressure = upper_score + max(0, upper_count - 1) * 0.75
    lower_pressure = lower_score + max(0, lower_count - 1) * 0.75

    if upper_count >= 2 and upper_pressure > lower_pressure * 1.1:
        bias = 'SHORT'
        phase = 'DISTRIBUTION'
        reason = f'{upper_count} rejection-шипа сверху с объёмом'
        strength_score = min(1.0, upper_pressure / 5.0)
    elif lower_count >= 2 and lower_pressure > upper_pressure * 1.1:
        bias = 'LONG'
        phase = 'ACCUMULATION'
        reason = f'{lower_count} rejection-шипа снизу с объёмом'
        strength_score = min(1.0, lower_pressure / 5.0)
    else:
        bias = 'NEUTRAL'
        phase = 'BALANCE'
        reason = 'выраженной серии rejection-шипов нет'
        strength_score = 0.2

    liquidity_above = upper_level
    liquidity_below = lower_level
    nearest_side = 'NONE'
    nearest_distance = None
    distances = []
    if liquidity_above is not None:
        distances.append(('ABOVE', abs(liquidity_above - current_price) / max(current_price, 1e-9) * 100.0))
    if liquidity_below is not None:
        distances.append(('BELOW', abs(current_price - liquidity_below) / max(current_price, 1e-9) * 100.0))
    if distances:
        nearest_side, nearest_distance = min(distances, key=lambda x: x[1])

    swing_high = max(float(x['high']) for x in bars)
    swing_low = min(float(x['low']) for x in bars)
    upside_room_pct = max(0.0, (swing_high - current_price) / max(current_price, 1e-9) * 100.0)
    downside_room_pct = max(0.0, (current_price - swing_low) / max(current_price, 1e-9) * 100.0)
    realized_up_pct = max(0.0, recent_move)
    realized_down_pct = max(0.0, -recent_move)
    impulse_up_pct = max(upside_room_pct, realized_up_pct)
    impulse_down_pct = max(downside_room_pct, realized_down_pct)

    def _grid_count(move_pct: float) -> int:
        if move_pct >= 2.9:
            return 3
        if move_pct >= 2.2:
            return 2
        if move_pct >= 1.3:
            return 1
        return 0

    return {
        'bias': bias,
        'strength': _strength_label(strength_score),
        'phase': phase,
        'reason': reason,
        'recent_move_pct': round(recent_move, 2),
        'upper_rejections_count': upper_count,
        'lower_rejections_count': lower_count,
        'upper_cluster_level': upper_level,
        'lower_cluster_level': lower_level,
        'liquidity_above': liquidity_above,
        'liquidity_below': liquidity_below,
        'nearest_liquidity_side': nearest_side,
        'nearest_liquidity_distance_pct': round(nearest_distance, 2) if nearest_distance is not None else None,
        'impulse_up_pct': round(impulse_up_pct, 2),
        'impulse_down_pct': round(impulse_down_pct, 2),
        'grid_trigger_up': _grid_count(impulse_up_pct),
        'grid_trigger_down': _grid_count(impulse_down_pct),
    }
