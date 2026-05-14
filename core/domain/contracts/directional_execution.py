from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DirectionalExecution:
    enabled: bool
    side: str
    state: str
    entry_model: str
    entry_zone: str
    trigger: str
    invalidation_zone: str
    stop_logic: str
    tp1: str
    tp2: str
    be_rule: str
    partial_exit_rule: str
    chase_allowed: bool
    preferred_mode: str
    size_hint: str
    execution_note: str
