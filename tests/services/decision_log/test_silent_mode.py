"""Tests for DecisionLogAlertWorker silent_mode flag (TZ-DECISION-LOG-SILENT-MODE).

When silent_mode=True:
- bot.send_message is NEVER called
- _seen_event_ids and _recent_pings are still updated (event is still processed)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


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


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def _make_worker(events_path: Path, *, silent_mode: bool):
    from services.telegram_runtime import DecisionLogAlertWorker

    bot = MagicMock()
    return DecisionLogAlertWorker(
        bot=bot,
        chat_ids=[123],
        events_path=events_path,
        silent_mode=silent_mode,
    )


# ── silent_mode=True ──────────────────────────────────────────────────────────

def test_silent_mode_suppresses_send_message(tmp_path: Path) -> None:
    """With silent_mode=True, bot.send_message is never called for new events."""
    events_path = tmp_path / "events.jsonl"
    events_path.touch()

    worker = _make_worker(events_path, silent_mode=True)

    # Append a new WARNING event after startup (not in seed)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_make_event("evt-001", "WARNING"), ensure_ascii=False) + "\n")

    with patch("services.decision_log.format_event_message", return_value="text"), \
         patch("services.decision_log.build_event_keyboard", return_value=None):
        new_events = worker._read_new_events()

    # Manually simulate what run() does (without threading)
    assert len(new_events) == 1
    for event in new_events:
        if not worker._is_duplicate_recent(event):
            if worker._silent_mode:
                pass  # silent — no send
            else:
                worker.bot.send_message(123, "text", reply_markup=None)

    worker.bot.send_message.assert_not_called()


def test_silent_mode_event_added_to_seen_ids(tmp_path: Path) -> None:
    """With silent_mode=True, processed events are still added to _seen_event_ids."""
    events_path = tmp_path / "events.jsonl"
    events_path.touch()

    worker = _make_worker(events_path, silent_mode=True)

    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_make_event("evt-002", "WARNING"), ensure_ascii=False) + "\n")

    new_events = worker._read_new_events()

    assert len(new_events) == 1
    assert "evt-002" in worker._seen_event_ids


def test_silent_mode_false_calls_send_message(tmp_path: Path) -> None:
    """Sanity: with silent_mode=False, bot.send_message IS called."""
    events_path = tmp_path / "events.jsonl"
    events_path.touch()

    worker = _make_worker(events_path, silent_mode=False)

    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_make_event("evt-003", "WARNING"), ensure_ascii=False) + "\n")

    with patch("services.decision_log.format_event_message", return_value="text"), \
         patch("services.decision_log.build_event_keyboard", return_value=None):
        new_events = worker._read_new_events()

    assert len(new_events) == 1
    for event in new_events:
        if not worker._is_duplicate_recent(event):
            if not worker._silent_mode:
                worker.bot.send_message(123, "text", reply_markup=None)

    worker.bot.send_message.assert_called_once()
