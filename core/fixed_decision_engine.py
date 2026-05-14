from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _normalize_direction(value: Any) -> str:
    v = _safe_str(value).strip().upper()
    if v in {"LONG", "ЛОНГ", "BUY", "BULLISH", "UP"}:
        return "LONG"
    if v in {"SHORT", "ШОРТ", "SELL", "BEARISH", "DOWN"}:
        return "SHORT"
    return "NEUTRAL"


def _direction_text(direction: str) -> str:
    return {
        "LONG": "ЛОНГ",
        "SHORT": "ШОРТ",
        "NEUTRAL": "НЕЙТРАЛЬНО",
    }.get(direction, "НЕЙТРАЛЬНО")


def _action_text(action: str) -> str:
    return {
        "ENTER": "ВХОДИТЬ",
        "ENTER_LONG": "ВХОДИТЬ",
        "ENTER_SHORT": "ВХОДИТЬ",
        "WATCH": "СМОТРЕТЬ СЕТАП",
        "WAIT": "ЖДАТЬ",
        "WAIT_CONFIRMATION": "ЖДАТЬ ПОДТВЕРЖДЕНИЕ",
        "WAIT_PULLBACK": "ЖДАТЬ ОТКАТ",
        "NO_TRADE": "ЖДАТЬ",
    }.get(action, "ЖДАТЬ")


def _extract_range_state(data: Dict[str, Any]) -> str:
    return _safe_str(
        data.get("range_state")
        or (data.get("range") or {}).get("state")
        or "",
        "",
    )


def _extract_range_position(data: Dict[str, Any]) -> str:
    state = _extract_range_state(data).lower()
    if "ниж" in state or "lower" in state:
        return "LOWER"
    if "верх" in state or "upper" in state:
        return "UPPER"
    if "серед" in state or "middle" in state:
        return "MIDDLE"
    return "UNKNOWN"


def _extract_impulse(data: Dict[str, Any]) -> Dict[str, Any]:
    impulse = data.get("impulse")
    if isinstance(impulse, dict):
        return impulse

    fc = _safe_float(data.get("forecast_confidence"), 0.0)
    if fc >= 65:
        return {
            "state": "IMPULSE_CONTINUES",
            "score": fc,
            "can_enter": True,
            "comment": "Импульс продолжается",
            "watch_conditions": [
                "удержание локальной поддержки/сопротивления",
                "свеча продолжения по направлению движения",
                "обновление локального экстремума",
            ],
        }
    if fc >= 45:
        return {
            "state": "IMPULSE_UNCERTAIN",
            "score": fc,
            "can_enter": False,
            "comment": "Импульс есть, но подтверждение слабое",
            "watch_conditions": [
                "реакция от уровня",
                "подтверждение на следующей свече",
            ],
        }
    return {
        "state": "IMPULSE_EXHAUSTING",
        "score": fc,
        "can_enter": False,
        "comment": "Импульс затухает",
        "watch_conditions": [
            "откат к зоне",
            "новый импульсный перезапуск",
        ],
    }


