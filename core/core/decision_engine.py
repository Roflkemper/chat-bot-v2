from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.safe_io import atomic_write_json as save_json, safe_read_json as load_json
from core.move_type_engine import build_move_type_context
from core.bot_mode_engine import build_bot_mode_context
from core.action_output import build_action_output


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
    if v in {"LONG", "ЛОНГ", "BUY", "BULLISH", "UP", "ВВЕРХ"}:
        return "LONG"
    if v in {"SHORT", "ШОРТ", "SELL", "BEARISH", "DOWN", "ВНИЗ"}:
        return "SHORT"
    return "NEUTRAL"


def _direction_text(direction: str) -> str:
    return {"LONG": "ЛОНГ", "SHORT": "ШОРТ", "NEUTRAL": "НЕЙТРАЛЬНО"}.get(direction, "НЕЙТРАЛЬНО")





def _apply_range_bot_best_trade_override(decision: Dict[str, Any]) -> Dict[str, Any]:
    try:
        action = str(decision.get("action") or "WAIT").upper()
        bot_mode_action = str(decision.get("bot_mode_action") or "OFF").upper()
        permission = decision.get("range_bot_permission") if isinstance(decision.get("range_bot_permission"), dict) else {}
        if action == "WAIT" and permission.get("can_run_now") and bot_mode_action in {"RANGE_VOLUME_REDUCED", "RANGE_VOLUME_SMALL", "RANGE_VOLUME_NORMAL"}:
            decision["best_trade_play"] = bot_mode_action.lower()
            decision["best_trade_side"] = "RANGE"
            decision["best_trade_score"] = max(float(decision.get("best_trade_score", 0.0) or 0.0), 58.0)
            decision["best_trade_reason"] = f"range-бот разрешён: {permission.get('status','OFF')} / {permission.get('size_mode','x0.00')}"
        return decision
    except Exception:
        return decision




def _apply_v771_confidence_split(decision: Dict[str, Any]) -> Dict[str, Any]:
    try:
        edge_block = decision.get("edge_score_data") if isinstance(decision.get("edge_score_data"), dict) else {}
        arming = decision.get("arming_logic") if isinstance(decision.get("arming_logic"), dict) else {}

        bias_conf = _safe_float(decision.get("confidence_pct") or decision.get("confidence"), 0.0)
        edge_score = _safe_float(edge_block.get("score", decision.get("edge_score", 0.0)), 0.0)
        confirmation_ready = _safe_float(arming.get("confirmation_ready"), 0.0)
        trade_authorized = bool(decision.get("trade_authorized"))

        execution_conf = edge_score * 100.0 if edge_score <= 1.0 else edge_score
        setup_ready = confirmation_ready * 100.0 if confirmation_ready <= 1.0 else confirmation_ready
        fallback_confirmation = 35.0 if setup_ready <= 0.0 else setup_ready

        final_conf = min(
            max(0.0, bias_conf),
            max(0.0, execution_conf),
            max(0.0, fallback_confirmation),
        )

        if not trade_authorized:
            final_conf = min(final_conf, 39.0)

        decision["bias_confidence"] = round(bias_conf, 1)
        decision["setup_readiness"] = round(setup_ready, 1)
        decision["execution_confidence"] = round(execution_conf, 1)
        decision["final_confidence"] = round(final_conf, 1)
        decision.setdefault("confidence", round(bias_conf, 1))
        decision.setdefault("confidence_pct", round(bias_conf, 1))
        return decision
    except Exception:
        return decision


