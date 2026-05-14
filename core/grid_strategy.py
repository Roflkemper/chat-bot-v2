from __future__ import annotations

from typing import Any, Dict, List


BOT_LEVELS = (
    ("BOT A", 1.5, "лёгкий контртренд"),
    ("BOT B", 2.5, "основной добор"),
    ("BOT C", 3.3, "агрессивный экстремум"),
)

PRE_ACTIVATION_A_PREPARE = 0.5
PRE_ACTIVATION_A_SMALL = 0.8


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
    raw = _safe_str(value, "").strip().upper()
    if raw in {"LONG", "ЛОНГ", "UP", "ВВЕРХ"}:
        return "ЛОНГ"
    if raw in {"SHORT", "ШОРТ", "DOWN", "ВНИЗ"}:
        return "ШОРТ"
    return "НЕЙТРАЛЬНО"


def _contrarian_side_from_deviation(deviation_pct: float) -> str:
    if deviation_pct >= 0:
        return "ШОРТ"
    return "ЛОНГ"


def _deviation_side_text(deviation_pct: float) -> str:
    if deviation_pct > 0:
        return "перегрев вверх"
    if deviation_pct < 0:
        return "перегрев вниз"
    return "без перегрева"


def build_three_bot_grid_strategy(data: Dict[str, Any]) -> Dict[str, Any]:
    data = data or {}
    deviation_pct = _safe_float(data.get("deviation_pct"), 0.0)
    abs_dev = abs(deviation_pct)
    mean_price = data.get("mean60_price")
    if mean_price in (None, 0, 0.0, ''):
        mean_price = data.get('price') or data.get('current_price') or data.get('close')
    forecast_dir = _normalize_direction(data.get("forecast_direction"))
    pattern_dir = _normalize_direction(data.get("pattern_forecast_direction") or data.get("history_pattern_direction"))
    range_position = _safe_str(data.get("range_position") or (data.get("decision") or {}).get("range_position"), "UNKNOWN").upper()
    ladder_action = _safe_str(data.get("ladder_action"), "нет данных")
    range_bias_action = _safe_str(data.get("range_bias_action"), "нет данных")
    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    setup_status = _safe_str(decision.get("setup_status"), "WAIT").upper()
    late_entry_risk = _safe_str(decision.get("late_entry_risk"), "HIGH").upper()
    trap_risk = _safe_str(decision.get("trap_risk"), "MEDIUM").upper()
    risk = _safe_str(decision.get("risk") or decision.get("risk_level"), "HIGH").upper()
    forecast_conf_pct = _safe_float(data.get("forecast_confidence"), 0.0)
    if 0.0 <= forecast_conf_pct <= 1.0:
        forecast_conf_pct *= 100.0
    pattern_conf_pct = _safe_float(data.get("pattern_forecast_confidence") or data.get("history_pattern_confidence"), 0.0)
    if 0.0 <= pattern_conf_pct <= 1.0:
        pattern_conf_pct *= 100.0

    contrarian_side = _contrarian_side_from_deviation(deviation_pct)
    supportive = 0
    if forecast_dir == contrarian_side:
        supportive += 1
    if pattern_dir == contrarian_side:
        supportive += 1
    if contrarian_side == "ЛОНГ" and any(x in range_position for x in ("LOW", "DISCOUNT", "BOTTOM")):
        supportive += 1
    if contrarian_side == "ШОРТ" and any(x in range_position for x in ("HIGH", "PREMIUM", "TOP")):
        supportive += 1

    bots: List[Dict[str, Any]] = []
    active_labels: List[str] = []
    for label, trigger, role in BOT_LEVELS:
        triggered = abs_dev >= trigger
        pre_prepare = label == "BOT A" and abs_dev >= PRE_ACTIVATION_A_PREPARE
        pre_small = label == "BOT A" and abs_dev >= PRE_ACTIVATION_A_SMALL
        entry_ok = triggered and setup_status != "INVALID"
        if trap_risk == "HIGH" and trigger <= 1.5 and not pre_small:
            entry_ok = False
        confidence = 0.0
        readiness = "LOW"
        trigger_fill_pct = min(100.0, (abs_dev / trigger) * 100.0) if trigger > 0 else 0.0
        if triggered:
            confidence = min(95.0, 42.0 + (abs_dev - trigger) * 18.0 + supportive * 6.0 + max(0.0, forecast_conf_pct - 50.0) * 0.15)
            if late_entry_risk == "HIGH":
                confidence -= 6.0
            if risk == "HIGH":
                confidence -= 4.0
            confidence = max(18.0, confidence)
            readiness = "READY" if entry_ok else "HIGH"
        elif pre_small:
            confidence = max(16.0, 22.0 + supportive * 4.0 + max(0.0, forecast_conf_pct - 50.0) * 0.08)
            readiness = "ARMING"
        elif pre_prepare:
            confidence = max(8.0, 12.0 + supportive * 3.0)
            readiness = "PREPARE"
        elif trigger_fill_pct >= 80.0:
            readiness = "MEDIUM"
        elif trigger_fill_pct >= 50.0:
            readiness = "LOW"
        action = "WAIT"
        if entry_ok:
            if label == "BOT A":
                action = "SCALP ENTRY"
            elif label == "BOT B":
                action = "MAIN ENTRY"
            else:
                action = "EXTREME ENTRY"
            active_labels.append(label)
        elif triggered:
            action = "WAIT CONFIRMATION"
        elif pre_small:
            action = "START SMALL"
        elif pre_prepare:
            action = "PREPARE"
        reason = f"порог {trigger:.1f}% | текущее отклонение {abs_dev:.2f}% | заполнение триггера {trigger_fill_pct:.0f}% | {_deviation_side_text(deviation_pct)}"
        if supportive > 0:
            reason += f" | подтверждений: {supportive}"
        bots.append({
            "label": label,
            "role": role,
            "trigger_pct": trigger,
            "triggered": triggered,
            "active": entry_ok,
            "side": contrarian_side if triggered else "НЕЙТРАЛЬНО",
            "confidence": round(confidence, 1),
            "readiness": readiness,
            "trigger_fill_pct": round(trigger_fill_pct, 1),
            "action": action,
            "reason": reason,
        })

    strongest = active_labels[-1] if active_labels else (bots[-1]["label"] if bots[-1]["triggered"] else bots[1]["label"] if bots[1]["triggered"] else bots[0]["label"] if bots[0]["triggered"] else "NONE")
    preactivated = [bot["label"] for bot in bots if bot.get("action") in {"PREPARE", "START SMALL"}]
    if active_labels:
        summary = f"активны {', '.join(active_labels)}; базовая сторона: {contrarian_side}; strongest: {strongest}"
    elif any(bot["triggered"] for bot in bots):
        summary = f"триггеры есть, но нужен confirm; strongest: {strongest}; сторона: {contrarian_side}"
    elif preactivated:
        summary = f"идёт ранняя pre-activation: {', '.join(preactivated)}; базовая сторона: {contrarian_side}"
    else:
        summary = "отклонение недостаточно для запуска 3-ботовой grid-логики"

    return {
        "enabled": True,
        "strategy_name": "3 BOT GRID ENGINE",
        "deviation_pct": round(deviation_pct, 3),
        "deviation_abs_pct": round(abs_dev, 3),
        "deviation_side": _deviation_side_text(deviation_pct),
        "contrarian_side": contrarian_side if abs_dev > 0 else "НЕЙТРАЛЬНО",
        "mean60_price": mean_price,
        "forecast_direction": forecast_dir,
        "pattern_direction": pattern_dir,
        "supportive_signals": supportive,
        "ladder_action": ladder_action,
        "range_bias_action": range_bias_action,
        "bots": bots,
        "active_bots": active_labels,
        "strongest_bot": strongest,
        "summary": summary,
        "execution_hint": "боты включаются по отклонению 1.5% / 2.5% / 3.3%, но BOT A теперь имеет PREPARE от 0.5% и START SMALL от 0.8% для более ранней работы по импульсу",
    }
