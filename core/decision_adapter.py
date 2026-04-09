from __future__ import annotations

from typing import Any

from core.decision_engine import build_final_decision, combine_trade_decision
from models.snapshots import DecisionSnapshot


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


def _get_from_analysis(snapshot, key: str, default: Any = None) -> Any:
    analysis = getattr(snapshot, "analysis", None)
    if isinstance(analysis, dict):
        return analysis.get(key, default)
    return default


def _range_state_from_position(position: str) -> str:
    mapping = {
        "LOW_EDGE": "низ диапазона / реакция поддержки",
        "LOWER_PART": "нижняя часть диапазона",
        "MID": "середина диапазона",
        "UPPER_PART": "верхняя часть диапазона",
        "HIGH_EDGE": "верх диапазона / реакция сопротивления",
        "LOWER": "нижняя часть диапазона",
        "MIDDLE": "середина диапазона",
        "UPPER": "верхняя часть диапазона",
    }
    return mapping.get(str(position), "позиция в диапазоне не определена")


def _range_position_zone(position: str) -> str:
    mapping = {
        "LOW_EDGE": "цена около низа диапазона",
        "LOWER_PART": "цена в нижней части диапазона",
        "MID": "цена около середины диапазона",
        "UPPER_PART": "цена в верхней части диапазона",
        "HIGH_EDGE": "цена около верха диапазона",
        "LOWER": "цена в нижней части диапазона",
        "MIDDLE": "цена около середины диапазона",
        "UPPER": "цена в верхней части диапазона",
    }
    return mapping.get(str(position), "позиция в диапазоне не определена")


def _ct_now_from_raw(raw: dict) -> str:
    direction = str(raw.get("direction", "NEUTRAL"))
    reason = str(raw.get("pressure_reason", "")).lower()
    action = str(raw.get("action", "NO_TRADE"))

    if direction == "LONG":
        if "перепродан" in reason:
            return "контртренд: рынок локально перепродан, возможен отскок"
        return "контекст: локальный перевес в лонг"
    if direction == "SHORT":
        if action == "WAIT_PULLBACK":
            return "контекст: рынок под давлением продавца, но вход лучше искать после отката"
        return "контекст: локальный перевес в шорт"
    return "контртренд: явного перекоса нет"


def _ginarea_advice_from_raw(raw: dict, range_low: float, range_mid: float, range_high: float) -> str:
    direction = str(raw.get("direction", "NEUTRAL"))
    position = str(raw.get("range_position", "UNKNOWN"))

    if direction == "LONG" and position in ("LOW_EDGE", "LOWER_PART", "LOWER"):
        return f"ближе поддержка в районе {int(range_low)}, при реакции возможен ход к середине {int(range_mid)}"
    if direction == "SHORT" and position in ("HIGH_EDGE", "UPPER_PART", "UPPER"):
        return f"ближе сопротивление в районе {int(range_high)}, при слабости возможен откат к середине {int(range_mid)}"
    if range_low > 0 and range_mid > 0:
        return f"ближе поддержка в районе {int(range_low)}, середина {int(range_mid)}"
    return "ключевые зоны range пока не определены"


