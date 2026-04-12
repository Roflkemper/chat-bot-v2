from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FinalDecision:
    symbol: str
    timeframe: str
    timestamp: str
    directional_state: str
    directional_side: str
    directional_strategy_id: str
    directional_score: float
    directional_confidence: float
    grid_state: str
    grid_side: str
    grid_strategy_id: str
    grid_score: float
    grid_confidence: float
    market_bias: str
    primary_action: str
    primary_mode: str
    risk_level: str
    why: list[str] = field(default_factory=list)
    not_now: list[str] = field(default_factory=list)
    where_to_watch: str = ''
    next_trigger_long: str = ''
    next_trigger_short: str = ''
    invalidation_zone: str = ''
    warnings: list[str] = field(default_factory=list)
