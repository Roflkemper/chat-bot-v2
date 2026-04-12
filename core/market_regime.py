from __future__ import annotations

import math
import pandas as pd


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def detect_market_regime(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    close = max(_safe_float(last.get("close"), 0.0), 1e-9)
    ema20 = _safe_float(last.get("ema20"))
    ema50 = _safe_float(last.get("ema50"))
    ema100 = _safe_float(last.get("ema100"))
    atr_pct = _safe_float(last.get("atr14")) / close * 100.0
    ret10 = _safe_float(last.get("ret10")) * 100.0
    rsi = _safe_float(last.get("rsi14"), 50.0)

    trend_gap = abs(ema20 - ema50) / close * 100.0
    trend_stack_bull = ema20 > ema50 > ema100
    trend_stack_bear = ema20 < ema50 < ema100
    above_pack = close > max(ema20, ema50, ema100)
    below_pack = close < min(ema20, ema50, ema100)

    compression = trend_gap < 0.18 and atr_pct < 0.85
    panic = ret10 <= -4.0 and atr_pct > 1.2
    recovery = ret10 >= 3.8 and atr_pct > 1.0 and above_pack
    breakout_attempt = atr_pct > 0.95 and trend_gap >= 0.22 and abs(ret10) >= 1.25

    if panic:
        regime = 'panic_impulse'
        bias = 'SHORT'
        confidence = 76.0
        summary = 'резкий bearish-импульс с расширением волатильности'
    elif recovery:
        regime = 'recovery'
        bias = 'LONG'
        confidence = 72.0
        summary = 'рынок восстанавливается после сильной слабости'
    elif compression:
        regime = 'compression'
        bias = 'NEUTRAL'
        confidence = 61.0
        summary = 'сжатие волатильности, рынок копит движение'
    elif breakout_attempt and trend_stack_bull and above_pack:
        regime = 'breakout_attempt'
        bias = 'LONG'
        confidence = 68.0
        summary = 'покупатель пытается развить breakout / continuation'
    elif breakout_attempt and trend_stack_bear and below_pack:
        regime = 'breakout_attempt'
        bias = 'SHORT'
        confidence = 68.0
        summary = 'продавец пытается развить breakout / continuation'
    elif trend_stack_bull and atr_pct >= 0.70 and ret10 > 0.6:
        regime = 'trend_continuation'
        bias = 'LONG'
        confidence = 70.0
        summary = 'тренд вверх остаётся рабочим и поддерживается структурой'
    elif trend_stack_bear and atr_pct >= 0.70 and ret10 < -0.6:
        regime = 'trend_continuation'
        bias = 'SHORT'
        confidence = 70.0
        summary = 'тренд вниз остаётся рабочим и поддерживается структурой'
    elif trend_gap >= 0.24 and ((trend_stack_bull and rsi > 69) or (trend_stack_bear and rsi < 31)):
        regime = 'trend_exhaustion'
        bias = 'LONG' if trend_stack_bull else 'SHORT'
        confidence = 64.0
        summary = 'тренд ещё есть, но видны признаки локального выдыхания'
    elif trend_gap < 0.30 and atr_pct < 1.05:
        regime = 'range_rotation'
        bias = 'NEUTRAL'
        confidence = 58.0
        summary = 'рыночная ротация внутри диапазона без чистого продолжения'
    else:
        regime = 'directional_bias'
        if trend_stack_bull or (above_pack and ret10 > 0):
            bias = 'LONG'
        elif trend_stack_bear or (below_pack and ret10 < 0):
            bias = 'SHORT'
        else:
            bias = 'NEUTRAL'
        confidence = 56.0 if bias == 'NEUTRAL' else 62.0
        summary = 'есть направленный перекос, но без полноценного режимного подтверждения'

    return {
        'regime': regime,
        'bias': bias,
        'confidence': round(confidence, 1),
        'summary': summary,
        'trend_gap_pct': round(trend_gap, 3),
        'atr_pct': round(atr_pct, 3),
        'ret10_pct': round(ret10, 3),
        'rsi14': round(rsi, 2),
        'compression_score': round(max(0.0, min(100.0, (0.25 - trend_gap) * 260 + (0.95 - atr_pct) * 20)), 1),
        'expansion_score': round(max(0.0, min(100.0, atr_pct * 55 + abs(ret10) * 6)), 1),
    }
