from __future__ import annotations

from typing import Any, Dict

from core.data_loader import load_klines
from core.indicators import add_indicators
from core.range_detector import analyze_range
from core.reversal_engine import analyze_reversal
from core.pattern_memory import analyze_history_pattern
from core.market_regime import detect_market_regime




def _safe_analysis_result(symbol: str, timeframe: str, price: float | None = None, range_info: Dict[str, Any] | None = None, error: str = "") -> Dict[str, Any]:
    range_info = range_info or {}
    price_value = float(price or 0.0) if price is not None else 0.0
    low = range_info.get("range_low")
    mid = range_info.get("range_mid")
    high = range_info.get("range_high")
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": round(price_value, 2) if price_value > 0 else None,
        "signal": "НЕЙТРАЛЬНО",
        "final_decision": "ЖДАТЬ",
        "forecast_direction": "НЕЙТРАЛЬНО",
        "forecast_confidence": 0.0,
        "forecast_strength": "NEUTRAL",
        "setup_confidence": 0.0,
        "setup_status_hint": "WAIT",
        "entry_zone": None,
        "stop_loss": None,
        "take_profit": None,
        "reversal_signal": "NO_REVERSAL",
        "reversal_direction": "NEUTRAL",
        "reversal_confidence": 0.0,
        "reversal_strength": 0.0,
        "reversal_summary": "нет данных",
        "reversal_patterns": [],
        "false_break_signal": "NONE",
        "trap_side": "NONE",
        "trap_comment": "",
        "history_pattern_direction": "NEUTRAL",
        "history_pattern_confidence": 0.0,
        "history_pattern_summary": "история недоступна",
        "history_pattern_matches": 0,
        "pattern_forecast_direction": "НЕЙТРАЛЬНО",
        "pattern_forecast_confidence": 0.0,
        "pattern_forecast_strength": "NEUTRAL",
        "market_regime": "insufficient_local_data",
        "market_regime_bias": "NEUTRAL",
        "market_regime_confidence": 0.0,
        "market_regime_summary": "локальных данных недостаточно для уверенного режима",
        "pattern_forecast_move": "ожидаемый ход не определён",
        "pattern_scope": "recent_multi_cycle",
        "pattern_years": [],
        "impulse": {
            "state": "NO_IMPULSE",
            "comment": "нет достаточно сильного импульса",
            "strength": 0.0,
            "freshness": 0.0,
            "exhaustion": 0.0,
            "confirmation": 0.0,
            "watch_conditions": ["ожидать новый импульс", "ожидать подход к зоне реакции"],
        },
        "impulse_state": "NO_IMPULSE",
        "impulse_comment": "нет достаточно сильного импульса",
        "impulse_strength": 0.0,
        "impulse_freshness": 0.0,
        "impulse_exhaustion": 0.0,
        "impulse_confirmation": 0.0,
        "analysis": {
            "signal_bias": "НЕЙТРАЛЬНО",
            "market_state": "UNKNOWN",
            "component_bias": 0.0,
            "edge_bias": range_info.get("edge_bias"),
            "breakout_risk": range_info.get("breakout_risk"),
            "history_pattern_direction": "NEUTRAL",
            "history_pattern_confidence": 0.0,
            "history_pattern_summary": "история недоступна",
            "pattern_bias": 0.0,
            "forecast_strength": "NEUTRAL",
            "setup_status_hint": "WAIT",
            "impulse_state": "NO_IMPULSE",
            "impulse_comment": "нет достаточно сильного импульса",
            "loader_error": error[:300],
        },
        "stats": {
            "trend_score": 0.0,
            "stretch_score": 0.0,
            "reversal_score": 0.0,
            "location_score": 0.0,
            "component_bias": 0.0,
            "edge_score": range_info.get("edge_score", 0.0),
            "history_pattern_confidence": 0.0,
            "pattern_bias": 0.0,
            "market_regime_confidence": 0.0,
            "market_regime_bias": "NEUTRAL",
        },
        "range_low": low,
        "range_mid": mid,
        "range_high": high,
        **range_info,
    }

