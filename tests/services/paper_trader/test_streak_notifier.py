"""Tests for streak_notifier — TG-уведомления о паузе paper_trader."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from services.paper_trader import journal
from services.paper_trader.streak_notifier import check_and_notify


def _write_journal(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _mk(action: str, ts: datetime, tid: str = "t1") -> dict:
    return {"ts": ts.isoformat(), "trade_id": tid, "action": action}


def test_notifies_on_pause_activation(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    j = tmp_path / "trades.jsonl"
    _write_journal(j, [_mk("SL", now - timedelta(hours=h), f"t{h}") for h in range(6, 0, -1)])
    monkeypatch.setattr(journal, "JOURNAL_PATH", j)
    state_p = tmp_path / "state.json"
    send = MagicMock()

    result = check_and_notify(send, now=now, state_path=state_p)
    assert result["paused"] is True
    assert result["notified"] is True
    send.assert_called_once()
    args = send.call_args[0][0]
    assert "приостановлен" in args


def test_no_duplicate_notification_when_already_paused(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    j = tmp_path / "trades.jsonl"
    _write_journal(j, [_mk("SL", now - timedelta(hours=h), f"t{h}") for h in range(6, 0, -1)])
    monkeypatch.setattr(journal, "JOURNAL_PATH", j)
    state_p = tmp_path / "state.json"
    state_p.write_text(json.dumps({"paused": True, "streak": 6}))
    send = MagicMock()

    result = check_and_notify(send, now=now, state_path=state_p)
    assert result["paused"] is True
    assert result["notified"] is False
    send.assert_not_called()


def test_notifies_on_resume(tmp_path: Path, monkeypatch) -> None:
    """Pause ON → OFF (timeout): один resume-алерт."""
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    j = tmp_path / "trades.jsonl"
    # SLs далеко в прошлом → pause snimaется по timeout
    _write_journal(j, [_mk("SL", now - timedelta(hours=h), f"t{h}") for h in range(15, 9, -1)])
    monkeypatch.setattr(journal, "JOURNAL_PATH", j)
    state_p = tmp_path / "state.json"
    state_p.write_text(json.dumps({"paused": True, "streak": 6}))
    send = MagicMock()

    result = check_and_notify(send, now=now, state_path=state_p)
    assert result["paused"] is False
    assert result["notified"] is True
    args = send.call_args[0][0]
    assert "возобновлён" in args


def test_handles_send_failure_gracefully(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    j = tmp_path / "trades.jsonl"
    _write_journal(j, [_mk("SL", now - timedelta(hours=h), f"t{h}") for h in range(6, 0, -1)])
    monkeypatch.setattr(journal, "JOURNAL_PATH", j)
    state_p = tmp_path / "state.json"
    send = MagicMock(side_effect=RuntimeError("TG down"))

    result = check_and_notify(send, now=now, state_path=state_p)
    assert result["paused"] is True
    assert result["notified"] is False  # exception caught
    # state still saved
    assert state_p.exists()


def test_no_pause_no_notification(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    j = tmp_path / "trades.jsonl"
    _write_journal(j, [_mk("SL", now - timedelta(hours=1), "t1")])
    monkeypatch.setattr(journal, "JOURNAL_PATH", j)
    state_p = tmp_path / "state.json"
    send = MagicMock()

    result = check_and_notify(send, now=now, state_path=state_p)
    assert result["paused"] is False
    assert result["notified"] is False
    send.assert_not_called()
