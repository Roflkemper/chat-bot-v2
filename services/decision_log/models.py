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


def compute_severity(
    event_type: EventType,
    payload: dict[str, Any],
    market_context: MarketContext,
    portfolio_context: PortfolioContext,
) -> EventSeverity:
    if event_type == EventType.BOUNDARY_BREACH:
        regime = market_context.regime_label
        if regime in ("trend_up", "trend_down"):
            if abs(market_context.price_change_1h_pct) > 1.0:
                return EventSeverity.WARNING
            return EventSeverity.NOTICE
        return EventSeverity.INFO

    if event_type == EventType.PNL_EXTREME:
        depo = portfolio_context.depo_total
        if depo <= 0:
            return EventSeverity.WARNING
        pct = abs(float(payload.get("value", 0.0))) / depo * 100
        if pct < 3:
            return EventSeverity.INFO
        if pct < 5:
            return EventSeverity.NOTICE
        if pct < 8:
            return EventSeverity.WARNING
        return EventSeverity.CRITICAL

    if event_type == EventType.PNL_EVENT:
        depo = portfolio_context.depo_total
        if depo <= 0:
            return EventSeverity.WARNING
        pct = abs(float(payload.get("delta_pnl_usd", 0.0))) / depo * 100
        if pct < 1.5:
            return EventSeverity.INFO
        if pct < 3:
            return EventSeverity.NOTICE
        if pct < 5:
            return EventSeverity.WARNING
        return EventSeverity.CRITICAL

    if event_type == EventType.PARAM_CHANGE:
        return EventSeverity.WARNING

    if event_type == EventType.BOT_LIFECYCLE:
        return EventSeverity.WARNING

    if event_type == EventType.BOT_STATE_CHANGE:
        return EventSeverity.NOTICE

    if event_type == EventType.POSITION_CHANGE:
        pct = abs(float(payload.get("delta_ratio", 0.0))) * 100
        if pct < 10:
            return EventSeverity.INFO
        if pct < 25:
            return EventSeverity.NOTICE
        return EventSeverity.WARNING

    if event_type == EventType.MARGIN_ALERT:
        margin = float(payload.get("new_margin_pct", 100.0))
        if margin >= 30:
            return EventSeverity.INFO
        if margin >= 15:
            return EventSeverity.WARNING
        return EventSeverity.CRITICAL

    if event_type == EventType.MARGIN_RECOVERY:
        return EventSeverity.NOTICE

    if event_type == EventType.REGIME_CHANGE:
        return EventSeverity.NOTICE

    if event_type == EventType.LIQ_CLUSTER_TOUCH:
        return EventSeverity.WARNING

    return EventSeverity.WARNING
