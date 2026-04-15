from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ActionViewModel:
    price: float
    current_action: str
    what_now: str
    trigger: str
    invalidation: str
    ban_list: str
    action_note: str
