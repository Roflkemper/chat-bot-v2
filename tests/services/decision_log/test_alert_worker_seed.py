"""Regression tests for DecisionLogAlertWorker pre-seeding fix (TZ-CASCADE-NOISE)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def _make_event(event_id: str, severity: str = "WARNING") -> dict:
    return {
        "event_id": event_id,
        "ts": "2026-04-30T10:00:00Z",
        "event_type": "BOUNDARY_BREACH",
        "severity": severity,
        "bot_id": "1",
        "summary": "test",
        "payload": {},
        "market_context": {
            "price_btc": 76000.0,
            "regime_label": "trend_down",
            "regime_modifiers": [],
            "rsi_1h": 40.0,
            "rsi_5m": 38.0,
            "price_change_5m_pct": -0.3,
            "price_change_1h_pct": -1.2,
            "atr_normalized": 0.01,
            "session_kz": "EU",
            "nearest_liq_above": None,
            "nearest_liq_below": None,
        },
        "portfolio_context": {
            "depo_total": 15000.0,
            "shorts_unrealized_usd": -50.0,
            "longs_unrealized_usd": 0.0,
            "net_unrealized_usd": -50.0,
            "free_margin_pct": 30.0,
            "drawdown_pct": 2.0,
            "shorts_position_btc": 0.1,
            "longs_position_usd": 0.0,
        },
    }


def _make_worker(events_path: Path):
    from services.telegram_runtime import DecisionLogAlertWorker

    bot = MagicMock()
    return DecisionLogAlertWorker(bot=bot, chat_ids=[123], events_path=events_path)


# ── test_cold_start_no_cascade ────────────────────────────────────────────────

def test_cold_start_no_cascade(tmp_path: Path) -> None:
    """Worker initialised with pre-existing JSONL → _read_new_events() returns empty list."""
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        _make_event("evt-001", "WARNING"),
        _make_event("evt-002", "CRITICAL"),
        _make_event("evt-003", "INFO"),
    ])

    worker = _make_worker(events_path)
    assert "evt-001" in worker._seen_event_ids
    assert "evt-002" in worker._seen_event_ids
    assert "evt-003" in worker._seen_event_ids

    new_events = worker._read_new_events()
    assert new_events == [], "No historical events must be returned after seeding"


# ── test_new_event_after_seed ─────────────────────────────────────────────────

def test_new_event_after_seed(tmp_path: Path) -> None:
    """After seeding, a newly appended WARNING event IS returned by _read_new_events()."""
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [_make_event("evt-001", "WARNING")])

    worker = _make_worker(events_path)
    assert worker._read_new_events() == []

    # Append a new event after startup
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_make_event("evt-new", "WARNING"), ensure_ascii=False) + "\n")

    new_events = worker._read_new_events()
    assert len(new_events) == 1
    assert new_events[0].event_id == "evt-new"


# ── test_seed_handles_missing_file ────────────────────────────────────────────

def test_seed_handles_missing_file(tmp_path: Path) -> None:
    """Missing JSONL → _load_seen_ids() returns empty set without crash."""
    events_path = tmp_path / "no_such_file.jsonl"
    worker = _make_worker(events_path)
    assert worker._seen_event_ids == set()
    # And _read_new_events on empty file also returns empty
    assert worker._read_new_events() == []
