from __future__ import annotations

from typing import Any


def _side_from_signal(signal: Any) -> str:
    s = str(signal or "").upper()
    if "LONG" in s:
        return "LONG"
    if "SHORT" in s:
        return "SHORT"
    return "NONE"


def build_final_decision(snapshot: dict, orch: dict) -> dict:
    signal = str(snapshot.get("signal") or "NO TRADE").upper()
    regime = snapshot.get("regime")
    confidence = float(snapshot.get("confidence") or 0.0)
    urgency = float(snapshot.get("urgency") or 0.0)

    filters = snapshot.get("filters") or {}
    allow = bool(filters.get("allow", False))
    reasons = filters.get("reasons") or []

    to_state = orch.get("to_state") or "UNKNOWN"
    side = _side_from_signal(signal)

    if not allow:
        final_decision = "NO TRADE"
        if "LONG" in signal:
            telegram_action_now = "ЖДАТЬ LONG-ПОДТВЕРЖДЕНИЕ"
        elif "SHORT" in signal:
            telegram_action_now = "ЖДАТЬ SHORT-ПОДТВЕРЖДЕНИЕ"
        else:
            telegram_action_now = "СИДЕТЬ ВНЕ РЫНКА"

    elif side == "LONG":
        if confidence >= 65 and urgency >= 60:
            final_decision = "ENTER LONG"
            telegram_action_now = "МОЖНО ИСКАТЬ LONG"
        else:
            final_decision = "WAIT LONG"
            telegram_action_now = "ЖДАТЬ LONG-ПОДТВЕРЖДЕНИЕ"

    elif side == "SHORT":
        if confidence >= 65 and urgency >= 60:
            final_decision = "ENTER SHORT"
            telegram_action_now = "МОЖНО ИСКАТЬ SHORT"
        else:
            final_decision = "WAIT SHORT"
            telegram_action_now = "ЖДАТЬ SHORT-ПОДТВЕРЖДЕНИЕ"

    else:
        final_decision = "NO TRADE"
        telegram_action_now = "СИДЕТЬ ВНЕ РЫНКА"

    reasons_text = ", ".join(str(x) for x in reasons) if reasons else "ограничений нет"

    final_summary = (
        f"{final_decision} | regime={regime} | urgency={round(urgency, 2)} | "
        f"confidence={round(confidence, 2)} | state={to_state}"
    )

    telegram_summary = (
        f"Режим: {regime} | confidence: {round(confidence, 1)} | "
        f"urgency: {round(urgency, 1)} | причины: {reasons_text}"
    )

    return {
        "final_decision": final_decision,
        "final_summary": final_summary,
        "telegram_action_now": telegram_action_now,
        "telegram_summary": telegram_summary,
    }