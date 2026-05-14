from __future__ import annotations

from typing import Any, Dict, List
import math

import numpy as np
import pandas as pd


def _safe_years(index) -> list[int]:
    try:
        if index is None or len(index) == 0:
            return []
        first = index[0]
        if isinstance(first, (int, float, np.integer, np.floating)):
            return []
        years = sorted({int(pd.Timestamp(x).year) for x in index})
        return years[-3:]
    except Exception:
        return []


def _classify_pattern(cur_close: np.ndarray, cur_ret: np.ndarray) -> tuple[str, str, str]:
    if len(cur_close) < 6:
        return 'LOCAL_MEMORY', 'нейтральная локальная структура', 'weak_local_memory'
    total_move = float(cur_close[-1] / max(cur_close[0], 1e-9) - 1.0)
    last_move = float(cur_close[-1] / max(cur_close[-3], 1e-9) - 1.0) if len(cur_close) >= 3 else total_move
    vol = float(np.std(cur_ret))
    if abs(total_move) < 0.004 and vol < 0.004:
        return 'COMPRESSION', 'сжатие диапазона / накопление', 'compression'
    if total_move > 0.008 and last_move < 0.0015:
        return 'EXHAUSTION_UP', 'рост замедляется после импульса вверх', 'exhaustion_up'
    if total_move < -0.008 and last_move > -0.0015:
        return 'EXHAUSTION_DOWN', 'снижение замедляется после импульса вниз', 'exhaustion_down'
    if total_move > 0.004:
        return 'CONTINUATION_UP', 'структура похожа на продолжение вверх после отката', 'continuation_up'
    if total_move < -0.004:
        return 'CONTINUATION_DOWN', 'структура похожа на продолжение вниз после отката', 'continuation_down'
    return 'RANGE_BEHAVIOR', 'пилообразная структура внутри диапазона', 'range_behavior'


