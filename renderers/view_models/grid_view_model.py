from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GridViewModel:
    decision_bias: str
    current_grid_action: str
    long_grid_state: str
    short_grid_state: str
    grid_reason: str
    zones_summary: str
    grid_note: str
