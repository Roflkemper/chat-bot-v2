from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from .models import CapturedEvent, EventSeverity, EventType, ManualAnnotation, MarketContext, OutcomeRecord, PortfolioContext


def _dump_dt(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def market_context_to_dict(ctx: MarketContext) -> dict[str, Any]:
    return asdict(ctx)


def market_context_from_dict(data: dict[str, Any]) -> MarketContext:
    return MarketContext(
        price_btc=float(data.get("price_btc", 0.0) or 0.0),
        regime_label=str(data.get("regime_label", "unknown")),
        regime_modifiers=list(data.get("regime_modifiers", []) or []),
        rsi_1h=data.get("rsi_1h"),
        rsi_5m=data.get("rsi_5m"),
        price_change_5m_pct=float(data.get("price_change_5m_pct", 0.0) or 0.0),
        price_change_1h_pct=float(data.get("price_change_1h_pct", 0.0) or 0.0),
        atr_normalized=data.get("atr_normalized"),
        session_kz=str(data.get("session_kz", "NONE")),
        nearest_liq_above=data.get("nearest_liq_above"),
        nearest_liq_below=data.get("nearest_liq_below"),
    )


def portfolio_context_to_dict(ctx: PortfolioContext) -> dict[str, Any]:
    return asdict(ctx)


def portfolio_context_from_dict(data: dict[str, Any]) -> PortfolioContext:
    return PortfolioContext(
        depo_total=float(data.get("depo_total", 0.0) or 0.0),
        shorts_unrealized_usd=float(data.get("shorts_unrealized_usd", 0.0) or 0.0),
        longs_unrealized_usd=float(data.get("longs_unrealized_usd", 0.0) or 0.0),
        net_unrealized_usd=float(data.get("net_unrealized_usd", 0.0) or 0.0),
        free_margin_pct=float(data.get("free_margin_pct", 0.0) or 0.0),
        drawdown_pct=float(data.get("drawdown_pct", 0.0) or 0.0),
        shorts_position_btc=float(data.get("shorts_position_btc", 0.0) or 0.0),
        longs_position_usd=float(data.get("longs_position_usd", 0.0) or 0.0),
    )


def event_to_dict(event: CapturedEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "ts": _dump_dt(event.ts),
        "event_type": event.event_type.value,
        "severity": event.severity.value,
        "bot_id": event.bot_id,
        "summary": event.summary,
        "payload": event.payload,
        "market_context": market_context_to_dict(event.market_context),
        "portfolio_context": portfolio_context_to_dict(event.portfolio_context),
    }


def event_from_dict(data: dict[str, Any]) -> CapturedEvent:
    return CapturedEvent(
        event_id=str(data["event_id"]),
        ts=_parse_dt(str(data["ts"])),
        event_type=EventType(str(data["event_type"])),
        severity=EventSeverity(str(data["severity"])),
        bot_id=data.get("bot_id"),
        summary=str(data.get("summary", "")),
        payload=dict(data.get("payload", {}) or {}),
        market_context=market_context_from_dict(dict(data.get("market_context", {}) or {})),
        portfolio_context=portfolio_context_from_dict(dict(data.get("portfolio_context", {}) or {})),
    )


def annotation_to_dict(annotation: ManualAnnotation) -> dict[str, Any]:
    return {
        "event_id": annotation.event_id,
        "annotation_ts": _dump_dt(annotation.annotation_ts),
        "is_intentional": annotation.is_intentional,
        "reason": annotation.reason,
    }


def annotation_from_dict(data: dict[str, Any]) -> ManualAnnotation:
    return ManualAnnotation(
        event_id=str(data["event_id"]),
        annotation_ts=_parse_dt(str(data["annotation_ts"])),
        is_intentional=bool(data.get("is_intentional", False)),
        reason=data.get("reason"),
    )


def outcome_to_dict(outcome: OutcomeRecord) -> dict[str, Any]:
    return {
        "event_id": outcome.event_id,
        "checkpoint_minutes": outcome.checkpoint_minutes,
        "checkpoint_ts": _dump_dt(outcome.checkpoint_ts),
        "price_at_checkpoint": outcome.price_at_checkpoint,
        "shorts_unrealized_at_checkpoint": outcome.shorts_unrealized_at_checkpoint,
        "longs_unrealized_at_checkpoint": outcome.longs_unrealized_at_checkpoint,
        "delta_pnl_since_event": outcome.delta_pnl_since_event,
        "delta_pnl_classification": outcome.delta_pnl_classification,
    }


def outcome_from_dict(data: dict[str, Any]) -> OutcomeRecord:
    return OutcomeRecord(
        event_id=str(data["event_id"]),
        checkpoint_minutes=int(data["checkpoint_minutes"]),
        checkpoint_ts=_parse_dt(str(data["checkpoint_ts"])),
        price_at_checkpoint=float(data.get("price_at_checkpoint", 0.0) or 0.0),
        shorts_unrealized_at_checkpoint=float(data.get("shorts_unrealized_at_checkpoint", 0.0) or 0.0),
        longs_unrealized_at_checkpoint=float(data.get("longs_unrealized_at_checkpoint", 0.0) or 0.0),
        delta_pnl_since_event=float(data.get("delta_pnl_since_event", 0.0) or 0.0),
        delta_pnl_classification=str(data.get("delta_pnl_classification", "neutral")),
    )
