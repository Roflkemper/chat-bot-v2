from __future__ import annotations

import asyncio
import logging
from datetime import date

import services.telegram_alert_client as telegram_alert_client
from services.telegram_alert_service import _split_chunks, send_daily_report, send_telegram_alert


class _DummyClient:
    def __init__(self, enabled: bool = True, fail: bool = False) -> None:
        self.enabled = enabled
        self.fail = fail
        self.sent: list[str] = []

    def is_enabled(self) -> bool:
        return self.enabled

    def send(self, text: str) -> bool:
        self.sent.append(text)
        if self.fail:
            raise RuntimeError("boom")
        return True


def test_split_chunks_returns_single_chunk_when_short():
    assert _split_chunks("hello") == ["hello"]


def test_split_chunks_splits_by_newline_boundary():
    text = ("A" * 2000) + "\n" + ("B" * 2000) + "\n" + ("C" * 2000)
    chunks = _split_chunks(text, limit=3800)
    assert len(chunks) == 3
    assert "".join(chunk.replace("\n", "") for chunk in chunks) == text.replace("\n", "")
    assert all(len(chunk) <= 3800 for chunk in chunks)


def test_split_chunks_falls_back_to_hard_cut_without_newline():
    text = "X" * 7601
    chunks = _split_chunks(text, limit=3800)
    assert len(chunks) == 3
    assert "".join(chunks) == text
    assert all(len(chunk) <= 3800 for chunk in chunks)


def test_send_telegram_alert_logs_always(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _DummyClient(enabled=False)
    monkeypatch.setattr(telegram_alert_client.TelegramAlertClient, "instance", lambda: client)
    asyncio.run(send_telegram_alert("hello alert"))
    assert "[ORCHESTRATOR ALERT]" in caplog.text
    assert "hello alert" in caplog.text
    assert client.sent == []


def test_send_telegram_alert_when_enabled(monkeypatch):
    client = _DummyClient(enabled=True)
    monkeypatch.setattr(telegram_alert_client.TelegramAlertClient, "instance", lambda: client)
    asyncio.run(send_telegram_alert("hello alert"))
    assert client.sent == ["hello alert"]


def test_send_telegram_alert_survives_exception(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    client = _DummyClient(enabled=True, fail=True)
    monkeypatch.setattr(telegram_alert_client.TelegramAlertClient, "instance", lambda: client)
    asyncio.run(send_telegram_alert("hello alert"))
    assert "Delivery failed" in caplog.text


def test_send_daily_report_logs_rendered_report(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    class _FakeLog:
        def summarize_day(self, day):
            return {"day": day, "total_events": 1, "event_counts": {"MANUAL_COMMAND": 1}}

    monkeypatch.setattr("core.orchestrator.calibration_log.CalibrationLog.instance", lambda: _FakeLog())
    monkeypatch.setattr("renderers.calibration_renderer.render_daily_report", lambda summary: f"report for {summary['day']}")
    monkeypatch.setattr(telegram_alert_client.TelegramAlertClient, "instance", lambda: _DummyClient(enabled=False))
    asyncio.run(send_daily_report(date(2026, 4, 18)))
    assert "[DAILY REPORT]" in caplog.text
    assert "report for 2026-04-18" in caplog.text


def test_send_daily_report_builds_report_and_sends(monkeypatch):
    class _FakeLog:
        def summarize_day(self, day):
            return {"day": day, "total_events": 2}

    client = _DummyClient(enabled=True)
    monkeypatch.setattr("core.orchestrator.calibration_log.CalibrationLog.instance", lambda: _FakeLog())
    monkeypatch.setattr("renderers.calibration_renderer.render_daily_report", lambda summary: f"report for {summary['day']}")
    monkeypatch.setattr(telegram_alert_client.TelegramAlertClient, "instance", lambda: client)
    asyncio.run(send_daily_report(date(2026, 4, 18)))
    assert client.sent == ["report for 2026-04-18"]
