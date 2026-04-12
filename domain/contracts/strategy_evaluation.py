from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StrategyEvaluation:
    strategy_id: str
    family: str
    side: str
    state: str
    action_type: str
    score: float
    confidence: float
    summary: str
    why: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trigger: str = ''
    invalidation: str = ''
    entry_model: str = ''
    grid_bias: str = 'NONE'
    management_bias: str = 'NONE'
    vetoes: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
