from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketContext:
    market_identity: dict[str, Any] = field(default_factory=dict)
    regime_context: dict[str, Any] = field(default_factory=dict)
    location_context: dict[str, Any] = field(default_factory=dict)
    liquidity_context: dict[str, Any] = field(default_factory=dict)
    movement_context: dict[str, Any] = field(default_factory=dict)
    confirmation_context: dict[str, Any] = field(default_factory=dict)
    reversal_context: dict[str, Any] = field(default_factory=dict)
    pattern_context: dict[str, Any] = field(default_factory=dict)
    risk_context: dict[str, Any] = field(default_factory=dict)
    strategy_allowance_context: dict[str, Any] = field(default_factory=dict)
    watch_context: dict[str, Any] = field(default_factory=dict)
