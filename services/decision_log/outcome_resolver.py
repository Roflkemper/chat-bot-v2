from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .event_detector import _load_latest_advise_market_context, build_portfolio_context
from .models import OutcomeRecord, PortfolioContext
from .storage import EVENTS_PATH, OUTCOMES_PATH, append_outcome, iter_events, iter_outcomes

CHECKPOINTS = (60, 240, 1440)


def _classify_delta(delta_pnl_usd: float) -> str:
    if delta_pnl_usd > 50.0:
        return "positive"
    if delta_pnl_usd < -50.0:
        return "negative"
    return "neutral"


def outcome_resolver_run_once(
    *,
    events_path: Path = EVENTS_PATH,
    outcomes_path: Path = OUTCOMES_PATH,
    now: datetime | None = None,
    current_price: float | None = None,
    current_portfolio: PortfolioContext | None = None,
) -> list[OutcomeRecord]:
    current_now = now or datetime.now(timezone.utc)
    existing = {(item.event_id, item.checkpoint_minutes) for item in iter_outcomes(outcomes_path)}
    if current_portfolio is None or current_price is None:
        market_context, free_margin_pct = _load_latest_advise_market_context()
        current_price = market_context.price_btc if current_price is None else current_price
        current_portfolio = build_portfolio_context({}, free_margin_pct=free_margin_pct) if current_portfolio is None else current_portfolio

    created: list[OutcomeRecord] = []
    for event in iter_events(events_path):
        for checkpoint in CHECKPOINTS:
            key = (event.event_id, checkpoint)
            if key in existing:
                continue
            checkpoint_ts = event.ts + timedelta(minutes=checkpoint)
            if checkpoint_ts > current_now:
                continue
            delta_pnl = current_portfolio.net_unrealized_usd - event.portfolio_context.net_unrealized_usd
            record = OutcomeRecord(
                event_id=event.event_id,
                checkpoint_minutes=checkpoint,
                checkpoint_ts=current_now,
                price_at_checkpoint=float(current_price),
                shorts_unrealized_at_checkpoint=current_portfolio.shorts_unrealized_usd,
                longs_unrealized_at_checkpoint=current_portfolio.longs_unrealized_usd,
                delta_pnl_since_event=delta_pnl,
                delta_pnl_classification=_classify_delta(delta_pnl),
            )
            append_outcome(record, outcomes_path)
            existing.add(key)
            created.append(record)
    return created