def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _compute_component_scores(last: Dict[str, Any], reversal: Dict[str, Any] | None = None, range_info: Dict[str, Any] | None = None) -> Dict[str, float]:
    reversal = reversal or {}
    range_info = range_info or {}
    close = float(last.get("close") or 0.0)
    ema20 = float(last.get("ema20") or 0.0)
    ema50 = float(last.get("ema50") or 0.0)
    ema100 = float(last.get("ema100") or 0.0)
    atr = max(float(last.get("atr14") or 0.0), 1e-9)
    vol = float(last.get("volume") or 0.0)
    vol_ma = max(float(last.get("vol_ma20") or 0.0), 1e-9)
    rsi = float(last.get("rsi14") or 50.0)
    ret1 = float(last.get("ret1") or 0.0)
    ret5 = float(last.get("ret5") or 0.0)

    trend_score = 0.0
    if close > ema20 > ema50 > ema100:
        trend_score += 0.65
    elif close < ema20 < ema50 < ema100:
        trend_score -= 0.65
    trend_score += _clamp((close - ema50) / atr, -0.35, 0.35)

    stretch_score = 0.0
    if rsi < 33:
        stretch_score += 0.45
    elif rsi > 67:
        stretch_score -= 0.45
    stretch_score += _clamp(-(close - ema20) / (2.2 * atr), -0.35, 0.35)

    reversal_score = 0.0
    rev_dir = str(reversal.get("direction") or "NEUTRAL").upper()
    rev_conf = float(reversal.get("confidence") or 0.0)
    if rev_dir == "LONG":
        reversal_score += 0.45 + rev_conf * 0.45
    elif rev_dir == "SHORT":
        reversal_score -= 0.45 + rev_conf * 0.45

    location_score = 0.0
    if abs((close - ema20) / atr) < 0.35:
        location_score += 0.10 if trend_score > 0 else -0.10 if trend_score < 0 else 0.0
    if vol > vol_ma * 1.15:
        location_score += 0.18 if ret1 > 0 else -0.18 if ret1 < 0 else 0.0
    location_score += _clamp(ret5 * 10.0, -0.25, 0.25)

    range_ratio = float(range_info.get("range_ratio") or 0.5)
    edge_bias = str(range_info.get("edge_bias") or "NONE").upper()
    edge_score = float(range_info.get("edge_score") or 0.0)
    if edge_bias == "LONG_EDGE":
        location_score += 0.25 * edge_score
    elif edge_bias == "SHORT_EDGE":
        location_score -= 0.25 * edge_score
    if 0.42 <= range_ratio <= 0.58:
        location_score *= 0.75

    return {
        "trend_score": round(_clamp(trend_score), 4),
        "stretch_score": round(_clamp(stretch_score), 4),
        "reversal_score": round(_clamp(reversal_score), 4),
        "location_score": round(_clamp(location_score), 4),
    }


def _market_state(direction: str, component_bias: float) -> str:
    if abs(component_bias) < 0.06:
        return "CONFLICTED" if direction != "НЕЙТРАЛЬНО" else "NEUTRAL"
    if direction == "НЕЙТРАЛЬНО":
        return "UNKNOWN"
    return "BIASED"


def _direction_and_score(last: Dict[str, Any], reversal: Dict[str, Any] | None = None, range_info: Dict[str, Any] | None = None) -> tuple[str, float, str, Dict[str, float]]:
    components = _compute_component_scores(last, reversal=reversal, range_info=range_info)
    component_bias = (
        components["trend_score"] * 0.40
        + components["stretch_score"] * 0.16
        + components["reversal_score"] * 0.24
        + components["location_score"] * 0.20
    )
    score = 0.5 + component_bias * 0.5
    score = max(0.0, min(1.0, score))

    rev_dir = str((reversal or {}).get("direction") or "NEUTRAL").upper()
    rev_conf = float((reversal or {}).get("confidence") or 0.0)
    if rev_dir == "SHORT" and rev_conf >= 0.60 and score <= 0.58:
        score = min(score, 0.30)
    elif rev_dir == "LONG" and rev_conf >= 0.60 and score >= 0.42:
        score = max(score, 0.70)

    if score >= 0.62:
        signal = "ЛОНГ"
        confidence = score
        final_decision = "ЛОНГ"
    elif score <= 0.38:
        signal = "ШОРТ"
        confidence = 1.0 - score
        final_decision = "ШОРТ"
    else:
        signal = "НЕЙТРАЛЬНО"
        confidence = min(abs(score - 0.5) * 2, 0.40)
        final_decision = "ЖДАТЬ"

    components["component_bias"] = round(component_bias, 4)
    components["market_state"] = _market_state(signal, component_bias)
    return signal, confidence, final_decision, components



