from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    PARAM_CHANGE = "PARAM_CHANGE"
    BOT_LIFECYCLE = "BOT_LIFECYCLE"
    BOT_STATE_CHANGE = "BOT_STATE_CHANGE"
    POSITION_CHANGE = "POSITION_CHANGE"
    PNL_EVENT = "PNL_EVENT"
    PNL_EXTREME = "PNL_EXTREME"
    MARGIN_ALERT = "MARGIN_ALERT"
    MARGIN_RECOVERY = "MARGIN_RECOVERY"
    BOUNDARY_BREACH = "BOUNDARY_BREACH"
    LIQ_CLUSTER_TOUCH = "LIQ_CLUSTER_TOUCH"
    REGIME_CHANGE = "REGIME_CHANGE"


class EventSeverity(str, Enum):
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class MarketContext:
    price_btc: float
    regime_label: str
    regime_modifiers: list[str] = field(default_factory=list)
    rsi_1h: float | None = None
    rsi_5m: float | None = None
    price_change_5m_pct: float = 0.0
    price_change_1h_pct: float = 0.0
    atr_normalized: float | None = None
    session_kz: str = "NONE"
    nearest_liq_above: float | None = None
    nearest_liq_below: float | None = None


@dataclass(frozen=True, slots=True)
class PortfolioContext:
    depo_total: float
    shorts_unrealized_usd: float
    longs_unrealized_usd: float
    net_unrealized_usd: float
    free_margin_pct: float
    drawdown_pct: float
    shorts_position_btc: float
    longs_position_usd: float


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    event_id: str
    ts: datetime
    event_type: EventType
    severity: EventSeverity
    bot_id: str | None
    summary: str
    payload: dict[str, Any]
    market_context: MarketContext
    portfolio_context: PortfolioContext


@dataclass(frozen=True, slots=True)
class ManualAnnotation:
    event_id: str
    annotation_ts: datetime
    is_intentional: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    event_id: str
    checkpoint_minutes: int
    checkpoint_ts: datetime
    price_at_checkpoint: float
    shorts_unrealized_at_checkpoint: float
    longs_unrealized_at_checkpoint: float
    delta_pnl_since_event: float
    delta_pnl_classification: str
