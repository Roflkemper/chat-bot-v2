from __future__ import annotations


def advise_position(snapshot: dict, current_state: str) -> dict:
    signal = snapshot["signal"]
    allow = snapshot["filters"]["allow"]
    plan = snapshot["execution_plan"]

    if signal == "NO TRADE":
        action = "WAIT"
        target_state = "CANDIDATE"
    elif current_state in {"CANDIDATE", "WAIT_REENTRY"} and allow:
        action = "PREPARE_ENTRY"
        target_state = "READY"
    elif current_state == "READY" and allow:
        action = "ENTER_ON_CONFIRMATION"
        target_state = "ENTERED"
    elif current_state in {"ENTERED", "MANAGE"}:
        action = "MANAGE_POSITION"
        target_state = "MANAGE"
    else:
        action = "WAIT"
        target_state = current_state

    return {
        "action": action,
        "target_state": target_state,
        "entry_zone": plan["entry_zone"],
        "tp1": plan["tp1"],
        "tp2": plan["tp2"],
        "invalidation": plan["invalidation"],
    }
