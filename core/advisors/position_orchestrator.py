from __future__ import annotations

from advisors.ginarea_advisor import build_ginarea_advice
from advisors.position_advisor import advise_position
from advisors.position_state_machine import can_transition


class PositionOrchestrator:
    def __init__(self, position_manager):
        self.position_manager = position_manager

    def run(self, snapshot: dict) -> dict:
        key = f"{snapshot['symbol']}:{snapshot['timeframe']}"
        current = self.position_manager.get(key)
        current_state = current.get("state", "CANDIDATE")
        advice = advise_position(snapshot, current_state)
        gin = build_ginarea_advice(snapshot)

        next_state = advice["target_state"] if can_transition(current_state, advice["target_state"]) else current_state
        new_state = {
            "state": next_state,
            "last_signal": snapshot["signal"],
            "last_price": snapshot["price"],
            "entry_zone": advice["entry_zone"],
            "tp1": advice["tp1"],
            "tp2": advice["tp2"],
            "invalidation": advice["invalidation"],
        }
        self.position_manager.set(key, new_state)

        return {
            "position_key": key,
            "from_state": current_state,
            "to_state": next_state,
            "advice": advice,
            "ginarea": gin,
        }