def _build_forecast(signal: str, confidence: float, components: Dict[str, float], reversal: Dict[str, Any] | None = None, history_pattern: Dict[str, Any] | None = None, range_info: Dict[str, Any] | None = None) -> tuple[str, float, float]:
    reversal = reversal or {}
    history_pattern = history_pattern or {}
    range_info = range_info or {}
    if signal == "ЛОНГ":
        return "ВВЕРХ", max(float(confidence), 0.62), 0.0
    if signal == "ШОРТ":
        return "ВНИЗ", max(float(confidence), 0.62), 0.0

    bias = float(components.get("component_bias") or 0.0)
    trend = float(components.get("trend_score") or 0.0)
    reversal_score = float(components.get("reversal_score") or 0.0)
    location = float(components.get("location_score") or 0.0)

    directional_bias = bias * 0.58 + trend * 0.16 + reversal_score * 0.14 + location * 0.12
    edge_bias = str(range_info.get("edge_bias") or "NONE").upper()
    edge_score = float(range_info.get("edge_score") or 0.0)
    range_ratio = float(range_info.get("range_ratio") or 0.5)
    if edge_bias == "LONG_EDGE":
        directional_bias += 0.05 + edge_score * 0.10
    elif edge_bias == "SHORT_EDGE":
        directional_bias -= 0.05 + edge_score * 0.10
    if 0.44 <= range_ratio <= 0.56:
        directional_bias *= 0.92
    pattern_bias = 0.0

    rev_dir = str(reversal.get("direction") or "NEUTRAL").upper()
    rev_conf = float(reversal.get("confidence") or 0.0)
    if rev_dir == "LONG":
        directional_bias += 0.05 + rev_conf * 0.12
    elif rev_dir == "SHORT":
        directional_bias -= 0.05 + rev_conf * 0.12

    pattern_dir = str(history_pattern.get("direction") or "NEUTRAL").upper()
    pattern_conf = float(history_pattern.get("confidence") or 0.0)
    if pattern_dir == "UP":
        pattern_bias = 0.04 + pattern_conf * 0.10
        directional_bias += pattern_bias
    elif pattern_dir == "DOWN":
        pattern_bias = -(0.04 + pattern_conf * 0.10)
        directional_bias += pattern_bias

    abs_bias = abs(directional_bias)
    if directional_bias >= 0.025:
        return "ВВЕРХ", min(0.55 + abs_bias * 0.58, 0.88), pattern_bias
    if directional_bias <= -0.025:
        return "ВНИЗ", min(0.55 + abs_bias * 0.58, 0.88), pattern_bias
    return "НЕЙТРАЛЬНО", min(0.46 + abs_bias * 0.22, 0.57), pattern_bias