def _soft_context(close: pd.Series, horizon: int, years: list[int]) -> Dict[str, Any]:
    rets = close.pct_change().fillna(0.0)
    drift = float(close.iloc[-1] / max(close.iloc[max(0, len(close)-horizon-1)], 1e-9) - 1.0) if len(close) > horizon + 1 else 0.0
    direction = 'LONG' if drift > 0.002 else 'SHORT' if drift < -0.002 else 'NEUTRAL'
    pattern_type, note, move_style = _classify_pattern(close.tail(min(20, len(close))).to_numpy(dtype=float), rets.tail(min(20, len(rets))).to_numpy(dtype=float))
    confidence = 28.0 if direction != 'NEUTRAL' else 18.0
    expected = 'BOUNCE_BIAS' if direction == 'LONG' else 'FADE_BIAS' if direction == 'SHORT' else 'RANGE_ROTATION'
    invalidation = 'паттерн ломается при обратном импульсе и закреплении за ближайшей локальной зоной'
    long_prob = 52.0 if direction == 'LONG' else 34.0 if direction == 'SHORT' else 40.0
    short_prob = 52.0 if direction == 'SHORT' else 34.0 if direction == 'LONG' else 40.0
    neutral_prob = max(0.0, 100.0 - long_prob - short_prob)
    return {
        'pattern_vector': rets.tail(min(20, len(rets))).round(6).tolist(),
        'matches': max(1, min(3, len(close)//10)),
        'matched_count': max(1, min(3, len(close)//10)),
        'direction': direction,
        'pattern_bias': direction,
        'pattern_type': pattern_type,
        'match_quality': 'SOFT',
        'pattern_note': note,
        'expected_path': expected,
        'invalidation': invalidation,
        'confidence': confidence,
        'avg_future_return': round(drift, 5),
        'lookahead_bars': horizon,
        'summary': f'локальная память: {note}; ожидаемый путь: {expected.lower().replace("_", " ")}',
        'source_years': years,
        'long_prob': round(long_prob, 1),
        'short_prob': round(short_prob, 1),
        'neutral_prob': round(neutral_prob, 1),
        'move_style': move_style,
    }


def build_pattern_history_context(df: pd.DataFrame, window: int = 20, horizon: int = 8, top_k: int = 12) -> Dict[str, Any]:
    if df is None or getattr(df, 'empty', True):
        return {'pattern_vector': None, 'matches': 0, 'matched_count': 0, 'summary': 'история паттернов недоступна', 'pattern_type': 'UNAVAILABLE', 'match_quality': 'NONE', 'expected_path': 'UNKNOWN', 'invalidation': 'нет данных', 'confidence': 0.0, 'long_prob': 33.3, 'short_prob': 33.3, 'neutral_prob': 33.4}
    close = pd.Series(df['close']).astype(float).reset_index(drop=True)
    years = _safe_years(getattr(df, 'index', []))
    n = len(close)
    window = max(8, min(window, max(8, n // 4)))
    horizon = max(3, min(horizon, max(3, n // 12)))
    if len(close) < window + horizon + 8:
        return _soft_context(close, horizon, years)

    returns = close.pct_change().fillna(0.0)
    cur = returns.iloc[-window:].to_numpy(dtype=float)
    cur = (cur - cur.mean()) / (cur.std() + 1e-9)
    cur_close = close.iloc[-window:].to_numpy(dtype=float)
    pattern_type, pattern_note, move_style = _classify_pattern(cur_close, returns.iloc[-window:].to_numpy(dtype=float))

    sims: List[tuple[float, int, float]] = []
    last_start = len(close) - window - horizon
    for start in range(5, last_start):
        seg = returns.iloc[start:start+window].to_numpy(dtype=float)
        seg = (seg - seg.mean()) / (seg.std() + 1e-9)
        sim = float(np.dot(cur, seg) / (np.linalg.norm(cur) * np.linalg.norm(seg) + 1e-9))
        if not math.isfinite(sim):
            continue
        future_ret = float(close.iloc[start+window+horizon-1] / close.iloc[start+window-1] - 1.0)
        sims.append((sim, start, future_ret))
    sims.sort(key=lambda x: x[0], reverse=True)
    top = [x for x in sims[:top_k] if x[0] > -1.0]
    if not top:
        return _soft_context(close, horizon, years)

    avg_ret = float(np.mean([x[2] for x in top]))
    pos = sum(1 for x in top if x[2] > 0.001)
    neg = sum(1 for x in top if x[2] < -0.001)
    avg_sim = float(np.mean([x[0] for x in top]))
    if avg_ret > 0.0015 and pos >= neg:
        direction = 'LONG'
        expected = 'CONTINUATION_UP' if pos >= int(len(top)*0.55) else 'BOUNCE_BIAS'
    elif avg_ret < -0.0015 and neg >= pos:
        direction = 'SHORT'
        expected = 'CONTINUATION_DOWN' if neg >= int(len(top)*0.55) else 'FADE_BIAS'
    else:
        direction = 'NEUTRAL'
        expected = 'RANGE_ROTATION' if pattern_type in {'COMPRESSION', 'RANGE_BEHAVIOR'} else 'UNCLEAR'
    dominant = max(pos, neg)
    confidence = max(18.0, min(90.0, (max(avg_sim, 0.0) * 55.0) + (dominant / max(len(top), 1)) * 35.0))
    match_quality = 'HIGH' if confidence >= 68 else 'MEDIUM' if confidence >= 48 else 'SOFT'
    long_prob = max(5.0, min(90.0, 100.0 * pos / max(len(top), 1)))
    short_prob = max(5.0, min(90.0, 100.0 * neg / max(len(top), 1)))
    if direction == 'LONG' and long_prob < 50:
        long_prob = 50.0
    if direction == 'SHORT' and short_prob < 50:
        short_prob = 50.0
    neutral_prob = max(0.0, 100.0 - long_prob - short_prob)
    invalidation = 'сценарий ломается при потере локального направления и резком обратном импульсе от текущей зоны'
    summary = f"{len(top)} похожих кейсов: {pattern_note}; средний ход {avg_ret*100:+.2f}% за {horizon} баров; ожидаемый путь {expected.lower().replace('_', ' ')}"
    return {
        'pattern_vector': cur.round(6).tolist(),
        'matches': len(top),
        'matched_count': len(top),
        'direction': direction,
        'pattern_bias': direction,
        'pattern_type': pattern_type,
        'match_quality': match_quality,
        'pattern_note': pattern_note,
        'expected_path': expected,
        'invalidation': invalidation,
        'confidence': round(confidence, 1),
        'avg_future_return': round(avg_ret, 5),
        'lookahead_bars': horizon,
        'source_years': years,
        'summary': summary,
        'top_similarity': round(avg_sim, 4),
        'long_prob': round(long_prob, 1),
        'short_prob': round(short_prob, 1),
        'neutral_prob': round(neutral_prob, 1),
        'move_style': move_style,
    }