def _apply_v780_consistency_engine(decision: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        payload = payload if isinstance(payload, dict) else {}
        edge_block = decision.get("edge_score_data") if isinstance(decision.get("edge_score_data"), dict) else {}
        arming = decision.get("arming_logic") if isinstance(decision.get("arming_logic"), dict) else {}

        raw_bias_conf = _safe_float(decision.get("confidence_pct") or decision.get("confidence"), 0.0)
        final_conf = _safe_float(decision.get("final_confidence", raw_bias_conf), raw_bias_conf)
        execution_conf = _safe_float(decision.get("execution_confidence", 0.0), 0.0)
        edge_score = _safe_float(edge_block.get("score", decision.get("edge_score", 0.0)), 0.0)
        confirmation_ready = _safe_float(arming.get("confirmation_ready"), 0.0)
        if 0.0 <= confirmation_ready <= 1.0:
            confirmation_ready *= 100.0

        edge_label = _safe_str(edge_block.get("label", decision.get("edge_label", "NO_EDGE")), "NO_EDGE").upper()
        action = _safe_str(decision.get("action"), "WAIT").upper()
        trade_authorized = bool(decision.get("trade_authorized"))
        forecast_direction = _normalize_direction(payload.get("forecast_direction") or decision.get("forecast_direction"))
        forecast_conf = _safe_float(payload.get("forecast_confidence", decision.get("forecast_confidence", raw_bias_conf)), raw_bias_conf)
        if 0.0 <= forecast_conf <= 1.0:
            forecast_conf *= 100.0

        display_conf = final_conf if final_conf > 0.0 else raw_bias_conf
        display_forecast_conf = forecast_conf

        if edge_label == "NO_EDGE" or edge_score <= 0.0:
            display_conf = min(display_conf, 39.0)
        elif edge_label == "WEAK":
            display_conf = min(display_conf, 55.0)

        if (not trade_authorized) or action in {"WAIT", "WAIT_CONFIRMATION"}:
            display_conf = min(display_conf, 49.0 if edge_label != "NO_EDGE" else 39.0)

        if confirmation_ready > 0.0:
            display_conf = min(display_conf, confirmation_ready)

        if forecast_direction == "NEUTRAL":
            display_forecast_conf = min(display_forecast_conf, max(display_conf, 35.0))
        if edge_label == "NO_EDGE":
            display_forecast_conf = min(display_forecast_conf, 59.0)

        decision["bias_confidence_raw"] = round(raw_bias_conf, 1)
        decision["confidence_pct"] = round(max(0.0, min(display_conf, 100.0)), 1)
        decision["confidence"] = decision["confidence_pct"]
        decision["forecast_confidence_effective"] = round(max(0.0, min(display_forecast_conf, 100.0)), 1)
        if "forecast_confidence" in payload:
            payload["forecast_confidence"] = decision["forecast_confidence_effective"]
        decision["consistency_guard_applied"] = True
        return decision
    except Exception:
        return decision


def _apply_manager_action_guard(decision: Dict[str, Any]) -> Dict[str, Any]:
    try:
        edge_block = decision.get("edge_score_data") if isinstance(decision.get("edge_score_data"), dict) else {}
        arming = decision.get("arming_logic") if isinstance(decision.get("arming_logic"), dict) else {}

        edge_score = _safe_float(edge_block.get("score", decision.get("edge_score", 0.0)), 0.0)
        trade_authorized = bool(decision.get("trade_authorized"))
        lifecycle = _safe_str(decision.get("lifecycle"), "").upper()
        confirmation_ready = _safe_float(arming.get("confirmation_ready"), 0.0)

        if (not trade_authorized) or edge_score <= 0.0 or lifecycle == "NO_TRADE" or confirmation_ready <= 0.0:
            existing_manager_action = _safe_str(decision.get("manager_action"), "").upper()
            close_now = bool(decision.get("close_now"))
            partial_reduce_now = bool(decision.get("partial_reduce_now"))
            if close_now or existing_manager_action.startswith(("REDUCE_", "INVALIDATE_", "RUNNER_EXIT_")) or lifecycle == "EXIT":
                decision["manager_action"] = existing_manager_action or "REDUCE_RISK"
                decision["manager_action_text"] = decision.get("manager_action_text") or ("ЛУЧШЕ ЗАКРЫТЬ" if close_now else "СОКРАТИТЬ РИСК")
            elif partial_reduce_now:
                decision["manager_action"] = existing_manager_action or "REDUCE_RISK"
                decision["manager_action_text"] = decision.get("manager_action_text") or "СОКРАТИТЬ РИСК"
            else:
                decision["manager_action"] = "WAIT"
                decision["manager_action_text"] = "ЖДАТЬ"
            decision["action"] = "WAIT"
            decision["action_text"] = "ЖДАТЬ"
            decision["trade_authorized"] = False
            decision["manager_reason"] = "execution не разрешён"
        return decision
    except Exception:
        return decision


def _apply_best_trade_guard(decision: Dict[str, Any]) -> Dict[str, Any]:
    try:
        trade_authorized = bool(decision.get("trade_authorized"))
        bot_mode = _safe_str(decision.get("bot_mode") or (decision.get("execution_verdict") or {}).get("bot_mode") if isinstance(decision.get("execution_verdict"), dict) else decision.get("bot_mode"), "").upper()
        if (not trade_authorized) and bot_mode not in {"READY_SMALL", "READY_SMALL_REDUCED", "CARD_SMALL"}:
            decision["best_trade_play"] = "wait"
            decision["best_trade_side"] = "FLAT"
            decision["best_trade_score"] = 0.0
            decision["action_now"] = "WAIT"
        return decision
    except Exception:
        return decision


def _apply_fake_move_decision_modifier(decision: Dict[str, Any], fake_move: Dict[str, Any]) -> Dict[str, Any]:
    try:
        fake_type = str(fake_move.get("type") or "NONE").upper()
        confirmed = bool(fake_move.get("confirmed"))
        execution_mode = str(fake_move.get("execution_mode") or "").upper()
        if fake_type == "FAKE_UP" and confirmed:
            decision["action"] = "WATCH_SHORT"
            decision["action_text"] = "СМОТРЕТЬ ШОРТ"
            decision["direction"] = "SHORT"
            decision["direction_text"] = "ШОРТ"
        elif fake_type == "FAKE_DOWN" and confirmed:
            decision["action"] = "WATCH_LONG"
            decision["action_text"] = "СМОТРЕТЬ ЛОНГ"
            decision["direction"] = "LONG"
            decision["direction_text"] = "ЛОНГ"
        elif execution_mode == "AVOID_COUNTERTREND_SHORT":
            decision["avoid_countertrend_short"] = True
        elif execution_mode == "AVOID_COUNTERTREND_LONG":
            decision["avoid_countertrend_long"] = True
        return decision
    except Exception:
        return decision

def _score_to_bias_label(long_score: float, short_score: float) -> str:
    diff = float(long_score) - float(short_score)
    ad = abs(diff)
    if ad < 3:
        return "NEUTRAL"
    return "LONG" if diff > 0 else "SHORT"



def _market_regime_text(regime: str) -> str:
    mapping = {
        "trend_continuation": "ПРОДОЛЖЕНИЕ ТРЕНДА",
        "trend_exhaustion": "ВЫДЫХАНИЕ ТРЕНДА",
        "breakout_attempt": "ПОПЫТКА ПРОБОЯ",
        "failed_breakout": "ЛОЖНЫЙ ПРОБОЙ",
        "range_rotation": "РОТАЦИЯ В ДИАПАЗОНЕ",
        "compression": "СЖАТИЕ",
        "panic_impulse": "ПАНИЧЕСКИЙ ИМПУЛЬС",
        "recovery": "ВОССТАНОВЛЕНИЕ",
        "directional_bias": "НАПРАВЛЕННЫЙ ПЕРЕКОС",
        "range": "РОТАЦИЯ В ДИАПАЗОНЕ",
        "trend": "НАПРАВЛЕННЫЙ ПЕРЕКОС",
        "transition": "ПЕРЕХОДНЫЙ РЕЖИМ",
    }
    return mapping.get(str(regime or "").lower(), "")


def _resolve_regime_lock(
    market_regime: Any,
    range_position: Any,
    impulse_state: Any,
    direction: Any,
    market_state: Any,
    summary: Any,
    confidence: Any,
) -> Dict[str, Any]:
    regime_key = _safe_str(market_regime, "").lower().strip()
    regime_text = _market_regime_text(regime_key)
    direction_norm = _normalize_direction(direction)
    range_pos = _safe_str(range_position, "").upper()
    impulse = _safe_str(impulse_state, "").upper()
    state = _safe_str(market_state, "").upper()
    conf = _safe_float(confidence, 0.0)

    if regime_text:
        bias = direction_norm if direction_norm in {"LONG", "SHORT"} else "NEUTRAL"
        summary_text = _safe_str(summary, "").strip() or "режим взят из analysis/signal слоя"
        return {
            "regime": regime_key or "transition",
            "text": regime_text,
            "bias": _direction_text(bias),
            "confidence": round(conf, 1) if conf > 0 else None,
            "summary": summary_text,
        }

    if range_pos == "MID" or state in {"NEUTRAL", "CONFLICTED"}:
        return {
            "regime": "range_rotation",
            "text": "РОТАЦИЯ В ДИАПАЗОНЕ",
            "bias": _direction_text(direction_norm if direction_norm in {"LONG", "SHORT"} else "NEUTRAL"),
            "confidence": round(max(conf, 55.0 if range_pos == "MID" else 45.0), 1),
            "summary": "regime lock: цена внутри диапазона, поэтому базовый режим принудительно RANGE",
        }

    if impulse in {"IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE", "BULLISH_BUILDING", "BEARISH_BUILDING"} and direction_norm in {"LONG", "SHORT"}:
        return {
            "regime": "directional_bias",
            "text": "НАПРАВЛЕННЫЙ ПЕРЕКОС",
            "bias": _direction_text(direction_norm),
            "confidence": round(max(conf, 60.0), 1),
            "summary": "regime lock: активный импульс и directional bias совпадают",
        }

    return {
        "regime": "transition",
        "text": "ПЕРЕХОДНЫЙ РЕЖИМ",
        "bias": _direction_text(direction_norm if direction_norm in {"LONG", "SHORT"} else "NEUTRAL"),
        "confidence": round(max(conf, 40.0), 1),
        "summary": "regime lock: явного трендового режима нет, рынок в переходной фазе",
    }

def _action_text(action: str) -> str:
    return {
        "ENTER": "ВХОДИТЬ",
        "ENTER_LONG": "ВХОД В ЛОНГ",
        "ENTER_SHORT": "ВХОД В ШОРТ",
        "WATCH": "СМОТРЕТЬ СЕТАП",
        "WATCH_LONG": "СМОТРЕТЬ ЛОНГ-СЕТАП",
        "WATCH_SHORT": "СМОТРЕТЬ ШОРТ-СЕТАП",
        "WAIT": "ЖДАТЬ",
        "WAIT_CONFIRMATION": "ЖДАТЬ ПОДТВЕРЖДЕНИЕ",
        "WAIT_PULLBACK": "ЖДАТЬ ОТКАТ",
        "WAIT_RANGE_EDGE": "ЖДАТЬ КРАЙ ДИАПАЗОНА",
        "ADD_LONG": "ДОБАВЛЯТЬ ЛОНГ",
        "ADD_SHORT": "ДОБАВЛЯТЬ ШОРТ",
        "REDUCE_SHORT": "СОКРАЩАТЬ ШОРТ",
        "REDUCE_LONG": "СОКРАЩАТЬ ЛОНГ",
        "HOLD_LONG": "ДЕРЖАТЬ ЛОНГ",
        "HOLD_SHORT": "ДЕРЖАТЬ ШОРТ",
        "PARTIAL_LONG": "ЧАСТИЧНО ФИКСИРОВАТЬ ЛОНГ",
        "PARTIAL_SHORT": "ЧАСТИЧНО ФИКСИРОВАТЬ ШОРТ",
        "MOVE_BE_LONG": "ПЕРЕВЕСТИ ЛОНГ В БЕ",
        "MOVE_BE_SHORT": "ПЕРЕВЕСТИ ШОРТ В БЕ",
        "INVALIDATE_LONG": "ОТМЕНИТЬ ЛОНГ-СЦЕНАРИЙ",
        "INVALIDATE_SHORT": "ОТМЕНИТЬ ШОРТ-СЦЕНАРИЙ",
        "RUNNER_HOLD_LONG": "ТЯНУТЬ ОСТАТОК ЛОНГА",
        "RUNNER_HOLD_SHORT": "ТЯНУТЬ ОСТАТОК ШОРТА",
        "RUNNER_TRAIL_LONG": "ПОДТЯГИВАТЬ ЗАЩИТУ ЛОНГА",
        "RUNNER_TRAIL_SHORT": "ПОДТЯГИВАТЬ ЗАЩИТУ ШОРТА",
        "RUNNER_EXIT_LONG": "ЗАКРЫТЬ ОСТАТОК ЛОНГА",
        "RUNNER_EXIT_SHORT": "ЗАКРЫТЬ ОСТАТОК ШОРТА",
        "ENTER_AGGRESSIVE_LONG": "ВХОДИТЬ В ЛОНГ АГРЕССИВНЕЕ",
        "ENTER_AGGRESSIVE_SHORT": "ВХОДИТЬ В ШОРТ АГРЕССИВНЕЕ",
        "NO_TRADE": "ЖДАТЬ",
    }.get(action, "ЖДАТЬ")


def _extract_range_state(data: Dict[str, Any]) -> str:
    return _safe_str(data.get("range_state") or (data.get("range") or {}).get("state") or "", "")


def _extract_range_position(data: Dict[str, Any], range_state: str) -> str:
    explicit = _safe_str(data.get("range_position") or "").upper()
    if explicit:
        return explicit
    rs = _safe_str(range_state).lower()
    if "ниж" in rs or "lower" in rs:
        return "LOWER_PART"
    if "верх" in rs or "upper" in rs:
        return "UPPER_PART"
    if "серед" in rs or "middle" in rs:
        return "MID"
    return "UNKNOWN"




def _bot_side_from_key(key: Any) -> str:
    key_s = _safe_str(key).lower()
    if key_s.endswith("long"):
        return "LONG"
    if key_s.endswith("short"):
        return "SHORT"
    return "NEUTRAL"


def _edge_activation_state(edge_label: Any, edge_action: Any, item_side: Any, edge_side: Any, execution_verdict: Optional[Dict[str, Any]] = None, bot_key: Any = None) -> str:
    label = _safe_str(edge_label, "NO_EDGE").upper()
    action = _safe_str(edge_action, "NO_TRADE").upper()
    side = _normalize_direction(item_side)
    gated_side = _normalize_direction(edge_side)
    bot_key_s = _safe_str(bot_key).lower()
    verdict = execution_verdict if isinstance(execution_verdict, dict) else {}
    verdict_status = _safe_str(verdict.get("status"), "NOT_AUTHORIZED").upper()

    if bot_key_s.startswith("range") and verdict_status in {"SOFT_RANGE_ALLOWED", "SOFT_RANGE_REDUCED"}:
        return "SOFT_READY"
    if label == "NO_EDGE" or action == "NO_TRADE":
        return "OFF"
    if gated_side in {"LONG", "SHORT"} and side in {"LONG", "SHORT"} and side != gated_side:
        return "OFF"
    if label in {"WEAK", "WORKABLE"} or action in {"WATCH_CONFIRMATION", "WAIT_BETTER_LOCATION", "SCALP_ONLY"}:
        return "WAIT"
    if label == "STRONG" and action == "CAN_EXECUTE":
        return "ARMED"
    return "WAIT"


def _apply_edge_gate_to_bot_cards(cards: Any, edge_label: Any, edge_action: Any, edge_side: Any, execution_verdict: Optional[Dict[str, Any]] = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in cards or []:
        card = dict(raw) if isinstance(raw, dict) else {}
        side = _bot_side_from_key(card.get("bot_key"))
        activation = _edge_activation_state(edge_label, edge_action, side, edge_side, execution_verdict, card.get("bot_key"))
        card["activation_state"] = activation
        note = _safe_str(card.get("note"), "").strip()
        reasons = []
        if activation == "OFF":
            card["status"] = "OFF"
            card["plan_state"] = "WAIT"
            card["management_action"] = "CANCEL SCENARIO"
            card["can_add"] = False
            card["small_entry_only"] = False
            card["aggressive_entry_ok"] = False
            card["entry_instruction"] = "бот не активировать: edge-логика сейчас не даёт рабочий запуск"
            if side in {"LONG", "SHORT"} and _normalize_direction(edge_side) in {"LONG", "SHORT"} and side != _normalize_direction(edge_side):
                reasons.append("сторона не совпадает с edge-side")
            else:
                reasons.append("edge слишком слабый для активации")
        elif activation in {"WAIT", "SOFT_READY"}:
            card["status"] = "WATCH"
            card["plan_state"] = "WAIT"
            card["management_action"] = "WAIT EDGE"
            card["can_add"] = False
            card["aggressive_entry_ok"] = False
            if str(card.get("bot_key") or "").startswith("range") and isinstance(execution_verdict, dict) and str(execution_verdict.get("status") or "").upper() in {"SOFT_RANGE_ALLOWED", "SOFT_RANGE_REDUCED"}:
                verdict_status = str(execution_verdict.get("status") or "").upper()
                card["status"] = "SOFT_READY"
                card["plan_state"] = "READY_SMALL_REDUCED" if verdict_status == "SOFT_RANGE_REDUCED" else "READY_SMALL"
                card["management_action"] = "ENABLE SMALL SIZE REDUCED" if verdict_status == "SOFT_RANGE_REDUCED" else "ENABLE SMALL SIZE"
                card["entry_instruction"] = str(execution_verdict.get("reason") or "range-режим допускает только маленький тестовый вход")
                card["small_entry_only"] = True
                card["soft_ready"] = True
                reasons.append("soft execution verdict: допустим только маленький запуск range-бота")
            else:
                card["entry_instruction"] = "ждать подтверждение / лучший край диапазона: edge ещё не готов к активации"
                reasons.append("edge есть, но пока только режим ожидания")
        else:
            if _safe_str(card.get("status"), "OFF").upper() == "OFF" and _safe_float(card.get("score"), 0.0) >= 0.25:
                card["status"] = "WATCH"
            reasons.append("edge допускает arm-состояние для этой стороны")
        merged = "; ".join([x for x in [note, *reasons] if x])
        if merged:
            card["note"] = merged
        result.append(card)
    return result


def _apply_edge_gate_to_unified_matrix(items: Any, edge_label: Any, edge_action: Any, edge_side: Any, execution_verdict: Optional[Dict[str, Any]] = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in items or []:
        item = dict(raw) if isinstance(raw, dict) else {}
        activation = _edge_activation_state(edge_label, edge_action, item.get("side"), edge_side, execution_verdict, item.get("bot_key") or item.get("label"))
        item["activation_state"] = activation
        comment = _safe_str(item.get("comment"), "").strip()
        if activation == "OFF":
            item["status"] = "OFF"
            item["action"] = "ОТКЛЮЧИТЬ"
            gate_comment = "edge-фильтр: bot activation OFF"
        elif activation == "WAIT":
            item["status"] = "WAIT"
            item["action"] = "ЖДАТЬ"
            gate_comment = "edge-фильтр: bot activation WAIT"
        else:
            if _safe_str(item.get("status"), "OFF").upper() == "OFF":
                item["status"] = "WATCH"
            item["action"] = "ARMED"
            gate_comment = "edge-фильтр: bot activation ARMED"
        item["comment"] = "; ".join([x for x in [comment, gate_comment] if x])
        result.append(item)
    return result


def _apply_edge_gate_to_ladder(items: Any, side: str, edge_label: Any, edge_action: Any, edge_side: Any, execution_verdict: Optional[Dict[str, Any]] = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in items or []:
        item = dict(raw) if isinstance(raw, dict) else {}
        activation = _edge_activation_state(edge_label, edge_action, side, edge_side, execution_verdict, card.get("bot_key"))
        item["activation_state"] = activation
        item["status"] = activation
        result.append(item)
    return result


def _build_execution_verdict(data: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    range_state = _safe_str(data.get("range_state") or (data.get("range") or {}).get("state") or decision.get("range_state") or "", "").lower()
    range_position = _extract_range_position(decision, _extract_range_state(data) or decision.get("range_position") or "")
    grid = data.get("grid_strategy") if isinstance(data.get("grid_strategy"), dict) else {}
    deviation = _safe_float(grid.get("deviation_abs_pct") or data.get("impulse_move_pct") or 0.0, 0.0)
    trap_risk = _safe_str(decision.get("trap_risk") or decision.get("risk_level") or "MEDIUM", "MEDIUM").upper()
    late_entry_risk = _safe_str(decision.get("late_entry_risk") or "MEDIUM", "MEDIUM").upper()
    impulse_state = _safe_str(decision.get("impulse_state") or data.get("impulse_state") or "NO_CLEAR_IMPULSE", "NO_CLEAR_IMPULSE").upper()
    edge_label = _safe_str(decision.get("edge_label"), "NO_EDGE").upper()
    edge_action = _safe_str(decision.get("edge_action"), "NO_TRADE").upper()
    mode = _safe_str(decision.get("mode") or decision.get("regime"), "MIXED").upper()

    range_detected = ("range" in range_state or "диапаз" in range_state or range_position in {"LOWER_PART", "UPPER_PART", "LOW_EDGE", "HIGH_EDGE", "MID"})
    near_edge = range_position in {"LOWER_PART", "UPPER_PART", "LOW_EDGE", "HIGH_EDGE"}
    in_mid = range_position == "MID"
    impulse_faded = impulse_state in {"NO_CLEAR_IMPULSE", "RANGE_NO_IMPULSE", "RANGE", "PENDING_CONFIRMATION", "IMPULSE_UNCERTAIN"}
    rotation_quality = "GOOD" if impulse_faded and (near_edge or deviation <= 0.35) else "OK" if impulse_faded else "BAD"
    reduced = trap_risk == "HIGH" or late_entry_risk == "HIGH"
    soft_range_allowed = bool(
        mode == "RANGE"
        and range_detected
        and in_mid
        and impulse_faded
        and rotation_quality in {"GOOD", "OK"}
        and deviation <= 0.55
        and trap_risk != "HIGH"
        and late_entry_risk != "HIGH"
        and edge_label in {"WEAK", "WORKABLE", "STRONG"}
        and edge_action not in {"NO_TRADE", "WAIT_BETTER_LOCATION"}
    )

    if in_mid and edge_label == "NO_EDGE":
        # keep bots armed in the middle of the range when there is a directional idea,
        # but do not authorize a real trade yet.
        directional_hint = _normalize_direction(decision.get("direction") or decision.get("direction_text") or data.get("forecast_direction"))
        if directional_hint in {"LONG", "SHORT"}:
            status = "SOFT_WAIT"
            reason = "середина диапазона: реальный вход рано, но сценарий стоит держать armed до reclaim/ложного выноса"
            size_multiplier = 0.25
            adds_allowed = False
        else:
            status = "NOT_AUTHORIZED"
            reason = "цена в середине диапазона и edge отсутствует: вход не разрешён"
            size_multiplier = 0.30
            adds_allowed = False
    elif edge_label == "STRONG" and edge_action == "CAN_EXECUTE":
        status = "AUTHORIZED"
        reason = "edge подтверждён: сценарий можно исполнять"
        size_multiplier = 1.0
        adds_allowed = True
    elif soft_range_allowed:
        status = "SOFT_RANGE_REDUCED" if reduced else "SOFT_RANGE_ALLOWED"
        size_multiplier = 0.30 if reduced else 0.50
        adds_allowed = False
        reason = "разрешён мягкий range-сценарий внутри диапазона: только small size"
        if reduced:
            reason += "; breakout risk высокий, поэтому только reduced size без adds"
    elif edge_label in {"WEAK", "WORKABLE"} and edge_action in {"SCALP_ONLY", "WATCH_CONFIRMATION", "WAIT_BETTER_LOCATION"}:
        status = "SOFT_WAIT"
        reason = "edge слабый: допускается только сценарный режим ожидания / scalp without force"
        size_multiplier = 0.50 if mode == "RANGE" else 0.30
        adds_allowed = False
    else:
        status = "NOT_AUTHORIZED"
        reason = "edge ещё не даёт права на исполнение: разрешён только сценарный режим ожидания"
        size_multiplier = 0.30 if reduced else 0.50 if in_mid else 1.0
        adds_allowed = False

    trade_status = "AUTHORIZED" if status == "AUTHORIZED" else "NOT_AUTHORIZED"
    bot_label = {
        "AUTHORIZED": "AUTHORIZED",
        "SOFT_RANGE_ALLOWED": "SOFT_AUTHORIZED",
        "SOFT_RANGE_REDUCED": "REDUCED_ONLY",
        "SOFT_WAIT": "WATCHLIST",
        "NOT_AUTHORIZED": "NOT_AUTHORIZED",
    }.get(status, "NOT_AUTHORIZED")
    bot_status = bot_label
    return {
        "status": status,
        "trade_status": trade_status,
        "bot_status": bot_status,
        "authorized": status == "AUTHORIZED",
        "soft_allowed": status in {"SOFT_RANGE_ALLOWED", "SOFT_RANGE_REDUCED", "SOFT_WAIT"},
        "trade_authorized": status == "AUTHORIZED",
        "bot_authorized": status in {"AUTHORIZED", "SOFT_RANGE_ALLOWED", "SOFT_RANGE_REDUCED", "SOFT_WAIT"},
        "bot_mode": "READY_SMALL_REDUCED" if status == "SOFT_RANGE_REDUCED" else "READY_SMALL" if status == "SOFT_RANGE_ALLOWED" else "ARMED" if status in {"AUTHORIZED", "SOFT_WAIT"} else "WAIT",
        "bot_state_label": bot_label,
        "size_multiplier": round(size_multiplier, 2),
        "adds_allowed": adds_allowed,
        "range_detected": range_detected,
        "rotation_quality": rotation_quality,
        "reason": reason,
        "trade_edge_score": 100.0 if status == "AUTHORIZED" else 35.0 if status == "SOFT_WAIT" else 0.0,
        "bot_edge_score": 65.0 if status == "SOFT_RANGE_ALLOWED" else 55.0 if status == "SOFT_RANGE_REDUCED" else 80.0 if status == "AUTHORIZED" else 32.0 if status == "SOFT_WAIT" else 0.0,
    }


def _manager_action_from_activation(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    execution_bias = _safe_str(payload.get("execution_bias"), "OFF").upper()
    best_status = _safe_str(payload.get("best_bot_status"), execution_bias).upper()
    edge_action = _safe_str(decision.get("edge_action"), "NO_TRADE").upper()
    current_action = _safe_str(decision.get("action"), "WAIT").upper()
    impulse_state = _safe_str(decision.get("impulse_state"), "NO_CLEAR_IMPULSE").upper()
    range_position = _safe_str(decision.get("range_position"), "").upper()
    decision_side = _normalize_direction(decision.get("direction") or decision.get("direction_text"))

    has_position = bool(
        payload.get("has_position")
        or payload.get("position_open")
        or (payload.get("position") or {}).get("has_position")
        or (payload.get("journal") or {}).get("has_active_trade")
        or (payload.get("journal") or {}).get("active")
    )
    position_side = _normalize_direction(
        payload.get("position_side")
        or (payload.get("position") or {}).get("side")
        or (payload.get("journal") or {}).get("side")
    )

    manager_action = "WAIT"
    manager_reason = "активной стороны сейчас нет: edge-фильтр держит систему в OFF"

    if best_status == "ARMED" or execution_bias == "ARMED":
        if edge_action == "CAN_EXECUTE":
            if current_action in {"ENTER", "ENTER_LONG", "ENTER_SHORT", "ADD_LONG", "ADD_SHORT"}:
                manager_action = current_action
                manager_reason = "бот ARMED и execution допускает активное исполнение"
            elif impulse_state in {"BULLISH_ACTIVE", "BEARISH_ACTIVE", "IMPULSE_CONTINUES"}:
                manager_action = "WATCH"
                manager_reason = "бот ARMED: есть рабочий edge, ждём локальный триггер без догонки"
            elif range_position == "MID":
                manager_action = "WAIT_RANGE_EDGE"
                manager_reason = "бот ARMED, но цена не у лучшего location: лучше дождаться края диапазона"
            else:
                manager_action = "WAIT_CONFIRMATION"
                manager_reason = "бот ARMED, но перед входом нужно подтверждение у уровня"
        elif edge_action == "WATCH_CONFIRMATION":
            manager_action = "WAIT_CONFIRMATION"
            manager_reason = "бот ARMED, но edge просит подтверждение перед входом"
        elif edge_action == "WAIT_BETTER_LOCATION":
            manager_action = "WAIT_RANGE_EDGE" if range_position == "MID" else "WAIT_PULLBACK"
            manager_reason = "бот ARMED, но location пока не лучший: нужен откат/край диапазона"
    elif best_status == "WAIT" or execution_bias == "WAIT":
        if edge_action == "WATCH_CONFIRMATION":
            manager_action = "WAIT_CONFIRMATION"
            manager_reason = "edge есть, но активация ещё не готова: нужен триггер подтверждения"
        elif edge_action == "WAIT_BETTER_LOCATION":
            manager_action = "WAIT_RANGE_EDGE" if range_position == "MID" else "WAIT_PULLBACK"
            manager_reason = "edge слабый: менеджер ждёт лучший location и не форсирует сценарий"
        elif current_action in {"WAIT_PULLBACK", "WAIT_RANGE_EDGE", "WAIT_CONFIRMATION"}:
            manager_action = current_action
            manager_reason = "текущая тактика сохранена, но activation_state не разрешает ускорять вход"
        else:
            manager_action = "WAIT"
            manager_reason = "activation_state=WAIT: сценарий только наблюдаем, без форсирования"

    if has_position:
        journal_obj = payload.get("journal") or {}
        position_obj = payload.get("position") or {}
        tp1_hit = bool(journal_obj.get("tp1_hit") or position_obj.get("tp1_hit"))
        partial_done = bool(journal_obj.get("partial_exit_done") or position_obj.get("partial_exit_done"))
        be_moved = bool(journal_obj.get("be_moved") or position_obj.get("be_moved"))
        tp2_hit = bool(journal_obj.get("tp2_hit") or position_obj.get("tp2_hit"))
        lifecycle_state = _safe_str(journal_obj.get("lifecycle_state") or position_obj.get("lifecycle_state"), "NO_TRADE").upper()
        runner_active = bool(journal_obj.get("runner_active") or position_obj.get("runner_active") or lifecycle_state == "HOLD_RUNNER")
        invalidation_type = _safe_str(decision.get("invalidation_type") or payload.get("invalidation_type"), "").lower()
        trap_risk = _safe_str(decision.get("trap_risk"), "MEDIUM").upper()
        location_quality = _safe_str(decision.get("location_quality"), "C").upper()

        if runner_active and position_side in {"LONG", "SHORT"}:
            if invalidation_type in {"structure_break", "level_break"} or (decision_side in {"LONG", "SHORT"} and decision_side != position_side):
                manager_action = f"RUNNER_EXIT_{position_side}"
                manager_reason = f"runner по {position_side} уже нельзя тянуть дальше: структура слабеет или рынок сместился против остатка"
            elif edge_action == "NO_TRADE" and trap_risk == "HIGH":
                manager_action = f"RUNNER_EXIT_{position_side}"
                manager_reason = f"для runner по {position_side} edge исчез и риск ловушки высокий: остаток лучше закрыть"
            elif be_moved and partial_done and (tp2_hit or impulse_state in {"BULLISH_ACTIVE", "BEARISH_ACTIVE", "IMPULSE_CONTINUES"}):
                manager_action = f"RUNNER_TRAIL_{position_side}"
                manager_reason = f"runner по {position_side} жив: логично подтягивать защиту и дать остатку работать"
            else:
                manager_action = f"RUNNER_HOLD_{position_side}"
                manager_reason = f"runner по {position_side} остаётся активным: держать остаток и не расширять риск"
            decision["runner_active"] = True
            decision["lifecycle_state"] = lifecycle_state
            decision["runner_mode"] = manager_action
            decision["manager_workflow"] = "auto_runner"
            decision["has_position"] = has_position
            decision["position_side"] = position_side
            decision["manager_action"] = manager_action
            decision["manager_action_text"] = _action_text(manager_action)
            decision["manager_reason"] = manager_reason
            return decision

        if position_side != "NEUTRAL" and decision_side == position_side:
            if invalidation_type in {"structure_break", "level_break"} or edge_action == "NO_TRADE":
                manager_action = f"INVALIDATE_{position_side}"
                manager_reason = f"сценарий {position_side} теряет структуру: лучше отменять идею и не ждать чудо-разворота"
            elif tp1_hit and not partial_done:
                manager_action = f"PARTIAL_{position_side}"
                manager_reason = f"по позиции {position_side} уже есть первый ход: логично снять часть и убрать эмоциональное давление"
            elif tp1_hit and partial_done and not be_moved:
                manager_action = f"MOVE_BE_{position_side}"
                manager_reason = f"часть уже зафиксирована по {position_side}: следующий шаг — защитить остаток переводом в безубыток"
            elif trap_risk == "HIGH" and location_quality in {"C", "D"}:
                manager_action = f"PARTIAL_{position_side}"
                manager_reason = f"позиция {position_side} ещё жива, но риск ловушки высокий: лучше частично разгрузиться"
            elif manager_action in {"WAIT", "WATCH", "WAIT_CONFIRMATION", "WAIT_PULLBACK", "WAIT_RANGE_EDGE"}:
                manager_action = f"HOLD_{position_side}"
                if edge_action == "CAN_EXECUTE" and best_status == "ARMED" and range_position != "MID":
                    manager_reason = f"позиция уже открыта по стороне {position_side}: базово держим; добор только по подтверждению у уровня"
                elif edge_action == "WAIT_BETTER_LOCATION":
                    manager_reason = f"позиция уже открыта по стороне {position_side}: не форсируем добор, ждём лучший location"
                else:
                    manager_reason = f"позиция уже открыта по стороне {position_side}: базовый режим hold, пока сценарий не сломан"
        elif position_side != "NEUTRAL" and decision_side in {"LONG", "SHORT"} and decision_side != position_side:
            manager_action = f"REDUCE_{position_side}"
            manager_reason = f"открыта позиция против нового bias ({position_side} против {decision_side}): лучше сокращать риск и не усреднять"
        elif position_side != "NEUTRAL" and decision_side == "NEUTRAL":
            if invalidation_type in {"structure_break", "level_break"}:
                manager_action = f"INVALIDATE_{position_side}"
                manager_reason = f"рынок нейтральный и структура {position_side} уже ломается: сценарий лучше отменить"
            elif tp1_hit and not partial_done:
                manager_action = f"PARTIAL_{position_side}"
                manager_reason = f"рынок ушёл в нейтраль, а первый ход уже был: разумно частично фиксировать {position_side}"
            elif tp1_hit and partial_done and not be_moved:
                manager_action = f"MOVE_BE_{position_side}"
                manager_reason = f"после partial по {position_side} лучше перевести остаток в безубыток"
            else:
                manager_action = f"HOLD_{position_side}" if best_status in {"WAIT", "ARMED"} else f"REDUCE_{position_side}"
                if best_status in {"WAIT", "ARMED"}:
                    manager_reason = f"на рынке нет новой активной стороны, но позиция {position_side} ещё не сломана: держать только аккуратно, без добавления"
                else:
                    manager_reason = f"рынок нейтральный и edge исчез: позицию {position_side} лучше сокращать, а не надеяться"

    decision["has_position"] = has_position
    decision["manager_workflow"] = "partial_be_invalidation"
    decision["position_side"] = position_side
    decision["manager_action"] = manager_action
    decision["manager_action_text"] = _action_text(manager_action)
    decision["manager_reason"] = manager_reason
    return decision


def _apply_edge_gate_to_payload(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    edge_label = decision.get("edge_label") or "NO_EDGE"
    edge_action = decision.get("edge_action") or "NO_TRADE"
    edge_side = decision.get("edge_side") or decision.get("direction") or decision.get("direction_text")

    execution_verdict = decision.get("execution_verdict") if isinstance(decision.get("execution_verdict"), dict) else {}
    cards = _apply_edge_gate_to_bot_cards(payload.get("bot_cards"), edge_label, edge_action, edge_side, execution_verdict)
    if cards:
        payload["bot_cards"] = cards

    matrix = _apply_edge_gate_to_unified_matrix(payload.get("unified_strategy_matrix"), edge_label, edge_action, edge_side, execution_verdict)
    if matrix:
        payload["unified_strategy_matrix"] = matrix

    deviation = dict(payload.get("deviation_ladder") or {})
    if deviation:
        deviation["long_ladder"] = _apply_edge_gate_to_ladder(deviation.get("long_ladder"), "LONG", edge_label, edge_action, edge_side, execution_verdict)
        deviation["short_ladder"] = _apply_edge_gate_to_ladder(deviation.get("short_ladder"), "SHORT", edge_label, edge_action, edge_side, execution_verdict)
        payload["deviation_ladder"] = deviation

    best_card = None
    for preferred_state in ("ARMED", "SOFT_READY", "WATCH", "WAIT"):
        for card in cards:
            if str(card.get("activation_state") or "").upper() == preferred_state:
                if best_card is None or _safe_float(card.get("score"), 0.0) > _safe_float(best_card.get("score"), 0.0):
                    best_card = card
        if best_card is not None:
            break

    if best_card is not None:
        payload["best_bot"] = best_card.get("bot_label")
        payload["best_bot_score"] = best_card.get("score")
        payload["best_bot_status"] = best_card.get("activation_state")
    else:
        payload["best_bot"] = "нет чистого кандидата"
        payload["best_bot_score"] = 0.0
        payload["best_bot_status"] = "OFF"

    activation_states = {str(card.get("activation_state") or "OFF").upper() for card in cards}
    if "ARMED" in activation_states:
        payload["execution_bias"] = "ARMED"
    elif "SOFT_READY" in activation_states:
        payload["execution_bias"] = "SOFT_READY"
    elif "WATCH" in activation_states:
        payload["execution_bias"] = "WATCHLIST"
    elif "WAIT" in activation_states:
        payload["execution_bias"] = "WAIT"
    else:
        payload["execution_bias"] = "OFF"

    if not cards or payload.get("execution_bias") == "OFF":
        payload["primary_bot"] = None
        payload["secondary_bot"] = None
        payload["primary_size_pct"] = 0
        payload["secondary_size_pct"] = 0

    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    if analysis is not None:
        analysis = dict(analysis)
        analysis["bot_cards"] = payload.get("bot_cards")
        analysis["unified_strategy_matrix"] = payload.get("unified_strategy_matrix")
        analysis["deviation_ladder"] = payload.get("deviation_ladder")
        analysis["best_bot"] = payload.get("best_bot")
        analysis["best_bot_score"] = payload.get("best_bot_score")
        analysis["best_bot_status"] = payload.get("best_bot_status")
        analysis["execution_bias"] = payload.get("execution_bias")
        payload["analysis"] = analysis
    return payload


def _forecast_strength_label(direction: str, confidence: float) -> str:
    direction = _normalize_direction(direction)
    confidence = _safe_float(confidence, 0.0)
    if 0.0 <= confidence <= 1.0:
        confidence *= 100.0
    if direction == "NEUTRAL" or confidence < 52.0:
        return "NEUTRAL"
    if confidence >= 70.0:
        return "STRONG"
    if confidence >= 58.0:
        return "MODERATE"
    return "WEAK"


def _normalize_impulse_state_name(state: str, direction: str = "NEUTRAL", confidence: float = 0.0) -> str:
    state = _safe_str(state, "").strip().upper()
    direction = _normalize_direction(direction)
    confidence = _safe_float(confidence, 0.0)
    if 0.0 <= confidence <= 1.0:
        confidence *= 100.0
    if state in {"", "UNKNOWN"}:
        if direction in {"LONG", "SHORT"} and confidence >= 52.0:
            return "PENDING_CONFIRMATION"
        return "NO_CLEAR_IMPULSE"
    return state

def _extract_impulse(data: Dict[str, Any]) -> Dict[str, Any]:
    impulse = data.get("impulse")
    if isinstance(impulse, dict):
        return impulse

    top_state = _safe_str(data.get("impulse_state"), "").upper()
    if top_state:
        return {
            "state": top_state,
            "score": _safe_float(data.get("impulse_strength"), 0.0),
            "strength": _safe_float(data.get("impulse_strength"), 0.0),
            "freshness": _safe_float(data.get("impulse_freshness"), 0.0),
            "exhaustion": _safe_float(data.get("impulse_exhaustion"), 0.0),
            "confirmation": _safe_float(data.get("impulse_confirmation"), 0.0),
            "can_enter": top_state in {"BULLISH_ACTIVE", "BEARISH_ACTIVE", "IMPULSE_CONTINUES"},
            "comment": _safe_str(data.get("impulse_comment"), ""),
            "watch_conditions": ["подтверждение следующей свечой", "реакция от уровня"],
        }

    fc = _safe_float(data.get("forecast_confidence"), 0.0)
    if 0.0 <= fc <= 1.0:
        fc *= 100.0
    bias = abs(_safe_float((data.get("stats") or {}).get("component_bias"), 0.0))
    pattern_bias = abs(_safe_float((data.get("analysis") or {}).get("pattern_bias"), _safe_float(data.get("pattern_bias"), 0.0)))
    long_score = _safe_float((data.get("decision") or {}).get("long_score"), 0.0)
    short_score = _safe_float((data.get("decision") or {}).get("short_score"), 0.0)
    if long_score <= 0.0 and short_score <= 0.0:
        proxy_long, proxy_short, proxy_bias, proxy_conf = _proxy_scores_from_bot_context(data)
        if proxy_long > 0.0 or proxy_short > 0.0:
            long_score, short_score = proxy_long, proxy_short
            if fc <= 0.0 and proxy_conf > 0.0:
                fc = proxy_conf
    score_gap = abs(long_score - short_score)
    forecast_direction = _normalize_direction(data.get("forecast_direction"))

    if fc >= 64 or bias >= 0.20 or score_gap >= 18:
        state = "BULLISH_ACTIVE" if forecast_direction == "LONG" else "BEARISH_ACTIVE" if forecast_direction == "SHORT" else "IMPULSE_CONTINUES"
        comment = "свежий импульс поддерживает текущую сторону"
    elif fc >= 54 or bias >= 0.10 or pattern_bias >= 0.08 or score_gap >= 10:
        state = "BULLISH_BUILDING" if forecast_direction == "LONG" else "BEARISH_BUILDING" if forecast_direction == "SHORT" else "CONFLICTED"
        comment = "импульс есть, но подтверждение пока слабое"
    elif score_gap < 6:
        state = "RANGE_NO_IMPULSE"
        comment = "внутри диапазона импульс слабый"
    else:
        state = "FADING"
        comment = "импульс затухает"

    return {
        "state": state,
        "score": max(fc, score_gap),
        "strength": max(0.0, min(max(fc / 100.0, bias * 2.5), 1.0)),
        "freshness": max(0.0, min(score_gap / 25.0, 1.0)),
        "exhaustion": 0.65 if state == "FADING" else 0.25 if state in {"BULLISH_BUILDING", "BEARISH_BUILDING", "CONFLICTED"} else 0.15,
        "confirmation": max(0.0, min(fc / 100.0, 1.0)),
        "can_enter": state in {"BULLISH_ACTIVE", "BEARISH_ACTIVE", "IMPULSE_CONTINUES"},
        "comment": comment,
        "watch_conditions": ["подтверждение следующей свечой", "реакция от уровня"],
    }


def _detect_market_state(direction: str, confidence: float, stats: Dict[str, Any], impulse_state: str) -> tuple[str, str]:
    component_bias = _safe_float(stats.get("component_bias"), 0.0)
    trend_score = _safe_float(stats.get("trend_score"), 0.0)
    stretch_score = _safe_float(stats.get("stretch_score"), 0.0)
    reversal_score = _safe_float(stats.get("reversal_score"), 0.0)
    location_score = _safe_float(stats.get("location_score"), 0.0)

    if direction == "NEUTRAL" and confidence <= 12 and abs(component_bias) < 0.05 and abs(reversal_score) < 0.08:
        return "NEUTRAL", "СЛАБЫЙ ПЕРЕВЕС / ЖДАТЬ ПОДТВЕРЖДЕНИЕ"
    if abs(component_bias) < 0.04 and confidence < 54:
        return "CONFLICTED", "КОНФЛИКТ ФАКТОРОВ"
    if direction == "NEUTRAL":
        return "NEUTRAL", "БЕЗ ПЕРЕВЕСА"
    if impulse_state == "IMPULSE_EXHAUSTING" and ((direction == "LONG" and reversal_score < -0.25) or (direction == "SHORT" and reversal_score > 0.25)):
        return "CONFLICTED", "ИМПУЛЬС ПРОТИВ СЕТАПА"
    if trend_score == 0 and location_score == 0 and stretch_score == 0:
        return "NEUTRAL", "СИГНАЛЫ СЛАБЫЕ / ЖДАТЬ НОВЫЙ СЕТАП"
    return "BIASED", "ЕСТЬ РАБОЧИЙ ПЕРЕВЕС"


def _setup_status(action: str, market_state: str, late_entry_risk: str) -> tuple[str, str]:
    if market_state == "UNKNOWN":
        return "WAIT", "ЖДАТЬ"
    if market_state == "CONFLICTED":
        return "INVALID", "КОНФЛИКТ / НЕ ЛЕЗТЬ"
    if action == "ENTER" and late_entry_risk == "LOW":
        return "VALID", "СЕТАП ВАЛИДЕН"
    if action in {"WATCH", "WAIT_CONFIRMATION", "WAIT_RANGE_EDGE"}:
        return "EARLY", "РАНО / НУЖНО ПОДТВЕРЖДЕНИЕ"
    if late_entry_risk == "HIGH" and action == "ENTER":
        return "LATE", "ПОЗДНИЙ ВХОД"
    return "WAIT", "ЖДАТЬ"


def _next_steps_for_no_trade(direction: str, range_position: str, impulse_state: str, false_break_signal: str) -> List[str]:
    steps: List[str] = []
    if range_position == "MID":
        steps.append("дождаться подхода цены к краю диапазона")
    if impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
        steps.append("не входить в догонку, дождаться отката")
    if direction == "LONG" and range_position in {"UPPER_PART", "HIGH_EDGE"}:
        steps.append("нужен retest или повторный выкуп после отката")
    if direction == "SHORT" and range_position in {"LOWER_PART", "LOW_EDGE"}:
        steps.append("нужен retest или повторное давление продавца после отката")
    if false_break_signal == "UP_TRAP":
        steps.append("смотреть подтверждение шорта после ложного пробоя вверх")
    elif false_break_signal == "DOWN_TRAP":
        steps.append("смотреть подтверждение лонга после ложного пробоя вниз")
    return steps[:4]


def _impulse_comment(impulse_state: str, direction: str, range_position: str = "UNKNOWN", range_state: str = "") -> str:
    if impulse_state in {"BULLISH", "BEARISH", "IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE"}:
        return "свежий импульс поддерживает текущую сторону" if direction != "NEUTRAL" else "на рынке есть движение, но сторона ещё не зафиксирована"
    if impulse_state in {"BULLISH_BUILDING", "BEARISH_BUILDING", "IMPULSE_UNCERTAIN", "CONFLICTED"}:
        return "импульс есть, но для входа всё ещё нужно подтверждение"
    if impulse_state in {"RANGE", "RANGE_NO_IMPULSE"}:
        range_state_l = _safe_str(range_state).lower()
        if range_position in {"HIGH_EDGE", "UPPER_PART"} or "верх" in range_state_l or "upper" in range_state_l:
            return "у верхней части диапазона импульс остаётся слабым и требует подтверждения"
        if range_position in {"LOW_EDGE", "LOWER_PART"} or "ниж" in range_state_l or "lower" in range_state_l:
            return "у нижней части диапазона импульс остаётся слабым и требует подтверждения"
        return "внутри диапазона импульс слабый и быстро гаснет"
    return "импульс выдыхается, лучше не заходить в догонку"


def _scenario_text(direction: str, range_position: str, impulse_state: str, false_break_signal: str, market_regime_bias: str = "NEUTRAL") -> str:
    market_regime_bias = _normalize_direction(market_regime_bias)
    if direction == "NEUTRAL" and market_regime_bias != "NEUTRAL":
        direction = market_regime_bias
    if direction == "LONG":
        if false_break_signal == "DOWN_TRAP":
            return "базовый сценарий: после ложного выноса вниз рынок может продолжить восстановление вверх"
        if range_position in {"LOW_EDGE", "LOWER_PART"}:
            return "базовый сценарий: покупатель защищает нижнюю часть диапазона, при подтверждении приоритет вверх"
        if impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
            return "базовый сценарий: уклон вверх сохраняется, но сначала нужен откат и новый выкуп"
        return "базовый сценарий: при удержании локальной структуры приоритет остаётся вверх"
    if direction == "SHORT":
        if false_break_signal == "UP_TRAP":
            return "базовый сценарий: после ложного выноса вверх рынок может продолжить снижение"
        if range_position in {"HIGH_EDGE", "UPPER_PART"}:
            return "базовый сценарий: продавец защищает верхнюю часть диапазона, при подтверждении приоритет вниз"
        if impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
            return "базовый сценарий: уклон вниз сохраняется, но сначала нужен откат и новый продавец"
        return "базовый сценарий: при удержании локальной структуры приоритет остаётся вниз"
    if range_position == "MID":
        return "базовый сценарий: пока рынок в середине диапазона, больше шансов на шум до подхода к краю"
    return "базовый сценарий: рынок без чистого перевеса, нужен новый собранный сетап"


def _trigger_text(direction: str, range_position: str, impulse_state: str, false_break_signal: str) -> str:
    if direction == "LONG":
        if false_break_signal == "DOWN_TRAP":
            return "триггер: возврат и удержание выше зоны ложного выноса вниз"
        if impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
            return "триггер: откат, удержание уровня и новый bullish impulse"
        return "триггер: удержание локального low и свеча продолжения вверх"
    if direction == "SHORT":
        if false_break_signal == "UP_TRAP":
            return "триггер: возврат и удержание ниже зоны ложного выноса вверх"
        if impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
            return "триггер: откат, удержание сопротивления и новый bearish impulse"
        return "триггер: удержание локального high продавцом и свеча продолжения вниз"
    if range_position == "MID":
        return "триггер: подход цены к краю диапазона или явный breakout с удержанием"
    return "триггер: появление явного directional-перевеса и подтверждающей свечи"


def _scenario_bundle(direction: str, range_position: str, impulse_state: str, false_break_signal: str, range_state: str = "") -> Dict[str, str]:
    range_state_l = _safe_str(range_state).lower()
    at_upper = range_position in {"HIGH_EDGE", "UPPER_PART"} or "верх" in range_state_l or "upper" in range_state_l
    at_lower = range_position in {"LOW_EDGE", "LOWER_PART"} or "ниж" in range_state_l or "lower" in range_state_l

    if direction == "LONG":
        base_case = _scenario_text(direction, range_position, impulse_state, false_break_signal)
        bull_case = "bull-case: удержание поддержки и подтверждающая свеча могут дать continuation вверх"
        bear_case = "bear-case: потеря поддержки и слабый retest отменят лонговый сценарий и вернут рынок к давлению вниз"
        invalidation = "инвалидация: закрепление ниже поддержки / low диапазона ломает long-сценарий"
        if at_upper:
            bull_case = "bull-case: только если покупатель удержит локальный high и не даст sharp rejection"
            bear_case = "bear-case: rejection от верхней части диапазона может быстро вернуть цену к mid"
        return {
            "base_case": base_case,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "trigger_up": _trigger_text("LONG", range_position, impulse_state, false_break_signal),
            "trigger_down": "триггер вниз: потеря поддержки и слабый retest после пробоя",
            "scenario_invalidation": invalidation,
        }

    if direction == "SHORT":
        base_case = _scenario_text(direction, range_position, impulse_state, false_break_signal)
        bull_case = "bull-case: только возврат выше сопротивления и удержание сломают short-идею"
        bear_case = "bear-case: rejection от сопротивления и свеча продолжения могут развить движение вниз"
        invalidation = "инвалидация: закрепление выше сопротивления / high диапазона ломает short-сценарий"
        if at_lower:
            bull_case = "bull-case: у нижней границы диапазона шорт опасен, возможен быстрый bounce к mid"
            bear_case = "bear-case: продолжение вниз требует пробоя и удержания ниже края диапазона"
        return {
            "base_case": base_case,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "trigger_up": "триггер вверх: возврат выше сопротивления и удержание после retest",
            "trigger_down": _trigger_text("SHORT", range_position, impulse_state, false_break_signal),
            "scenario_invalidation": invalidation,
        }

    base_case = _scenario_text(direction, range_position, impulse_state, false_break_signal)
    if at_upper:
        bull_case = "bull-case: только clean breakout и удержание выше верхней границы откроют continuation вверх"
        bear_case = "bear-case: rejection от верхней части диапазона вернёт рынок в short rotation к mid"
    elif at_lower:
        bull_case = "bull-case: защита нижней части диапазона может дать bounce к mid / upper band"
        bear_case = "bear-case: только пробой и удержание ниже поддержки дадут развитие вниз"
    else:
        bull_case = "bull-case: для роста нужен выход из середины диапазона и подтверждение покупателя"
        bear_case = "bear-case: для падения нужен выход из середины диапазона и подтверждение продавца"
    return {
        "base_case": base_case,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "trigger_up": "триггер вверх: пробой локального сопротивления и удержание после retest",
        "trigger_down": "триггер вниз: пробой локальной поддержки и удержание после retest",
        "scenario_invalidation": "инвалидация: пока цена в середине диапазона, оба сценария остаются неполными",
    }



def build_decision_block(
    signal_block: Dict[str, Any] | None = None,
    range_block: Dict[str, Any] | None = None,
    impulse_block: Dict[str, Any] | None = None,
    countertrend_block: Dict[str, Any] | None = None,
    analysis_block: Dict[str, Any] | None = None,
    stats_block: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal_block = signal_block or {}
    range_block = range_block or {}
    impulse_block = impulse_block or {}
    countertrend_block = countertrend_block or {}
    analysis_block = analysis_block or {}
    stats_block = stats_block or {}

    raw_signal = signal_block.get("final_signal") or signal_block.get("signal")
    confidence = _safe_float(signal_block.get("confidence"), 50.0)
    if 0.0 <= confidence <= 1.0:
        confidence *= 100.0
    impulse_state = _normalize_impulse_state_name(
        impulse_block.get("state"),
        signal_block.get("forecast_direction") or analysis_block.get("forecast_direction") or raw_signal,
        signal_block.get("forecast_confidence") or analysis_block.get("forecast_confidence") or confidence,
    )
    range_state = _safe_str(range_block.get("state"), "")
    range_position = _extract_range_position(range_block, range_state)
    edge_bias = _safe_str(range_block.get("edge_bias"), "NONE").upper()
    edge_score = _safe_float(range_block.get("edge_score"), 0.0)
    breakout_risk = _safe_str(range_block.get("breakout_risk"), "LOW").upper()
    ct_context = _safe_str(countertrend_block.get("context") or countertrend_block.get("bias"), "")
    false_break_signal = _safe_str(analysis_block.get("false_break_signal") or signal_block.get("false_break_signal"), "NONE").upper()
    trap_comment = _safe_str(signal_block.get("trap_comment") or analysis_block.get("trap_comment"), "")
    market_regime = _safe_str(analysis_block.get("market_regime") or signal_block.get("market_regime"), "")
    market_regime_bias = _normalize_direction(analysis_block.get("market_regime_bias") or signal_block.get("market_regime_bias"))
    market_regime_confidence = _safe_float(analysis_block.get("market_regime_confidence") or signal_block.get("market_regime_confidence"), 0.0)
    market_regime_summary = _safe_str(analysis_block.get("market_regime_summary") or signal_block.get("market_regime_summary"), "")

    reasons: List[str] = []
    mode_reasons: List[str] = []
    expectation: List[str] = []

    forced_long = _safe_float(analysis_block.get("forced_long_score") or stats_block.get("forced_long_score"), 0.0)
    forced_short = _safe_float(analysis_block.get("forced_short_score") or stats_block.get("forced_short_score"), 0.0)
    if forced_long > 0.0 or forced_short > 0.0:
        long_score = max(0.0, min(100.0, forced_long))
        short_score = max(0.0, min(100.0, forced_short))
    else:
        component_bias = _safe_float(stats_block.get("component_bias"), 0.0)
        reversal_score = _safe_float(stats_block.get("reversal_score"), 0.0)
        pattern_bias = _safe_float(analysis_block.get("pattern_bias"), 0.0)
        directional_edge = max(-1.0, min(1.0, component_bias * 0.76 + reversal_score * 0.12 + pattern_bias * 0.12))
        long_score = max(0.0, min(100.0, 50.0 + directional_edge * 42.0))
        short_score = max(0.0, min(100.0, 100.0 - long_score))

    if range_position in {"HIGH_EDGE", "UPPER_PART"}:
        short_score += 8.0 if edge_bias == "SHORT_EDGE" else 6.0
        long_score -= 10.0
    elif range_position in {"LOW_EDGE", "LOWER_PART"}:
        long_score += 8.0 if edge_bias == "LONG_EDGE" else 6.0
        short_score -= 10.0
    elif range_position == "MID":
        long_score -= 2.0
        short_score -= 2.0

    long_score = max(0.0, min(100.0, long_score))
    short_score = max(0.0, min(100.0, short_score))
    if abs(long_score - 50.0) < 0.001 and abs(short_score - 50.0) < 0.001:
        proxy_long, proxy_short, _proxy_bias, _proxy_conf = _proxy_scores_from_bot_context({**analysis_block, **signal_block, **range_block, **stats_block})
        if proxy_long > 0.0 or proxy_short > 0.0:
            long_score, short_score = proxy_long, proxy_short

    bias_direction = _score_to_bias_label(long_score, short_score)
    core_signal_direction = _normalize_direction(raw_signal)
    forecast_direction_now = _normalize_direction(signal_block.get("forecast_direction") or analysis_block.get("forecast_direction"))
    forecast_conf_now = _safe_float(signal_block.get("forecast_confidence") or analysis_block.get("forecast_confidence"), 0.0)
    if 0.0 <= forecast_conf_now <= 1.0:
        forecast_conf_now *= 100.0
    score_gap_now = abs(long_score - short_score)
    range_state_now = _safe_str(range_block.get("state") or "", "").lower()
    in_mid_zone = range_position == "MID" or ("серед" in range_state_now) or ("middle" in range_state_now)
    hard_neutral_lock = (
        core_signal_direction == "NEUTRAL"
        and forecast_direction_now == "NEUTRAL"
        and score_gap_now <= 3.0
        and confidence <= 15.0
        and impulse_state in {"NO_CLEAR_IMPULSE", "PENDING_CONFIRMATION", "IMPULSE_UNCERTAIN", "CONFLICTED", "RANGE_NO_IMPULSE", "RANGE"}
        and in_mid_zone
    )

    direction = core_signal_direction
    if hard_neutral_lock:
        direction = "NEUTRAL"
        bias_direction = "NEUTRAL"
    elif direction == "NEUTRAL" and bias_direction != "NEUTRAL":
        direction = bias_direction
    direction_text = _direction_text(direction)

    if hard_neutral_lock:
        reasons.append("Score сбалансированы, импульс не собран и цена в середине диапазона — directional edge нет.")
    elif direction == "LONG":
        reasons.append("По текущей логике есть перевес в лонг.")
    elif direction == "SHORT":
        reasons.append("По текущей логике есть перевес в шорт.")
    else:
        reasons.append("Явного directional-перевеса нет.")

    if market_regime == "trend_continuation" and direction != "NEUTRAL":
        confidence += 8
        reasons.append("Режим рынка поддерживает продолжение текущего направления.")
        expectation.append("базовый режим рынка поддерживает continuation")
    elif market_regime == "trend_exhaustion":
        confidence -= 6
        reasons.append("Режим рынка показывает признаки локального выдыхания тренда.")
        expectation.append("лучше искать подтверждение, а не входить в догонку")
    elif market_regime == "compression":
        confidence -= 7
        reasons.append("Рынок в сжатии: движение ещё не раскрылось.")
        expectation.append("сначала ждать выход из compression и подтверждение")
    elif market_regime == "range_rotation":
        confidence -= 4
        reasons.append("Режим рынка ближе к range rotation, чем к чистому тренду.")
        expectation.append("основной сценарий — работа от краёв диапазона")

    if impulse_state in {"IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE"}:
        confidence += 10
        reasons.append("Импульс поддерживает текущее направление.")
        expectation.append("движение может продолжиться без глубокого отката")
    elif impulse_state in {"IMPULSE_UNCERTAIN", "BULLISH_BUILDING", "BEARISH_BUILDING", "CONFLICTED"}:
        reasons.append("Импульс есть, но без чистого подтверждения.")
        expectation.append("нужна реакция от уровня или свеча подтверждения")
    elif impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
        confidence -= 15
        reasons.append("Импульс затухает, вход в догонку рискованный.")
        expectation.append("лучше ждать откат или новый импульс")

    trend_context = market_regime == "trend_continuation" or impulse_state in {"IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE"}
    mode = "TREND" if trend_context and breakout_risk == "LOW" else "RANGE"
    location_quality = "C"
    if range_position == "MID":
        mode = "RANGE"
        mode_reasons.append("Цена находится в середине диапазона — edge нет.")
        confidence -= 12
    elif range_position in {"LOW_EDGE", "LOWER_PART"} and direction == "LONG":
        mode_reasons.append("Лонг рассматривается ближе к нижней части диапазона.")
        confidence += 7
        location_quality = "A" if range_position == "LOW_EDGE" else "B"
    elif range_position in {"HIGH_EDGE", "UPPER_PART"} and direction == "SHORT":
        mode_reasons.append("Шорт рассматривается ближе к верхней части диапазона.")
        confidence += 7
        location_quality = "A" if range_position == "HIGH_EDGE" else "B"
    elif range_position in {"LOW_EDGE", "HIGH_EDGE"}:
        mode_reasons.append("Цена у края диапазона, но в сторону входа edge слабый.")
        location_quality = "B"
        confidence -= 4
    else:
        location_quality = "C"

    if false_break_signal == "UP_TRAP":
        reasons.append("Есть риск trap после ложного выноса вверх.")
        expectation.append("если продавец удержит возврат под high, шорт станет качественнее")
    elif false_break_signal == "DOWN_TRAP":
        reasons.append("Есть риск trap после ложного выноса вниз.")
        expectation.append("если покупатель удержит возврат над low, лонг станет качественнее")

    if ct_context:
        expectation.append(ct_context)

    confidence = max(0.0, min(100.0, confidence))

    late_entry_risk = "MEDIUM"
    if impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
        late_entry_risk = "MEDIUM" if direction != "NEUTRAL" and range_position in {"LOW_EDGE", "LOWER_PART", "HIGH_EDGE", "UPPER_PART"} else "HIGH"
    elif location_quality == "A" and impulse_state != "IMPULSE_EXHAUSTING":
        late_entry_risk = "LOW"
    elif direction == "LONG" and range_position in {"UPPER_PART", "HIGH_EDGE"}:
        late_entry_risk = "HIGH"
    elif direction == "SHORT" and range_position in {"LOWER_PART", "LOW_EDGE"}:
        late_entry_risk = "HIGH"

    market_state, market_state_text = _detect_market_state(direction, confidence, stats_block, impulse_state)

    trap_risk = "MEDIUM"
    if false_break_signal in {"UP_TRAP", "DOWN_TRAP"}:
        trap_risk = "HIGH"
    elif market_state == "CONFLICTED" or late_entry_risk == "HIGH":
        trap_risk = "HIGH"
    elif breakout_risk == "HIGH" and direction == "NEUTRAL":
        trap_risk = "HIGH"
    elif location_quality == "A" and impulse_state == "IMPULSE_UNCERTAIN":
        trap_risk = "LOW"

    no_trade_reasons: List[str] = []
    execution_hints: List[str] = []
    if market_state == "UNKNOWN":
        no_trade_reasons.append("перевес пока слишком слабый или не подтверждён")
        execution_hints.append("лучше ждать новый собранный сетап, а не интерпретировать шум")
    if market_state == "CONFLICTED":
        no_trade_reasons.append("факторы конфликтуют между собой")
        execution_hints.append("нужно исчезновение конфликта между trend / reversal / location")
    if range_position == "MID":
        no_trade_reasons.append("цена в середине диапазона, edge слабый")
        execution_hints.append("лучше дождаться подхода к краю диапазона")
    if late_entry_risk == "HIGH":
        no_trade_reasons.append("вход уже выглядит поздним")
        execution_hints.append("не входить в догонку, лучше ждать pullback / re-entry")
    if trap_risk == "HIGH":
        no_trade_reasons.append("повышен риск ловушки / ложного пробоя")
        execution_hints.append("без подтверждения лучше не рассчитывать на hold, только scalp/partial")

    if direction == "NEUTRAL":
        action = "WAIT"
    elif false_break_signal == "UP_TRAP" and direction == "SHORT":
        action = "WATCH" if impulse_state != "IMPULSE_CONTINUES" else "ENTER"
    elif false_break_signal == "DOWN_TRAP" and direction == "LONG":
        action = "WATCH" if impulse_state != "IMPULSE_CONTINUES" else "ENTER"
    elif range_position == "MID":
        action = "WAIT_RANGE_EDGE"
    elif impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
        action = "WAIT_PULLBACK"
    elif confidence >= 63 and late_entry_risk != "HIGH" and trap_risk != "HIGH":
        action = "ENTER"
    elif confidence >= 50:
        action = "WATCH"
    else:
        action = "WAIT"

    risk = "HIGH" if range_position == "MID" or confidence < 50 or trap_risk == "HIGH" else "MEDIUM"
    if confidence >= 75 and action == "ENTER" and location_quality == "A":
        risk = "LOW"

    forecast_dir = forecast_direction_now
    forecast_conf = forecast_conf_now
    if 0.0 <= forecast_conf <= 1.0:
        forecast_conf *= 100.0
    if not hard_neutral_lock and direction == "NEUTRAL" and bias_direction != "NEUTRAL":
        direction = bias_direction
    if range_position in {"HIGH_EDGE", "UPPER_PART"} and direction == "SHORT":
        short_score = min(100.0, short_score + 3.0)
        long_score = max(0.0, long_score - 4.0)
    elif range_position in {"LOW_EDGE", "LOWER_PART"} and direction == "LONG":
        long_score = min(100.0, long_score + 3.0)
        short_score = max(0.0, short_score - 4.0)
    if not hard_neutral_lock and direction == "NEUTRAL" and forecast_dir in {"LONG", "SHORT"} and forecast_conf >= 54.0:
        direction = forecast_dir
        confidence = max(confidence, round(forecast_conf * 0.72, 1))
    direction_text = _direction_text(direction)

    if direction == "LONG":
        long_score = min(100.0, max(long_score, confidence))
        short_score = max(0.0, min(short_score, 100.0 - confidence * 0.65))
    elif direction == "SHORT":
        short_score = min(100.0, max(short_score, confidence))
        long_score = max(0.0, min(long_score, 100.0 - confidence * 0.65))

    bias_direction = _score_to_bias_label(long_score, short_score)
    # Do not promote NEUTRAL into a trade direction at the tail end.
    # Score bias is already considered earlier before action/risk/setup are built.
    if direction in {"LONG", "SHORT"}:
        direction_text = _direction_text(direction)

    setup_status, setup_status_text = _setup_status(action, market_state, late_entry_risk)

    entry_type = "no_trade"
    if false_break_signal == "UP_TRAP" and direction == "SHORT":
        entry_type = "reversal"
    elif false_break_signal == "DOWN_TRAP" and direction == "LONG":
        entry_type = "reversal"
    elif action == "ENTER":
        entry_type = "breakout" if impulse_state in {"IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE"} else "pullback"

    execution_mode = "conservative"
    if action == "ENTER" and risk == "LOW":
        execution_mode = "aggressive"
    elif action in {"ENTER", "WATCH"}:
        execution_mode = "balanced"
    elif action == "WAIT_RANGE_EDGE":
        execution_mode = "defensive"

    no_trade_reasons = list(dict.fromkeys(no_trade_reasons))
    execution_hints = list(dict.fromkeys(execution_hints))
    no_trade_reason = "; ".join(no_trade_reasons[:3])

    scenario_bundle = _scenario_bundle(direction, range_position, impulse_state, false_break_signal, range_state)
    scenario_text = scenario_bundle.get("base_case", _scenario_text(direction, range_position, impulse_state, false_break_signal))
    trigger_text = _trigger_text(direction, range_position, impulse_state, false_break_signal)
    impulse_comment = _impulse_comment(impulse_state, direction, range_position, range_state)

    if action == "ENTER":
        summary = "Есть рабочий перевес, но вход допустим только после подтверждения." if not trap_comment else f"Есть рабочий перевес, но вход допустим только после подтверждения; {trap_comment}."
    elif action == "WATCH":
        summary = "Есть перевес, но лучше искать подтверждение у уровня."
    elif action == "WAIT_PULLBACK":
        summary = "Сейчас лучше не входить в догонку: рынок просит откат."
    elif action == "WAIT_RANGE_EDGE":
        summary = "Середина диапазона: лучше ждать край диапазона или явный breakout-confirm."
    elif market_state == "CONFLICTED":
        summary = "Есть конфликт факторов: лучше не спешить и дождаться прояснения."
    elif market_state == "UNKNOWN":
        summary = "Перевес пока слабый: рынок ещё не дал чистого подтверждения."
    else:
        summary = "Сейчас лучше ждать более чистую ситуацию."

    if not summary and no_trade_reason:
        summary = f"Сейчас лучше без сделки: {no_trade_reason}."

    score_gap = abs(long_score - short_score)
    situation_shift = "БЕЗ ИЗМЕНЕНИЙ"
    if direction == "LONG":
        if score_gap >= 16:
            situation_shift = "ПЕРЕВЕС В ЛОНГ УСИЛИВАЕТСЯ"
        elif score_gap >= 8:
            situation_shift = "ЛОНГ-ПЕРЕВЕС ДЕРЖИТСЯ"
        else:
            situation_shift = "ЛОНГ-ПЕРЕВЕС ЕСТЬ, НО ОН ХРУПКИЙ"
    elif direction == "SHORT":
        if score_gap >= 16:
            situation_shift = "ПЕРЕВЕС В ШОРТ УСИЛИВАЕТСЯ"
        elif score_gap >= 8:
            situation_shift = "ШОРТ-ПЕРЕВЕС ДЕРЖИТСЯ"
        else:
            situation_shift = "ШОРТ-ПЕРЕВЕС ЕСТЬ, НО ОН ХРУПКИЙ"

    positioning_action = "WAIT"
    if direction == "LONG":
        if confidence >= 66 and location_quality == "A" and trap_risk != "HIGH":
            positioning_action = "ENTER_AGGRESSIVE_LONG"
        elif confidence >= 58:
            positioning_action = "ADD_LONG"
        elif confidence >= 51:
            positioning_action = "REDUCE_SHORT"
        else:
            positioning_action = "WATCH_LONG"
    elif direction == "SHORT":
        if confidence >= 66 and location_quality == "A" and trap_risk != "HIGH":
            positioning_action = "ENTER_AGGRESSIVE_SHORT"
        elif confidence >= 58:
            positioning_action = "ADD_SHORT"
        elif confidence >= 51:
            positioning_action = "REDUCE_LONG"
        else:
            positioning_action = "WATCH_SHORT"

    if market_state == "CONFLICTED" and trap_risk == "HIGH" and confidence < 58:
        if direction == "LONG":
            positioning_action = "REDUCE_SHORT" if confidence >= 50 else "WATCH_LONG"
        elif direction == "SHORT":
            positioning_action = "REDUCE_LONG" if confidence >= 50 else "WATCH_SHORT"
        else:
            positioning_action = "WAIT"

    position_hint = _action_text(positioning_action)

    if not expectation:
        expectation = list(impulse_block.get("watch_conditions") or [])
    expectation.insert(0, f"изменение ситуации: {situation_shift.lower()}")
    expectation.insert(0, f"позиционно: {position_hint.lower()}")
    expectation.insert(0, trigger_text)
    expectation.insert(0, scenario_text)
    expectation.insert(0, impulse_comment)
    expectation.extend(execution_hints)
    expectation.extend(_next_steps_for_no_trade(direction, range_position, impulse_state, false_break_signal))

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
        "scenario_text": scenario_text,
        "trigger_text": trigger_text,
        "impulse_state": impulse_state,
        "impulse_comment": impulse_comment,
        "impulse_strength": impulse_block.get("strength"),
        "impulse_freshness": impulse_block.get("freshness"),
        "impulse_exhaustion": impulse_block.get("exhaustion"),
        "impulse_confirmation": impulse_block.get("confirmation"),
        "long_score": round(long_score, 1),
        "short_score": round(short_score, 1),
        "positioning_action": positioning_action,
        "positioning_action_text": position_hint,
        "situation_shift": situation_shift,
        "score_gap": round(score_gap, 1),
        "pressure_reason": ct_context or trap_comment,
        "entry_reason": summary,
        "invalidation": scenario_bundle.get("scenario_invalidation") or "ожидать слом уровня/структуры против идеи",
        "base_case": scenario_bundle.get("base_case", ""),
        "bull_case": scenario_bundle.get("bull_case", ""),
        "bear_case": scenario_bundle.get("bear_case", ""),
        "trigger_up": scenario_bundle.get("trigger_up", ""),
        "trigger_down": scenario_bundle.get("trigger_down", ""),
        "scenario_invalidation": scenario_bundle.get("scenario_invalidation", ""),
        "active_bot": "countertrend_bot" if entry_type == "reversal" else "none",
        "range_position": range_position,
        "range_position_zone": range_state or "позиция в диапазоне не определена",
        "expectation": expectation[:6],
        "expectation_text": expectation[0] if expectation else "",
        "reasons": reasons[:6],
        "mode_reasons": mode_reasons[:4],
        "market_state": market_state,
        "market_state_text": market_state_text,
        "setup_status": setup_status,
        "setup_status_text": setup_status_text,
        "late_entry_risk": late_entry_risk,
        "location_quality": location_quality,
        "entry_type": entry_type,
        "execution_mode": execution_mode,
        "no_trade_reason": no_trade_reason,
        "trap_risk": trap_risk,
        "breakout_risk": breakout_risk,
        "false_break_signal": false_break_signal,
        "trap_comment": trap_comment,
        "edge_bias": edge_bias,
        "edge_score": round(edge_score, 3),
        "market_regime": market_regime,
        "market_regime_text": _market_regime_text(market_regime),
        "market_regime_bias": _direction_text(market_regime_bias),
        "market_regime_confidence": round(market_regime_confidence, 1),
        "market_regime_summary": market_regime_summary,
    }

    regime_lock = _resolve_regime_lock(
        market_regime=market_regime,
        range_position=range_position,
        impulse_state=impulse_state,
        direction=direction,
        market_state=market_state,
        summary=market_regime_summary,
        confidence=market_regime_confidence,
    )
    result["market_regime"] = regime_lock["regime"]
    result["market_regime_text"] = regime_lock["text"]
    result["market_regime_bias"] = regime_lock["bias"]
    result["market_regime_confidence"] = regime_lock["confidence"]
    result["market_regime_summary"] = regime_lock["summary"]
    return result








def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _build_edge_score(data: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    direction = _normalize_direction(result.get("direction_text") or result.get("direction"))
    long_score = _safe_float(result.get("long_score"), 0.0)
    short_score = _safe_float(result.get("short_score"), 0.0)
    score_gap = abs(long_score - short_score)
    confidence = _safe_float(result.get("confidence_pct") or result.get("confidence"), 0.0)
    impulse_state = _safe_str(result.get("impulse_state"), "").upper()
    range_position = _safe_str(result.get("range_position"), "").upper()
    market_state = _safe_str(result.get("market_state"), "").upper()
    trap_risk = _safe_str(result.get("trap_risk"), "").upper()
    breakout_risk = _safe_str(data.get("breakout_risk") or result.get("breakout_risk"), "LOW").upper()
    forecast_direction = _normalize_direction(data.get("forecast_direction"))
    core_signal = _normalize_direction(data.get("signal"))

    gap_component = _clamp(score_gap * 1.35, 0.0, 34.0)
    confidence_component = _clamp((confidence - 20.0) * 0.48, 0.0, 24.0)

    location_component = 0.0
    if range_position in {"LOW_EDGE", "HIGH_EDGE"}:
        if (direction == "LONG" and range_position == "LOW_EDGE") or (direction == "SHORT" and range_position == "HIGH_EDGE"):
            location_component = 24.0
        elif direction != "NEUTRAL":
            location_component = 8.0
    elif range_position in {"LOWER_PART", "UPPER_PART"}:
        if (direction == "LONG" and range_position == "LOWER_PART") or (direction == "SHORT" and range_position == "UPPER_PART"):
            location_component = 16.0
        elif direction != "NEUTRAL":
            location_component = 6.0
    elif range_position == "MID":
        location_component = -10.0

    impulse_component = 0.0
    if impulse_state in {"IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE"}:
        impulse_component = 18.0
    elif impulse_state in {"BULLISH_BUILDING", "BEARISH_BUILDING"}:
        impulse_component = 10.0
    elif impulse_state in {"PENDING_CONFIRMATION", "IMPULSE_UNCERTAIN", "CONFLICTED"}:
        impulse_component = 1.5
    elif impulse_state in {"NO_CLEAR_IMPULSE", "RANGE_NO_IMPULSE", "RANGE"}:
        impulse_component = -12.0
    elif impulse_state in {"IMPULSE_EXHAUSTING", "FADING"}:
        impulse_component = -10.0

    history_pattern_direction = _normalize_direction(data.get("pattern_forecast_direction") or data.get("history_pattern_direction"))
    history_pattern_conf = _safe_float(data.get("pattern_forecast_confidence") or data.get("history_pattern_confidence"), 0.0)
    if 0.0 <= history_pattern_conf <= 1.0:
        history_pattern_conf *= 100.0

    alignment_component = 0.0
    if direction != "NEUTRAL" and forecast_direction == direction:
        alignment_component += 8.0
    if direction != "NEUTRAL" and core_signal == direction:
        alignment_component += 10.0
    if direction != "NEUTRAL" and history_pattern_direction == direction:
        alignment_component += min(10.0, 3.0 + max(0.0, history_pattern_conf - 50.0) * 0.18)
    # soft edge activation: when final side is neutral but both forecast and pattern lean the same way,
    # keep a small executable bias instead of collapsing to zero.
    if direction == "NEUTRAL" and forecast_direction in {"LONG", "SHORT"} and history_pattern_direction == forecast_direction:
        alignment_component += min(12.0, 4.0 + max(0.0, history_pattern_conf - 50.0) * 0.12)

    penalty_component = 0.0
    if market_state == "CONFLICTED":
        penalty_component += 14.0
    elif market_state == "NEUTRAL":
        penalty_component += 8.0
    if trap_risk == "HIGH":
        penalty_component += 16.0
    elif trap_risk == "MEDIUM":
        penalty_component += 6.0
    if breakout_risk == "HIGH" and direction == "NEUTRAL":
        penalty_component += 2.0
    elif breakout_risk == "HIGH":
        penalty_component += 4.0

    raw_score = gap_component + confidence_component + location_component + impulse_component + alignment_component - penalty_component
    edge_score = _clamp(raw_score, 0.0, 100.0)

    if direction == "NEUTRAL":
        edge_score = min(edge_score, 42.0)
    if score_gap < 5.0:
        edge_score = min(edge_score, 42.0)
    if confidence < 25.0 and impulse_state not in {"IMPULSE_CONTINUES", "BULLISH_ACTIVE", "BEARISH_ACTIVE"}:
        edge_score = min(edge_score, 42.0)
    if range_position == "MID" and impulse_state in {"NO_CLEAR_IMPULSE", "PENDING_CONFIRMATION", "IMPULSE_UNCERTAIN", "CONFLICTED", "RANGE_NO_IMPULSE", "RANGE"}:
        edge_score = min(edge_score, 40.0)

    if edge_score >= 66.0:
        edge_label = "STRONG"
    elif edge_score >= 45.0:
        edge_label = "WORKABLE"
    elif edge_score >= 18.0:
        edge_label = "WEAK"
    else:
        edge_label = "NO_EDGE"

    side = direction if direction in {"LONG", "SHORT"} else ("LONG" if long_score > short_score else "SHORT" if short_score > long_score else "NEUTRAL")
    if side == "NEUTRAL" and forecast_direction in {"LONG", "SHORT"}:
        side = forecast_direction
    if side == "NEUTRAL" and history_pattern_direction in {"LONG", "SHORT"}:
        side = history_pattern_direction
    if edge_label == "STRONG":
        edge_action = "CAN_EXECUTE"
    elif edge_label == "WORKABLE":
        edge_action = "WATCH_CONFIRMATION"
    elif edge_label == "WEAK":
        edge_action = "SCALP_ONLY" if range_position == "MID" else "WATCH_CONFIRMATION"
    else:
        edge_action = "NO_TRADE"

    return {
        "score": round(edge_score, 1),
        "label": edge_label,
        "action": edge_action,
        "side": side,
        "components": {
            "gap": round(gap_component, 1),
            "confidence": round(confidence_component, 1),
            "location": round(location_component, 1),
            "impulse": round(impulse_component, 1),
            "alignment": round(alignment_component, 1),
            "penalty": round(penalty_component, 1),
        },
    }
def _force_neutral_decision(result: Dict[str, Any], reason: str = "Score сбалансированы, edge нет.") -> Dict[str, Any]:
    result["direction"] = "NEUTRAL"
    result["direction_text"] = "НЕЙТРАЛЬНО"
    result["action"] = "WAIT"
    result["action_text"] = _action_text("WAIT")
    result["positioning_action"] = "WAIT"
    result["positioning_action_text"] = "ЖДАТЬ"
    result["market_state"] = "NEUTRAL"
    result["market_state_text"] = "БЕЗ ПЕРЕВЕСА"
    result["setup_status"] = "WAIT"
    result["setup_status_text"] = "ЖДАТЬ"
    result["risk_level"] = "HIGH"
    result["entry_type"] = "no_trade"
    result["execution_mode"] = "defensive"
    result["summary"] = "Есть перевес, но вход не разрешён без подтверждения."
    result["entry_reason"] = result["summary"]
    result["situation_shift"] = "БЕЗ ИЗМЕНЕНИЙ"
    result["forecast_strength"] = "NEUTRAL"
    result["no_trade_reason"] = "score сбалансированы, edge нет"
    result["expectation_text"] = "ждать выход к краю диапазона или появление чистого импульса"
    result["invalidation"] = "без активной стороны нет рабочей invalidation-зоны"
    result["edge_score"] = min(_safe_float(result.get("edge_score"), 0.0), 34.0)
    result["edge_label"] = "NO_EDGE"
    result["edge_action"] = "NO_TRADE"
    if isinstance(result.get("reasons"), list):
        result["reasons"] = [reason]
    return result


def _should_force_neutral_result(data: Dict[str, Any], result: Dict[str, Any]) -> bool:
    signal = _normalize_direction(data.get("signal"))
    forecast = _normalize_direction(data.get("forecast_direction"))
    long_score = _safe_float(result.get("long_score"), 0.0)
    short_score = _safe_float(result.get("short_score"), 0.0)
    gap = abs(long_score - short_score)
    conf = _safe_float(result.get("confidence_pct") or result.get("confidence"), 0.0)
    impulse_state = _safe_str(result.get("impulse_state"), "").upper()
    range_state = _safe_str((data.get("range_state") or (data.get("range") or {}).get("state") or result.get("range_position_zone") or ""), "").lower()
    in_mid = ("серед" in range_state) or ("middle" in range_state) or _safe_str(result.get("range_position"), "").upper() == "MID"
    return (
        signal == "NEUTRAL"
        and forecast == "NEUTRAL"
        and gap <= 3.0
        and conf <= 15.0
        and impulse_state in {"NO_CLEAR_IMPULSE", "PENDING_CONFIRMATION", "IMPULSE_UNCERTAIN", "CONFLICTED"}
        and in_mid
    )


def _enforce_action_consistency(data: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    action = _safe_str(result.get("action"), "WAIT").upper()
    impulse_state = _safe_str(result.get("impulse_state"), "").upper()
    setup_status = _safe_str(result.get("setup_status"), "WAIT").upper()
    conf = _safe_float(result.get("confidence_pct") or result.get("confidence"), 0.0)
    confirmation = _safe_float(result.get("impulse_confirmation"), 0.0)
    if action == "ENTER" and (
        impulse_state in {"PENDING_CONFIRMATION", "IMPULSE_UNCERTAIN", "CONFLICTED", "NO_CLEAR_IMPULSE"}
        or setup_status in {"EARLY", "WAIT", "INVALID"}
        or confirmation <= 0.05
    ):
        downgraded = "WATCH" if conf >= 55.0 else "WAIT_CONFIRMATION"
        result["action"] = downgraded
        result["action_text"] = _action_text(downgraded)
        result["summary"] = "Есть перевес, но вход лучше брать только после подтверждения у уровня."
        result["entry_reason"] = result["summary"]
    return result
def _map_score_direction(long_score: float, short_score: float) -> tuple[str, float, str]:
    long_score = float(long_score or 0.0)
    short_score = float(short_score or 0.0)
    total = max(long_score + short_score, 1e-9)
    long_ratio = long_score / total
    diff = abs(long_score - short_score)
    bias_conf = 0.5 + diff / 200.0
    if long_ratio >= 0.61:
        return 'ЛОНГ', min(bias_conf + 0.10, 0.88), 'STRONG LONG'
    if long_ratio >= 0.56:
        return 'ЛОНГ', min(bias_conf + 0.05, 0.82), 'MODERATE LONG'
    if long_ratio >= 0.53:
        return 'ЛОНГ', min(bias_conf + 0.02, 0.74), 'WEAK LONG'
    if long_ratio <= 0.39:
        return 'ШОРТ', min(bias_conf + 0.10, 0.88), 'STRONG SHORT'
    if long_ratio <= 0.44:
        return 'ШОРТ', min(bias_conf + 0.05, 0.82), 'MODERATE SHORT'
    if long_ratio <= 0.47:
        return 'ШОРТ', min(bias_conf + 0.02, 0.74), 'WEAK SHORT'
    return 'НЕЙТРАЛЬНО', min(0.54, max(0.0, diff / 100.0 + 0.42)), 'NEUTRAL'



def _proxy_scores_from_bot_context(data: Dict[str, Any]) -> tuple[float, float, str, float]:
    best_bot = _safe_str(data.get("best_bot") or data.get("preferred_bot"), "").lower()
    best_score_raw = _safe_float(data.get("best_bot_score"), 0.0)
    if best_score_raw <= 0.0:
        cards = data.get("bot_cards") or []
        if isinstance(cards, list) and cards:
            try:
                top = max(cards, key=lambda x: float((x or {}).get("score") or 0.0))
                if isinstance(top, dict):
                    best_bot = _safe_str(top.get("bot_key") or best_bot, "").lower()
                    best_score_raw = _safe_float(top.get("score"), best_score_raw)
            except Exception:
                pass

    hold_bias = _normalize_direction(data.get("hold_bias"))
    if hold_bias == "NEUTRAL":
        if "short" in best_bot:
            hold_bias = "SHORT"
        elif "long" in best_bot:
            hold_bias = "LONG"

    if best_score_raw <= 0.0:
        return 0.0, 0.0, hold_bias, 0.0

    best_score = best_score_raw * 100.0 if 0.0 <= best_score_raw <= 1.0 else best_score_raw
    best_score = max(0.0, min(100.0, best_score))
    edge = max(0.0, min((best_score - 45.0) / 35.0, 1.0))
    major = 50.0 + edge * 22.0
    minor = 50.0 - edge * 14.0
    if hold_bias == "SHORT":
        return minor, major, hold_bias, best_score
    if hold_bias == "LONG":
        return major, minor, hold_bias, best_score
    return 50.0, 50.0, hold_bias, best_score



_DECISION_STATE_PATH = Path("state/decision_state.json")
_DECISION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _decision_state_key(data: Dict[str, Any]) -> str:
    symbol = str(data.get("symbol") or "BTCUSDT").upper()
    timeframe = str(data.get("timeframe") or "1h").lower()
    return f"{symbol}:{timeframe}"


def _decision_state_snapshot(decision: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "direction": decision.get("direction_text") or decision.get("direction") or "НЕЙТРАЛЬНО",
        "positioning_action_text": decision.get("positioning_action_text") or "ЖДАТЬ",
        "long_score": round(_safe_float(decision.get("long_score"), 0.0), 1),
        "short_score": round(_safe_float(decision.get("short_score"), 0.0), 1),
        "confidence": round(_safe_float(decision.get("confidence_pct") or decision.get("confidence"), 0.0), 1),
        "summary": str(decision.get("summary") or ""),
    }



def _load_previous_decision_state(data: Dict[str, Any]) -> Dict[str, Any]:
    state = load_json(_DECISION_STATE_PATH, {})
    if not isinstance(state, dict):
        return {}
    entry = state.get(_decision_state_key(data), {})
    if not isinstance(entry, dict):
        return {}
    history = entry.get("history")
    if isinstance(history, list) and history:
        latest = history[-1]
        return latest if isinstance(latest, dict) else {}
    return entry



def _load_decision_state_history(data: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
    state = load_json(_DECISION_STATE_PATH, {})
    if not isinstance(state, dict):
        return []
    entry = state.get(_decision_state_key(data), {})
    if not isinstance(entry, dict):
        return []
    history = entry.get("history")
    if isinstance(history, list) and history:
        cleaned = [item for item in history if isinstance(item, dict)]
        return cleaned[-limit:] if limit > 0 else cleaned
    return [entry] if entry else []



def _save_decision_state(data: Dict[str, Any], decision: Dict[str, Any]) -> None:
    state = load_json(_DECISION_STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    key = _decision_state_key(data)
    previous_entry = state.get(key, {})
    history = []
    if isinstance(previous_entry, dict):
        prev_history = previous_entry.get("history")
        if isinstance(prev_history, list):
            history = [item for item in prev_history if isinstance(item, dict)][-4:]
        elif previous_entry:
            history = [previous_entry]
    snapshot = _decision_state_snapshot(decision)
    history.append(snapshot)
    history = history[-4:]
    state[key] = {
        **snapshot,
        "history": history,
    }
    save_json(_DECISION_STATE_PATH, state)



def _enrich_decision_change_context(data: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    history = _load_decision_state_history(data, limit=3)
    previous = history[-1] if history else {}
    cur_long = _safe_float(decision.get("long_score"), 0.0)
    cur_short = _safe_float(decision.get("short_score"), 0.0)
    cur_conf = _safe_float(decision.get("confidence_pct") or decision.get("confidence"), 0.0)
    cur_dir = _normalize_direction(decision.get("direction_text") or decision.get("direction"))
    prev_long = _safe_float(previous.get("long_score"), cur_long)
    prev_short = _safe_float(previous.get("short_score"), cur_short)
    prev_conf = _safe_float(previous.get("confidence"), cur_conf)
    prev_dir = _normalize_direction(previous.get("direction"))

    long_delta = round(cur_long - prev_long, 1)
    short_delta = round(cur_short - prev_short, 1)
    conf_delta = round(cur_conf - prev_conf, 1)
    direction_transition = "БЕЗ СМЕНЫ"
    if prev_dir != cur_dir:
        if prev_dir == "NEUTRAL" and cur_dir in {"LONG", "SHORT"}:
            direction_transition = f"СДВИГ ИЗ НЕЙТРАЛИ В {_direction_text(cur_dir)}"
        elif cur_dir == "NEUTRAL" and prev_dir in {"LONG", "SHORT"}:
            direction_transition = f"ИМПУЛЬС В {_direction_text(prev_dir)} ПОГАС"
        elif prev_dir in {"LONG", "SHORT"} and cur_dir in {"LONG", "SHORT"}:
            direction_transition = f"ПЕРЕВОРОТ: {_direction_text(prev_dir)} → {_direction_text(cur_dir)}"

    prev2 = history[-2] if len(history) >= 2 else previous
    prev2_long = _safe_float(prev2.get("long_score"), prev_long)
    prev2_short = _safe_float(prev2.get("short_score"), prev_short)
    prev2_conf = _safe_float(prev2.get("confidence"), prev_conf)
    long_prev_delta = round(prev_long - prev2_long, 1)
    short_prev_delta = round(prev_short - prev2_short, 1)
    conf_prev_delta = round(prev_conf - prev2_conf, 1)
    long_accel = round(long_delta - long_prev_delta, 1)
    short_accel = round(short_delta - short_prev_delta, 1)
    conf_accel = round(conf_delta - conf_prev_delta, 1)
    acceleration_state = "БЕЗ УСКОРЕНИЯ"
    acceleration_comment = "скорость изменения пока ровная"
    if cur_dir == "LONG":
        if long_accel >= 3 and conf_accel >= 1:
            acceleration_state = "ЛОНГ УСКОРЯЕТСЯ"
            acceleration_comment = "покупатель усиливает давление быстрее, чем в прошлом снапшоте"
        elif long_delta > 0 and long_accel <= -2:
            acceleration_state = "РОСТ ЕСТЬ, НО ЛОНГ ВЫДЫХАЕТСЯ"
            acceleration_comment = "лонг ещё держится, но темп набора замедляется"
        elif short_accel >= 3 and long_accel <= 0:
            acceleration_state = "ШОРТ УСКОРЯЕТСЯ ПРОТИВ ЛОНГА"
            acceleration_comment = "продавец начинает давить быстрее, чем раньше"
    elif cur_dir == "SHORT":
        if short_accel >= 3 and conf_accel >= 1:
            acceleration_state = "ШОРТ УСКОРЯЕТСЯ"
            acceleration_comment = "продавец усиливает давление быстрее, чем в прошлом снапшоте"
        elif short_delta > 0 and short_accel <= -2:
            acceleration_state = "ПАДЕНИЕ ЕСТЬ, НО ШОРТ ВЫДЫХАЕТСЯ"
            acceleration_comment = "шорт ещё держится, но темп давления замедляется"
        elif long_accel >= 3 and short_accel <= 0:
            acceleration_state = "ЛОНГ УСКОРЯЕТСЯ ПРОТИВ ШОРТА"
            acceleration_comment = "покупатель отбирает инициативу быстрее, чем раньше"
    else:
        if abs(long_accel) >= 3 or abs(short_accel) >= 3:
            dominant = "ЛОНГ" if long_accel > short_accel else "ШОРТ"
            acceleration_state = f"ВНУТРИ НЕЙТРАЛИ УСКОРЕНИЕ В {dominant}"
            acceleration_comment = "нейтральный режим сохраняется, но внутреннее смещение ускоряется"

    if cur_dir == "LONG":
        if long_delta >= 6 and short_delta <= -4:
            situation_shift = "ЛОНГ УСИЛИВАЕТСЯ, ШОРТ СДАЁТ"
        elif long_delta >= 3:
            situation_shift = "ЛОНГ ПОДБИРАЮТ"
        elif short_delta >= 4 and long_delta <= 0:
            situation_shift = "ШОРТ ДАВИТ, ЛОНГ СЛАБЕЕТ"
        else:
            situation_shift = decision.get("situation_shift") or "ЛОНГ ДЕРЖИТСЯ"
    elif cur_dir == "SHORT":
        if short_delta >= 6 and long_delta <= -4:
            situation_shift = "ШОРТ УСИЛИВАЕТСЯ, ЛОНГ СДАЁТ"
        elif short_delta >= 3:
            situation_shift = "ШОРТ ПОДДАВЛИВАЕТ"
        elif long_delta >= 4 and short_delta <= 0:
            situation_shift = "ЛОНГ ОТБИВАЕТСЯ, ШОРТ СЛАБЕЕТ"
        else:
            situation_shift = decision.get("situation_shift") or "ШОРТ ДЕРЖИТСЯ"
    else:
        if abs(long_delta) >= 4 or abs(short_delta) >= 4:
            dominant = "ЛОНГ" if cur_long > cur_short else "ШОРТ" if cur_short > cur_long else "БЕЗ ЯВНОГО ПЕРЕВЕСА"
            situation_shift = f"НЕЙТРАЛЬНО, НО ВНУТРИ ДНЯ СМЕЩЕНИЕ В {dominant}"
        else:
            situation_shift = "БЕЗ СИЛЬНОГО СДВИГА"

    delta_lines = []
    if long_delta or short_delta or conf_delta:
        delta_lines = [
            f"лонг {long_delta:+.1f}%",
            f"шорт {short_delta:+.1f}%",
            f"confidence {conf_delta:+.1f}%",
        ]

    pos_text = str(decision.get("positioning_action_text") or "ЖДАТЬ")
    if cur_dir == "LONG" and long_delta >= 5 and conf_delta >= 3:
        pos_text = "ДОБАВЛЯТЬ ЛОНГ" if cur_conf < 66 else "ВХОДИТЬ В ЛОНГ АГРЕССИВНЕЕ"
    elif cur_dir == "LONG" and short_delta >= 5:
        pos_text = "СОКРАЩАТЬ ЛОНГ / НЕ ДОБАВЛЯТЬ"
    elif cur_dir == "SHORT" and short_delta >= 5 and conf_delta >= 3:
        pos_text = "ДОБАВЛЯТЬ ШОРТ" if cur_conf < 66 else "ВХОДИТЬ В ШОРТ АГРЕССИВНЕЕ"
    elif cur_dir == "SHORT" and long_delta >= 5:
        pos_text = "СОКРАЩАТЬ ШОРТ / НЕ ДОБАВЛЯТЬ"

    if cur_dir == "LONG" and acceleration_state == "ЛОНГ УСКОРЯЕТСЯ" and cur_conf >= 58:
        pos_text = "ВХОДИТЬ В ЛОНГ АГРЕССИВНЕЕ" if cur_conf >= 66 else "ДОБАВЛЯТЬ ЛОНГ"
    elif cur_dir == "LONG" and acceleration_state in {"РОСТ ЕСТЬ, НО ЛОНГ ВЫДЫХАЕТСЯ", "ШОРТ УСКОРЯЕТСЯ ПРОТИВ ЛОНГА"}:
        pos_text = "ЛОНГ НЕ ДОГОНЯТЬ / ЖДАТЬ ОТКАТ"
    elif cur_dir == "SHORT" and acceleration_state == "ШОРТ УСКОРЯЕТСЯ" and cur_conf >= 58:
        pos_text = "ВХОДИТЬ В ШОРТ АГРЕССИВНЕЕ" if cur_conf >= 66 else "ДОБАВЛЯТЬ ШОРТ"
    elif cur_dir == "SHORT" and acceleration_state in {"ПАДЕНИЕ ЕСТЬ, НО ШОРТ ВЫДЫХАЕТСЯ", "ЛОНГ УСКОРЯЕТСЯ ПРОТИВ ШОРТА"}:
        pos_text = "ШОРТ НЕ ДОГОНЯТЬ / ЖДАТЬ ОТСКОК"

    decision["long_delta_pct"] = long_delta
    decision["short_delta_pct"] = short_delta
    decision["confidence_delta_pct"] = conf_delta
    decision["direction_transition"] = direction_transition
    decision["delta_summary"] = " | ".join(delta_lines) if delta_lines else "нет заметного сдвига"
    decision["situation_shift"] = situation_shift
    decision["acceleration_state"] = acceleration_state
    decision["acceleration_comment"] = acceleration_comment
    decision["long_acceleration_pct"] = long_accel
    decision["short_acceleration_pct"] = short_accel
    decision["confidence_acceleration_pct"] = conf_accel
    decision["positioning_action_text"] = pos_text
    expectation = list(decision.get("expectation") or [])
    if acceleration_state != "БЕЗ УСКОРЕНИЯ":
        expectation.insert(0, f"ускорение: {acceleration_state.lower()}")
    if direction_transition != "БЕЗ СМЕНЫ":
        expectation.insert(0, f"смена режима: {direction_transition.lower()}")
    if delta_lines:
        expectation.insert(0, f"дельта: {' | '.join(delta_lines)}")
    decision["expectation"] = expectation[:8]
    return decision


def build_final_decision(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = data or {}
    raw_final = _safe_str(data.get("final_decision"), "").strip().upper()
    raw_signal = _safe_str(data.get("signal"), "").strip().upper()
    raw_forecast = _safe_str(data.get("forecast_direction"), "").strip().upper()

    directional_final = raw_final if raw_final in {"ЛОНГ", "ШОРТ", "LONG", "SHORT", "ВВЕРХ", "ВНИЗ", "UP", "DOWN"} else ""
    directional_signal = raw_signal if raw_signal in {"ЛОНГ", "ШОРТ", "LONG", "SHORT"} else ""
    directional_forecast = raw_forecast if raw_forecast in {"ВВЕРХ", "ВНИЗ", "UP", "DOWN", "LONG", "SHORT"} else ""
    long_score = _safe_float((data.get("decision") or {}).get("long_score"), 0.0)
    short_score = _safe_float((data.get("decision") or {}).get("short_score"), 0.0)
    if long_score <= 0.0 and short_score <= 0.0:
        proxy_long, proxy_short, proxy_bias, proxy_conf = _proxy_scores_from_bot_context(data)
        if proxy_long > 0.0 or proxy_short > 0.0:
            long_score = proxy_long
            short_score = proxy_short
            if not directional_forecast and proxy_bias in {"LONG", "SHORT"}:
                directional_forecast = proxy_bias
            if not directional_signal and proxy_bias in {"LONG", "SHORT"}:
                directional_signal = proxy_bias
            if not directional_final and proxy_bias in {"LONG", "SHORT"}:
                directional_final = proxy_bias
            if _safe_float(data.get("forecast_confidence"), 0.0) <= 0.0 and proxy_conf > 0.0:
                data["forecast_confidence"] = round(proxy_conf, 1)
    score_direction, score_confidence, score_strength = _map_score_direction(long_score, short_score)

    # Do not let an inherited advisory LONG/SHORT override a freshly neutral core state.
    # Priority: explicit core signal -> sufficiently strong forecast -> score bias -> only then legacy final_decision.
    chosen_direction = ""
    if directional_signal:
        chosen_direction = directional_signal
    elif directional_forecast and _safe_float(data.get("forecast_confidence"), 0.0) >= 54.0:
        chosen_direction = directional_forecast
    elif score_direction != 'НЕЙТРАЛЬНО':
        chosen_direction = score_direction
    elif directional_final and directional_final == directional_forecast and _safe_float(data.get("forecast_confidence"), 0.0) >= 54.0:
        chosen_direction = directional_final

    signal_confidence = data.get("forecast_confidence", 50.0)
    if chosen_direction == score_direction and score_direction != 'НЕЙТРАЛЬНО':
        signal_confidence = max(float(signal_confidence or 0.0), score_confidence)
    proxy_floor = max(long_score, short_score)
    if chosen_direction in {"LONG", "SHORT", "ЛОНГ", "ШОРТ", "UP", "DOWN", "ВВЕРХ", "ВНИЗ"} and proxy_floor > 50.0:
        signal_confidence = max(float(signal_confidence or 0.0), proxy_floor)

    # Hard safety: when scores are essentially balanced and there is no confirmed forecast,
    # keep the decision neutral instead of leaking a stale directional bias.
    if score_direction == 'НЕЙТРАЛЬНО' and _safe_float(data.get("forecast_confidence"), 0.0) < 54.0 and not directional_signal:
        chosen_direction = ""

    impulse = _extract_impulse(data)
    result = build_decision_block(
        signal_block={
            "signal": data.get("signal"),
            "final_signal": chosen_direction or raw_signal,
            "forecast_direction": chosen_direction or data.get("forecast_direction"),
            "forecast_confidence": signal_confidence,
            "confidence": signal_confidence,
            "trap_comment": data.get("trap_comment"),
            "false_break_signal": data.get("false_break_signal"),
        },
        range_block={
            "state": _extract_range_state(data),
            "range_position": data.get("range_position"),
            "edge_bias": data.get("edge_bias"),
            "edge_score": data.get("edge_score"),
            "breakout_risk": data.get("breakout_risk"),
        },
        impulse_block=impulse,
        countertrend_block={"context": data.get("ct_now")},
        analysis_block={
            **(data.get("analysis") if isinstance(data.get("analysis"), dict) else {}),
            "best_bot": data.get("best_bot"),
            "best_bot_score": data.get("best_bot_score"),
            "best_bot_status": data.get("best_bot_status"),
            "hold_bias": data.get("hold_bias"),
            "preferred_bot": data.get("preferred_bot"),
            "bot_cards": data.get("bot_cards"),
            "forced_long_score": long_score if long_score > 0.0 else 0.0,
            "forced_short_score": short_score if short_score > 0.0 else 0.0,
        },
        stats_block=(data.get("stats") if isinstance(data.get("stats"), dict) else {}),
    )
    raw_strength = data.get("forecast_strength") or score_strength
    synced_strength = _forecast_strength_label(chosen_direction or result.get("direction") or result.get("direction_text"), signal_confidence)
    current_strength = str(raw_strength or '').upper()
    strength_rank = {'NEUTRAL': 0, 'WEAK': 1, 'MODERATE': 2, 'STRONG': 3}
    result["forecast_strength"] = synced_strength if strength_rank.get(synced_strength, 0) >= strength_rank.get(current_strength, 0) else current_strength
    if _safe_float(result.get("long_score"), 0.0) <= 0.0 and _safe_float(result.get("short_score"), 0.0) <= 0.0 and (long_score > 0.0 or short_score > 0.0):
        result["long_score"] = round(long_score, 1)
        result["short_score"] = round(short_score, 1)
    if _safe_float(result.get("confidence"), 0.0) <= 0.0 and _safe_float(signal_confidence, 0.0) > 0.0:
        result["confidence"] = round(float(signal_confidence), 1)
        result["confidence_pct"] = round(float(signal_confidence), 1)
    if proxy_floor > 50.0 and _safe_float(result.get("confidence"), 0.0) < proxy_floor:
        boosted = round(float(proxy_floor), 1)
        if str(result.get("edge_label") or "").upper() == "NO_EDGE":
            boosted = min(boosted, 39.0)
        result["confidence"] = boosted
        result["confidence_pct"] = boosted
    if _normalize_direction(result.get("direction_text") or result.get("direction")) in {"LONG", "SHORT"} and str(result.get("action") or "").upper() in {"WAIT", "WAIT_PULLBACK"} and proxy_floor >= 50.0 and not _should_force_neutral_result(data, result):
        result["action"] = "WATCH"
        result["action_text"] = _action_text("WATCH")
    result["impulse_state"] = _normalize_impulse_state_name(result.get("impulse_state"), result.get("direction_text") or result.get("direction"), result.get("confidence"))
    result["setup_status_hint"] = data.get("setup_status_hint") or result.get("setup_status")
    if result.get("direction_text") == "НЕЙТРАЛЬНО" and score_direction != 'НЕЙТРАЛЬНО' and abs(long_score - short_score) >= 8.0 and _safe_float(result.get("confidence"), 0.0) >= 45.0:
        result["direction"] = score_direction
        result["direction_text"] = score_direction
    if result.get("setup_status") == "WAIT" and str(data.get("setup_status_hint") or '').upper() in {'WATCH','EARLY'}:
        result["setup_status"] = str(data.get("setup_status_hint")).upper()
        result["setup_status_text"] = 'СМОТРЕТЬ СЕТАП' if str(data.get("setup_status_hint")).upper() == 'WATCH' else 'РАНО / НУЖНО ПОДТВЕРЖДЕНИЕ'
    edge = _build_edge_score(data, result)
    result["edge_score"] = edge["score"]
    result["edge_label"] = edge["label"]
    result["edge_action"] = edge["action"]
    result["edge_side"] = edge["side"]
    result["edge_components"] = edge["components"]
    result["bias_direction"] = result.get("direction_text") or result.get("direction") or "НЕЙТРАЛЬНО"
    execution_verdict = _build_execution_verdict(data, result)
    result["execution_verdict"] = execution_verdict
    result["trade_authorized"] = bool(execution_verdict.get("trade_authorized"))
    result["trade_authority"] = str(execution_verdict.get("trade_status") or "NOT_AUTHORIZED")
    result["bot_authorized"] = bool(execution_verdict.get("bot_authorized"))
    result["bot_authority"] = str(execution_verdict.get("bot_status") or "NOT_AUTHORIZED")
    result["trade_authority_reason"] = str(execution_verdict.get("reason") or "нет данных")

    soft_allowed = bool(execution_verdict.get("soft_allowed"))
    bot_authorized = bool(execution_verdict.get("bot_authorized"))
    effective_edge = max(
        _safe_float(edge.get("score"), 0.0),
        _safe_float(execution_verdict.get("trade_edge_score"), 0.0),
        _safe_float(execution_verdict.get("bot_edge_score"), 0.0),
    )

    if edge["label"] == "NO_EDGE":
        if (soft_allowed or bot_authorized) and _normalize_direction(result.get("direction_text") or result.get("direction")) in {"LONG", "SHORT"}:
            result["edge_score"] = round(max(effective_edge, 24.0), 1)
            result["edge_label"] = "WEAK"
            result["edge_action"] = "WATCH"
            result["action"] = "WATCH"
            result["action_text"] = _action_text("WATCH")
            result["summary"] = "Есть рабочий мягкий сценарий: допускается только small/probe после локального подтверждения."
            result["entry_reason"] = result["summary"]
            result["no_trade_reason"] = "soft-режим: нужен локальный reclaim/ложный вынос, без форсирования"
            result["setup_status"] = "WATCH"
            result["setup_status_text"] = "СМОТРЕТЬ СЕТАП"
        else:
            result = _force_neutral_decision(result, "Edge score слишком слабый: активной стороны нет, лучше ждать край диапазона или новый импульс.")
    elif edge["label"] == "WEAK":
        if str(result.get("action") or "").upper() in {"ENTER", "WATCH", "WAIT_PULLBACK"}:
            downgraded = "WAIT_RANGE_EDGE" if _safe_str(result.get("range_position"), "").upper() == "MID" else "WAIT_CONFIRMATION"
            result["action"] = downgraded
            result["action_text"] = _action_text(downgraded)
        result["entry_type"] = "scalp_only" if str(result.get("mode") or "").upper() == "RANGE" else "no_trade"
        result["execution_mode"] = "defensive"
        result["summary"] = "Перевес слабый, но рабочий: допустим только мягкий сценарий small/scalp без форсирования."
        if str(result.get("range_position") or "").upper() == "MID":
            result["setup_status"] = "WATCH"
            result["setup_status_text"] = "СМОТРЕТЬ СЕТАП"
        result["entry_reason"] = result["summary"]
        result["no_trade_reason"] = "edge пока слабый, нужен лучший location/impulse"

    if _should_force_neutral_result(data, result):
        result = _force_neutral_decision(result, "Score сбалансированы, confidence низкий и цена в середине диапазона — активной стороны нет.")

    if not bool(result.get("trade_authorized")):
        current_action = str(result.get("action") or "WAIT").upper()
        if bool(result.get("bot_authorized")) and current_action == "WAIT":
            result["action"] = "WATCH"
            result["action_text"] = _action_text("WATCH")
            current_action = "WATCH"
        if current_action in {"ENTER", "ADD_LONG", "ADD_SHORT", "ENTER_LONG", "ENTER_SHORT", "ENTER_AGGRESSIVE_LONG", "ENTER_AGGRESSIVE_SHORT"}:
            downgraded = "WAIT_CONFIRMATION" if str(result.get("edge_label") or "").upper() in {"WEAK", "WORKABLE"} else "WAIT"
            result["action"] = downgraded
            result["action_text"] = _action_text(downgraded)
        if str(result.get("edge_label") or "").upper() == "NO_EDGE":
            result["entry_type"] = "no_trade"
        result["execution_mode"] = "defensive" if str(result.get("edge_label") or "").upper() != "STRONG" else result.get("execution_mode")

    result = _enforce_action_consistency(data, result)
    if _should_force_neutral_result(data, result):
        result = _force_neutral_decision(result, "Score сбалансированы, confidence низкий и цена в середине диапазона — активной стороны нет.")
    execution_verdict = _build_execution_verdict(data, result)
    result["execution_verdict"] = execution_verdict
    result["trade_authorized"] = bool(execution_verdict.get("trade_authorized"))
    result["trade_authority"] = str(execution_verdict.get("trade_status") or "NOT_AUTHORIZED")
    result["bot_authorized"] = bool(execution_verdict.get("bot_authorized"))
    result["bot_authority"] = str(execution_verdict.get("bot_status") or "NOT_AUTHORIZED")
    result["trade_authority_reason"] = str(execution_verdict.get("reason") or "нет данных")
    return result


def combine_trade_decision(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = dict(data or {})
    payload["impulse"] = _extract_impulse(payload)
    payload["decision"] = build_final_decision(payload)

    decision = _enrich_decision_change_context(payload, payload["decision"])
    payload["decision"] = decision
    if not payload.get("decision_summary") or str(payload.get("decision_summary") or "").strip().lower() in {"", "нет итогового summary"}:
        payload["decision_summary"] = decision.get("summary", "")
    decision_dir = _normalize_direction(decision.get("direction_text") or decision.get("direction"))
    payload["final_decision"] = decision.get("direction_text", "НЕЙТРАЛЬНО")
    if decision_dir in {"LONG", "SHORT"} and _safe_float(decision.get("confidence"), 0.0) >= 45.0:
        payload["forecast_direction"] = decision.get("direction_text", payload.get("forecast_direction"))
        payload["forecast_confidence"] = max(_safe_float(payload.get("forecast_confidence"), 0.0), _safe_float(decision.get("confidence"), 0.0))
    elif decision_dir == "NEUTRAL":
        payload["forecast_direction"] = "НЕЙТРАЛЬНО"
        payload["forecast_confidence"] = min(_safe_float(payload.get("forecast_confidence"), 0.0), _safe_float(decision.get("confidence"), 0.0))
    payload = _apply_edge_gate_to_payload(payload, decision)
    payload["decision"] = _manager_action_from_activation(payload, payload["decision"])
    _save_decision_state(payload, payload["decision"])
    return payload



def _apply_nextgen_overlays(payload: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    expectancy = payload.get('expectancy_context', {}) if isinstance(payload.get('expectancy_context'), dict) else {}
    vol_ctx = payload.get('volatility_impulse', {}) if isinstance(payload.get('volatility_impulse'), dict) else {}
    orderflow = payload.get('orderflow_context', {}) if isinstance(payload.get('orderflow_context'), dict) else {}
    liq_ctx = payload.get('liquidation_context', {}) if isinstance(payload.get('liquidation_context'), dict) else {}
    fast_move = payload.get('fast_move_context', {}) if isinstance(payload.get('fast_move_context'), dict) else {}
    no_trade = payload.get('no_trade_context', {}) if isinstance(payload.get('no_trade_context'), dict) else {}
    ranked = payload.get('best_trade_rank', {}) if isinstance(payload.get('best_trade_rank'), dict) else {}
    regime = payload.get('regime_v2', {}) if isinstance(payload.get('regime_v2'), dict) else {}
    grid_cmd = payload.get('grid_cmd', {}) if isinstance(payload.get('grid_cmd'), dict) else {}

    decision['market_mode'] = regime.get('base_regime', decision.get('mode') or 'UNKNOWN')
    decision['market_submode'] = regime.get('regime_label', decision.get('regime') or 'UNKNOWN')
    decision['best_trade_play'] = ranked.get('best_play', decision.get('best_trade_play', 'wait'))
    decision['best_trade_side'] = ranked.get('best_side', decision.get('best_trade_side', 'FLAT'))
    decision['best_trade_score'] = ranked.get('best_score', decision.get('best_trade_score', 0.0))
    decision['best_play'] = decision['best_trade_play']
    decision['top_plays'] = ranked.get('top_plays', decision.get('top_plays', []))
    decision['avoid_plays'] = ranked.get('avoid_plays', decision.get('avoid_plays', []))
    decision['long_grid'] = grid_cmd.get('long_grid', decision.get('long_grid', 'HOLD'))
    decision['short_grid'] = grid_cmd.get('short_grid', decision.get('short_grid', 'HOLD'))
    decision['liquidity_context'] = (payload.get('liquidity_map') or {}).get('liquidity_state', decision.get('liquidity_context', 'NEUTRAL'))
    decision['price_oi_regime'] = (payload.get('derivatives_context') or {}).get('price_oi_regime', decision.get('price_oi_regime', 'NEUTRAL'))
    decision['funding_state'] = (payload.get('derivatives_context') or {}).get('funding_state', decision.get('funding_state', 'NEUTRAL'))
    decision['squeeze_risk'] = (payload.get('derivatives_context') or {}).get('squeeze_risk', decision.get('squeeze_risk', 'LOW'))
    decision['derivatives_summary'] = (payload.get('derivatives_context') or {}).get('summary', decision.get('derivatives_summary', ''))
    decision['micro_bias'] = (payload.get('microstructure') or {}).get('micro_bias', decision.get('micro_bias', 'NEUTRAL'))
    decision['microstructure_summary'] = (payload.get('microstructure') or {}).get('summary', decision.get('microstructure_summary', ''))
    decision['expectancy_long'] = expectancy.get('exp_long', 0.0)
    decision['expectancy_short'] = expectancy.get('exp_short', 0.0)
    decision['volatility_summary'] = vol_ctx.get('summary', '')
    decision['impulse_strength'] = vol_ctx.get('impulse_strength', 'LOW')
    decision['countertrend_risk'] = vol_ctx.get('countertrend_risk', 'LOW')
    decision['orderflow_summary'] = orderflow.get('summary', '')
    decision['orderflow_bias'] = orderflow.get('bias', 'NEUTRAL')
    decision['liquidation_summary'] = liq_ctx.get('summary', '')
    decision['liquidation_magnet'] = liq_ctx.get('magnet_side', 'NEUTRAL')
    decision['liquidation_cascade_risk'] = liq_ctx.get('cascade_risk', 'LOW')
    decision['liquidity_state_live'] = liq_ctx.get('liquidity_state', 'NEUTRAL')
    decision['fast_move_classification'] = fast_move.get('classification', 'BALANCED')
    decision['fast_move_summary'] = fast_move.get('summary', '')
    decision['fast_move_action'] = fast_move.get('action', '')
    decision['fast_move_long_action'] = fast_move.get('long_action', '')
    decision['fast_move_short_action'] = fast_move.get('short_action', '')
    decision['fast_move_watch'] = fast_move.get('watch_text', '')
    decision['fast_move_alert'] = fast_move.get('alert_text', '')
    decision['continuation_target'] = fast_move.get('continuation_target', '')
    soft_signal = payload.get('soft_signal', {}) if isinstance(payload.get('soft_signal'), dict) else {}
    fake_move_detector = payload.get('fake_move_detector', {}) if isinstance(payload.get('fake_move_detector'), dict) else {}
    move_projection = payload.get('move_projection', {}) if isinstance(payload.get('move_projection'), dict) else {}
    decision['soft_signal'] = soft_signal
    decision['fake_move_detector'] = fake_move_detector
    decision['move_projection'] = move_projection
    decision = _apply_fake_move_decision_modifier(decision, fake_move_detector)
    move_type_context = build_move_type_context(payload, decision)
    bot_mode_context = build_bot_mode_context(payload, decision, move_type_context)
    action_output = build_action_output(payload, decision, move_type_context, bot_mode_context)
    decision['move_type_context'] = move_type_context
    decision['bot_mode_context'] = bot_mode_context
    decision['range_bot_permission'] = bot_mode_context.get('range_bot_permission', {})
    decision['bot_mode_action'] = bot_mode_context.get('bot_mode_action', 'OFF')
    decision['directional_action'] = decision.get('action', 'WAIT')
    decision['action_output'] = action_output
    decision['edge_score_data'] = {
        'score': decision.get('edge_score', 0.0),
        'label': decision.get('edge_label', 'NO_EDGE'),
        'action': decision.get('edge_action', 'NO_TRADE'),
        'side': decision.get('edge_side', 'NEUTRAL'),
    }
    decision = _apply_v771_confidence_split(decision)
    decision = _apply_v780_consistency_engine(decision, payload)
    decision = _apply_manager_action_guard(decision)
    decision = _apply_best_trade_guard(decision)
    decision = _apply_range_bot_best_trade_override(decision)
    decision['is_no_trade'] = bool(no_trade.get('is_no_trade', False))
    decision['no_trade_level'] = no_trade.get('level', 'LOW')
    decision['no_trade_reasons'] = no_trade.get('reasons', [])
    decision['setup_type'] = (payload.get('ml_v2') or {}).get('setup_type', decision.get('setup_type', 'unknown'))
    decision['ml_probability'] = (payload.get('ml_v2') or {}).get('probability', decision.get('ml_probability', 0.5))
    decision['pattern_long_prob'] = (payload.get('pattern_memory_v2') or {}).get('long_prob', decision.get('pattern_long_prob', 50.0))
    decision['pattern_short_prob'] = (payload.get('pattern_memory_v2') or {}).get('short_prob', decision.get('pattern_short_prob', 50.0))
    decision['mfe'] = (payload.get('backtest_v2') or {}).get('mfe', decision.get('mfe', 0.0))
    decision['mae'] = (payload.get('backtest_v2') or {}).get('mae', decision.get('mae', 0.0))
    decision['adaptive_weights'] = payload.get('adaptive_weights', decision.get('adaptive_weights', {}))

    scenario_rank = payload.get('scenario_rank', {}) if isinstance(payload.get('scenario_rank'), dict) else {}
    primary = scenario_rank.get('primary', {}) if isinstance(scenario_rank.get('primary'), dict) else {}
    alternative = scenario_rank.get('alternative', {}) if isinstance(scenario_rank.get('alternative'), dict) else {}
    factor = payload.get('factor_breakdown', {}) if isinstance(payload.get('factor_breakdown'), dict) else {}
    authority = payload.get('bot_authority_v2', {}) if isinstance(payload.get('bot_authority_v2'), dict) else {}

    decision['scenario_base'] = f"{primary.get('side','NEUTRAL')} {primary.get('status','NO_EDGE')} | zone {primary.get('zone','нет данных')}"
    decision['scenario_alt'] = f"{alternative.get('side','NEUTRAL')} {alternative.get('status','ALT')} | zone {alternative.get('zone','нет данных')}"
    decision['scenario_invalidation'] = scenario_rank.get('invalidation', 'при закреплении против направления → сценарий отменяется')
    decision['pretrade_signal'] = scenario_rank.get('pretrade_signal', 'WAIT')
    decision['scenario_reasons'] = scenario_rank.get('reasons', [])
    decision['factor_breakdown'] = factor
    decision['scenario_primary'] = primary
    decision['scenario_alternative'] = alternative
    decision['trigger_readiness'] = scenario_rank.get('trigger_readiness', primary.get('readiness', 0.0))
    decision['action_layer_hint'] = scenario_rank.get('action_now_hint', '')
    decision['bot_authority'] = authority.get('authority', decision.get('bot_authority', 'NOT_AUTHORIZED'))
    decision['bot_authority_cards'] = authority.get('cards', [])
    decision['master_mode'] = authority.get('master_mode', 'WAIT')
    decision['smart_neutral'] = 'BALANCED' if factor.get('dominance') == 'NEUTRAL' else 'PRE-BREAK COMPRESSION' if str(decision.get('market_submode','')).upper().startswith('RANGE') else 'TRANSITION'

    if factor.get('dominance') == 'LONG' and str(factor.get('edge_stage')).upper() in {'PREPARE','BUILDING'}:
        decision['direction_text'] = 'ЛОНГ BIAS'
        decision['action_text'] = 'ГОТОВИТЬ ЛОНГ'
    elif factor.get('dominance') == 'SHORT' and str(factor.get('edge_stage')).upper() in {'PREPARE','BUILDING'}:
        decision['direction_text'] = 'ШОРТ BIAS'
        decision['action_text'] = 'ГОТОВИТЬ ШОРТ'

    best_play = decision.get('best_trade_play', 'wait')
    if best_play == 'wait':
        decision['action_now'] = 'ЖДАТЬ'
    elif 'grid' in best_play:
        decision['action_now'] = 'ВЕСТИ СЕТКУ'
    elif 'trend' in best_play:
        decision['action_now'] = 'СМОТРЕТЬ ТРЕНДОВЫЙ ВХОД'
    elif 'countertrend' in best_play:
        decision['action_now'] = 'СМОТРЕТЬ КОНТРТРЕНД'
    else:
        decision['action_now'] = 'ЖДАТЬ'
    decision['action_note'] = ''
    if decision['is_no_trade']:
        decision['best_trade_play'] = 'wait'
        decision['best_trade_side'] = 'FLAT'
        decision['best_trade_score'] = max(float(decision.get('best_trade_score', 0.0) or 0.0), 55.0)
        decision['best_play'] = 'wait'
        decision['action_now'] = 'ЖДАТЬ'
        decision['action_note'] = 'NO TRADE FILTER ACTIVE'
        decision['long_grid'] = 'OFF'
        decision['short_grid'] = 'OFF'
    elif decision.get('pretrade_signal', 'WAIT') != 'WAIT':
        decision['action_note'] = f"{decision.get('pretrade_signal')} | {decision.get('master_mode', 'WAIT')}"
        if decision.get('action_layer_hint'):
            decision['action_now'] = decision.get('action_layer_hint')
    elif decision.get('action_layer_hint'):
        decision['action_now'] = decision.get('action_layer_hint')
    if str(decision.get('fast_move_classification','')).upper() in {'LIKELY_FAKE_UP','LIKELY_FAKE_DOWN','CONTINUATION_UP','CONTINUATION_DOWN','POST_LIQUIDATION_EXHAUSTION'}:
        decision['action_note'] = decision.get('fast_move_alert') or decision.get('action_note','')
    return decision