def build_decision_block(
    signal_block: Dict[str, Any] | None = None,
    range_block: Dict[str, Any] | None = None,
    impulse_block: Dict[str, Any] | None = None,
    countertrend_block: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal_block = signal_block or {}
    range_block = range_block or {}
    impulse_block = impulse_block or {}
    countertrend_block = countertrend_block or {}

    raw_signal = signal_block.get("final_signal") or signal_block.get("signal")
    direction = _normalize_direction(raw_signal)
    direction_text = _direction_text(direction)

    confidence = _safe_float(signal_block.get("confidence"), 50.0)
    impulse_state = _safe_str(impulse_block.get("state"), "").upper()
    range_state = _safe_str(range_block.get("state"), "")
    ct_context = _safe_str(countertrend_block.get("context") or countertrend_block.get("bias"), "")

    reasons: List[str] = []
    mode_reasons: List[str] = []
    expectation: List[str] = []

    if direction == "LONG":
        reasons.append("По текущей логике есть перевес в лонг.")
    elif direction == "SHORT":
        reasons.append("По текущей логике есть перевес в шорт.")
    else:
        reasons.append("Явного directional-перевеса нет.")

    if impulse_state == "IMPULSE_CONTINUES":
        confidence += 10
        reasons.append("Импульс поддерживает текущее направление.")
        expectation.append("движение может продолжиться без глубокого отката")
    elif impulse_state == "IMPULSE_UNCERTAIN":
        reasons.append("Импульс есть, но без чистого подтверждения.")
        expectation.append("нужна реакция от уровня или свеча подтверждения")
    elif impulse_state == "IMPULSE_EXHAUSTING":
        confidence -= 15
        reasons.append("Импульс затухает, вход в догонку рискованный.")
        expectation.append("лучше ждать откат или новый импульс")

    rs = range_state.lower()
    mode = "TREND"
    if "серед" in rs or "middle" in rs or "range" in rs or "диапаз" in rs:
        mode = "RANGE"
        mode_reasons.append("Цена не у края, а внутри диапазона.")
        confidence -= 10
    elif "ниж" in rs and direction == "LONG":
        mode_reasons.append("Лонг рассматривается ближе к нижней части диапазона.")
        confidence += 5
    elif "верх" in rs and direction == "SHORT":
        mode_reasons.append("Шорт рассматривается ближе к верхней части диапазона.")
        confidence += 5

    if ct_context:
        expectation.append(ct_context)

    confidence = max(0.0, min(100.0, confidence))

    if direction == "NEUTRAL":
        action = "WAIT"
    elif impulse_state == "IMPULSE_EXHAUSTING":
        action = "WAIT_CONFIRMATION"
    elif confidence >= 65:
        action = "ENTER"
    elif confidence >= 45:
        action = "WATCH"
    else:
        action = "WAIT"

    risk = "HIGH" if ("серед" in rs or "middle" in rs or confidence < 50) else "MEDIUM"
    if confidence >= 75 and action == "ENTER":
        risk = "LOW"

    long_score = confidence if direction == "LONG" else max(0.0, 100.0 - confidence)
    short_score = confidence if direction == "SHORT" else max(0.0, 100.0 - confidence)

    if action == "ENTER":
        summary = "Есть рабочий перевес, вход допустим по текущему направлению."
    elif action == "WATCH":
        summary = "Есть перевес, но лучше искать подтверждение у уровня."
    elif action == "WAIT_CONFIRMATION":
        summary = "Импульс затухает, лучше дождаться подтверждения."
    else:
        summary = "Сейчас лучше ждать более чистую ситуацию."

    if not expectation:
        expectation = list(impulse_block.get("watch_conditions") or [])

    return {
        "direction": direction,
        "direction_text": direction_text,
        "action": action,
        "action_text": _action_text(action),
        "manager_action": action,
        "manager_action_text": _action_text(action),
        "mode": mode,
        "regime": mode,
        "confidence": round(confidence, 1),
        "confidence_pct": round(confidence, 1),
        "risk": risk,
        "risk_level": risk,
        "summary": summary,
        "long_score": round(long_score, 1),
        "short_score": round(short_score, 1),
        "pressure_reason": ct_context,
        "entry_reason": summary,
        "invalidation": "",
        "active_bot": "none",
        "range_position": _extract_range_position({"range_state": range_state}),
        "range_position_zone": range_state or "позиция в диапазоне не определена",
        "expectation": expectation[:5],
        "expectation_text": expectation[0] if expectation else "",
        "reasons": reasons[:5],
        "mode_reasons": mode_reasons[:3],
    }


def build_final_decision(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = data or {}
    impulse = _extract_impulse(data)
    return build_decision_block(
        signal_block={
            "signal": data.get("signal"),
            "final_signal": data.get("final_decision") or data.get("forecast_direction") or data.get("signal"),
            "confidence": data.get("forecast_confidence", 50.0),
        },
        range_block={"state": _extract_range_state(data)},
        impulse_block=impulse,
        countertrend_block={"context": data.get("ct_now")},
    )


def combine_trade_decision(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = dict(data or {})
    payload["impulse"] = _extract_impulse(payload)
    payload["decision"] = build_final_decision(payload)

    decision = payload["decision"]
    if not payload.get("decision_summary"):
        payload["decision_summary"] = decision.get("summary", "")

    if not payload.get("final_decision"):
        payload["final_decision"] = decision.get("direction_text", "НЕЙТРАЛЬНО")

    return payload