def inject_new_decision(snapshot, timeframe: str):
    range_obj = getattr(snapshot, "range", None)
    price = _safe_float(getattr(snapshot, "price", None), _safe_float(_get_from_analysis(snapshot, "price")))
    range_low = _safe_float(getattr(range_obj, "low", 0))
    range_mid = _safe_float(getattr(range_obj, "mid", 0))
    range_high = _safe_float(getattr(range_obj, "high", 0))

    analysis = getattr(snapshot, "analysis", None)
    if not isinstance(analysis, dict):
        analysis = {}
        snapshot.analysis = analysis

    signal = _safe_str(getattr(snapshot, "signal", None) or analysis.get("signal"), "НЕЙТРАЛЬНО")
    final_decision = _safe_str(getattr(snapshot, "final_decision", None) or analysis.get("final_decision") or signal, signal)
    forecast_direction = _safe_str(getattr(snapshot, "forecast_direction", None) or analysis.get("forecast_direction") or final_decision, final_decision)
    forecast_confidence = getattr(snapshot, "forecast_confidence", None)
    if forecast_confidence is None:
        forecast_confidence = analysis.get("forecast_confidence")
    forecast_confidence = _safe_float(forecast_confidence, 0.0)
    if 0.0 <= forecast_confidence <= 1.0:
        forecast_confidence *= 100.0

    base_payload = dict(analysis) if isinstance(analysis, dict) else {}
    base_payload.update({
        "timeframe": timeframe,
        "price": price,
        "signal": signal,
        "final_decision": final_decision,
        "forecast_direction": forecast_direction,
        "forecast_confidence": forecast_confidence,
        "range_position": getattr(snapshot, "range_position", None) or analysis.get("range_position"),
        "range_state": getattr(snapshot, "range_state", None) or analysis.get("range_state") or _range_state_from_position(str(getattr(snapshot, "range_position", "UNKNOWN"))),
        "ct_now": getattr(snapshot, "ct_now", None) or analysis.get("ct_now") or "контртренд: явного перекоса нет",
        "range": {"low": range_low, "mid": range_mid, "high": range_high},
        "best_bot": analysis.get("best_bot") or analysis.get("best_bot_label") or getattr(snapshot, "best_bot", None) or getattr(snapshot, "best_bot_label", None),
        "best_bot_score": analysis.get("best_bot_score") or getattr(snapshot, "best_bot_score", None),
        "best_bot_status": analysis.get("best_bot_status") or getattr(snapshot, "best_bot_status", None),
        "preferred_bot": analysis.get("preferred_bot") or getattr(snapshot, "preferred_bot", None),
        "hold_bias": analysis.get("hold_bias") or getattr(snapshot, "hold_bias", None),
        "bot_cards": analysis.get("bot_cards"),
        "analysis": analysis,
        "stats": getattr(snapshot, "stats", None) or {},
    })
    try:
        combined = combine_trade_decision(base_payload)
        raw = combined.get('decision') if isinstance(combined, dict) and isinstance(combined.get('decision'), dict) else build_final_decision(base_payload)
        if isinstance(combined, dict):
            for key in ('fake_move_detector','move_type_context','bot_mode_context','range_bot_permission','action_output','bot_mode_action','directional_action','soft_signal','move_projection'):
                if key in combined:
                    analysis[key] = combined.get(key)
    except Exception:
        raw = build_final_decision(base_payload)

    raw["range_position_zone"] = raw.get("range_position_zone") or _range_position_zone(str(raw.get("range_position", "UNKNOWN")))
    raw["confidence_pct"] = _safe_float(raw.get("confidence_pct", raw.get("confidence", 0)))
    raw["manager_action"] = raw.get("manager_action") or raw.get("action")
    raw["manager_action_text"] = raw.get("manager_action_text") or _safe_str(raw.get("action_text"), "ЖДАТЬ") or "ЖДАТЬ"
    raw["manager_reason"] = raw.get("manager_reason") or raw.get("no_trade_reason") or raw.get("summary") or ""

    ct_now = _ct_now_from_raw(raw)
    ginarea_advice = _ginarea_advice_from_raw(raw, range_low, range_mid, range_high)
    range_state = getattr(snapshot, "range_state", None) or analysis.get("range_state") or _range_state_from_position(str(raw.get("range_position", "UNKNOWN")))

    snapshot.decision = DecisionSnapshot.from_dict(raw)
    snapshot.final_decision = raw.get("direction_text", snapshot.final_decision)
    snapshot.range_state = range_state
    snapshot.range_position = raw.get("range_position", "UNKNOWN")
    snapshot.ct_now = ct_now
    snapshot.ginarea_advice = ginarea_advice
    snapshot.decision_summary = raw.get("summary", "")

    analysis["final_decision"] = snapshot.final_decision
    analysis["range_state"] = range_state
    analysis["range_position"] = snapshot.range_position
    analysis["ct_now"] = ct_now
    analysis["ginarea_advice"] = ginarea_advice
    analysis["decision_summary"] = snapshot.decision_summary
    try:
        analysis["decision"] = snapshot.decision.to_dict()
    except Exception:
        analysis["decision"] = raw

    return snapshot