def _build_impulse(last: Dict[str, Any], signal: str, forecast_direction: str, forecast_confidence: float, components: Dict[str, float], reversal: Dict[str, Any] | None = None, range_info: Dict[str, Any] | None = None) -> Dict[str, Any]:
    reversal = reversal or {}
    range_info = range_info or {}
    close = float(last.get("close") or 0.0)
    ema20 = float(last.get("ema20") or 0.0)
    ema50 = float(last.get("ema50") or 0.0)
    atr = max(float(last.get("atr14") or 0.0), 1e-9)
    vol = float(last.get("volume") or 0.0)
    vol_ma = max(float(last.get("vol_ma20") or 0.0), 1e-9)
    ret1 = float(last.get("ret1") or 0.0)
    ret5 = float(last.get("ret5") or 0.0)
    trend_score = float(components.get("trend_score") or 0.0)
    location_score = float(components.get("location_score") or 0.0)
    reversal_score = float(components.get("reversal_score") or 0.0)
    range_ratio = float(range_info.get("range_ratio") or 0.5)
    breakout_risk = str(range_info.get("breakout_risk") or "MEDIUM").upper()
    rev_conf = float(reversal.get("confidence") or 0.0)

    vol_ratio = vol / vol_ma
    move_strength = abs(ret1) * 8.0 + abs(ret5) * 5.0 + abs((close - ema20) / atr) * 0.18 + max(vol_ratio - 1.0, 0.0) * 0.45
    impulse_strength = max(0.0, min(move_strength, 1.0))

    freshness = 0.35
    if abs(ret1) > abs(ret5) * 0.35:
        freshness += 0.25
    if vol_ratio >= 1.10:
        freshness += 0.20
    if abs((ema20 - ema50) / atr) >= 0.20:
        freshness += 0.10
    freshness = max(0.0, min(freshness, 1.0))

    exhaustion = 0.10
    if 0.42 <= range_ratio <= 0.58:
        exhaustion += 0.28
    if breakout_risk == 'HIGH':
        exhaustion += 0.18
    if rev_conf >= 0.45 and reversal_score * trend_score < 0:
        exhaustion += 0.22
    if vol_ratio < 0.95:
        exhaustion += 0.10
    exhaustion = max(0.0, min(exhaustion, 1.0))

    confirmation = 0.25
    if forecast_direction == 'ВВЕРХ' and trend_score > 0 and location_score >= -0.05:
        confirmation += 0.28
    elif forecast_direction == 'ВНИЗ' and trend_score < 0 and location_score <= 0.05:
        confirmation += 0.28
    if vol_ratio >= 1.05:
        confirmation += 0.12
    if abs(ret1) > 0.0015:
        confirmation += 0.10
    if rev_conf >= 0.35 and ((forecast_direction == 'ВВЕРХ' and reversal_score > 0) or (forecast_direction == 'ВНИЗ' and reversal_score < 0)):
        confirmation += 0.12
    confirmation = max(0.0, min(confirmation, 1.0))

    direction_hint = str(forecast_direction or 'НЕЙТРАЛЬНО').upper()
    if direction_hint not in {'ВВЕРХ', 'ВНИЗ'}:
        direction_hint = 'ВВЕРХ' if trend_score > 0 else 'ВНИЗ' if trend_score < 0 else 'НЕЙТРАЛЬНО'

    if impulse_strength >= 0.58 and freshness >= 0.58 and confirmation >= 0.58 and exhaustion < 0.42:
        state = 'BULLISH_ACTIVE' if direction_hint == 'ВВЕРХ' else 'BEARISH_ACTIVE' if direction_hint == 'ВНИЗ' else 'IMPULSE_CONTINUES'
        comment = 'свежий импульс поддерживает текущее направление'
    elif exhaustion >= 0.62 and impulse_strength < 0.58:
        state = 'FADING'
        comment = 'импульс выдыхается, лучше не заходить в догонку'
    elif 0.42 <= range_ratio <= 0.58 and confirmation < 0.55:
        state = 'RANGE_NO_IMPULSE'
        comment = 'внутри диапазона импульс слабый и быстро гаснет'
    elif confirmation >= 0.50 or impulse_strength >= 0.50:
        state = 'BULLISH_BUILDING' if direction_hint == 'ВВЕРХ' else 'BEARISH_BUILDING' if direction_hint == 'ВНИЗ' else 'CONFLICTED'
        comment = 'импульс есть, но для входа нужно подтверждение'
    else:
        state = 'CONFLICTED'
        comment = 'импульс смешанный: рынок пока не дал чистого подтверждения'

    return {
        'state': state,
        'strength': round(impulse_strength, 3),
        'freshness': round(freshness, 3),
        'exhaustion': round(exhaustion, 3),
        'confirmation': round(confirmation, 3),
        'comment': comment,
        'watch_conditions': [
            'подтверждение следующей свечой',
            'удержание уровня / зоны реакции',
            'рост объёма по направлению движения',
        ],
    }

