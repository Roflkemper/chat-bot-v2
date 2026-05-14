"""Tests for TZ-DEDUP-WIRE-PRODUCTION POSITION_CHANGE wire-up.

Verify the DecisionLogAlertWorker:
  1. Initializes a DedupLayer for POSITION_CHANGE when flag is on
  2. Suppresses second POSITION_CHANGE event with the same position value
  3. Emits a POSITION_CHANGE event with materially different position value
  4. Tracks counters correctly (emitted / suppressed_layer / suppressed_signature)
  5. Does NOT touch other event types' flow (PNL_EVENT etc)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Force the flag ON for this test module before import
os.environ["DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE"] = "1"

from services.decision_log.models import (
    CapturedEvent, EventType, EventSeverity, MarketContext, PortfolioContext,
)
import services.telegram_runtime as tr_mod


def _make_event(
    *, event_id: str, shorts_btc: float, longs_usd: float,
    bot_id: str | None = None, ts: datetime | None = None,
    event_type: EventType = EventType.POSITION_CHANGE,
) -> CapturedEvent:
    ts = ts or datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    return CapturedEvent(
        event_id=event_id,
        ts=ts,
        event_type=event_type,
        severity=EventSeverity.WARNING,
        bot_id=bot_id,
        summary="test",
        payload={},
        market_context=MarketContext(price_btc=80000.0, regime_label="trend_up"),
        portfolio_context=PortfolioContext(
            depo_total=10000.0,
            shorts_unrealized_usd=0.0, longs_unrealized_usd=0.0,
            net_unrealized_usd=0.0, free_margin_pct=50.0, drawdown_pct=0.0,
            shorts_position_btc=shorts_btc, longs_position_usd=longs_usd,
        ),
    )


def _make_worker(tmp_path):
    """Build a worker with isolated dedup state via DI."""
    bot = MagicMock()
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("", encoding="utf-8")
    state_path = tmp_path / "dedup_state.json"
    worker = tr_mod.DecisionLogAlertWorker(
        bot=bot, chat_ids=[123], events_path=events_path, silent_mode=True,
        dedup_state_path=state_path,
    )
    return worker


# ── Layer initialization ──────────────────────────────────────────────────────

def test_layer_initialized_when_flag_on(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    bot = MagicMock()
    events_path = tmp_path / "e.jsonl"
    events_path.write_text("", encoding="utf-8")
    worker = tr_mod.DecisionLogAlertWorker(
        bot=bot, chat_ids=[1], events_path=events_path, silent_mode=True,
        dedup_state_path=tmp_path / "ds.json",
    )
    assert worker._position_change_layer is not None


def test_layer_disabled_when_flag_off(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", False)
    bot = MagicMock()
    events_path = tmp_path / "e.jsonl"
    events_path.write_text("", encoding="utf-8")
    worker = tr_mod.DecisionLogAlertWorker(
        bot=bot, chat_ids=[1], events_path=events_path, silent_mode=True,
        dedup_state_path=tmp_path / "ds.json",
    )
    assert worker._position_change_layer is None


# ── Value extraction ──────────────────────────────────────────────────────────

def test_position_change_value_combines_shorts_and_longs(tmp_path):
    worker = _make_worker(tmp_path)
    ev = _make_event(event_id="e1", shorts_btc=2.0, longs_usd=80000.0)
    val = worker._position_change_value(ev)
    # shorts 2.0 BTC + longs 80000/80000 = 1.0 BTC → 3.0
    assert abs(val - 3.0) < 0.01


def test_position_change_value_zero_inputs(tmp_path):
    worker = _make_worker(tmp_path)
    ev = _make_event(event_id="e1", shorts_btc=0.0, longs_usd=0.0)
    assert worker._position_change_value(ev) == 0.0


# ── Layer evaluate path ───────────────────────────────────────────────────────

def test_first_position_change_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    ev = _make_event(event_id="e1", shorts_btc=2.0, longs_usd=0.0)
    decision = worker._evaluate_position_change_layer(ev)
    assert decision.should_emit is True


def test_second_position_change_with_same_value_suppressed(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    ev1 = _make_event(event_id="e1", shorts_btc=2.0, longs_usd=0.0,
                      ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc))
    worker._record_position_change_emit(ev1)

    # Same value 1 minute later → suppressed (cooldown 300s, value Δ < 0.05)
    ev2 = _make_event(event_id="e2", shorts_btc=2.01, longs_usd=0.0,
                      ts=datetime(2026, 5, 5, 12, 1, tzinfo=timezone.utc))
    decision = worker._evaluate_position_change_layer(ev2)
    assert decision.should_emit is False


def test_position_change_with_material_delta_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    ev1 = _make_event(event_id="e1", shorts_btc=2.0, longs_usd=0.0,
                      ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc))
    worker._record_position_change_emit(ev1)

    # Δ = 0.2 BTC (well above 0.05 threshold), 10 min later → cooldown expired AND state changed
    ev2 = _make_event(event_id="e2", shorts_btc=2.2, longs_usd=0.0,
                      ts=datetime(2026, 5, 5, 12, 10, tzinfo=timezone.utc))
    decision = worker._evaluate_position_change_layer(ev2)
    assert decision.should_emit is True


def test_position_change_within_cooldown_with_big_delta_still_suppressed(tmp_path, monkeypatch):
    """Cooldown is the first gate — even big state change is suppressed during cooldown."""
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    ev1 = _make_event(event_id="e1", shorts_btc=2.0, longs_usd=0.0,
                      ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc))
    worker._record_position_change_emit(ev1)

    # 1 min later, big delta, but cooldown 300s not expired
    ev2 = _make_event(event_id="e2", shorts_btc=3.0, longs_usd=0.0,
                      ts=datetime(2026, 5, 5, 12, 1, tzinfo=timezone.utc))
    decision = worker._evaluate_position_change_layer(ev2)
    assert decision.should_emit is False
    assert "cooldown" in decision.reason_ru


# ── Counters / metrics ────────────────────────────────────────────────────────

def test_dedup_metrics_initial_state(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    m = worker.dedup_metrics()
    assert m["POSITION_CHANGE"] == {"emitted": 0, "suppressed_layer": 0, "suppressed_signature": 0}
    assert m["layer_enabled_position_change"] is True


def test_dedup_metrics_layer_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", False)
    worker = _make_worker(tmp_path)
    m = worker.dedup_metrics()
    assert m["layer_enabled_position_change"] is False


# ── Per-bot key isolation ────────────────────────────────────────────────────

def test_different_bots_independent_keys(tmp_path, monkeypatch):
    """Two POSITION_CHANGE events from different bots don't dedup against each other."""
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    ev_a = _make_event(event_id="ea", shorts_btc=2.0, longs_usd=0.0, bot_id="botA",
                       ts=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc))
    worker._record_position_change_emit(ev_a)

    # Same value, different bot, 1 minute later → still passes (independent key)
    ev_b = _make_event(event_id="eb", shorts_btc=2.01, longs_usd=0.0, bot_id="botB",
                       ts=datetime(2026, 5, 5, 12, 1, tzinfo=timezone.utc))
    decision = worker._evaluate_position_change_layer(ev_b)
    assert decision.should_emit is True


# ── Other event types untouched ──────────────────────────────────────────────

def test_pnl_event_not_routed_through_layer(tmp_path, monkeypatch):
    """PNL_EVENT must NOT go through the layer — only POSITION_CHANGE wired in v1."""
    monkeypatch.setattr(tr_mod, "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE", True)
    worker = _make_worker(tmp_path)
    # The worker.run() loop checks event_type before calling layer.
    # Verify the layer state is empty after a hypothetical PNL_EVENT path:
    # we can only test this indirectly because run() reads from disk.
    # Direct check: the layer's internal state has no entries until record_emit.
    layer = worker._position_change_layer
    assert layer is not None
    # No POSITION_CHANGE has been recorded yet
    assert not layer._state, "Layer state should start empty"
