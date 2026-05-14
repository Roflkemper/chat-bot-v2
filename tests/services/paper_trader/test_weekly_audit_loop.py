"""Tests for weekly_audit_loop."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from services.paper_trader.weekly_audit_loop import _should_send_now, check_and_send


def test_should_send_only_on_monday_10utc() -> None:
    # Monday 10:00 UTC — да
    assert _should_send_now(datetime(2026, 5, 11, 10, 5, tzinfo=timezone.utc), None) is True
    # Tuesday — нет
    assert _should_send_now(datetime(2026, 5, 12, 10, 5, tzinfo=timezone.utc), None) is False
    # Monday 11:00 — нет (только 10:00 час)
    assert _should_send_now(datetime(2026, 5, 11, 11, 5, tzinfo=timezone.utc), None) is False


def test_should_skip_if_already_sent_today() -> None:
    now = datetime(2026, 5, 11, 10, 30, tzinfo=timezone.utc)
    already = datetime(2026, 5, 11, 10, 5, tzinfo=timezone.utc).isoformat()
    assert _should_send_now(now, already) is False


def test_should_send_if_sent_last_week() -> None:
    now = datetime(2026, 5, 18, 10, 5, tzinfo=timezone.utc)  # next Monday
    last_week = datetime(2026, 5, 11, 10, 5, tzinfo=timezone.utc).isoformat()
    assert _should_send_now(now, last_week) is True


def test_check_and_send_invokes_send_fn(tmp_path: Path, monkeypatch) -> None:
    send = MagicMock()
    state_p = tmp_path / "state.json"
    monday_10 = datetime(2026, 5, 11, 10, 5, tzinfo=timezone.utc)
    # Mock the audit report
    from services.paper_trader import audit_report
    monkeypatch.setattr(audit_report, "build_filter_audit", lambda days=7: "stub report")

    sent = check_and_send(send, now=monday_10, state_path=state_p)
    assert sent is True
    send.assert_called_once()
    assert "stub report" in send.call_args[0][0]
    # State written
    state = json.loads(state_p.read_text())
    assert "last_sent" in state


def test_check_and_send_idempotent(tmp_path: Path, monkeypatch) -> None:
    """Не шлёт второй раз в тот же день."""
    send = MagicMock()
    state_p = tmp_path / "state.json"
    monday_10 = datetime(2026, 5, 11, 10, 5, tzinfo=timezone.utc)
    from services.paper_trader import audit_report
    monkeypatch.setattr(audit_report, "build_filter_audit", lambda days=7: "stub")

    check_and_send(send, now=monday_10, state_path=state_p)
    send.reset_mock()
    # Second call within same hour
    sent = check_and_send(send, now=monday_10, state_path=state_p)
    assert sent is False
    send.assert_not_called()
