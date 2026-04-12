from __future__ import annotations

VALID_TRANSITIONS = {
    "NO_TRADE": ["ENTRY"],
    "ENTRY": ["TP1", "PARTIAL_DONE", "BE_MOVED", "HOLD_RUNNER", "EXIT"],
    "TP1": ["PARTIAL_DONE", "BE_MOVED", "HOLD_RUNNER", "EXIT"],
    "PARTIAL_DONE": ["BE_MOVED", "HOLD_RUNNER", "EXIT"],
    "BE_MOVED": ["HOLD_RUNNER", "EXIT"],
    "HOLD_RUNNER": ["EXIT"],
    "EXIT": ["ENTRY", "NO_TRADE"],
}


def can_transition(current: str, target: str) -> bool:
    current = str(current or "NO_TRADE").upper()
    target = str(target or "NO_TRADE").upper()
    return target in VALID_TRANSITIONS.get(current, [])
