from __future__ import annotations

from typing import Any, Dict


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _normalize_signal(value: Any) -> str:
    v = str(value or "").strip().upper()
    mapping = {
        "LONG": "LONG",
        "STRONG LONG": "LONG",
        "BUY": "LONG",
        "ЛОНГ": "LONG",
        "SHORT": "SHORT",
        "STRONG SHORT": "SHORT",
        "SELL": "SHORT",
        "ШОРТ": "SHORT",
        "NEUTRAL": "NEUTRAL",
        "WAIT": "NEUTRAL",
        "NO TRADE": "NEUTRAL",
        "НЕЙТРАЛЬНО": "NEUTRAL",
        "ЖДАТЬ": "NEUTRAL",
        "НЕТ ДАННЫХ": "NEUTRAL",
    }
    return mapping.get(v, "NEUTRAL")


def _normalize_reversal(value: Any) -> str:
    v = str(value or "").strip().upper()
    if not v:
        return "NO_REVERSAL"
    if v in {"NO_REVERSAL", "NONE", "NO DATA", "НЕТ", "НЕТ ДАННЫХ"}:
        return "NO_REVERSAL"
    return v


def _state_text(value: Any) -> str:
    return str(value or "").strip()


def build_decision_block(
    signal_block: Dict[str, Any] | None = None,
    reversal_block: Dict[str, Any] | None = None,
    range_block: Dict[str, Any] | None = None,
    countertrend_block: Dict[str, Any] | None = None,
    ginarea_block: Dict[str, Any] | None = None,
    impulse_block: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal_block = signal_block or {}
    reversal_block = reversal_block or {}
    range_block = range_block or {}
    countertrend_block = countertrend_block or {}
    ginarea_block = ginarea_block or {}
    impulse_block = impulse_block or {}

    raw_signal = signal_block.get("final_signal") or signal_block.get("signal")
    direction = _normalize_signal(raw_signal)
    confidence = _to_float(signal_block.get("confidence"), 0.0)

    reversal_state = _normalize_reversal(reversal_block.get("state"))
    reversal_conf = _to_float(reversal_block.get("confidence"), 0.0)

    range_state = _state_text(range_block.get("state"))
    ct_context = _state_text(countertrend_block.get("context") or countertrend_block.get("bias"))
    ginarea_advice = _state_text(ginarea_block.get("advice"))

    impulse_state = _state_text(impulse_block.get("state"))
    impulse_score = _to_float(impulse_block.get("score"), 0.0)
    can_enter = bool(impulse_block.get("can_enter", False))

    rs = range_state.lower()
    ct = ct_context.lower()
    ia = impulse_state.lower()

    if "continue" in ia or "продолж" in ia:
        confidence += 8
    elif "exhaust" in ia or "затух" in ia or "weak" in ia:
        confidence -= 10

    if "середина" in rs or "middle" in rs:
        confidence -= 12
    elif ("ниж" in rs or "low" in rs) and direction == "LONG":
        confidence += 6
    elif ("верх" in rs or "high" in rs) and direction == "SHORT":
        confidence += 6

    if reversal_state != "NO_REVERSAL" and reversal_conf >= 50:
        confidence -= 15

    confidence = max(0.0, min(100.0, confidence))

    if reversal_state != "NO_REVERSAL":
        mode = "REVERSAL"
    elif "range" in rs or "диапаз" in rs or "середина" in rs:
        mode = "RANGE"
    elif "контртренд" in ct:
        mode = "COUNTERTREND"
    else:
        mode = "TREND"

    if direction == "NEUTRAL":
        action = "WAIT"
    elif "середина" in rs or "middle" in rs:
        action = "WAIT"
    elif not can_enter and ("uncertain" in ia or "затух" in ia or "weak" in ia or "exhaust" in ia):
        action = "WAIT_CONFIRMATION"
    elif can_enter and confidence >= 60:
        action = "LOOK_FOR_ENTRY"
    elif confidence >= 70:
        action = "ENTER"
    elif confidence >= 45:
        action = "LOOK_FOR_ENTRY"
    else:
        action = "WAIT"

    if reversal_state != "NO_REVERSAL":
        risk = "HIGH"
    elif "середина" in rs or "middle" in rs:
        risk = "HIGH"
    elif confidence >= 70:
        risk = "LOW"
    elif confidence >= 50:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    if action == "ENTER":
        entry_comment = "Есть условия для входа по текущему направлению."
    elif action == "LOOK_FOR_ENTRY":
        entry_comment = "Есть перевес, но вход лучше искать по подтверждению."
    elif action == "WAIT_CONFIRMATION":
        entry_comment = "Импульс слабеет. Лучше дождаться подтверждения или отката в более сильную зону."
    else:
        entry_comment = "Сейчас лучше ждать более чистую ситуацию."

    return {
        "direction": direction,
        "action": action,
        "mode": mode,
        "confidence": round(confidence, 1),
        "risk": risk,
        "entry_comment": entry_comment,
        "reasoning": {
            "signal_confidence": round(_to_float(signal_block.get("confidence"), 0.0), 1),
            "reversal_state": reversal_state,
            "reversal_confidence": round(reversal_conf, 1),
            "range_state": range_state,
            "countertrend_context": ct_context,
            "impulse_state": impulse_state,
            "impulse_score": round(impulse_score, 1),
            "ginarea_advice": ginarea_advice,
        },
    }


# Backward-compatible wrapper for existing imports.
def combine_trade_decision(normalized: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(normalized or {})
    decision = build_decision_block(
        signal_block={
            "signal": data.get("signal"),
            "final_signal": data.get("final_decision"),
            "confidence": data.get("forecast_confidence") or 0,
        },
        reversal_block={
            "state": data.get("reversal"),
            "confidence": data.get("reversal_confidence") or 0,
        },
        range_block={
            "state": data.get("range_state"),
            "low": data.get("range_low"),
            "mid": data.get("range_mid"),
            "high": data.get("range_high"),
        },
        countertrend_block={"context": data.get("ct_now")},
        ginarea_block={"advice": data.get("ginarea_advice")},
        impulse_block=data.get("impulse") or {},
    )
    data["decision"] = decision
    # Preserve old flattened keys for legacy renderers.
    data.setdefault("decision_direction", decision.get("direction"))
    data.setdefault("decision_action", decision.get("action"))
    data.setdefault("decision_mode", decision.get("mode"))
    data.setdefault("decision_confidence", decision.get("confidence"))
    data.setdefault("decision_risk", decision.get("risk"))
    return data
