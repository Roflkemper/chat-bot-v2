from __future__ import annotations

import time
from typing import Any, Dict, Optional

from storage.json_store import load_json, save_json
from storage.position_store import load_position_state

try:
    from core.live_alert_policy import build_live_alert_policy
except Exception:
    build_live_alert_policy = None

try:
    from core.live_context_memory import build_live_context_memory
except Exception:
    build_live_context_memory = None

STATE_FILE = "state/transition_alert_state.json"
COOLDOWN_SECONDS = 300
MIN_REPEAT_SECONDS = 90


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


def _analysis_dict(snapshot_or_dict: Any) -> Dict[str, Any]:
    if snapshot_or_dict is None:
        return {}
    if isinstance(snapshot_or_dict, dict):
        return dict(snapshot_or_dict)
    if hasattr(snapshot_or_dict, "to_dict"):
        try:
            data = snapshot_or_dict.to_dict()
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
    return {}


def _load_state() -> Dict[str, Any]:
    return load_json(STATE_FILE, {"by_timeframe": {}})


def _save_state(state: Dict[str, Any]) -> None:
    save_json(STATE_FILE, state)


def _pick(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    bags = [payload]
    for name in ("analysis", "decision", "setup_quality", "market_structure", "fast_move", "liquidation_context", "scenario_engine"):
        bag = payload.get(name)
        if isinstance(bag, dict):
            bags.append(bag)
    for bag in bags:
        for key in keys:
            if key in bag and bag.get(key) is not None:
                return bag.get(key)
    return default


def _normalize_status(value: str) -> str:
    val = _safe_str(value).upper().strip()
    if not val:
        return "OFF"
    return val


def _normalize_action_code(action_code: str, action_text: str) -> str:
    code = _safe_str(action_code).upper().strip()
    if code:
        return code
    text = _safe_str(action_text).upper()
    if "ВХОД" in text:
        return "ENTER"
    if "СМОТР" in text or "SETUP" in text:
        return "WATCH"
    if "ДЕРЖ" in text:
        return "HOLD"
    if "СОКРА" in text or "ФИКС" in text:
        return "REDUCE"
    if "ВЫХ" in text or "ЗАКР" in text:
        return "EXIT"
    return "WAIT"


def _extract_current(snapshot_or_dict: Any) -> Dict[str, Any]:
    payload = _analysis_dict(snapshot_or_dict)
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    fast_move = payload.get("fast_move") if isinstance(payload.get("fast_move"), dict) else {}
    liquidation = payload.get("liquidation_context") if isinstance(payload.get("liquidation_context"), dict) else {}
    scenario = payload.get("scenario_engine") if isinstance(payload.get("scenario_engine"), dict) else {}
    pos = load_position_state()

    best_score = _safe_float(_pick(payload, "best_bot_score"), 0.0)
    if 0.0 <= best_score <= 1.0:
        best_score *= 100.0

    setup_valid = bool(_pick(payload, "setup_valid", default=False))
    choch_risk_raw = _pick(payload, "choch_risk", "structure_status", default="")
    choch_risk_text = _safe_str(choch_risk_raw).upper()
    choch_risk = choch_risk_text in {"1", "TRUE", "YES", "ДА", "CHOCH_RISK"} or "CHOCH_RISK" in choch_risk_text

    payload_out = {
        "timeframe": _safe_str(payload.get("timeframe") or "1h"),
        "price": round(_safe_float(payload.get("price"), 0.0), 2),
        "direction": _safe_str(decision.get("direction_text") or payload.get("final_decision") or "НЕЙТРАЛЬНО").upper(),
        "action": _safe_str(decision.get("action_text") or "ЖДАТЬ").upper(),
        "action_code": _normalize_action_code(decision.get("action") or "", decision.get("action_text") or "ЖДАТЬ"),
        "confidence": round(_safe_float(decision.get("confidence_pct") or decision.get("confidence") or payload.get("forecast_confidence"), 0.0), 1),
        "best_bot": _safe_str(
            analysis.get("best_bot_label")
            or analysis.get("best_bot")
            or analysis.get("preferred_bot")
            or payload.get("best_bot_label")
            or payload.get("best_bot")
            or payload.get("preferred_bot")
            or "нет данных"
        ),
        "best_bot_status": _normalize_status(analysis.get("best_bot_status") or payload.get("best_bot_status") or "OFF"),
        "best_bot_score": round(best_score, 1),
        "hold_bias": _safe_str(analysis.get("hold_bias") or payload.get("hold_bias") or "none").lower(),
        "range_state": _safe_str(payload.get("range_state") or analysis.get("range_state") or "нет данных"),
        "invalidation": _safe_str(decision.get("invalidation") or analysis.get("invalidation_hint") or payload.get("invalidation_hint") or "нет данных"),
        "has_position": bool(pos.get("has_position")),
        "position_side": _safe_str(pos.get("side") or "").upper(),
        "setup_grade": _safe_str(_pick(payload, "grade", "setup_grade", default="")).upper(),
        "setup_valid": setup_valid,
        "setup_status": _normalize_status(_pick(payload, "setup_status", default="")),
        "setup_status_text": _safe_str(_pick(payload, "setup_status_text", default="")),
        "structure_status": _safe_str(_pick(payload, "structure_status", default="")).upper(),
        "choch_risk": choch_risk,
        "fast_move_classification": _safe_str(_pick(payload, "classification", "fast_move_classification", default="BALANCED")).upper(),
        "move_acceptance": _safe_str(_pick(payload, "acceptance_state", "acceptance", default="UNDEFINED")).upper(),
        "reclaim_state": _safe_str(_pick(payload, "reclaim_state", default="UNDEFINED")).upper(),
        "scenario_state": _safe_str(_pick(payload, "scenario_state", default="")).upper(),
        "next_zone": _safe_str(_pick(payload, "continuation_target", "primary_target", default="нет данных")),
        "liquidity_state": _safe_str(_pick(payload, "liquidity_state", default="UNDEFINED")).upper(),
        "magnet_side": _safe_str(_pick(payload, "magnet_side", default="NEUTRAL")).upper(),
        "analysis": payload,
    }

    hold_bias = payload_out["hold_bias"]
    best_status = payload_out["best_bot_status"]
    if payload_out["direction"] in {"НЕЙТРАЛЬНО", "NEUTRAL"} and hold_bias in {"short", "long"} and best_status in {"WATCH", "READY", "ACTIVE", "SMALL ENTRY", "CAN ADD"}:
        payload_out["direction"] = "ШОРТ" if hold_bias == "short" else "ЛОНГ"
        payload_out["action_code"] = "ENTER" if best_status in {"READY", "ACTIVE", "SMALL ENTRY", "CAN ADD"} else "WATCH"
        payload_out["action"] = "ВХОДИТЬ" if payload_out["action_code"] == "ENTER" else "СМОТРЕТЬ СЕТАП"
        payload_out["confidence"] = round(max(payload_out["confidence"], payload_out["best_bot_score"]), 1)

    if payload_out["direction"] in {"ЛОНГ", "ШОРТ"} and payload_out["confidence"] <= 0.0:
        payload_out["confidence"] = round(max(payload_out["best_bot_score"], 51.0), 1)
    return payload_out


def _same_alert_recent(slot: Dict[str, Any], key: str, cooldown_seconds: int | None = None) -> bool:
    cooldown = int(cooldown_seconds or slot.get("cooldown_seconds") or COOLDOWN_SECONDS)
    now_ts = time.time()
    last_key = _safe_str(slot.get("last_alert_key"))
    last_ts = _safe_float(slot.get("last_alert_ts"), 0.0)
    if last_key != key:
        return False
    return (now_ts - last_ts) < max(cooldown, MIN_REPEAT_SECONDS)


def _store(slot: Dict[str, Any], current: Dict[str, Any], key: Optional[str] = None, cooldown_seconds: int | None = None, priority: str | None = None) -> None:
    slot["current"] = current
    slot["updated_at"] = time.time()
    if cooldown_seconds is not None:
        slot["cooldown_seconds"] = int(cooldown_seconds)
    if priority:
        slot["last_priority"] = _safe_str(priority).upper()
    if key:
        slot["last_alert_key"] = key
        slot["last_alert_ts"] = time.time()


def _side_ru(direction: str) -> str:
    d = _safe_str(direction).upper()
    if d in {"SHORT", "ШОРТ"}:
        return "ШОРТ"
    if d in {"LONG", "ЛОНГ"}:
        return "ЛОНГ"
    return "НЕЙТРАЛЬНО"


def _build_memory_line(current: Dict[str, Any]) -> str:
    if build_live_context_memory is None:
        return ""
    try:
        mem = build_live_context_memory(current) or {}
    except Exception:
        return ""
    parts = []
    if mem.get("acceptance_memory"):
        parts.append(f"acceptance: {mem['acceptance_memory']}")
    if mem.get("last_fake_signal"):
        parts.append(f"last fake: {mem['last_fake_signal']}")
    if mem.get("last_continuation_signal"):
        parts.append(f"last continuation: {mem['last_continuation_signal']}")
    return " | ".join(parts)


def _alert_header(event_family: str, priority: str) -> str:
    fam = _safe_str(event_family).lower()
    pr = _safe_str(priority).upper()
    if fam == "fake_breakout":
        return "🪤 FAKE BREAKOUT ALERT"
    if fam == "continuation_confirmed":
        return "🚀 CONTINUATION CONFIRMED"
    if fam == "exhaustion_alert":
        return "♻️ EXHAUSTION ALERT"
    if fam == "reclaim_failed":
        return "⛔ RECLAIM FAILED"
    if fam == "trap_risk":
        return "⚠️ TRAP RISK ALERT"
    if fam == "bot_activation":
        return "🤖 BOT LAYER ACTIVATION"
    return "🔔 LIVE ALERT" if pr in {"HIGH", "MEDIUM"} else "ℹ️ LIVE UPDATE"


def build_transition_alert(snapshot_or_dict: Any) -> str:
    state = _load_state()
    by_tf = state.setdefault("by_timeframe", {})
    current = _extract_current(snapshot_or_dict)
    tf = current["timeframe"]

    slot = by_tf.setdefault(tf, {})
    prev = slot.get("current") if isinstance(slot.get("current"), dict) else None

    if not prev:
        _store(slot, current)
        _save_state(state)
        return ""

    policy = {
        "priority": "LOW",
        "cooldown_sec": COOLDOWN_SECONDS,
        "anti_spam_key": "",
        "invalidate_zone": current.get("invalidation", "нет данных"),
        "next_zone": current.get("next_zone", "нет данных"),
        "classification": current.get("fast_move_classification", ""),
        "magnet_side": current.get("magnet_side", ""),
        "event_family": "status_update",
        "should_alert": True,
        "suppress_secondary": False,
    }
    if build_live_alert_policy is not None:
        try:
            policy.update(build_live_alert_policy(current.get("analysis")) or {})
        except Exception:
            pass

    if not bool(policy.get("should_alert", True)):
        _store(slot, current, cooldown_seconds=policy.get("cooldown_sec"), priority=policy.get("priority"))
        _save_state(state)
        return ""

    alerts: list[str] = []
    key: Optional[str] = None

    prev_dir = _side_ru(prev.get("direction"))
    prev_action = _safe_str(prev.get("action_code")).upper()
    prev_conf = _safe_float(prev.get("confidence"), 0.0)
    prev_best_status = _normalize_status(prev.get("best_bot_status"))
    prev_best_bot = _safe_str(prev.get("best_bot"))
    prev_class = _safe_str(prev.get("fast_move_classification")).upper()
    prev_accept = _safe_str(prev.get("move_acceptance")).upper()

    cur_dir = _side_ru(current["direction"])
    cur_action = _safe_str(current["action_code"]).upper()
    cur_conf = _safe_float(current["confidence"], 0.0)
    cur_best_status = _normalize_status(current["best_bot_status"])
    cur_best_bot = _safe_str(current["best_bot"])
    setup_valid = bool(current.get("setup_valid"))
    structure_status = _safe_str(current.get("structure_status")).upper()
    choch_risk = bool(current.get("choch_risk"))
    cur_class = _safe_str(current.get("fast_move_classification")).upper()
    cur_accept = _safe_str(current.get("move_acceptance")).upper()

    if prev_dir in {"ЛОНГ", "ШОРТ"} and cur_dir == "НЕЙТРАЛЬНО":
        key = f"cancel:{prev_dir}->{cur_dir}:{cur_action}"
        if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
            alerts = [
                "🚨 ACTION UPDATE — сценарий ослаб",
                f"Было: {prev_dir} / {prev.get('action')}",
                f"Стало: {cur_dir} / {current['action']}",
                "Действие: новый вход лучше не форсировать; если позиция уже есть, её лучше сократить или закрыть по месту.",
            ]
    elif prev_dir in {"ЛОНГ", "ШОРТ"} and cur_dir in {"ЛОНГ", "ШОРТ"} and prev_dir != cur_dir:
        key = f"flip:{prev_dir}->{cur_dir}"
        if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
            alerts = [
                "🔄 ACTION UPDATE — рынок сменил сторону",
                f"Было: {prev_dir}",
                f"Стало: {cur_dir}",
                "Действие: старый сценарий лучше не держать; новый вход смотреть только после подтверждения.",
            ]

    if not alerts and cur_class != prev_class:
        key = f"class-shift:{prev_class}->{cur_class}:{cur_dir}:{policy.get('event_family','status_update')}"
        if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
            title = _alert_header(policy.get("event_family", "status_update"), policy.get("priority", "LOW"))
            action_line = "Действие: наблюдаю дальше, дам сигнал если характер снова изменится."
            why_now = "Причина: изменился характер движения."
            if cur_class == "LIKELY_FAKE_UP":
                action_line = "Действие: вынос вверх похож на ложный; шорт смотреть только после возврата/слабой реакции. Лонги в зоне выноса лучше частично фиксировать."
                why_now = "Причина: рынок снял верхнюю ликвидность без чистого acceptance."
            elif cur_class == "LIKELY_FAKE_DOWN":
                action_line = "Действие: пролив вниз похож на ложный; лонг смотреть только после возврата/подтверждения. Шорты внизу лучше частично фиксировать."
                why_now = "Причина: рынок снял нижнюю ликвидность без чистого acceptance."
            elif cur_class == "EARLY_FAKE_UP_RISK":
                action_line = "Действие: ранний риск ложного выноса вверх; шорт без подтверждения не форсировать, нужен возврат под локальный high."
                why_now = "Причина: импульс вверх есть, но принятие движения ещё не подтверждено."
            elif cur_class == "EARLY_FAKE_DOWN_RISK":
                action_line = "Действие: ранний риск ложного пролива вниз; лонг только после reclaim и удержания возврата."
                why_now = "Причина: пролив выглядит агрессивно, но удержание низов ещё не подтверждено."
            elif cur_class == "CONTINUATION_UP":
                action_line = "Действие: движение вверх не выглядит ложным; шорты лучше прикрывать. Наблюдаю дальше на признаки выдоха."
                why_now = "Причина: пробитую зону удерживают, continuation подтверждается."
            elif cur_class == "CONTINUATION_DOWN":
                action_line = "Действие: движение вниз продолжается; лонги лучше защищать или сокращать. Контртренд без подтверждения слабый."
                why_now = "Причина: движение вниз принимают, продавец пока контролирует сценарий."
            elif cur_class == "WEAK_CONTINUATION_UP":
                action_line = "Действие: мягкое continuation вверх; не шортить в лоб, лонг смотреть только на retest."
            elif cur_class == "WEAK_CONTINUATION_DOWN":
                action_line = "Действие: мягкое continuation вниз; не добавлять лонг против движения, шорт только на retest."
            elif cur_class == "POST_LIQUIDATION_EXHAUSTION":
                action_line = "Действие: движение выдыхается после снятия ликвидности; в догонку не входить, ждать новую реакцию."
                why_now = "Причина: импульс сделал работу по ликвидности и теряет follow-through."
            alerts = [
                title,
                f"Было: {prev_class or 'UNDEFINED'}",
                f"Стало: {cur_class or 'UNDEFINED'}",
                why_now,
                action_line,
            ]

    if not alerts and cur_accept != prev_accept and cur_accept not in {"", "UNDEFINED"}:
        key = f"acceptance:{prev_accept}->{cur_accept}:{cur_dir}"
        if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
            if "FAILED" in cur_accept or "AT_RISK" in cur_accept:
                alerts = [
                    _alert_header("reclaim_failed", policy.get("priority", "HIGH")),
                    f"Сторона: {cur_dir}",
                    "Причина: движение не принимают чисто; агрессивное продолжение лучше не преследовать.",
                    "Действие: ждать новый reclaim / retest / возврат структуры.",
                ]
            elif "EXHAUST" in cur_accept:
                alerts = [
                    _alert_header("exhaustion_alert", policy.get("priority", "MEDIUM")),
                    f"Сторона: {cur_dir}",
                    "Причина: импульс выдыхается после движения.",
                    "Действие: часть можно фиксировать, новый вход только после новой структуры.",
                ]
            else:
                alerts = [
                    _alert_header("continuation_confirmed", policy.get("priority", "HIGH")),
                    f"Сторона: {cur_dir}",
                    "Причина: пробитую зону пока удерживают; сценарий продолжения усилился.",
                    "Действие: работать по тренду, без погони за ценой.",
                ]

    if not alerts:
        became_ready = prev_best_status not in {"READY", "ACTIVE", "SMALL ENTRY", "CAN ADD"} and cur_best_status in {"READY", "ACTIVE", "SMALL ENTRY", "CAN ADD"}
        confidence_jump = cur_conf >= 58.0 and prev_conf < 58.0
        if (became_ready or confidence_jump) and cur_dir in {"ЛОНГ", "ШОРТ"}:
            if not setup_valid or structure_status == "CHOCH_RISK" or choch_risk:
                key = f"entry_blocked:{cur_best_bot}:{cur_best_status}:{cur_dir}:{structure_status or 'NOSETUP'}"
                if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
                    reason = "есть CHOCH risk против входа" if (structure_status == "CHOCH_RISK" or choch_risk) else "фильтр входа пока не даёт чистого качества"
                    alerts = [
                        f"⚠️ ENTRY BLOCKED — {cur_best_bot}",
                        f"Статус: {prev_best_status or 'OFF'} → {cur_best_status}",
                        f"Сторона: {cur_dir}",
                        f"Confidence: {cur_conf:.1f}%",
                        f"Причина: {reason}.",
                        "Действие: не входить вслепую; ждать confirm / retest / clean trigger.",
                    ]
            else:
                key = f"entry_ready:{cur_best_bot}:{cur_best_status}:{cur_dir}"
                if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
                    action_hint = "можно смотреть вход небольшим размером" if cur_best_status in {"READY", "SMALL ENTRY"} else "можно искать вход по подтверждению"
                    alerts = [
                        _alert_header("bot_activation", policy.get("priority", "MEDIUM")) + f" — {cur_best_bot}",
                        f"Статус: {prev_best_status or 'OFF'} → {cur_best_status}",
                        f"Сторона: {cur_dir}",
                        f"Confidence: {cur_conf:.1f}%",
                        f"Действие: {action_hint}.",
                    ]

    if not alerts and current["has_position"] and current["position_side"]:
        pos_side = _side_ru(current["position_side"])
        if pos_side == cur_dir and cur_conf - prev_conf >= 6.0 and setup_valid and not choch_risk and cur_best_status in {"READY", "ACTIVE", "CAN ADD"}:
            key = f"add:{pos_side}:{cur_best_status}:{int(cur_conf)}"
            if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
                alerts = [
                    f"➕ ADD ALERT — {cur_best_bot}",
                    f"Сценарий усилился: {prev_conf:.1f}% → {cur_conf:.1f}%",
                    "Действие: можно аккуратно добавить только по подтверждению и без погони за ценой.",
                ]
        elif pos_side == cur_dir and ((prev_conf - cur_conf >= 8.0) or choch_risk or not setup_valid):
            key = f"reduce:{pos_side}:{int(cur_conf)}:{structure_status or 'SETUP'}"
            if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
                reason = "есть CHOCH risk" if choch_risk or structure_status == "CHOCH_RISK" else "сценарий ослаб"
                alerts = [
                    f"⚠️ REDUCE ALERT — {cur_best_bot}",
                    f"Позиция: {pos_side}",
                    f"Причина: {reason}.",
                    "Действие: лучше сократить размер или не добирать, пока подтверждение не вернётся.",
                ]
        elif pos_side != cur_dir and cur_dir in {"ЛОНГ", "ШОРТ"}:
            key = f"exit:{pos_side}->{cur_dir}"
            if not _same_alert_recent(slot, key, policy.get("cooldown_sec")):
                alerts = [
                    "⛔ EXIT ALERT — старый сценарий больше не лучший",
                    f"Позиция: {pos_side}",
                    f"Текущий перевес: {cur_dir}",
                    "Действие: лучше защищать позицию, сокращать или выходить по плану.",
                ]

    if alerts and policy.get("suppress_secondary") and _safe_str(policy.get("event_family")).lower() in {"status_update", "continuation_watch"}:
        alerts = []

    _store(slot, current, key if alerts else None, cooldown_seconds=policy.get("cooldown_sec"), priority=policy.get("priority"))
    if alerts:
        memory_line = _build_memory_line(current)
        if policy.get("priority") not in {"", "LOW"}:
            alerts.append(f"Priority: {policy.get('priority')}")
        if policy.get("event_family"):
            alerts.append(f"Класс алерта: {policy.get('event_family')}")
        if policy.get("next_zone") and policy.get("next_zone") != "нет данных":
            alerts.append(f"Следующая зона: {policy.get('next_zone')}")
            alerts.append(f"Что изменит взгляд: реакция относительно зоны {policy.get('next_zone')}")
        if policy.get("invalidate_zone") and policy.get("invalidate_zone") != "нет данных":
            alerts.append(f"Инвалидация: {policy.get('invalidate_zone')}")
        if memory_line:
            alerts.append(f"Память: {memory_line}")
    _save_state(state)
    return "\n".join(alerts).strip()
