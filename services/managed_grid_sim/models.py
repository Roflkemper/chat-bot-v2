from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RegimeLabel(Enum):
    RANGE = "range"
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    COMPRESSION = "compression"
    CASCADE_UP = "cascade_up"
    CASCADE_DOWN = "cascade_down"
    UNCERTAIN = "uncertain"


class TrendType(Enum):
    VOLATILE_TRENDING = "volatile_trending"
    SMOOTH_TRENDING = "smooth_trending"
    CASCADE_DRIVEN = "cascade_driven"
    UNCERTAIN = "uncertain"


class InterventionType(Enum):
    PAUSE_NEW_ENTRIES = "pause_new_entries"
    RESUME_NEW_ENTRIES = "resume_new_entries"
    PARTIAL_UNLOAD = "partial_unload"
    MODIFY_PARAMS = "modify_params"
    ACTIVATE_BOOSTER = "activate_booster"
    RAISE_BOUNDARY = "raise_boundary"


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    bar_idx: int
    ts: datetime
    ohlcv: tuple[float, float, float, float, float]
    regime: RegimeLabel
    trend_type: TrendType
    delta_price_5m_pct: float
    delta_price_1h_pct: float
    delta_price_4h_pct: float
    atr_normalized: float
    pdh: float | None
    pdl: float | None
    volume_ratio_to_avg: float
    bars_since_last_pivot: int


@dataclass(frozen=True, slots=True)
class BotState:
    bot_id: str
    bot_alias: str
    side: str
    contract_type: str
    is_active: bool
    position_size_native: float
    position_size_usd: float
    avg_entry_price: float
    unrealized_pnl_usd: float
    hold_time_minutes: int
    bar_count_in_drawdown: int
    max_unrealized_pnl_usd: float
    min_unrealized_pnl_usd: float
    params_current: dict[str, Any]
    params_original: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InterventionEvent:
    bar_idx: int
    ts: datetime
    bot_id: str
    intervention_type: InterventionType
    params_before: dict[str, Any]
    params_after: dict[str, Any]
    reason: str
    market_snapshot: MarketSnapshot
    pnl_usd_at_event: float


@dataclass(frozen=True, slots=True)
class ManagedRunResult:
    run_id: str
    config_hash: str
    bot_configs: list[dict[str, Any]]
    trend_type: TrendType
    final_realized_pnl_usd: float
    final_unrealized_pnl_usd: float
    total_volume_usd: float
    max_drawdown_pct: float
    max_drawdown_usd: float
    sharpe_ratio: float
    total_trades: int
    total_interventions: int
    interventions_by_type: dict[InterventionType, int]
    intervention_log: list[InterventionEvent] = field(default_factory=list)
    bar_count: int = 0
    sim_duration_seconds: float = 0.0
