"""Tests for TZ-DEDUP-WIRE-BOUNDARY-BREACH wire-up."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Force the flag ON for this module before import
os.environ["DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH"] = "1"

from services.decision_log.models import (
    CapturedEvent, EventSeverity, EventType, MarketContext, PortfolioContext,
)
import services.telegram_runtime as tr_mod


def _make_event(
    *,
    event_id: str,
    bot_id: str | None = None,
    price_btc: float = 80000.0,
    ts: datetime | None = None,
    event_type: EventType = EventType.BOUNDARY_BREACH,
    payload: dict | None = None,
) -> CapturedEvent:
    ts = ts or datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    return CapturedEvent(
        event_id=event_id,
        ts=ts,
        event_type=event_type,
        severity=EventSeverity.WARNING,
        bot_id=bot_id,
        summary="test",
        payload=payload or {"border_top": 81000.0},
        market_context=MarketContext(price_btc=price_btc, regime_label="trend_up"),
        portfolio_context=PortfolioContext(
            depo_total=10000.0,
            shorts_unrealized_usd=0.0,
            longs_unrealized_usd=0.0,
            net_unrealized_usd=0.0,
            free_margin_pct=50.0,
            drawdown_pct=0.0,
            shorts_position_btc=0.0,
            longs_position_usd=0.0,
        ),
    )


def _make_worker(tmp_path):
    bot = MagicMock()
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("", encoding="utf-8")
    state_path = tmp_path / "dedup_state.json"
    return tr_mod.DecisionLogAlertWorker(
        bot=bot,
        chat_ids=[123],
        events_path=events_path,
        silent_mode=True,
        dedup_state_path=state_path,
    )


def test_layer_initialized_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    assert worker._boundary_breach_layer is not None


def test_layer_disabled_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", False)
    worker = _make_worker(tmp_path)
    assert worker._boundary_breach_layer is None


def test_first_boundary_breach_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    ev = _make_event(event_id="e1", bot_id="botA")
    decision = worker._evaluate_boundary_breach_layer(ev)
    assert decision.should_emit is True


def test_repeat_boundary_breach_within_cooldown_suppressed(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    ev1 = _make_event(
        event_id="e1", bot_id="botA",
        ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
    )
    worker._record_boundary_breach_emit(ev1)
    ev2 = _make_event(
        event_id="e2", bot_id="botA", price_btc=82000.0,
        payload={"border_bottom": 79000.0},
        ts=datetime(2026, 5, 5, 12, 5, tzinfo=timezone.utc),
    )
    decision = worker._evaluate_boundary_breach_layer(ev2)
    assert decision.should_emit is False


def test_same_bot_different_boundary_within_cooldown_still_suppressed(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    ev1 = _make_event(
        event_id="e1", bot_id="botA", payload={"border_top": 81000.0},
        ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
    )
    worker._record_boundary_breach_emit(ev1)
    ev2 = _make_event(
        event_id="e2", bot_id="botA", payload={"border_bottom": 78000.0},
        ts=datetime(2026, 5, 5, 12, 8, tzinfo=timezone.utc),
    )
    decision = worker._evaluate_boundary_breach_layer(ev2)
    assert decision.should_emit is False
    assert "cooldown" in decision.reason_ru


def test_after_600s_emit_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    ev1 = _make_event(
        event_id="e1", bot_id="botA",
        ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
    )
    worker._record_boundary_breach_emit(ev1)
    ev2 = _make_event(
        event_id="e2", bot_id="botA",
        ts=datetime(2026, 5, 5, 12, 10, tzinfo=timezone.utc),
    )
    decision = worker._evaluate_boundary_breach_layer(ev2)
    assert decision.should_emit is True


def test_per_bot_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    ev_a = _make_event(
        event_id="ea", bot_id="TEST_1",
        ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
    )
    worker._record_boundary_breach_emit(ev_a)
    ev_b = _make_event(
        event_id="eb", bot_id="TEST_2",
        ts=datetime(2026, 5, 5, 12, 1, tzinfo=timezone.utc),
    )
    decision = worker._evaluate_boundary_breach_layer(ev_b)
    assert decision.should_emit is True


def test_dedup_metrics_include_boundary_breach(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    metrics = worker.dedup_metrics()
    assert metrics["BOUNDARY_BREACH"] == {
        "emitted": 0,
        "suppressed_layer": 0,
        "suppressed_signature": 0,
    }
    assert metrics["layer_enabled_boundary_breach"] is True


def test_record_emit_updates_counter_manually(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    ev = _make_event(event_id="e1", bot_id="botA")
    worker._record_boundary_breach_emit(ev)
    worker._dedup_counters["BOUNDARY_BREACH"]["emitted"] += 1
    assert worker.dedup_metrics()["BOUNDARY_BREACH"]["emitted"] == 1


def test_pnl_event_not_routed_through_boundary_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_BOUNDARY_BREACH", True)
    worker = _make_worker(tmp_path)
    layer = worker._boundary_breach_layer
    assert layer is not None
    ev = _make_event(event_id="p1", event_type=EventType.PNL_EVENT, payload={"delta_pnl_usd": 150.0})
    assert worker._compute_signature(ev).startswith("pnl_delta_")
    assert not layer._state
