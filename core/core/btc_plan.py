from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Union

from core.import_compat import normalize_confidence, normalize_direction, to_float
from models.snapshots import AnalysisSnapshot
from core.ux_mode import build_ultra_wait_block, is_no_trade_context


LONG_WORDS = ("лонг", "вверх", "buy", "long", "bull")
SHORT_WORDS = ("шорт", "вниз", "sell", "short", "bear")
WAIT_WORDS = ("ждать", "wait", "нет сделки", "без сделки", "neutral", "flat")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _contains_any(text: str, words: Tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def fmt_price(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "нет данных"
    if abs(number) >= 1000:
        return f"{number:,.2f}".replace(",", " ")
    if abs(number) >= 1:
        return f"{number:.4f}"
    return f"{number:.6f}"


def fmt_pct(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "нет данных"
    if number <= 1.0:
        number *= 100.0
    return f"{number:.1f}%"



def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def _position_bucket(payload: Dict[str, Any]) -> str:
    position = _lower(payload.get("range_position") or payload.get("range_position_zone") or payload.get("range_state"))
    if any(x in position for x in ("low_edge", "lower_part", "ниж", "support", "поддерж")):
        return "LOW"
    if any(x in position for x in ("high_edge", "upper_part", "верх", "resist", "сопротив")):
        return "HIGH"
    if "mid" in position or "серед" in position:
        return "MID"
    return "UNKNOWN"


def _setup_requirements(payload: Dict[str, Any], side: str = "AUTO") -> Dict[str, Any]:
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    direction = str((decision or {}).get("direction_text") or (decision or {}).get("direction") or payload.get("final_decision") or payload.get("forecast_direction") or "НЕЙТРАЛЬНО").upper()
    if side == "AUTO":
        side = "LONG" if "ЛОНГ" in direction or direction == "LONG" else "SHORT" if "ШОРТ" in direction or direction == "SHORT" else "NONE"
    side = str(side or "NONE").upper()

    low = _as_float(payload.get("range_low"))
    mid = _as_float(payload.get("range_mid"))
    high = _as_float(payload.get("range_high"))
    position = _position_bucket(payload)
    impulse = payload.get("impulse_state") or (decision or {}).get("impulse_state") or "NO_CLEAR_IMPULSE"
    reversal_patterns = payload.get("reversal_patterns") or []
    edge = _as_float((decision or {}).get("edge_score")) or 0.0
    if edge <= 1.0:
        edge *= 100.0

    reqs = []
    if side == "LONG":
        zone = f"{fmt_price(low)}–{fmt_price(mid)}" if low is not None and mid is not None else fmt_price(low)
        reqs.append(f"локация: подход к нижней части диапазона {zone}")
        reqs.append("триггер: ложный вынос вниз / удержание low / bullish confirm на рабочем ТФ")
        reqs.append("запрет: не брать лонг в середине диапазона без reclaim")
    elif side == "SHORT":
        zone = f"{fmt_price(mid)}–{fmt_price(high)}" if mid is not None and high is not None else fmt_price(high)
        reqs.append(f"локация: подход к верхней части диапазона {zone}")
        reqs.append("триггер: ложный вынос вверх / rejection от high / bearish confirm на рабочем ТФ")
        reqs.append("запрет: не шортить середину диапазона без возврата под high")
    else:
        reqs.append("сначала нужна локация у края диапазона")
        reqs.append("нужен retest / reclaim / confirm вместо входа из середины шума")

    if position == "MID":
        reqs.append("сейчас цена в середине диапазона: сначала нужен подход к краю")
    if str(impulse).upper() == "NO_CLEAR_IMPULSE":
        reqs.append("чистый импульс не собран: ждать подтверждение, а не форсировать вход")
    if edge <= 0.0:
        reqs.append("edge отсутствует: execution не разрешён до появления перевеса")
    if reversal_patterns:
        reqs.append(f"паттерн-подтверждение: учитывать {reversal_patterns[0]}")

    return {"side": side, "items": reqs[:5]}


def _arming_logic(payload: Dict[str, Any], side: str = "AUTO") -> Dict[str, Any]:
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    position = _position_bucket(payload)
    range_state = _lower(payload.get("range_state"))
    impulse_state = str(payload.get("impulse_state") or (decision or {}).get("impulse_state") or "NO_CLEAR_IMPULSE").upper()
    confirmation = _as_float(payload.get("impulse_confirmation") or (decision or {}).get("impulse_confirmation")) or 0.0
    if confirmation <= 1.0:
        confirmation *= 100.0
    freshness = _as_float(payload.get("impulse_freshness") or (decision or {}).get("impulse_freshness")) or 0.0
    if freshness <= 1.0:
        freshness *= 100.0
    edge = _as_float((decision or {}).get("edge_score")) or 0.0
    if edge <= 1.0:
        edge *= 100.0
    patterns = payload.get("reversal_patterns") or []

    location_ready = 100 if position in {"LOW", "HIGH"} else 35 if position == "MID" else 20
    regime_ready = 100 if ("range" in range_state or "диапаз" in range_state) else 55
    reversal_ready = 80 if patterns else 20
    confirm_ready = min(100, int(max(confirmation, freshness * 0.5)))
    edge_ready = min(100, int(edge))
    total = int(round((location_ready * 0.30) + (regime_ready * 0.20) + (reversal_ready * 0.20) + (confirm_ready * 0.20) + (edge_ready * 0.10)))

    if confirm_ready <= 0 or edge < 20:
        status = "WATCH" if total >= 35 else "OFF"
    elif total >= 85 and edge >= 55:
        status = "READY"
    elif total >= 60:
        status = "ARMING"
    elif total >= 35:
        status = "WATCH"
    else:
        status = "OFF"

    blockers = []
    if position == "MID":
        blockers.append("цена не у края диапазона")
    if impulse_state == "NO_CLEAR_IMPULSE":
        blockers.append("нет чистого импульса / reclaim")
    if edge < 25:
        blockers.append("edge слишком слабый")
    if not patterns:
        blockers.append("нет reversal/return сигнала")
    if confirm_ready <= 0:
        blockers.append("нет confirmation trigger")

    return {
        "status": status,
        "total": total,
        "location_ready": location_ready,
        "regime_ready": regime_ready,
        "reversal_ready": reversal_ready,
        "confirm_ready": confirm_ready,
        "edge_ready": edge_ready,
        "blockers": blockers[:4],
    }




def _move_type_block(payload: Dict[str, Any], decision: Dict[str, Any]) -> list[str]:
    ctx = decision.get('move_type_context') if isinstance(decision.get('move_type_context'), dict) else {}
    if not ctx:
        return []
    return ['MOVE TYPE:', f"• type: {ctx.get('type', 'NO_CLEAR_MOVE')}", f"• bias: {ctx.get('bias', 'NEUTRAL')}", f"• summary: {ctx.get('summary', 'нет данных')}", f"• implication: {ctx.get('implication', 'нет данных')}"]


def _fake_move_block(payload: Dict[str, Any], decision: Dict[str, Any]) -> list[str]:
    fake = decision.get('fake_move_detector') if isinstance(decision.get('fake_move_detector'), dict) else {}
    if not fake:
        return []
    lines = ['FAKE MOVE:']
    lines.append(f"• status: {fake.get('type') or 'NONE'}")
    lines.append(f"• confidence: {fake.get('confidence', 0.0)}%")
    if 'confirmed' in fake:
        lines.append(f"• confirmed: {'YES' if fake.get('confirmed') else 'NO'}")
    if fake.get('reclaim_needed') is not None:
        lines.append(f"• reclaim needed: {fake.get('reclaim_needed')}")
    if fake.get('invalidation_level') is not None:
        lines.append(f"• invalidation: {fake.get('invalidation_level')}")
    lines.append(f"• implication: {fake.get('implication') or fake.get('summary') or 'нет данных'}")
    return lines

def _volume_range_bot_conditions(payload: Dict[str, Any]) -> Dict[str, Any]:
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    permission = decision.get('range_bot_permission') if isinstance(decision.get('range_bot_permission'), dict) else {}
    if permission:
        borders = permission.get('working_borders') if isinstance(permission.get('working_borders'), dict) else {}
        return {
            'status': permission.get('status', 'OFF'),
            'add_status': 'READY_ADD' if permission.get('adds_allowed') else 'WAIT_ADD',
            'deviation_pct': 0.0,
            'range_detected': 'YES' if borders.get('low') and borders.get('high') else 'NO',
            'location_state': permission.get('entry_location', 'UNKNOWN'),
            'post_impulse_fade': (decision.get('move_type_context') or {}).get('fade_quality', 'NONE') if isinstance(decision.get('move_type_context'), dict) else 'NONE',
            'breakout_risk': permission.get('breakout_risk', decision.get('trap_risk', 'UNKNOWN')),
            'rotation_quality': 'GOOD' if (decision.get('move_type_context') or {}).get('range_rotation_ready') else 'OK',
            'size_multiplier': float(str(permission.get('size_mode', 'x0.00')).replace('x','') or 0.0),
            'conditions': permission.get('launch_conditions', []),
            'blockers': permission.get('invalidation_conditions', []),
            'launch_hint': permission.get('summary', ''),
            'working_borders': borders,
            'long_zone': permission.get('long_zone', []),
            'short_zone': permission.get('short_zone', []),
        }
    low = _as_float(payload.get("range_low"))
    mid = _as_float(payload.get("range_mid"))
    high = _as_float(payload.get("range_high"))
    position = _position_bucket(payload)
    range_state = _lower(payload.get("range_state"))
    grid = payload.get("grid_strategy") if isinstance(payload.get("grid_strategy"), dict) else {}
    deviation = _as_float(grid.get("deviation_abs_pct") or payload.get("impulse_move_pct")) or 0.0
    breakout_risk = str((decision or {}).get("trap_risk") or "MEDIUM").upper()
    impulse_state = str(payload.get("impulse_state") or (decision or {}).get("impulse_state") or "NO_CLEAR_IMPULSE").upper()

    range_detected = ("range" in range_state or "диапаз" in range_state or position in {"LOW", "HIGH", "MID"})
    near_edge = position in {"LOW", "HIGH"}
    impulse_faded = impulse_state == "NO_CLEAR_IMPULSE"
    reaccepted = near_edge or (position == "MID" and deviation <= 0.35)
    low_breakout_risk = breakout_risk in {"LOW", "MEDIUM"}
    breakout_penalty_mode = breakout_risk == "HIGH"
    rotation_quality = "GOOD" if impulse_faded and reaccepted else "OK" if impulse_faded or reaccepted else "BAD"
    location_state = "EDGE" if near_edge else "MID" if position == "MID" else "UNKNOWN"
    post_impulse_fade = "YES" if impulse_faded and deviation >= 0.8 else "PARTIAL" if impulse_faded else "NO"

    if range_detected and near_edge and impulse_faded and low_breakout_risk:
        status = "READY_SMALL"
    elif range_detected and near_edge and low_breakout_risk:
        status = "ARMING"
    elif range_detected and position == "MID" and impulse_faded and rotation_quality in {"GOOD", "OK"} and deviation <= 0.8:
        status = "READY_SMALL"
    elif range_detected and impulse_faded and reaccepted and (low_breakout_risk or breakout_penalty_mode):
        status = "WATCH"
    else:
        status = "OFF"

    if breakout_penalty_mode and status == "READY_SMALL":
        status = "READY_SMALL_REDUCED"
    add_status = "READY_ADD" if status in {"READY_SMALL", "READY_SMALL_REDUCED"} and reaccepted and rotation_quality == "GOOD" and breakout_risk != "HIGH" else "WAIT_ADD"

    conditions = [
        "режим: range / возврат в диапазон после импульса",
        f"локация: лучше у края диапазона {fmt_price(low)}–{fmt_price(mid)} / {fmt_price(mid)}–{fmt_price(high)}",
        "импульс: после сильного выноса ждать затухание и возврат в спокойную проторговку",
        "риск пробоя: при HIGH не выключать полностью, а уменьшать размер и запрещать добавления",
        "исполнение: READY_SMALL = старт малым размером, READY_SMALL_REDUCED = старт только уменьшенным размером, READY_ADD = добавление только после повторного удержания зоны",
    ]

    blockers = []
    if position == "MID" and deviation < 0.5:
        blockers.append("цена в середине диапазона без сильного выноса")
    if not impulse_faded and deviation >= 0.8:
        blockers.append("импульс ещё жив: рано включать объёмный range-бот")
    if breakout_risk == "HIGH":
        blockers.append("высокий breakout risk: только reduced size, без adds")
    if not range_detected:
        blockers.append("рынок не похож на range / re-acceptance")

    size_multiplier = 0.30 if breakout_risk == "HIGH" else 0.50 if location_state == "MID" else 1.00
    verdict = decision.get("execution_verdict") if isinstance(decision.get("execution_verdict"), dict) else (payload.get("execution_verdict") if isinstance(payload.get("execution_verdict"), dict) else {})
    edge_score = _as_float((decision or {}).get('edge_score') or payload.get('edge_score')) or 0.0
    effective_edge = max(edge_score, _as_float(verdict.get('trade_edge_score')) or 0.0, _as_float(verdict.get('bot_edge_score')) or 0.0)
    soft_allowed = bool(verdict.get('soft_allowed')) or bool((decision or {}).get('bot_authorized'))
    trade_or_soft_authorized = bool((decision or {}).get('trade_authorized')) or soft_allowed
    no_trade_lock = (not trade_or_soft_authorized) or effective_edge <= 0.0 or str((decision or {}).get('action_bias') or '').upper() == 'NO TRADE' or str((decision or {}).get('setup_grade') or '').upper() == 'NO TRADE' or bool((decision or {}).get('setup_valid')) is False
    if verdict and not no_trade_lock:
        status = "READY_SMALL_REDUCED" if str(verdict.get("status") or "").upper() == "SOFT_RANGE_REDUCED" else "READY_SMALL" if str(verdict.get("status") or "").upper() == "SOFT_RANGE_ALLOWED" else status
        size_multiplier = float(verdict.get("size_multiplier") or size_multiplier)
    if no_trade_lock and status in {'READY_SMALL', 'READY_SMALL_REDUCED', 'ARMING'}:
        status = 'WATCH_ONLY'
        add_status = 'WAIT_ADD'
        blockers.append('truth lock: ждём reclaim/ложный вынос перед small/probe launch')
        add_status = "READY_ADD" if bool(verdict.get("adds_allowed")) else add_status
    return {
        "status": status,
        "add_status": add_status,
        "deviation_pct": deviation,
        "range_detected": "YES" if range_detected else "NO",
        "location_state": location_state,
        "post_impulse_fade": post_impulse_fade,
        "breakout_risk": breakout_risk,
        "rotation_quality": rotation_quality,
        "size_multiplier": round(size_multiplier, 2),
        "conditions": conditions,
        "blockers": blockers[:4],
        "launch_hint": "можно запускать объёмный range-бот малым размером" if status in {"READY_SMALL", "READY_SMALL_REDUCED"} else "ещё рано включать объёмный range-бот",
    }



def _soft_bias_direction(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> tuple[str, str]:
    payload = _to_data_dict(data)
    long_score = calc_long_score(data)
    short_score = calc_short_score(data)
    diff = long_score - short_score
    if diff >= 0.08:
        return 'ЛОНГ', f'long score сильнее: {long_score*100:.1f}% против {short_score*100:.1f}%'
    if diff <= -0.08:
        return 'ШОРТ', f'short score сильнее: {short_score*100:.1f}% против {long_score*100:.1f}%'

    hints = ' '.join([
        str(payload.get('scenario_text') or ''),
        str(payload.get('base_case') or ''),
        str(payload.get('bull_case') or ''),
        str(payload.get('bear_case') or ''),
        str(payload.get('trigger_text') or ''),
        str(payload.get('trigger_up') or ''),
        str(payload.get('trigger_down') or ''),
        ' '.join(str(x) for x in (payload.get('expectation') or [])[:3]),
    ]).lower()
    range_state = str(payload.get('range_state') or '').lower()
    gin = str(payload.get('ginarea_advice') or '').lower()
    short_votes = 0
    long_votes = 0
    if any(x in hints for x in ['вниз', 'down', 'продав', 'short', 'ниже']):
        short_votes += 2
    if any(x in hints for x in ['вверх', 'up', 'покуп', 'long', 'выше']):
        long_votes += 2
    if 'сопротив' in gin or 'верх' in range_state:
        short_votes += 1
    if 'поддерж' in gin or 'низ' in range_state:
        long_votes += 1
    if short_votes >= long_votes + 1 and short_votes >= 2:
        return 'СЛАБЫЙ ШОРТ', 'текстовый сценарий и локация слегка поддерживают движение вниз'
    if long_votes >= short_votes + 1 and long_votes >= 2:
        return 'СЛАБЫЙ ЛОНГ', 'текстовый сценарий и локация слегка поддерживают движение вверх'
    return 'НЕЙТРАЛЬНО', 'score почти равны'


def forecast_bias_label(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    long_score = calc_long_score(data)
    short_score = calc_short_score(data)
    diff = abs(long_score - short_score)
    side = 'LONG' if long_score > short_score else 'SHORT'
    if diff < 0.04:
        bias, _ = _soft_bias_direction(data)
        return bias.lower() if bias != 'НЕЙТРАЛЬНО' else 'почти нейтрально'
    if diff < 0.10:
        return f'слабый {side} bias'
    if diff < 0.18:
        return f'умеренный {side} bias'
    return f'сильный {side} bias'


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _to_data_dict(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(data, AnalysisSnapshot):
        range_obj = _safe_get(data, "range", None)
        return {
            "symbol": _safe_get(data, "symbol", "BTCUSDT"),
            "timeframe": _safe_get(data, "timeframe", "1h"),
            "price": _safe_get(data, "price", 0.0),
            "signal": _safe_get(data, "signal", "НЕЙТРАЛЬНО"),
            "final_decision": _safe_get(data, "final_decision", "НЕЙТРАЛЬНО"),
            "forecast_direction": _safe_get(data, "forecast_direction", "НЕЙТРАЛЬНО"),
            "forecast_confidence": _safe_get(data, "forecast_confidence", 0.0),
            "range_state": _safe_get(data, "range_state", "нет данных"),
            "range_position": _safe_get(data, "range_position", "UNKNOWN"),
            "ct_now": _safe_get(data, "ct_now", "контртренд: явного перекоса нет"),
            "ginarea_advice": _safe_get(data, "ginarea_advice", "нет данных"),
            "decision_summary": _safe_get(data, "decision_summary", ""),
            "range_low": _safe_get(range_obj, "low", 0.0),
            "range_mid": _safe_get(range_obj, "mid", 0.0),
            "range_high": _safe_get(range_obj, "high", 0.0),
        }
    return dict(data or {})


def _decision(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(data, AnalysisSnapshot):
        obj = _safe_get(data, "decision", None)
        if obj is None or obj is data:
            return {}
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "to_dict"):
            try:
                payload = obj.to_dict()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        out: Dict[str, Any] = {}
        for key in (
            "direction", "direction_text",
            "action", "action_text",
            "manager_action", "manager_action_text", "manager_reason",
            "mode", "regime",
            "confidence", "confidence_pct",
            "risk", "risk_level",
            "summary",
            "long_score", "short_score",
            "pressure_reason", "entry_reason", "invalidation",
            "active_bot",
            "range_position", "range_position_zone",
            "expectation", "expectation_text",
            "reasons", "mode_reasons",
        ):
            try:
                out[key] = getattr(obj, key)
            except Exception:
                continue
        return out

    payload = dict(data or {})
    obj = payload.get("decision")
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            result = obj.to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    return {}


def _score_from_signal(signal: Any) -> Tuple[float, float]:
    signal_l = _lower(signal)
    if _contains_any(signal_l, LONG_WORDS):
        return 1.0, 0.0
    if _contains_any(signal_l, SHORT_WORDS):
        return 0.0, 1.0
    return 0.0, 0.0


def _score_from_forecast(direction: Any, confidence: Any) -> Tuple[float, float]:
    conf = normalize_confidence(confidence) or 0.0
    direction_l = _lower(direction)
    if _contains_any(direction_l, LONG_WORDS):
        return conf, 0.0
    if _contains_any(direction_l, SHORT_WORDS):
        return 0.0, conf
    return 0.0, 0.0


def _score_from_final_decision(final_decision: Any) -> Tuple[float, float, bool]:
    text = _lower(final_decision)
    if _contains_any(text, WAIT_WORDS):
        return 0.0, 0.0, True
    if _contains_any(text, LONG_WORDS):
        return 1.0, 0.0, False
    if _contains_any(text, SHORT_WORDS):
        return 0.0, 1.0, False
    return 0.0, 0.0, False


def _score_from_countertrend(ct_now: Any) -> Tuple[float, float]:
    text = _lower(ct_now)
    long_score = 0.0
    short_score = 0.0

    if any(word in text for word in ("перепрод", "oversold", "отскок", "снизу")):
        long_score += 0.75
    if any(word in text for word in ("перекуп", "overbought", "откат", "сверху")):
        short_score += 0.75
    if any(word in text for word in ("нет перекоса", "явного перекоса нет", "нет преимущества")):
        long_score *= 0.3
        short_score *= 0.3

    return min(long_score, 1.0), min(short_score, 1.0)


def _score_from_ginarea(ginarea_advice: Any) -> Tuple[float, float]:
    text = _lower(ginarea_advice)
    long_score = 0.0
    short_score = 0.0

    if any(word in text for word in ("поддерж", "support")):
        long_score += 0.70
    if any(word in text for word in ("сопротив", "resistance")):
        short_score += 0.70
    if "середина" in text or "middle" in text:
        long_score += 0.10
        short_score += 0.10

    return min(long_score, 1.0), min(short_score, 1.0)


def _score_from_range(range_state: Any, price: Any, low: Any, mid: Any, high: Any) -> Tuple[float, float]:
    text = _lower(range_state)
    price_f = to_float(price)
    low_f = to_float(low)
    mid_f = to_float(mid)
    high_f = to_float(high)

    long_score = 0.0
    short_score = 0.0

    if any(word in text for word in ("низ диапазона", "поддержк", "дно", "lower range")):
        long_score += 0.70
    if any(word in text for word in ("верх диапазона", "сопротив", "верхняя граница", "upper range")):
        short_score += 0.70
    if "середина диапазона" in text:
        long_score += 0.15
        short_score += 0.15

    if price_f is not None and low_f is not None and high_f is not None and high_f > low_f:
        band = max(high_f - low_f, 1e-9)
        ratio = (price_f - low_f) / band

        if ratio <= 0.18:
            long_score += 0.85
        elif ratio <= 0.35:
            long_score += 0.35
        elif ratio >= 0.82:
            short_score += 0.85
        elif ratio >= 0.65:
            short_score += 0.35

        if mid_f is not None and abs(price_f - mid_f) / band <= 0.08:
            long_score += 0.10
            short_score += 0.10

    return min(long_score, 1.0), min(short_score, 1.0)


def calc_long_score(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> float:
    payload = _to_data_dict(data)
    decision = _decision(data)
    direct = to_float(decision.get("long_score"))
    if direct is not None:
        if direct > 1.0:
            direct = direct / 100.0
        return round(min(max(direct, 0.0), 1.0), 4)

    signal_long, _ = _score_from_signal(payload.get("signal"))
    forecast_long, _ = _score_from_forecast(payload.get("forecast_direction"), payload.get("forecast_confidence"))
    final_long, _, _ = _score_from_final_decision(payload.get("final_decision"))
    ct_long, _ = _score_from_countertrend(payload.get("ct_now"))
    gin_long, _ = _score_from_ginarea(payload.get("ginarea_advice"))
    range_long, _ = _score_from_range(
        payload.get("range_state"),
        payload.get("price"),
        payload.get("range_low"),
        payload.get("range_mid"),
        payload.get("range_high"),
    )

    score = 0.0
    score += signal_long * 0.24
    score += forecast_long * 0.24
    score += final_long * 0.18
    score += ct_long * 0.13
    score += gin_long * 0.12
    score += range_long * 0.09
    return round(min(score, 1.0), 4)


def calc_short_score(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> float:
    payload = _to_data_dict(data)
    decision = _decision(data)
    direct = to_float(decision.get("short_score"))
    if direct is not None:
        if direct > 1.0:
            direct = direct / 100.0
        return round(min(max(direct, 0.0), 1.0), 4)

    _, signal_short = _score_from_signal(payload.get("signal"))
    _, forecast_short = _score_from_forecast(payload.get("forecast_direction"), payload.get("forecast_confidence"))
    _, final_short, _ = _score_from_final_decision(payload.get("final_decision"))
    _, ct_short = _score_from_countertrend(payload.get("ct_now"))
    _, gin_short = _score_from_ginarea(payload.get("ginarea_advice"))
    _, range_short = _score_from_range(
        payload.get("range_state"),
        payload.get("price"),
        payload.get("range_low"),
        payload.get("range_mid"),
        payload.get("range_high"),
    )

    score = 0.0
    score += signal_short * 0.24
    score += forecast_short * 0.24
    score += final_short * 0.18
    score += ct_short * 0.13
    score += gin_short * 0.12
    score += range_short * 0.09
    return round(min(score, 1.0), 4)


def _decision_direction_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    decision = _decision(data)
    payload = _to_data_dict(data)
    long_score = to_float(decision.get("long_score"))
    short_score = to_float(decision.get("short_score"))
    conf = to_float(decision.get("confidence_pct") or decision.get("confidence")) or 0.0
    signal = normalize_direction(payload.get("signal"))
    forecast = normalize_direction(payload.get("forecast_direction"))
    range_state = _lower(payload.get("range_state") or decision.get("range_position_zone"))
    impulse_state = _text(decision.get("impulse_state")).upper()
    if long_score is not None and short_score is not None:
        if abs(float(long_score) - float(short_score)) <= 3.0 and conf <= 15.0 and signal == 'НЕЙТРАЛЬНО' and forecast == 'НЕЙТРАЛЬНО' and ('серед' in range_state or _text(decision.get('range_position')).upper() == 'MID') and impulse_state in {'NO_CLEAR_IMPULSE','PENDING_CONFIRMATION','IMPULSE_UNCERTAIN','CONFLICTED',''}:
            return 'НЕЙТРАЛЬНО'
    text = _text(decision.get("direction_text"))
    if text:
        return text

    raw = _text(decision.get("direction")).upper()
    mapping = {"LONG": "ЛОНГ", "SHORT": "ШОРТ", "NEUTRAL": "НЕЙТРАЛЬНО", "NONE": "НЕЙТРАЛЬНО"}
    if raw in mapping:
        return mapping[raw]

    if calc_long_score(payload) >= calc_short_score(payload) + 0.12:
        return "ЛОНГ"
    if calc_short_score(payload) >= calc_long_score(payload) + 0.12:
        return "ШОРТ"
    return "НЕЙТРАЛЬНО"


def _decision_action_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    decision = _decision(data)
    text = _text(decision.get("action_text"))
    if text:
        return text

    raw = _text(decision.get("action")).upper()
    mapping = {
        "ENTER": "ВХОДИТЬ",
        "ENTER_LONG": "ВХОДИТЬ",
        "ENTER_SHORT": "ВХОДИТЬ",
        "WATCH": "СМОТРЕТЬ СЕТАП",
        "WAIT": "ЖДАТЬ",
        "WAIT_CONFIRMATION": "ЖДАТЬ ПОДТВЕРЖДЕНИЕ",
        "WAIT_PULLBACK": "ЖДАТЬ",
        "WAIT_RANGE_EDGE": "ЖДАТЬ",
        "NO_TRADE": "ЖДАТЬ",
    }
    if raw in mapping:
        return mapping[raw]

    direction = _decision_direction_text(data)
    if direction == "НЕЙТРАЛЬНО":
        return "ЖДАТЬ"
    return "СМОТРЕТЬ СЕТАП"


def _decision_mode(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    decision = _decision(data)
    text = _text(decision.get("mode") or decision.get("regime"))
    return text if text else "MIXED"


def _decision_risk(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    decision = _decision(data)
    text = _text(decision.get("risk_level") or decision.get("risk"))
    return text if text else "HIGH"




def _effective_trade_confidence(decision: Dict[str, Any]) -> float:
    final_conf = to_float(decision.get('final_confidence'))
    if final_conf is not None:
        if final_conf <= 1.0:
            final_conf *= 100.0
        return max(0.0, min(float(final_conf), 100.0))

    bias_conf = to_float(decision.get('bias_confidence'))
    if bias_conf is None:
        bias_conf = to_float(decision.get('confidence_pct'))
    if bias_conf is None:
        bias_conf = to_float(decision.get('confidence'))
    bias_conf = float(bias_conf or 0.0)
    if bias_conf <= 1.0:
        bias_conf *= 100.0

    exec_conf = to_float(decision.get('execution_confidence'))
    exec_conf = float(exec_conf or 0.0)
    if exec_conf <= 1.0 and exec_conf > 0.0:
        exec_conf *= 100.0

    setup_conf = to_float(decision.get('setup_readiness'))
    setup_conf = float(setup_conf or 0.0)
    if setup_conf <= 1.0 and setup_conf > 0.0:
        setup_conf *= 100.0

    edge = to_float(decision.get('edge_score'))
    edge = float(edge or 0.0)
    if edge <= 1.0 and edge > 0.0:
        edge *= 100.0

    trade_authorized = bool(decision.get('trade_authorized'))
    action = str(decision.get('action') or decision.get('action_text') or '').upper()
    edge_label = str(decision.get('edge_label') or '').upper()

    candidates = [x for x in [bias_conf, exec_conf, setup_conf, edge] if x > 0.0]
    if candidates:
        effective = min(candidates)
    else:
        effective = bias_conf

    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else (payload.get('execution_verdict') if isinstance(payload.get('execution_verdict'), dict) else {})
    soft_allowed = bool(verdict.get('soft_allowed')) or bool(decision.get('bot_authorized'))
    effective_edge = max(edge, to_float(verdict.get('trade_edge_score')) or 0.0, to_float(verdict.get('bot_edge_score')) or 0.0)
    if (not trade_authorized and not soft_allowed) or (edge_label == 'NO_EDGE' and effective_edge <= 0.0) or action in {'WAIT', 'WAIT_CONFIRMATION', 'ЖДАТЬ'}:
        effective = min(effective if effective > 0.0 else bias_conf, 39.0)

    return max(0.0, min(float(effective), 100.0))
def _decision_confidence_pct(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> float:
    decision = _decision(data)
    effective = _effective_trade_confidence(decision)
    if effective > 0.0:
        return effective

    pct = to_float(decision.get("confidence_pct"))
    if pct is not None:
        if pct <= 1.0:
            pct *= 100.0
        return max(0.0, min(float(pct), 100.0))

    conf = to_float(decision.get("confidence"))
    if conf is not None:
        if conf <= 1.0:
            conf *= 100.0
        return max(0.0, min(float(conf), 100.0))

    payload = _to_data_dict(data)
    return max(calc_long_score(payload), calc_short_score(payload)) * 100.0


def _decision_summary(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    decision = _decision(data)
    summary = _text(decision.get("summary"))
    if summary:
        return summary

    direction = _decision_direction_text(data)
    action = _decision_action_text(data)

    if direction == "НЕЙТРАЛЬНО":
        return "Сейчас лучше без сделки: рынок не даёт чистого перевеса."
    if action == "ВХОДИТЬ":
        return f"Сейчас приоритетный сценарий — {direction.lower()}."
    if action == "СМОТРЕТЬ СЕТАП":
        return f"Приоритет в сторону {direction.lower()}, но нужен более аккуратный триггер."
    return f"Идея в сторону {direction.lower()} есть, но прямо сейчас лучше не спешить."


def _range_position_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    decision = _decision(data)
    zone = _text(decision.get("range_position_zone"))
    if zone:
        return zone

    payload = _to_data_dict(data)
    price = to_float(payload.get("price"))
    low = to_float(payload.get("range_low"))
    mid = to_float(payload.get("range_mid"))
    high = to_float(payload.get("range_high"))

    if price is None or low is None or high is None or high <= low:
        return "позиция в диапазоне не определена"

    band = max(high - low, 1e-9)
    ratio = (price - low) / band

    if ratio <= 0.18:
        return "цена около низа диапазона"
    if ratio <= 0.35:
        return "цена в нижней части диапазона"
    if ratio >= 0.82:
        return "цена около верха диапазона"
    if ratio >= 0.65:
        return "цена в верхней части диапазона"
    if mid is not None and abs(price - mid) / band <= 0.08:
        return "цена около середины диапазона"
    return "цена в центральной части диапазона"


def _long_plan_levels(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> Tuple[str, str, str]:
    payload = _to_data_dict(data)
    price = to_float(payload.get("price"))
    low = to_float(payload.get("range_low"))
    mid = to_float(payload.get("range_mid"))
    high = to_float(payload.get("range_high"))

    if low is not None and mid is not None:
        entry_zone = f"{fmt_price(low)} - {fmt_price(mid)}"
    elif price is not None:
        entry_zone = f"около {fmt_price(price)} после отката"
    else:
        entry_zone = "от поддержки после подтверждения"

    if low is not None:
        invalidation = f"ниже {fmt_price(low)}"
    elif price is not None:
        invalidation = f"ниже {fmt_price(price * 0.995)}"
    else:
        invalidation = "ниже ближайшей поддержки"

    if high is not None:
        target = fmt_price(high)
    elif price is not None:
        target = fmt_price(price * 1.01)
    else:
        target = "по ближайшему сопротивлению"

    return entry_zone, invalidation, target


def _short_plan_levels(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> Tuple[str, str, str]:
    payload = _to_data_dict(data)
    price = to_float(payload.get("price"))
    low = to_float(payload.get("range_low"))
    mid = to_float(payload.get("range_mid"))
    high = to_float(payload.get("range_high"))

    if mid is not None and high is not None:
        entry_zone = f"{fmt_price(mid)} - {fmt_price(high)}"
    elif price is not None:
        entry_zone = f"около {fmt_price(price)} после отката"
    else:
        entry_zone = "от сопротивления после подтверждения"

    if high is not None:
        invalidation = f"выше {fmt_price(high)}"
    elif price is not None:
        invalidation = f"выше {fmt_price(price * 1.005)}"
    else:
        invalidation = "выше ближайшего сопротивления"

    if low is not None:
        target = fmt_price(low)
    elif price is not None:
        target = fmt_price(price * 0.99)
    else:
        target = "по ближайшей поддержке"

    return entry_zone, invalidation, target


def _decision_compare_lines(data: Union[AnalysisSnapshot, Dict[str, Any]], journal: Optional[Dict[str, Any]]) -> list[str]:
    journal = journal or {}
    if not journal.get("has_active_trade") or not journal.get("decision_snapshot"):
        return []

    decision_now = _decision(data)
    decision_entry = journal.get("decision_snapshot") or {}

    now_direction = decision_now.get("direction_text") or decision_now.get("direction") or "нет"
    now_action = decision_now.get("action_text") or decision_now.get("action") or "нет"
    now_mode = decision_now.get("mode") or decision_now.get("regime") or "нет"
    now_risk = decision_now.get("risk_level") or decision_now.get("risk") or "нет"
    now_conf = round(to_float(decision_now.get("confidence_pct")) or 0.0, 1)

    entry_direction = decision_entry.get("direction_text") or decision_entry.get("direction") or "нет"
    entry_action = decision_entry.get("action_text") or decision_entry.get("action") or "нет"
    entry_mode = decision_entry.get("mode") or "нет"
    entry_risk = decision_entry.get("risk_level") or "нет"
    entry_conf = round(to_float(decision_entry.get("confidence_pct")) or 0.0, 1)

    changes = []
    if now_direction != entry_direction:
        changes.append(f"• направление изменилось: было {entry_direction}, сейчас {now_direction}")
    else:
        changes.append(f"• направление сохранилось: {now_direction}")

    if now_action != entry_action:
        changes.append(f"• действие изменилось: было {entry_action}, сейчас {now_action}")
    else:
        changes.append(f"• действие без смены: {now_action}")

    if now_mode != entry_mode:
        changes.append(f"• режим изменился: был {entry_mode}, сейчас {now_mode}")

    if now_risk != entry_risk:
        changes.append(f"• риск изменился: был {entry_risk}, сейчас {now_risk}")

    if abs(now_conf - entry_conf) >= 5:
        if now_conf > entry_conf:
            changes.append(f"• confidence вырос: было {entry_conf}%, сейчас {now_conf}%")
        else:
            changes.append(f"• confidence снизился: было {entry_conf}%, сейчас {now_conf}%")

    return [
        "",
        "Сравнение с точкой входа:",
        f"• entry direction: {entry_direction}",
        f"• now direction: {now_direction}",
        f"• entry action: {entry_action}",
        f"• now action: {now_action}",
        f"• entry mode: {entry_mode}",
        f"• now mode: {now_mode}",
        f"• entry risk: {entry_risk}",
        f"• now risk: {now_risk}",
        f"• entry confidence: {entry_conf}%",
        f"• now confidence: {now_conf}%",
        "",
        "Что изменилось:",
        *changes,
    ]



def _edge_score_lines(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> list[str]:
    payload = _to_data_dict(data)
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    edge_score = to_float(payload.get("edge_score"), to_float(decision.get("edge_score"), 0.0))
    edge_label = str(payload.get("edge_label") or decision.get("edge_label") or "NO_EDGE").upper()
    edge_action = str(payload.get("edge_action") or decision.get("edge_action") or "WAIT").upper()
    edge_side = normalize_direction(payload.get("edge_side") or decision.get("edge_side")) or _decision_direction_text(data)
    execution = str(decision.get("execution") or payload.get("execution") or "").upper()
    final_action = str(decision.get("action") or "").upper()
    if execution == "PROBE_ALLOWED" or final_action in {"ENTER", "ВХОДИТЬ", "PROBE"}:
        edge_score = max(edge_score, 35.0)
        if edge_label == "NO_EDGE":
            edge_label = "WORKABLE"
        if edge_action in {"WAIT", "WAIT_CONFIRMATION"}:
            edge_action = "ALLOW_ENTRY"
    label_map = {
        "NO_EDGE": "нет edge",
        "WEAK": "слабый edge",
        "WORKABLE": "рабочий edge",
        "STRONG": "сильный edge",
    }
    action_map = {
        "WAIT": "ждать",
        "WAIT_CONFIRMATION": "ждать подтверждение",
        "WAIT_RANGE_EDGE": "ждать край диапазона",
        "ALLOW_ENTRY": "можно искать вход",
        "READY": "готово к исполнению",
    }
    lines = [
        "EDGE SCORE:",
        f"• score: {edge_score:.1f}%",
        f"• label: {edge_label} / {label_map.get(edge_label, edge_label.lower())}",
        f"• side: {edge_side}",
        f"• action: {action_map.get(edge_action, edge_action)}",
    ]
    components = payload.get("edge_components") or {}
    if isinstance(components, dict):
        for key, label in (("delta_score", "delta"), ("confidence", "confidence"), ("location", "location"), ("impulse", "impulse"), ("alignment", "alignment"), ("penalty", "penalty")):
            if components.get(key) is None:
                continue
            try:
                value = float(components.get(key) or 0.0)
            except Exception:
                continue
            sign = "+" if value > 0 else ""
            lines.append(f"• {label}: {sign}{value:.1f}")
    return lines

def build_btc_summary_text(data: Union[AnalysisSnapshot, Dict[str, Any]], journal: Optional[Dict[str, Any]] = None) -> str:
    payload = _to_data_dict(data)
    timeframe = payload.get("timeframe", "1h")
    return build_ultra_wait_block(f"📘 BTC SUMMARY [{timeframe}]", payload)
    decision_direction = _decision_direction_text(data)
    decision_action = _decision_action_text(data)
    decision_mode = _decision_mode(data)
    decision_risk = _decision_risk(data)
    decision_conf = _decision_confidence_pct(data)
    summary = _decision_summary(data)

    lines = [
        f"📘 BTC SUMMARY [{timeframe}]",
        "",
        f"Цена: {fmt_price(payload.get('price')) if to_float(payload.get('price')) not in (0.0, None) else 'нет данных'}",
        "",
        "Итог сверху вниз:",
        f"• направление: {decision_direction}",
        f"• действие: {decision_action}",
        f"• режим: {decision_mode}",
        f"• риск: {decision_risk}",
        f"• confidence: {decision_conf:.1f}%",
        "",
        *_edge_score_lines(data),
        "",
        f"Коротко: {summary}",
        "",
        "Нижний слой контекста:",
        f"• signal: {payload.get('signal') or decision_direction}",
        f"• final_decision: {decision_direction}",
        f"• forecast: {payload.get('forecast_direction') or decision_direction} ({fmt_pct(payload.get('forecast_confidence_effective') or min(to_float(payload.get('forecast_confidence') or decision_conf) or decision_conf, max(decision_conf, 35.0)))})",
        f"• range_state: {payload.get('range_state') or 'нет данных'}",
        f"• range_position: {_range_position_text(data)}",
        f"• ct_now: {payload.get('ct_now') or 'нет данных'}",
        f"• ginarea: {payload.get('ginarea_advice') or 'нет данных'}",
        "",
        f"Long score: {fmt_pct(calc_long_score(data))}",
        f"Short score: {fmt_pct(calc_short_score(data))}",
        f"Bias layer: {forecast_bias_label(data)}",
    ]

    learning_forecast = payload.get('learning_forecast_adjustment') or {}
    if isinstance(learning_forecast, dict) and (learning_forecast.get('summary') or abs(float(learning_forecast.get('delta') or 0.0)) >= 0.005):
        delta_pct = float(learning_forecast.get('delta') or 0.0) * 100.0
        sign = '+' if delta_pct >= 0 else ''
        lines.extend([
            '',
            'LEARNING-AWARE FORECAST:',
            f"• влияние обучения: {sign}{delta_pct:.1f}%",
            f"• бот-контекст: {learning_forecast.get('bot_label') or 'нет данных'}",
            f"• вывод: {learning_forecast.get('summary') or 'нет данных'}",
        ])

    reasons = (_decision(data).get("reasons") or [])[:4]
    if reasons:
        lines.extend(["", "Почему:"])
        lines.extend([f"• {x}" for x in reasons])

    lines.extend(_decision_compare_lines(data, journal))
    return "\n".join(lines)


def _synced_forecast_strength(direction: str, confidence: float, raw_strength: str) -> str:
    strength = str(raw_strength or "NEUTRAL").upper()
    conf = to_float(confidence) or 0.0
    if conf <= 1.0:
        conf *= 100.0
    direction = normalize_direction(direction)
    if direction == "НЕЙТРАЛЬНО":
        return "NEUTRAL"
    if conf >= 70.0:
        return "STRONG"
    if conf >= 52.0:
        return "MODERATE"
    if conf >= 35.0:
        return "WEAK"
    return strength if strength in {"STRONG", "MODERATE", "WEAK", "NEUTRAL"} else "NEUTRAL"


def build_btc_forecast_text(data: Union[AnalysisSnapshot, Dict[str, Any]], journal: Optional[Dict[str, Any]] = None) -> str:
    payload = _to_data_dict(data)
    timeframe = payload.get("timeframe", "1h")
    return build_ultra_wait_block(f"🔮 BTC FORECAST [{timeframe}]", payload)
    direction = _decision_direction_text(data)
    action = _decision_action_text(data)
    mode = _decision_mode(data)
    risk = _decision_risk(data)
    conf = _decision_confidence_pct(data)

    forecast_direction = normalize_direction(payload.get("forecast_direction")) or direction
    forecast_conf_effective = payload.get("forecast_confidence_effective") or min(to_float(payload.get("forecast_confidence") or conf) or conf, max(conf, 35.0))
    forecast_strength = _synced_forecast_strength(forecast_direction, forecast_conf_effective, payload.get("forecast_strength") or _decision(data).get("forecast_strength") or 'NEUTRAL')
    raw_forecast_conf = fmt_pct(forecast_conf_effective)
    summary = _decision_summary(data)

    if direction == "НЕЙТРАЛЬНО":
        base = "Сейчас лучше ждать: рынок не даёт чистого сценария вверх или вниз."
    elif direction == "ЛОНГ":
        if action == "ВХОДИТЬ":
            base = "Базовый прогноз сейчас смещён вверх."
        elif action == "СМОТРЕТЬ СЕТАП":
            base = "Прогноз умеренно смотрит вверх, но нужен аккуратный триггер."
        else:
            base = "Идея вверх есть, но момент пока не идеальный."
    else:
        if action == "ВХОДИТЬ":
            base = "Базовый прогноз сейчас смещён вниз."
        elif action == "СМОТРЕТЬ СЕТАП":
            base = "Прогноз умеренно смотрит вниз, но нужен аккуратный триггер."
        else:
            base = "Идея вниз есть, но момент пока не идеальный."

    pattern_dir = normalize_direction(payload.get("pattern_forecast_direction") or payload.get("history_pattern_direction"))
    pattern_conf = fmt_pct(payload.get("pattern_forecast_confidence") or payload.get("history_pattern_confidence") or 0.0)
    pattern_move = payload.get("pattern_forecast_move") or ""
    pattern_regime = payload.get("pattern_forecast_regime") or ""
    pattern_style = payload.get("pattern_forecast_style") or ""
    pattern_summary = payload.get("history_pattern_summary") or ""
    pattern_years = payload.get("pattern_years") or []
    pattern_scope = payload.get("pattern_scope") or "recent_multi_cycle"
    pattern_years_text = ", ".join(str(x) for x in pattern_years) if pattern_years else "2025"

    lines = [
        f"🔮 BTC FORECAST [{timeframe}]",
        "",
        f"Главный forecast слой: {direction}",
        f"Действие: {action}",
        f"Режим рынка: {mode}",
        f"Риск: {risk}",
        f"Decision confidence: {conf:.1f}%",
        f"Market regime: {payload.get('market_regime') or 'нет данных'}",
        f"Market regime bias: {normalize_direction(payload.get('market_regime_bias'))}",
        "",
        f"Прогноз: {base}",
        f"Коротко: {summary}",
        f"Bias layer: {forecast_bias_label(data)}",
    ]

    learning_forecast = payload.get('learning_forecast_adjustment') or {}
    if isinstance(learning_forecast, dict) and (learning_forecast.get('summary') or abs(float(learning_forecast.get('delta') or 0.0)) >= 0.005):
        delta_pct = float(learning_forecast.get('delta') or 0.0) * 100.0
        sign = '+' if delta_pct >= 0 else ''
        lines.extend([
            '',
            'LEARNING-AWARE FORECAST:',
            f"• влияние обучения: {sign}{delta_pct:.1f}%",
            f"• бот-контекст: {learning_forecast.get('bot_label') or 'нет данных'}",
            f"• вывод: {learning_forecast.get('summary') or 'нет данных'}",
        ])

    if pattern_dir and pattern_dir != "НЕЙТРАЛЬНО":
        lines.extend([
            "",
            f"PATTERN FORECAST EXTENDED ({pattern_years_text}):",
            f"• направление по историческим паттернам: {pattern_dir}",
            f"• confidence: {pattern_conf}",
            f"• режим памяти: {pattern_scope}",
        ])
        if pattern_regime:
            lines.append(f"• похожий режим: {pattern_regime}")
        if pattern_style:
            lines.append(f"• тип движения: {pattern_style}")
        if pattern_move:
            lines.append(f"• ожидаемый ход: {pattern_move}")
        if pattern_summary:
            lines.append(f"• вывод: {pattern_summary}")
    elif pattern_summary:
        lines.extend([
            "",
            f"PATTERN FORECAST EXTENDED ({pattern_years_text}):",
            f"• направление по историческим паттернам: {pattern_dir or 'НЕЙТРАЛЬНО'}",
            f"• confidence: {pattern_conf}",
            f"• режим памяти: {pattern_scope}",
            f"• вывод: {pattern_summary}",
        ])

    learning_forecast = payload.get('learning_forecast_adjustment') or {}
    if isinstance(learning_forecast, dict) and (learning_forecast.get('summary') or abs(float(learning_forecast.get('delta') or 0.0)) >= 0.005):
        delta_pct = float(learning_forecast.get('delta') or 0.0) * 100.0
        sign = '+' if delta_pct >= 0 else ''
        lines.extend([
            '',
            'LEARNING-AWARE FORECAST:',
            f"• влияние обучения: {sign}{delta_pct:.1f}%",
            f"• бот-контекст: {learning_forecast.get('bot_label') or 'нет данных'}",
            f"• вывод: {learning_forecast.get('summary') or 'нет данных'}",
        ])
        for reason in (learning_forecast.get('reasons') or [])[:2]:
            lines.append(f"• {reason}")

    lines.extend([
        "",
        "Под капотом:",
        f"• raw forecast_direction: {forecast_direction or 'нет данных'}",
        f"• raw forecast_strength: {forecast_strength}",
        f"• raw forecast_confidence: {raw_forecast_conf}",
        f"• signal: {payload.get('signal') or direction}",
        f"• final_decision: {payload.get('final_decision') or direction}",
        f"• range_state: {payload.get('range_state') or 'нет данных'}",
        f"• ct_now: {payload.get('ct_now') or 'нет данных'}",
        f"• ginarea: {payload.get('ginarea_advice') or 'нет данных'}",
    ])

    mode_reasons = (_decision(data).get("mode_reasons") or [])[:3]
    if mode_reasons:
        lines.extend(["", "Почему такой режим:"])
        lines.extend([f"• {x}" for x in mode_reasons])

    lines.extend(_decision_compare_lines(data, journal))
    return "\n".join(lines)


def build_btc_ginarea_text(data: Union[AnalysisSnapshot, Dict[str, Any]]) -> str:
    payload = _to_data_dict(data)
    timeframe = payload.get("timeframe", "1h")
    direction = _decision_direction_text(data)
    action = _decision_action_text(data)
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    decision = analysis.get("decision") if isinstance(analysis.get("decision"), dict) else (payload.get("decision") if isinstance(payload.get("decision"), dict) else {})

    ginarea_advice = analysis.get("ginarea_advice") or payload.get("ginarea_advice") or "нет данных"
    unified_advice = analysis.get("unified_advice") or ginarea_advice
    best_bot_label = analysis.get("best_bot_label") or analysis.get("preferred_bot") or "нет данных"
    best_bot_status = analysis.get("best_bot_status") or "OFF"
    best_bot_score = analysis.get("best_bot_score")
    best_bot_ranking_score = analysis.get("best_bot_ranking_score")
    trade_style = analysis.get("trade_style") or "wait"
    hold_bias = analysis.get("hold_bias") or "none"
    execution_bias = analysis.get("execution_bias") or "WAIT"
    scalp_bot_label = analysis.get("scalp_bot_label")
    intraday_bot_label = analysis.get("intraday_bot_label")
    avoid_bot_label = analysis.get("avoid_bot_label") or "нет данных"
    avoid_bot_reason = analysis.get("avoid_bot_reason") or "нет данных"
    matrix_summary = analysis.get("matrix_summary") or []
    recommended_sequence = analysis.get("recommended_sequence") or []
    management_summary = analysis.get("management_summary") or []
    range_management = analysis.get("range_management") or []
    ct_management = analysis.get("ct_management") or []
    custom_bot_labels = analysis.get("custom_bot_labels") or {}
    dangerous_bots = analysis.get("dangerous_bots") or []
    state_summary = analysis.get("state_summary") or []
    active_bots_now = analysis.get("active_bots_now") or []
    manual_summary = analysis.get("manual_summary") or []
    personal_learning = analysis.get("personal_learning") or {}
    learning_weighted_bots = analysis.get("learning_weighted_bots") or []
    learning_overview = personal_learning.get("learning_overview") or []
    learning_cards = personal_learning.get("learning_cards") or []
    learning_execution_weighted = personal_learning.get("execution_weighted_bots") or []
    learning_execution_summary = analysis.get("learning_execution_summary") or []
    learning_ranking_summary = analysis.get("learning_ranking_summary") or []
    best_historic_bot = personal_learning.get("best_historic_bot")
    learning_ready = bool(personal_learning.get("learning_ready"))
    reentry_zone = analysis.get("reentry_zone") or "нет данных"
    invalidation_hint = analysis.get("invalidation_hint") or "нет данных"
    tactical_plan = analysis.get("tactical_plan") or []
    bot_cards = analysis.get("bot_cards") or []
    deviation_ladder = analysis.get("deviation_ladder") or {}
    impulse_base_price = deviation_ladder.get("impulse_base_price")
    impulse_move_pct = deviation_ladder.get("impulse_move_pct")
    ladder_action = deviation_ladder.get("ladder_action") or "нет данных"
    range_bias_action = deviation_ladder.get("range_action") or "нет данных"
    unified_strategy_matrix = analysis.get("unified_strategy_matrix") or []
    overlay_commentary = analysis.get("overlay_commentary") or []
    execution_priority = analysis.get("execution_priority") or []
    primary_bot = analysis.get("primary_bot")
    secondary_bot = analysis.get("secondary_bot")
    primary_size_pct = analysis.get("primary_size_pct") or 0
    secondary_size_pct = analysis.get("secondary_size_pct") or 0
    size_plan = analysis.get("size_plan") or []
    bots_to_reduce = analysis.get("bots_to_reduce") or []
    aggression_mode = analysis.get("aggression_mode") or "WAIT"
    spy_context = analysis.get("spy_context") or {}
    history_pattern_direction = analysis.get("history_pattern_direction") or "NEUTRAL"
    history_pattern_confidence = analysis.get("history_pattern_confidence") or 0.0
    setup_req = _setup_requirements(payload)
    arming = _arming_logic(payload)
    volume_range = _volume_range_bot_conditions(payload)

    decision_exec = str((decision or {}).get('execution') or '').upper()
    decision_action = str((decision or {}).get('action') or '').upper()
    soft_probe_allowed = decision_exec == 'PROBE_ALLOWED' or decision_action in {'ENTER','ВХОДИТЬ','PROBE'}
    no_trade_lock = (str((volume_range or {}).get('status') or '').upper() == 'WATCH_ONLY') and (not soft_probe_allowed)
    strong_candidates = [] if no_trade_lock else [c for c in bot_cards if str(c.get("activation_state") or c.get("status") or "").upper() == "ARMED"]
    soft_candidates = [] if no_trade_lock else [c for c in bot_cards if str(c.get("activation_state") or c.get("status") or "").upper() == "SOFT_READY"]
    watchlist_candidates = [c for c in bot_cards if str(c.get("activation_state") or c.get("status") or "").upper() in {"SOFT_READY", "WATCH"}]
    range_watchlist = [c for c in bot_cards if str(c.get("bot_key") or "").startswith("range")]
    strong_label = (strong_candidates[0].get("bot_label") if strong_candidates else "нет")
    if soft_candidates:
        soft_label = strong_candidates[0].get("bot_label") if False else soft_candidates[0].get("bot_label")
    elif (not no_trade_lock) and str(volume_range.get("status")) in {"READY_SMALL", "READY_SMALL_REDUCED"}:
        soft_label = (range_watchlist[0].get("bot_label") if range_watchlist else "RANGE LONG бот")
    else:
        soft_label = "нет"
    if watchlist_candidates:
        watchlist_label = ", ".join([str(c.get("bot_label") or "") for c in watchlist_candidates[:2] if c.get("bot_label")]) or "нет"
    elif (not no_trade_lock) and str(volume_range.get("status")) in {"READY_SMALL", "READY_SMALL_REDUCED"} and range_watchlist:
        watchlist_label = ", ".join([str(c.get("bot_label") or "") for c in range_watchlist[:2] if c.get("bot_label")]) or "нет"
    else:
        watchlist_label = "нет"
    display_status = best_bot_status
    if str(volume_range.get("status")) == "READY_SMALL_REDUCED":
        display_status = "REDUCED_ONLY"
    elif str(volume_range.get("status")) == "READY_SMALL":
        display_status = "SOFT_READY"
    elif display_status == "OFF" and watchlist_candidates:
        display_status = "WATCHLIST"

    verdict = decision.get('execution_verdict') if isinstance(decision.get('execution_verdict'), dict) else (payload.get('execution_verdict') if isinstance(payload.get('execution_verdict'), dict) else {})
    compact_edge = max(_as_float((payload.get('edge_score') if isinstance(payload, dict) else None) or 0.0), _as_float(verdict.get('trade_edge_score') or 0.0), _as_float(verdict.get('bot_edge_score') or 0.0))
    compact_soft = bool(verdict.get('soft_allowed')) or bool(decision.get('bot_authorized'))
    compact_off_mode = no_trade_lock or ((str(display_status).upper() in {'OFF', 'WATCHLIST', 'WATCH_ONLY'}) and (compact_edge <= 0.0) and (not compact_soft))
    if compact_off_mode:
        compact_lines = [
            f"🧩 BTC GINAREA [{timeframe}]",
            "",
            f"Верхний вывод decision: {direction}",
            f"Текущее действие: {action}",
            "",
            *_edge_score_lines(data),
            "",
            "КРАТКО ПО БОТАМ:",
            f"• статус: {display_status}",
            "• strong: нет",
            "• soft: нет",
            "• reason: нет edge / нет confirm",
            "• trigger: ложный вынос / reclaim у края диапазона",
            f"• range hint: {volume_range.get('launch_hint')}",
            f"• blockers: {'; '.join((volume_range.get('blockers') or arming.get('blockers') or ['нет чистого импульса'])[:3])}",
        ]
        text = "\n".join(compact_lines)
        try:
            return text
        except Exception:
            return text

    lines = [
        f"🧩 BTC GINAREA [{timeframe}]",
        "",
        f"Верхний вывод decision: {direction}",
        f"Текущее действие: {action}",
        "",
        *_edge_score_lines(data),
        "",
        f"GINAREA advice: {ginarea_advice}",
        f"CT NOW: {payload.get('ct_now') or analysis.get('ct_now') or 'нет данных'}",
        f"Range state: {payload.get('range_state') or analysis.get('range_state') or 'нет данных'}",
        f"Позиция в диапазоне: {_range_position_text(data)}",
        "",
        "Ключевой вывод по твоим ботам:",
        f"• сильный кандидат: {'нет' if no_trade_lock else strong_label}",
        f"• мягкий кандидат: {'нет' if no_trade_lock else soft_label}",
        f"• watchlist: {watchlist_label}",
        f"• статус: {display_status}",
        f"• confidence: {float(best_bot_score) * 100:.1f}%" if best_bot_score is not None else "• confidence: нет данных",
        f"• ranking score: {float(best_bot_ranking_score) * 100:.1f}%" if best_bot_ranking_score is not None else "• ranking score: нет данных",
        f"• стиль: {trade_style}",
        f"• режим по твоим ботам сейчас: {execution_bias}",
        f"• перекос удержания: {hold_bias}",
        f"• зона re-entry: {reentry_zone}",
        f"• отмена идеи: {invalidation_hint}",
    ]

    if impulse_base_price:
        lines.extend([
            "",
            "IMPULSE LADDER 60m:",
            f"• база импульса 60m: {float(impulse_base_price):.2f}",
            f"• импульс от базы: {float(impulse_move_pct or 0.0):+.2f}%",
            f"• действие по лесенке: {ladder_action}",
            f"• работа range-блоком: {range_bias_action}",
        ])
        long_ladder = deviation_ladder.get("long_ladder") or []
        short_ladder = deviation_ladder.get("short_ladder") or []
        if long_ladder:
            lines.append("• LONG deviation-боты:")
            for item in long_ladder:
                suffix = " | агрессивнее" if item.get("aggressive") else ""
                lines.append(f"  - {item.get('label')}: {item.get('status')}{suffix}")
        if short_ladder:
            lines.append("• SHORT deviation-боты:")
            for item in short_ladder:
                suffix = " | агрессивнее" if item.get("aggressive") else ""
                lines.append(f"  - {item.get('label')}: {item.get('status')}{suffix}")

    if unified_strategy_matrix:
        lines.extend(["", "UNIFIED BOT MATRIX:"])
        for item in unified_strategy_matrix[:8]:
            size_label = str(item.get('size_label') or '').strip()
            suffix = f" | {size_label}" if size_label else ""
            activation = str(item.get('activation_state') or item.get('status') or 'OFF').upper()
            action_label = str(item.get('action') or 'OFF')
            if activation == 'BLOCKED' and action_label == 'WAIT_CONFIRM':
                action_label = 'WAIT_CONFIRM / BLOCKED'
            lines.append(f"• {item.get('label')}: {activation} | {action_label}{suffix}")
            comment = str(item.get('comment') or '').strip()
            if comment:
                lines.append(f"  - {comment}")

    if overlay_commentary:
        lines.extend(["", "OVERLAY COMMENTS:"])
        for item in overlay_commentary[:6]:
            lines.append(f"• {item}")

    if primary_bot or size_plan:
        lines.extend(["", "SIZE PLAN:"])
        if primary_bot:
            lines.append(f"• PRIMARY BOT: {primary_bot} | {int(primary_size_pct)}%")
        if secondary_bot:
            lines.append(f"• SECONDARY BOT: {secondary_bot} | {int(secondary_size_pct)}%")
        lines.append(f"• AGGRESSION MODE: {aggression_mode}")
        for item in size_plan[:4]:
            lines.append(f"• {item}")
        for item in bots_to_reduce[:3]:
            lines.append(f"• ослабить: {item}")

    if spy_context:
        lines.extend(["", "S&P 500 FILTER:"])
        if spy_context.get("available"):
            lines.append(f"• bias: {spy_context.get('bias')}")
            lines.append(f"• 1d: {float(spy_context.get('ret1_pct') or 0.0):+.2f}%")
            lines.append(f"• 5d: {float(spy_context.get('ret5_pct') or 0.0):+.2f}%")
        lines.append(f"• комментарий: {spy_context.get('comment') or 'нет данных'}")
        lines.append(f"• pattern-memory: {history_pattern_direction} / {float(history_pattern_confidence or 0.0) * 100:.1f}%")

    lines.extend(["", "SETUP REQUIREMENTS:"])
    for item in setup_req.get("items")[:5]:
        lines.append(f"• {item}")

    lines.extend(["", "ARMING LOGIC:"])
    lines.append(f"• status: {arming.get('status')}")
    lines.append(f"• total readiness: {arming.get('total')}%")
    lines.append(f"• location ready: {arming.get('location_ready')}%")
    lines.append(f"• regime ready: {arming.get('regime_ready')}%")
    lines.append(f"• reversal ready: {arming.get('reversal_ready')}%")
    lines.append(f"• confirmation ready: {arming.get('confirm_ready')}%")
    if arming.get("blockers"):
        lines.append("• blockers: " + "; ".join(arming.get("blockers")[:3]))

    edge_now = _as_float((payload.get('edge_score') if isinstance(payload, dict) else None) or (analysis.get('edge_score') if isinstance(analysis, dict) else None) or 0.0)
    vr_status = str(volume_range.get('status') or '')
    soft_range_allowed = vr_status in {'READY_SMALL', 'READY_SMALL_REDUCED'}
    range_now_text = 'prepare only / ждать подтверждение' if edge_now <= 0.0 or action == 'ЖДАТЬ' else ('можно стартовать range small' if soft_range_allowed else 'ждать')
    move_lines = _move_type_block(payload, decision)
    if move_lines:
        lines.extend([""] + move_lines)
    fake_lines = _fake_move_block(payload, decision)
    if fake_lines:
        lines.extend([""] + fake_lines)
    lines.extend(["", "⚡ ACTIONABLE RANGE PLAN:"])
    lines.append(f"• now: {range_now_text}")
    lines.append(f"• size mode: x{float(volume_range.get('size_multiplier') or 1.0):.2f}")
    lines.append(f"• adds: {'только после повторного удержания' if str(volume_range.get('add_status')) == 'READY_ADD' and edge_now > 0.0 and action != 'ЖДАТЬ' else 'пока без adds'}")
    lines.extend(["", "RANGE VOLUME BOT CONDITIONS:"])
    lines.append(f"• status: {volume_range.get('status')}")
    lines.append(f"• deviation from base: {float(volume_range.get('deviation_pct') or 0.0):.2f}%")
    lines.append(f"• launch hint: {volume_range.get('launch_hint')}")
    lines.append(f"• range detected: {volume_range.get('range_detected')}")
    lines.append(f"• location state: {volume_range.get('location_state')}")
    lines.append(f"• post-impulse fade: {volume_range.get('post_impulse_fade')}")
    lines.append(f"• breakout risk: {volume_range.get('breakout_risk')}")
    lines.append(f"• size multiplier: x{float(volume_range.get('size_multiplier') or 1.0):.2f}")
    lines.append(f"• rotation quality: {volume_range.get('rotation_quality')}")
    lines.append(f"• add status: {volume_range.get('add_status')}")
    for item in volume_range.get("conditions")[:5]:
        lines.append(f"• {item}")
    if volume_range.get("blockers"):
        lines.append("• blockers: " + "; ".join(volume_range.get("blockers")[:3]))

    if active_bots_now:
        lines.extend(["", "Какие боты уже в работе:"])
        for item in active_bots_now[:4]:
            lines.append(f"• {item}")

    if custom_bot_labels:
        lines.extend(["", "Названия твоих 4 ботов в системе:"])
        for key in ("ct_long", "ct_short", "range_long", "range_short"):
            if custom_bot_labels.get(key):
                lines.append(f"• {key}: {custom_bot_labels.get(key)}")

    bot_control_center = analysis.get("bot_control_center") or {}
    bot_control_assets = bot_control_center.get("assets") if isinstance(bot_control_center, dict) else {}
    bot_control_precision = bot_control_center.get("precision") if isinstance(bot_control_center, dict) else {}

    if bot_cards:
        lines.extend(["", "BOT MATRIX:"])
        for card in bot_cards[:4]:
            activation = str(card.get('activation_state') or card.get('status') or 'OFF').upper()
            if activation == 'READY' and str(card.get('management_action') or '').upper() == 'WAIT_CONFIRM':
                activation = 'BLOCKED'
            lines.append(
                f"• {card.get('bot_label')}: {activation} | score {float(card.get('score') or 0) * 100:.1f}% | зона {card.get('zone')}"
            )
            note = str(card.get("note") or "").strip()
            if note:
                lines.append(f"  - {note}")
            manual_action = str(((card.get("manager_state") or {}).get("manual") or {}).get("action") or "").strip()
            lines.append(f"  - режим: {card.get('plan_state') or 'WAIT'} | ведение: {card.get('management_action') or 'WAIT'}")
            learning_delta = float(card.get("learning_delta") or 0.0)
            if abs(learning_delta) >= 0.01:
                sign = "+" if learning_delta >= 0 else ""
                lines.append(f"  - обучение: {sign}{learning_delta * 100:.1f}%")
            learning_rank_delta = float(card.get("learning_rank_delta") or 0.0)
            if abs(learning_rank_delta) >= 0.01:
                sign = "+" if learning_rank_delta >= 0 else ""
                lines.append(f"  - ranking learning: {sign}{learning_rank_delta * 100:.1f}% | {card.get('learning_rank_summary')}")
            learning_reasons = card.get("learning_reasons") or []
            for reason in learning_reasons[:2]:
                lines.append(f"    · {reason}")
            exec_learning_delta = float(card.get("execution_learning_delta") or 0.0)
            if abs(exec_learning_delta) >= 0.01:
                sign = "+" if exec_learning_delta >= 0 else ""
                lines.append(f"  - execution learning: {sign}{exec_learning_delta * 100:.1f}% | {card.get('execution_learning_summary')}")
            exec_learning_reasons = card.get("execution_learning_reasons") or []
            for reason in exec_learning_reasons[:2]:
                lines.append(f"    · execution: {reason}")
            if manual_action:
                lines.append(f"  - ручное состояние: {manual_action}")
            entry_instruction = str(card.get("entry_instruction") or "").strip()
            if entry_instruction:
                lines.append(f"  - вход: {entry_instruction}")
            exit_instruction = str(card.get("exit_instruction") or "").strip()
            if exit_instruction:
                lines.append(f"  - ведение/выход: {exit_instruction}")
            invalidation = str(card.get("invalidation") or "").strip()
            if invalidation:
                lines.append(f"  - отмена: {invalidation}")


    if bot_control_assets:
        lines.extend(["", "BOT CONTROL PRECISION V7.3:"])
        for asset in ("BTC",):
            payload = bot_control_assets.get(asset) or {}
            precision = bot_control_precision.get(asset) or {}
            long_layers = payload.get("long") or []
            short_layers = payload.get("short") or []
            if precision:
                lines.append(
                    f"• {asset}: side {precision.get('dominant_side')} | risk {precision.get('side_risk')} | new entries {precision.get('top_permission')}"
                )
                if precision.get('top_reason'):
                    lines.append(f"  - причина: {precision.get('top_reason')}")
            if long_layers:
                lines.append(f"• {asset} LONG:")
                for item in long_layers[:3]:
                    lines.append(
                        f"  - {item.get('bot_label')}: {item.get('status')} | {item.get('layer_kind')} | {float(item.get('score') or 0.0) * 100:.1f}% | {item.get('permission')}"
                    )
                    if item.get('reason'):
                        lines.append(f"    причина: {item.get('reason')}")
                    if item.get('entry'):
                        lines.append(f"    вход: {item.get('entry')}")
                    if item.get('zone'):
                        lines.append(f"    зона: {item.get('zone')}")
                    if item.get('invalidation'):
                        lines.append(f"    отмена: {item.get('invalidation')}")
                    if item.get('action') and str(item.get('action')).upper() != 'WAIT':
                        lines.append(f"    ведение: {item.get('action')}")
            if short_layers:
                lines.append(f"• {asset} SHORT:")
                for item in short_layers[:3]:
                    lines.append(
                        f"  - {item.get('bot_label')}: {item.get('status')} | {item.get('layer_kind')} | {float(item.get('score') or 0.0) * 100:.1f}% | {item.get('permission')}"
                    )
                    if item.get('reason'):
                        lines.append(f"    причина: {item.get('reason')}")
                    if item.get('entry'):
                        lines.append(f"    вход: {item.get('entry')}")
                    if item.get('zone'):
                        lines.append(f"    зона: {item.get('zone')}")
                    if item.get('invalidation'):
                        lines.append(f"    отмена: {item.get('invalidation')}")
                    if item.get('action') and str(item.get('action')).upper() != 'WAIT':
                        lines.append(f"    ведение: {item.get('action')}")

    if execution_priority:
        lines.extend(["", "EXECUTION PRIORITY:"])
        for idx, item in enumerate(execution_priority[:4], start=1):
            lines.append(f"• {idx}. {item}")

    if matrix_summary:
        lines.extend(["", "Прикладной вывод по ботам:"])
        for item in matrix_summary[:4]:
            lines.append(f"• {item}")

    if state_summary:
        lines.extend(["", "State-ведение ботов:"])
        for item in state_summary[:6]:
            lines.append(f"• {item}")
        lines.append("• ручные команды: BOT CT LONG SMALL / BOT RANGE SHORT CANCEL / BOTS STATUS")

    if management_summary:
        lines.extend(["", "Ведение ботов сейчас:"])
        for item in management_summary[:6]:
            lines.append(f"• {item}")

    if manual_summary:
        lines.extend(["", "Ручные отметки по ботам:"])
        for item in manual_summary[:6]:
            lines.append(f"• {item}")

    if learning_overview:
        lines.extend(["", "PERSONAL BOT LEARNING:"])
        if learning_weighted_bots:
            lines.append(f"• сейчас обучение сильнее влияет на: {', '.join(learning_weighted_bots[:3])}")
        if learning_execution_weighted:
            lines.append(f"• execution-подсказки сильнее двигаются через: {', '.join(learning_execution_weighted[:3])}")
        if best_historic_bot:
            lines.append(f"• исторически сильнее у тебя выглядит: {best_historic_bot}")
        lines.append(f"• слой обучения готов: {'ДА' if learning_ready else 'НЕТ'}")
        for item in learning_overview[:4]:
            lines.append(f"• {item}")
        for item in learning_execution_summary[:4]:
            lines.append(f"• {item}")
        for item in learning_ranking_summary[:4]:
            lines.append(f"• {item}")
        for card in learning_cards[:4]:
            lines.append(f"  - {card.get('bot_label')}: {card.get('learned_summary')}")

    if range_management:
        lines.extend(["", "Range-блок: включать / добавлять / выходить:"])
        for item in range_management[:4]:
            lines.append(f"• {item}")

    if ct_management:
        lines.extend(["", "Контртренд-блок: размер входа и добавление:"])
        for item in ct_management[:4]:
            lines.append(f"• {item}")

    if scalp_bot_label or intraday_bot_label or avoid_bot_label:
        lines.extend(["", "Практика запуска:"])
        if intraday_bot_label:
            lines.append(f"• для спокойного intraday сейчас лучше смотреть: {intraday_bot_label}")
        if scalp_bot_label:
            if not no_trade_lock:
                lines.append(f"• быстрый scalp смотреть только после confirm: {scalp_bot_label}")
        if avoid_bot_label and avoid_bot_label != "нет данных":
            lines.append(f"• сейчас лучше не форсировать: {avoid_bot_label}")
            lines.append(f"  - причина: {avoid_bot_reason}")

    if recommended_sequence:
        lines.extend(["", "Последовательность действий:"])
        for item in recommended_sequence[:4]:
            lines.append(f"• {item}")

    if dangerous_bots:
        lines.extend(["", "Где опасно:"])
        for item in dangerous_bots[:3]:
            reasons = ", ".join(item.get("reasons") or [])
            lines.append(f"• {item.get('bot_label')}: {reasons or 'повышенный риск'}")

    if tactical_plan:
        lines.extend(["", "Что делать по логике ginarea:"])
        for item in tactical_plan[:5]:
            lines.append(f"• {item}")

    lines.extend(["", "Вывод:"])
    if best_bot_status == "READY":
        lines.append(f"• сейчас есть рабочая идея под бот: {best_bot_label}")
        lines.append("• но вход всё равно лучше брать по подтверждению, а не вслепую")
    elif best_bot_status == "OPEN":
        lines.append(f"• активна уже открытая позиция по боту: {best_bot_label}")
        lines.append("• нового входа нет: только сопровождение / частичная фиксация")
    elif best_bot_status == "WATCH":
        lines.append(f"• сетап для {best_bot_label} собирается, но ещё не добран до ready")
        lines.append("• лучше ждать reclaim / retest / подтверждение на уровне")
    else:
        lines.append("• ни один из ботов пока не имеет чистого edge")
        lines.append("• лучше не форсировать сделку в середине шума")

    lines.append(f"• общий итог: {unified_advice}")
    return "\n".join(lines)

def build_btc_long_plan_text(data: Union[AnalysisSnapshot, Dict[str, Any]], journal: Optional[Dict[str, Any]] = None) -> str:
    payload = _to_data_dict(data)
    timeframe = payload.get("timeframe", "1h")
    direction = _decision_direction_text(data)
    action = _decision_action_text(data)
    mode = _decision_mode(data)
    risk = _decision_risk(data)
    conf = _decision_confidence_pct(data)

    entry_zone, invalidation, target = _long_plan_levels(data)
    long_score = calc_long_score(data)
    short_score = calc_short_score(data)

    if direction != "ЛОНГ":
        verdict = "Лонг-план сейчас не главный сценарий."
    elif action == "ВХОДИТЬ":
        verdict = "Лонг — основной рабочий сценарий."
    elif action == "СМОТРЕТЬ СЕТАП":
        verdict = "Лонг остаётся приоритетом, но вход лучше брать только после подтверждения."
    else:
        verdict = "Идея в лонг есть, но момент сейчас не самый чистый."

    lines = [
        f"🟢 BTC LONG PLAN [{timeframe}]",
        "",
        f"Decision direction: {direction}",
        f"Decision action: {action}",
        f"Mode: {mode}",
        f"Risk: {risk}",
        f"Confidence: {conf:.1f}%",
        "",
        f"Вывод: {verdict}",
        "",
        "План:",
        f"• зона интереса: {entry_zone}",
        f"• первая цель: {target}",
        f"• invalidation: {invalidation}",
        "",
        "Контекст:",
        f"• signal: {payload.get('signal') or direction}",
        f"• forecast: {payload.get('forecast_direction') or direction} ({fmt_pct(payload.get('forecast_confidence_effective') or payload.get('forecast_confidence') or conf)})",
        f"• range_state: {payload.get('range_state') or 'нет данных'}",
        f"• ct_now: {payload.get('ct_now') or 'нет данных'}",
        f"• ginarea: {payload.get('ginarea_advice') or 'нет данных'}",
        "",
        f"Long score: {fmt_pct(long_score)}",
        f"Short score: {fmt_pct(short_score)}",
    ]

    reasons = (_decision(data).get("reasons") or [])[:4]
    if reasons:
        lines.extend(["", "Почему лонг вообще рассматривается:"])
        lines.extend([f"• {x}" for x in reasons])

    lines.extend(_decision_compare_lines(data, journal))
    return "\n".join(lines)


def build_btc_short_plan_text(data: Union[AnalysisSnapshot, Dict[str, Any]], journal: Optional[Dict[str, Any]] = None) -> str:
    payload = _to_data_dict(data)
    timeframe = payload.get("timeframe", "1h")
    direction = _decision_direction_text(data)
    action = _decision_action_text(data)
    mode = _decision_mode(data)
    risk = _decision_risk(data)
    conf = _decision_confidence_pct(data)

    entry_zone, invalidation, target = _short_plan_levels(data)
    long_score = calc_long_score(data)
    short_score = calc_short_score(data)

    if direction != "ШОРТ":
        verdict = "Шорт-план сейчас не главный сценарий."
    elif action == "ВХОДИТЬ":
        verdict = "Шорт — основной рабочий сценарий."
    elif action == "СМОТРЕТЬ СЕТАП":
        verdict = "Шорт остаётся приоритетом, но вход лучше брать только после подтверждения."
    else:
        verdict = "Идея в шорт есть, но момент сейчас не самый чистый."

    lines = [
        f"🔴 BTC SHORT PLAN [{timeframe}]",
        "",
        f"Decision direction: {direction}",
        f"Decision action: {action}",
        f"Mode: {mode}",
        f"Risk: {risk}",
        f"Confidence: {conf:.1f}%",
        "",
        f"Вывод: {verdict}",
        "",
        "План:",
        f"• зона интереса: {entry_zone}",
        f"• первая цель: {target}",
        f"• invalidation: {invalidation}",
        "",
        "Контекст:",
        f"• signal: {payload.get('signal') or direction}",
        f"• forecast: {payload.get('forecast_direction') or direction} ({fmt_pct(payload.get('forecast_confidence_effective') or payload.get('forecast_confidence') or conf)})",
        f"• range_state: {payload.get('range_state') or 'нет данных'}",
        f"• ct_now: {payload.get('ct_now') or 'нет данных'}",
        f"• ginarea: {payload.get('ginarea_advice') or 'нет данных'}",
        "",
        f"Long score: {fmt_pct(long_score)}",
        f"Short score: {fmt_pct(short_score)}",
    ]

    reasons = (_decision(data).get("reasons") or [])[:4]
    if reasons:
        lines.extend(["", "Почему шорт вообще рассматривается:"])
        lines.extend([f"• {x}" for x in reasons])

    lines.extend(_decision_compare_lines(data, journal))
    return "\n".join(lines)


__all__ = [
    "fmt_price",
    "fmt_pct",
    "calc_long_score",
    "calc_short_score",
    "build_btc_summary_text",
    "build_btc_forecast_text",
    "build_btc_ginarea_text",
    "build_btc_long_plan_text",
    "build_btc_short_plan_text",
]