def _build_pattern_forecast(history_pattern: Dict[str, Any] | None = None) -> tuple[str, float, str, str, str]:
    history_pattern = history_pattern or {}
    pattern_dir = str(history_pattern.get("direction") or "NEUTRAL").upper()
    pattern_conf = float(history_pattern.get("confidence") or 0.0)
    avg_future = float(history_pattern.get("avg_future_return") or 0.0)
    horizon = int(history_pattern.get("horizon_bars") or 0)
    regime = str(history_pattern.get("regime") or "UNKNOWN").upper()
    move_style = str(history_pattern.get("move_style") or "unknown").lower()
    if pattern_dir == "UP":
        direction = "ВВЕРХ"
    elif pattern_dir == "DOWN":
        direction = "ВНИЗ"
    else:
        direction = "НЕЙТРАЛЬНО"
    move_text = f"ожидаемый ход {avg_future * 100:.2f}% за {horizon} баров" if horizon > 0 else "ожидаемый ход не определён"
    regime_map = {
        "TREND_CONTINUATION": "продолжение тренда",
        "DIRECTIONAL_BIAS": "направленный перекос",
        "RANGE_MEAN_REVERSION": "возврат к среднему в диапазоне",
        "COMPRESSION": "сжатие / набор энергии",
        "FADE_AFTER_IMPULSE": "затухание после импульса",
        "BALANCED_EXPANSION": "баланс с расширением",
        "EXPANSION": "расширение диапазона",
        "INSUFFICIENT_LOCAL_DATA": "мало локальных данных",
        "HISTORY_UNAVAILABLE": "история недоступна",
        "FAST_TF_DISABLED": "отключено для быстрого тф",
    }
    style_map = {
        "trend_continuation": "continuation",
        "directional_bias": "directional_bias",
        "mean_reversion": "mean_reversion",
        "compression": "compression",
        "fade_after_impulse": "fade_after_impulse",
        "fast_tf_disabled": "disabled",
        "unknown": "unknown",
    }
    return direction, max(0.0, min(pattern_conf, 1.0)), move_text, regime_map.get(regime, regime.lower()), style_map.get(move_style, move_style)



def _direction_strength_label(direction: str, confidence: float) -> str:
    direction = str(direction or 'НЕЙТРАЛЬНО').upper()
    conf = float(confidence or 0.0)
    if direction in {'НЕЙТРАЛЬНО', 'NEUTRAL', 'UNKNOWN', ''}:
        return 'NEUTRAL'
    if conf >= 0.78:
        level = 'STRONG'
    elif conf >= 0.68:
        level = 'MODERATE'
    elif conf >= 0.58:
        level = 'WEAK'
    else:
        level = 'VERY WEAK'
    return f"{level} {direction}"


def _setup_status_from_inputs(signal: str, range_info: Dict[str, Any] | None = None, reversal: Dict[str, Any] | None = None, forecast_direction: str | None = None, forecast_confidence: float | None = None) -> str:
    range_info = range_info or {}
    reversal = reversal or {}
    if signal in {'ЛОНГ', 'ШОРТ'}:
        return 'READY'
    ratio = float(range_info.get('range_ratio') or 0.5)
    edge_score = float(range_info.get('edge_score') or 0.0)
    breakout_risk = str(range_info.get('breakout_risk') or 'MEDIUM').upper()
    rev_conf = float(reversal.get('confidence') or 0.0)
    fc = float(forecast_confidence or 0.0)
    near_edge = ratio <= 0.18 or ratio >= 0.82
    upper_half = ratio >= 0.62
    lower_half = ratio <= 0.38
    directional = str(forecast_direction or 'НЕЙТРАЛЬНО').upper()
    if directional in {'ВВЕРХ', 'UP'} and (near_edge or lower_half) and fc >= 0.60 and breakout_risk != 'HIGH':
        return 'WATCH'
    if directional in {'ВНИЗ', 'DOWN'} and (near_edge or upper_half) and fc >= 0.60 and breakout_risk != 'HIGH':
        return 'WATCH'
    if edge_score >= 0.55 and rev_conf >= 0.45 and directional not in {'НЕЙТРАЛЬНО', 'NEUTRAL'}:
        return 'EARLY'
    return 'WAIT'

