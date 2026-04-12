from __future__ import annotations

from typing import Any, Dict, List


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, str):
            v = v.replace(" ", "").replace(",", "")
        return float(v)
    except Exception:
        return default


def _u(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v).strip().upper()
    except Exception:
        return default


def _extract_working_borders(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, float]:
    low = _f(payload.get("range_low") or decision.get("range_low"))
    mid = _f(payload.get("range_mid") or decision.get("range_mid"))
    high = _f(payload.get("range_high") or decision.get("range_high"))
    return {"low": round(low, 2) if low > 0 else 0.0, "mid": round(mid, 2) if mid > 0 else 0.0, "high": round(high, 2) if high > 0 else 0.0}


def _zones(borders: Dict[str, float]) -> Dict[str, List[float]]:
    low = _f(borders.get("low")); mid = _f(borders.get("mid")); high = _f(borders.get("high"))
    return {
        "long_zone": [round(low, 2), round(mid, 2)] if low > 0 and mid > low else [],
        "short_zone": [round(mid, 2), round(high, 2)] if high > mid > 0 else [],
    }


def build_bot_mode_context(payload: Dict[str, Any], decision: Dict[str, Any], move_type_context: Dict[str, Any]) -> Dict[str, Any]:
    execution_verdict = decision.get("execution_verdict") if isinstance(decision.get("execution_verdict"), dict) else {}

    regime = _u(move_type_context.get("regime") or decision.get("market_mode") or decision.get("regime"))
    move_type = _u(move_type_context.get("type"))
    location_state = _u(move_type_context.get("location_state"))
    continuation_risk = _u(move_type_context.get("continuation_risk"))
    fade_quality = _u(move_type_context.get("fade_quality"))
    trap_risk = _u(move_type_context.get("trap_risk"))

    if location_state == "UPPER_EDGE":
        location_state = "EDGE_HIGH"
    elif location_state == "LOWER_EDGE":
        location_state = "EDGE_LOW"

    borders = _extract_working_borders(payload, decision)
    zones = _zones(borders)

    breakout_risk = _u(execution_verdict.get("breakout_risk") or decision.get("breakout_risk") or trap_risk or "MEDIUM")

    adds_allowed = False
    can_run_now = False
    status = "OFF"
    bot_mode_action = "OFF"
    size_mode = "x0.00"
    summary = "range-бот пока не разрешён"

    launch_conditions = [
        "подход к краю диапазона",
        "удержание внутри диапазона",
        "нет подтверждённого impulse continuation",
    ]
    invalidation_conditions = [
        "закрепление выше high диапазона",
        "закрепление ниже low диапазона",
        "breakout risk EXTREME",
        "confirmed impulse continuation",
    ]

    range_valid = regime == "RANGE" and borders.get("low", 0.0) > 0 and borders.get("high", 0.0) > borders.get("low", 0.0)
    continuation_block = move_type in {"IMPULSE_CONTINUATION_UP", "IMPULSE_CONTINUATION_DOWN"}
    fake_range_ok = move_type in {"FAKE_BREAK_UP", "FAKE_BREAK_DOWN"}
    rotation_ok = move_type in {"RANGE_ROTATION", "RANGE_ROTATION_PENDING", "NO_CLEAR_MOVE"}

    near_edge = location_state in {"EDGE_LOW", "LOW", "EDGE_HIGH", "HIGH"}

    if not range_valid:
        summary = "режим range не подтверждён — объёмный range-бот выключен"

    elif continuation_block or breakout_risk == "EXTREME":
        status = "BLOCKED_BREAKOUT_RISK"
        bot_mode_action = "BLOCK_ALL"
        summary = "подтверждённое continuation или экстремальный breakout risk блокирует range-бот"

    else:
        if near_edge and breakout_risk in {"LOW", "MEDIUM"} and fade_quality in {"GOOD", "STRONG", "PARTIAL"} and rotation_ok:
            status = "READY_NORMAL"
            bot_mode_action = "RANGE_VOLUME_NORMAL"
            can_run_now = True
            adds_allowed = breakout_risk == "LOW"
            size_mode = "x1.00"
            summary = "range-бот можно запускать нормальным размером от края диапазона"

        elif near_edge and (rotation_ok or fake_range_ok):
            if breakout_risk == "HIGH":
                status = "READY_REDUCED"
                bot_mode_action = "RANGE_VOLUME_REDUCED"
                can_run_now = True
                adds_allowed = False
                size_mode = "x0.30"
                summary = "range-бот допустим только reduced size и без добавок"
            else:
                status = "READY_SMALL"
                bot_mode_action = "RANGE_VOLUME_SMALL"
                can_run_now = True
                adds_allowed = False
                size_mode = "x0.50"
                summary = "range-бот можно запускать малым размером; adds только после confirm"

        elif rotation_ok and location_state == "MID":
            status = "READY_REDUCED"
            bot_mode_action = "RANGE_VOLUME_REDUCED"
            can_run_now = True
            adds_allowed = False
            size_mode = "x0.30"
            summary = "range-бот допустим только reduced size и без добавок: цена в середине диапазона"

        elif continuation_risk in {"LOW", "MEDIUM"} and regime == "RANGE":
            status = "ARMING"
            summary = "range-режим есть, но нужен подход к краю / лучшее место для запуска"

    if fake_range_ok and can_run_now:
        launch_conditions = [
            "возврат обратно внутрь диапазона после выноса",
            "слабое удержание зоны выноса",
            "нет нового подтверждения continuation",
        ]

    return {
        "bot_mode_action": bot_mode_action,
        "range_bot_permission": {
            "status": status,
            "can_run_now": can_run_now,
            "size_mode": size_mode,
            "adds_allowed": adds_allowed,
            "entry_location": location_state or "UNKNOWN",
            "working_borders": borders,
            "long_zone": zones["long_zone"],
            "short_zone": zones["short_zone"],
            "launch_conditions": launch_conditions,
            "invalidation_conditions": invalidation_conditions,
            "summary": summary,
            "breakout_risk": breakout_risk,
            "move_type": move_type,
        },
    }


__all__ = ["build_bot_mode_context"]
