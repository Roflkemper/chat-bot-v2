from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
from pathlib import Path

from services.decision_log.models import PortfolioContext
from services.decision_log.outcome_resolver import outcome_resolver_run_once
from services.decision_log.storage import append_event, iter_outcomes


def test_outcome_recorded_at_60min_checkpoint(tmp_path: Path, sample_event) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    append_event(sample_event, events_path)
    current_portfolio = replace(sample_event.portfolio_context, net_unrealized_usd=-300.0)
    created = outcome_resolver_run_once(
        events_path=events_path,
        outcomes_path=outcomes_path,
        now=sample_event.ts + timedelta(minutes=60),
        current_price=76600.0,
        current_portfolio=current_portfolio,
    )
    assert any(item.checkpoint_minutes == 60 for item in created)


def test_outcome_recorded_at_240min_checkpoint(tmp_path: Path, sample_event) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    append_event(sample_event, events_path)
    created = outcome_resolver_run_once(
        events_path=events_path,
        outcomes_path=outcomes_path,
        now=sample_event.ts + timedelta(minutes=240),
        current_price=76000.0,
        current_portfolio=sample_event.portfolio_context,
    )
    assert any(item.checkpoint_minutes == 240 for item in created)


def test_outcome_recorded_at_1440min_checkpoint(tmp_path: Path, sample_event) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    append_event(sample_event, events_path)
    created = outcome_resolver_run_once(
        events_path=events_path,
        outcomes_path=outcomes_path,
        now=sample_event.ts + timedelta(minutes=1440),
        current_price=75000.0,
        current_portfolio=sample_event.portfolio_context,
    )
    assert any(item.checkpoint_minutes == 1440 for item in created)


def test_outcome_idempotent_not_double_written(tmp_path: Path, sample_event) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    append_event(sample_event, events_path)
    now = sample_event.ts + timedelta(minutes=1440)
    outcome_resolver_run_once(events_path=events_path, outcomes_path=outcomes_path, now=now, current_price=76000.0, current_portfolio=sample_event.portfolio_context)
    outcome_resolver_run_once(events_path=events_path, outcomes_path=outcomes_path, now=now, current_price=76000.0, current_portfolio=sample_event.portfolio_context)
    assert len(list(iter_outcomes(outcomes_path))) == 3


def test_outcome_classification_positive_negative_neutral(tmp_path: Path, sample_event) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    append_event(sample_event, events_path)
    positive_portfolio = replace(sample_event.portfolio_context, net_unrealized_usd=-300.0)
    negative_portfolio = replace(sample_event.portfolio_context, net_unrealized_usd=-600.0)
    neutral_portfolio = replace(sample_event.portfolio_context, net_unrealized_usd=-450.0)
    positive = outcome_resolver_run_once(events_path=events_path, outcomes_path=outcomes_path, now=sample_event.ts + timedelta(minutes=60), current_price=1.0, current_portfolio=positive_portfolio)[0]
    assert positive.delta_pnl_classification == "positive"
    outcomes_path.unlink()
    negative = outcome_resolver_run_once(events_path=events_path, outcomes_path=outcomes_path, now=sample_event.ts + timedelta(minutes=60), current_price=1.0, current_portfolio=negative_portfolio)[0]
    assert negative.delta_pnl_classification == "negative"
    outcomes_path.unlink()
    neutral = outcome_resolver_run_once(events_path=events_path, outcomes_path=outcomes_path, now=sample_event.ts + timedelta(minutes=60), current_price=1.0, current_portfolio=neutral_portfolio)[0]
    assert neutral.delta_pnl_classification == "neutral"


def test_outcome_skips_events_younger_than_checkpoint(tmp_path: Path, sample_event) -> None:
    events_path = tmp_path / "events.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    append_event(sample_event, events_path)
    created = outcome_resolver_run_once(
        events_path=events_path,
        outcomes_path=outcomes_path,
        now=sample_event.ts + timedelta(minutes=59),
        current_price=76000.0,
        current_portfolio=sample_event.portfolio_context,
    )
    assert created == []