def analyze_btc(symbol: str = "BTCUSDT", timeframe: str = "1h") -> Dict[str, Any]:
    range_info: Dict[str, Any] = {}
    try:
        df = add_indicators(load_klines(symbol=symbol, timeframe=timeframe, limit=320))
        if df is None or df.empty or len(df) < 50:
            return _safe_analysis_result(symbol, timeframe, range_info=range_info, error="empty_or_short_dataframe")
        range_info = analyze_range(symbol=symbol, timeframe=timeframe) or {}
        last = df.iloc[-1].to_dict()
        reversal = analyze_reversal(df, range_info=range_info)
        try:
            history_pattern = analyze_history_pattern(df, symbol=symbol, timeframe=timeframe)
        except Exception as exc:
            history_pattern = {"direction": "NEUTRAL", "confidence": 0.0, "summary": f"pattern memory fallback: {type(exc).__name__}"}
        signal, confidence, final_decision, components = _direction_and_score(last, reversal=reversal, range_info=range_info)
    except Exception as exc:
        return _safe_analysis_result(symbol, timeframe, range_info=range_info, error=f"{type(exc).__name__}: {exc}")
    forecast_direction, forecast_confidence, pattern_bias = _build_forecast(signal, confidence, components, reversal=reversal, history_pattern=history_pattern, range_info=range_info)
    pattern_forecast_direction, pattern_forecast_confidence, pattern_forecast_move, pattern_forecast_regime, pattern_forecast_style = _build_pattern_forecast(history_pattern)
    market_regime = detect_market_regime(df)
    pattern_scope = history_pattern.get("pattern_scope")
    pattern_years = history_pattern.get("source_years") or ([history_pattern.get("source_year")] if history_pattern.get("source_year") else [])
    forecast_strength = _direction_strength_label(forecast_direction, forecast_confidence)
    impulse = _build_impulse(last, signal, forecast_direction, forecast_confidence, components, reversal=reversal, range_info=range_info)
    pattern_forecast_strength = _direction_strength_label(pattern_forecast_direction, pattern_forecast_confidence)
    setup_status = _setup_status_from_inputs(signal, range_info=range_info, reversal=reversal, forecast_direction=forecast_direction, forecast_confidence=forecast_confidence)

    atr = float(last["atr14"])
    price = float(last["close"])

    if signal == "ЛОНГ":
        entry_zone = f"{price - 0.25 * atr:.0f} - {price:.0f}"
        stop_loss = round(price - 1.2 * atr, 2)
        take_profit = f"{price + 1.2 * atr:.0f} / {price + 2.2 * atr:.0f}"
    elif signal == "ШОРТ":
        entry_zone = f"{price:.0f} - {price + 0.25 * atr:.0f}"
        stop_loss = round(price + 1.2 * atr, 2)
        take_profit = f"{price - 1.2 * atr:.0f} / {price - 2.2 * atr:.0f}"
    else:
        entry_zone = None
        stop_loss = None
        take_profit = None

    analysis = {
        "signal_bias": signal,
        "market_state": components.get("market_state"),
        "component_bias": components.get("component_bias"),
        "range_ratio": range_info.get("range_ratio"),
        "edge_bias": range_info.get("edge_bias"),
        "breakout_risk": range_info.get("breakout_risk"),
        "false_break_signal": reversal.get("false_break_signal"),
        "history_pattern_direction": history_pattern.get("direction"),
        "history_pattern_confidence": history_pattern.get("confidence"),
        "history_pattern_summary": history_pattern.get("summary"),
        "pattern_bias": round(pattern_bias, 4),
        "market_regime_confidence": market_regime.get("confidence"),
        "market_regime_bias": market_regime.get("bias"),
        "pattern_forecast_direction": pattern_forecast_direction,
        "pattern_forecast_confidence": pattern_forecast_confidence,
        "pattern_forecast_move": pattern_forecast_move,
        "market_regime": market_regime.get("regime"),
        "market_regime_bias": market_regime.get("bias"),
        "market_regime_confidence": market_regime.get("confidence"),
        "market_regime_summary": market_regime.get("summary"),
        "pattern_forecast_regime": pattern_forecast_regime,
        "pattern_forecast_style": pattern_forecast_style,
        "forecast_strength": forecast_strength,
        "pattern_forecast_strength": pattern_forecast_strength,
        "market_regime": market_regime.get("regime"),
        "market_regime_bias": market_regime.get("bias"),
        "market_regime_confidence": market_regime.get("confidence"),
        "market_regime_summary": market_regime.get("summary"),
        "setup_status_hint": setup_status,
        "pattern_scope": pattern_scope,
        "pattern_years": pattern_years,
        "impulse_state": impulse.get('state'),
        "impulse_comment": impulse.get('comment'),
        "impulse_strength": impulse.get('strength'),
        "impulse_freshness": impulse.get('freshness'),
        "impulse_exhaustion": impulse.get('exhaustion'),
        "impulse_confirmation": impulse.get('confirmation'),
    }

    stats = {
        "trend_score": components.get("trend_score"),
        "stretch_score": components.get("stretch_score"),
        "reversal_score": components.get("reversal_score"),
        "location_score": components.get("location_score"),
        "component_bias": components.get("component_bias"),
        "edge_score": range_info.get("edge_score"),
        "history_pattern_confidence": history_pattern.get("confidence"),
        "pattern_bias": round(pattern_bias, 4),
        "market_regime_confidence": market_regime.get("confidence"),
        "market_regime_bias": market_regime.get("bias"),
    }

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": round(price, 2),
        "signal": signal,
        "final_decision": final_decision,
        "forecast_direction": forecast_direction,
        "forecast_confidence": round(forecast_confidence, 3),
        "forecast_strength": forecast_strength,
        "setup_confidence": round(confidence, 3),
        "setup_status_hint": setup_status,
        "entry_zone": entry_zone,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rsi": round(float(last["rsi14"]), 2),
        "ema20": round(float(last["ema20"]), 2),
        "ema50": round(float(last["ema50"]), 2),
        "ema100": round(float(last["ema100"]), 2),
        "reversal_signal": reversal.get("signal"),
        "reversal_direction": reversal.get("direction"),
        "reversal_confidence": reversal.get("confidence"),
        "reversal_strength": reversal.get("strength"),
        "reversal_summary": reversal.get("summary"),
        "reversal_patterns": reversal.get("patterns"),
        "false_break_signal": reversal.get("false_break_signal"),
        "trap_side": reversal.get("trap_side"),
        "trap_comment": reversal.get("trap_comment"),
        "history_pattern_direction": history_pattern.get("direction"),
        "history_pattern_confidence": history_pattern.get("confidence"),
        "history_pattern_summary": history_pattern.get("summary"),
        "history_pattern_matches": history_pattern.get("matched_count"),
        "pattern_forecast_direction": pattern_forecast_direction,
        "pattern_forecast_confidence": round(pattern_forecast_confidence, 3),
        "pattern_forecast_strength": pattern_forecast_strength,
        "market_regime": market_regime.get("regime"),
        "market_regime_bias": market_regime.get("bias"),
        "market_regime_confidence": market_regime.get("confidence"),
        "market_regime_summary": market_regime.get("summary"),
        "pattern_forecast_move": pattern_forecast_move,
        "market_regime": market_regime.get("regime"),
        "market_regime_bias": market_regime.get("bias"),
        "market_regime_confidence": market_regime.get("confidence"),
        "market_regime_summary": market_regime.get("summary"),
        "pattern_scope": pattern_scope,
        "pattern_years": pattern_years,
        "impulse": impulse,
        "impulse_state": impulse.get('state'),
        "impulse_comment": impulse.get('comment'),
        "impulse_strength": impulse.get('strength'),
        "impulse_freshness": impulse.get('freshness'),
        "impulse_exhaustion": impulse.get('exhaustion'),
        "impulse_confirmation": impulse.get('confirmation'),
        "analysis": analysis,
        "stats": stats,
        **range_info,
    }
