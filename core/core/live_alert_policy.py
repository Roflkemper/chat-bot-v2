from __future__ import annotations

from typing import Any, Dict


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _s(value: Any, default: str = "") -> str:
    return str(value or default)


def build_live_alert_policy(analysis: Dict[str, Any] | None = None) -> Dict[str, Any]:
    analysis = analysis or {}

    fast_move = analysis.get("fast_move") if isinstance(analysis.get("fast_move"), dict) else analysis.get("fast_move_context") if isinstance(analysis.get("fast_move_context"), dict) else {}
    liquidation = analysis.get("liquidation_context") if isinstance(analysis.get("liquidation_context"), dict) else {}
    scenario = analysis.get("scenario_engine") if isinstance(analysis.get("scenario_engine"), dict) else {}
    decision = analysis.get("decision") if isinstance(analysis.get("decision"), dict) else {}
    soft = analysis.get("soft_signal") if isinstance(analysis.get("soft_signal"), dict) else {}
    tactical = analysis.get("tactical_edge") if isinstance(analysis.get("tactical_edge"), dict) else {}
    bot_center = analysis.get("bot_control_center") if isinstance(analysis.get("bot_control_center"), dict) else {}

    classification = _s(fast_move.get("classification"), "BALANCED").upper()
    confidence = _f(fast_move.get("confidence"), _f(decision.get("confidence"), 48.0))
    cascade_risk = _s(liquidation.get("cascade_risk"), "LOW").upper()
    magnet_side = _s(liquidation.get("magnet_side"), "NEUTRAL").upper()
    scenario_state = _s(scenario.get("scenario_state"), decision.get("scenario_status", "")).upper()
    acceptance_state = _s(fast_move.get("acceptance_state"), "UNDEFINED").upper()
    reclaim_state = _s(fast_move.get("reclaim_state") or tactical.get("reclaim_state"), "UNDEFINED").upper()
    trap_bias = _s(liquidation.get("trap_bias"), "NEUTRAL").upper()
    top_permission = _s(bot_center.get("top_permission"), "").upper()

    priority = "LOW"
    cooldown_sec = 600
    event_family = "status_update"
    invalidate_zone = _s(decision.get("invalidation") or fast_move.get("invalidation") or scenario.get("invalidation") or "нет данных")
    next_zone = _s(fast_move.get("continuation_target") or scenario.get("primary_target") or tactical.get("next_trigger") or "нет данных")
    anti_spam_key = f"{classification}:{magnet_side}:{scenario_state}:{acceptance_state}:{reclaim_state}:{int(confidence)}"

    if classification in {"LIKELY_FAKE_UP", "LIKELY_FAKE_DOWN"}:
        event_family = "fake_breakout"
        priority = "HIGH" if confidence >= 64 else "MEDIUM"
        cooldown_sec = 180 if confidence >= 70 else 240
    elif classification in {"EARLY_FAKE_UP_RISK", "EARLY_FAKE_DOWN_RISK"}:
        event_family = "trap_risk"
        priority = "MEDIUM"
        cooldown_sec = 210
    elif classification in {"CONTINUATION_UP", "CONTINUATION_DOWN"}:
        event_family = "continuation_confirmed"
        priority = "HIGH" if cascade_risk == "HIGH" or confidence >= 68 or "CONFIRMED" in acceptance_state else "MEDIUM"
        cooldown_sec = 180 if priority == "HIGH" else 300
    elif classification in {"WEAK_CONTINUATION_UP", "WEAK_CONTINUATION_DOWN"}:
        event_family = "continuation_watch"
        priority = "MEDIUM"
        cooldown_sec = 240
    elif classification in {"POST_LIQUIDATION_EXHAUSTION", "SQUEEZE_WITHOUT_CONFIRMATION"}:
        event_family = "exhaustion_alert"
        priority = "HIGH" if "EXHAUST" in acceptance_state else "MEDIUM"
        cooldown_sec = 240
    elif "FAILED" in acceptance_state or reclaim_state in {"FAILED", "LOST"}:
        event_family = "reclaim_failed"
        priority = "HIGH"
        cooldown_sec = 180
    elif scenario_state in {"TRIGGERED", "READY"} or bool(soft.get("active")):
        event_family = "setup_trigger"
        priority = "MEDIUM"
        cooldown_sec = 300

    if trap_bias in {"TRAP_UP", "TRAP_DOWN", "FAKE_UP", "FAKE_DOWN"} and priority == "LOW":
        priority = "MEDIUM"
        event_family = "trap_risk"
        cooldown_sec = min(cooldown_sec, 240)

    if top_permission in {"ALLOW", "SMALL ONLY"} and priority == "LOW":
        event_family = "bot_activation"
        priority = "MEDIUM"
        cooldown_sec = 300

    should_alert = priority in {"MEDIUM", "HIGH"}
    suppress_secondary = priority == "LOW" or (event_family in {"status_update", "continuation_watch"} and confidence < 58)

    return {
        "priority": priority,
        "cooldown_sec": int(cooldown_sec),
        "anti_spam_key": anti_spam_key,
        "invalidate_zone": invalidate_zone,
        "next_zone": next_zone,
        "classification": classification,
        "magnet_side": magnet_side,
        "acceptance_state": acceptance_state,
        "reclaim_state": reclaim_state,
        "event_family": event_family,
        "should_alert": bool(should_alert),
        "suppress_secondary": bool(suppress_secondary),
        "trap_bias": trap_bias,
        "top_permission": top_permission,
    }
