from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GridExecution:
    enabled: bool
    side: str
    state: str
    grid_mode: str
    arm_status: str
    add_allowed: bool
    reduce_allowed: bool
    exit_required: bool
    aggression_mode: str
    size_mode: str
    reactivation_rule: str
    kill_switch_reason: str
    grid_note: str
