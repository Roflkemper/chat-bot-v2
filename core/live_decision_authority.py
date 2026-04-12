from __future__ import annotations

from typing import Any, Dict


def _side_sign(side: str) -> int:
    side = str(side or "").upper()
    if side == "LONG":
        return 1
    if side == "SHORT":
        return -1
    return 0


def _normalize_action(action: str) -> str:
    action = str(action or "WAIT").upper()
    aliases = {
        "WAIT_CONFIRMATION": "WAIT",
        "WATCH": "WAIT",
        "PROTECT": "EXIT",
        "PREPARE": "PREPARE",
        "ENTER": "ENTER",
        "WAIT": "WAIT",
        "HOLD": "MANAGE",
        "MANAGE": "MANAGE",
        "EXIT": "EXIT",
    }
    return aliases.get(action, action)


def evaluate_live_decision(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    action = _normalize_action(snapshot.get("action"))
    active_side = str(snapshot.get("execution_side") or "NONE").upper()
    consensus_direction = str(snapshot.get("consensus_direction") or "NONE").upper()
    structural_bias = str((snapshot.get("structural_context") or {}).get("bias") or "NONE").upper()
    context_score = int(snapshot.get("context_score") or 0)
    depth_label = str(snapshot.get("depth_label") or "RISK").upper()
    bias_score = int(snapshot.get("bias_score") or 0)
    danger = bool(snapshot.get("danger_to_active_side"))
    near_breakout = bool(snapshot.get("near_breakout"))
    absorption = snapshot.get("absorption") or {}
    absorption_active = bool(absorption.get("is_active"))
    flip_status = str(snapshot.get("flip_prep_status") or "IDLE").upper()
    entry_quality = str(snapshot.get("entry_quality") or "NO_TRADE").upper()
    execution_profile = str(snapshot.get("execution_profile") or "NO_ENTRY").upper()
    partial_entry_allowed = bool(snapshot.get("partial_entry_allowed"))
    scale_in_allowed = bool(snapshot.get("scale_in_allowed"))
    range_low = float(snapshot.get("range_low") or 0.0)
    range_high = float(snapshot.get("range_high") or 0.0)
    range_size = max(range_high - range_low, 1e-9)
    price = float(snapshot.get("price") or 0.0)

    score = 50
    score += 10 * context_score
    score += max(-12, min(12, bias_score * 2))

    if entry_quality == "A":
        score += 16
    elif entry_quality == "B":
        score += 8
    elif entry_quality == "C":
        score -= 6
    else:
        score -= 18

    if execution_profile in {"AGGRESSIVE", "STANDARD"}:
        score += 6
    elif execution_profile in {"PROBE_ONLY", "NO_ENTRY"}:
        score -= 8

    if depth_label in {"EARLY", "WORK"}:
        score += 8
    elif depth_label in {"RISK", "DEEP"}:
        score -= 10

    if danger:
        score -= 18
    elif near_breakout:
        score -= 6

    if absorption_active:
        score += 10
    if flip_status == "ARMED":
        score -= 4 if action == "WAIT" else 0
    elif flip_status == "CONFIRMED":
        score -= 8 if _side_sign(active_side) * _side_sign(structural_bias) < 0 else 6

    if consensus_direction not in {"LONG", "SHORT"}:
        score -= 8
    elif consensus_direction == active_side:
        score += 8
    else:
        score -= 12

    if structural_bias in {"LONG", "SHORT"} and structural_bias == active_side:
        score += 4
    elif structural_bias in {"LONG", "SHORT"}:
        score -= 10

    execution_quality_score = max(0, min(100, int(score)))
    if action == "WAIT":
        execution_grade = "NO_TRADE" if execution_quality_score < 55 else "C"
    elif execution_quality_score >= 82:
        execution_grade = "A"
    elif execution_quality_score >= 68:
        execution_grade = "B"
    elif execution_quality_score >= 55:
        execution_grade = "C"
    else:
        execution_grade = "NO_TRADE"

    if action == "WAIT":
        live_state = "OBSERVE"
    elif action == "PREPARE":
        live_state = "PREPARE"
    elif action == "ENTER":
        live_state = "ENTER"
    elif action == "EXIT":
        live_state = "EXIT"
    else:
        live_state = "MANAGE"

    urgency = 35
    urgency += 18 if near_breakout else 0
    urgency += 14 if danger else 0
    urgency += 8 if action in {"PREPARE", "ENTER", "EXIT"} else 0
    urgency += 6 if flip_status == "ARMED" else 0
    urgency += 4 if absorption_active else 0
    urgency += 6 if abs(bias_score) >= 5 else 0
    urgency = max(0, min(100, urgency))
    if urgency >= 80:
        urgency_label = "IMMEDIATE"
    elif urgency >= 62:
        urgency_label = "HIGH"
    elif urgency >= 45:
        urgency_label = "MID"
    else:
        urgency_label = "LOW"

    location_offset = 0.0
    if range_size > 0:
        location_offset = abs(price - ((range_low + range_high) / 2.0)) / range_size
    late_entry_risk = "HIGH" if near_breakout and action in {"PREPARE", "ENTER"} else "MID" if location_offset > 0.28 else "LOW"
    chase_risk = "HIGH" if near_breakout and consensus_direction == active_side else "MID" if action in {"PREPARE", "ENTER"} else "LOW"
    bad_location = danger or depth_label in {"RISK", "DEEP"}

    management_mode = "HARD_DEFENSE" if danger else "ACTIVE" if action in {"ENTER", "MANAGE"} else "WAIT"
    manual_action = "WAIT"
    if action == "ENTER" and execution_grade in {"A", "B"} and not bad_location:
        manual_action = f"ENTER {active_side}"
    elif action == "PREPARE":
        manual_action = f"PREPARE {active_side}"
    elif danger and active_side in {"LONG", "SHORT"}:
        manual_action = f"DEFEND {active_side}"
    elif action == "EXIT":
        manual_action = "EXIT / REDUCE"

    bot_action = "MONITOR"
    grid_action = snapshot.get("grid_action") or {}
    long_action = str(grid_action.get("long_action") or "HOLD").upper()
    short_action = str(grid_action.get("short_action") or "HOLD").upper()
    if active_side == "LONG":
        bot_action = "BOOST LONG / PAUSE SHORT" if long_action == "BOOST" or short_action == "PAUSE" else "HOLD LONG"
    elif active_side == "SHORT":
        bot_action = "BOOST SHORT / PAUSE LONG" if short_action == "BOOST" or long_action == "PAUSE" else "HOLD SHORT"

    tp1 = tp2 = be_trigger = invalidation = None
    if active_side == "LONG":
        risk_unit = max(price - range_low, range_size * 0.18)
        invalidation = round(range_low, 2)
        tp1 = round(price + risk_unit * 0.8, 2)
        tp2 = round(min(range_high + risk_unit * 0.4, price + risk_unit * 1.6), 2)
        be_trigger = round(price + risk_unit * 0.6, 2)
    elif active_side == "SHORT":
        risk_unit = max(range_high - price, range_size * 0.18)
        invalidation = round(range_high, 2)
        tp1 = round(price - risk_unit * 0.8, 2)
        tp2 = round(max(range_low - risk_unit * 0.4, price - risk_unit * 1.6), 2)
        be_trigger = round(price - risk_unit * 0.6, 2)

    notes = []
    if danger:
        notes.append("опасная локация: активная сторона под риском пробоя")
    if chase_risk == "HIGH":
        notes.append("вход в догонку плохой: рынок уже у края диапазона")
    if absorption_active:
        notes.append("absorption подтверждён: уровень держат несколько баров")
    if structural_bias in {"LONG", "SHORT"} and structural_bias != active_side:
        notes.append("структура против активной стороны")
    if action == "WAIT":
        notes.append("без подтверждения лучше не открывать новую сделку")
    elif execution_grade in {"A", "B"}:
        notes.append("исполнение допустимо только по плану, без догонки")

    return {
        "live_state": live_state,
        "execution_quality_score": execution_quality_score,
        "execution_grade_live": execution_grade,
        "urgency_score_live": urgency,
        "urgency_label_live": urgency_label,
        "late_entry_risk": late_entry_risk,
        "chase_risk": chase_risk,
        "bad_location": bad_location,
        "manual_action_now": manual_action,
        "bot_action_now": bot_action,
        "management_mode": management_mode,
        "tp1_live": tp1,
        "tp2_live": tp2,
        "be_trigger_live": be_trigger,
        "invalidation_live": invalidation,
        "partial_allowed_live": partial_entry_allowed,
        "scale_allowed_live": scale_in_allowed,
        "live_notes": notes,
    }
