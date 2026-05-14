from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RawMarketContext:
    symbol: str
    timeframe: str
    timestamp: str
    current_price: float
    last_close: float
    candles_main_tf: list[dict[str, Any]] = field(default_factory=list)
    candles_higher_tf: list[dict[str, Any]] = field(default_factory=list)
    volume_snapshot: dict[str, Any] = field(default_factory=dict)
    orderflow_snapshot: dict[str, Any] = field(default_factory=dict)
    liquidity_feed_status: str = 'unknown'
    liquidation_feed_status: str = 'unknown'
    source_health: dict[str, str] = field(default_factory=dict)
    fallback_flags: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    data_quality_score: float = 0.0
