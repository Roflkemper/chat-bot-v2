"""Tests for cron_report."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from services.cron_report import build_cron_report, _query_tasks


def test_query_tasks_handles_no_schtasks():
    """If schtasks doesn't exist, return empty list — graceful."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert _query_tasks() == []


def test_query_tasks_handles_timeout():
    import subprocess
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("schtasks", 10)):
        assert _query_tasks() == []


def test_query_tasks_filters_bot7_prefix():
    """Only TaskNames starting with bot7- should be returned."""
    fake_csv = (
        '"HOST","\\\\Other","09:00","Ready","Mode","08:00","0","auth","cmd","dir","cmt"\n'
        '"HOST","\\\\bot7-test","09:00","Ready","Mode","08:00","0","auth","cmd","dir","cmt"\n'
    )
    result = MagicMock()
    result.returncode = 0
    result.stdout = fake_csv
    with patch("subprocess.run", return_value=result):
        tasks = _query_tasks()
    names = [t["name"] for t in tasks]
    assert names == ["bot7-test"]


def test_build_cron_report_empty():
    """Empty tasks list still produces a valid header."""
    with patch("services.cron_report._query_tasks", return_value=[]):
        text = build_cron_report()
    assert "[CRON]" in text
    assert "none" in text or "Total: 0" in text


def test_build_cron_report_renders_tasks():
    fake_tasks = [{
        "name": "bot7-test", "state": "Ready",
        "last_run": "2026-05-11 09:00:00", "last_result": "0",
        "next_run": "2026-05-12 09:00:00",
    }]
    with patch("services.cron_report._query_tasks", return_value=fake_tasks):
        text = build_cron_report()
    assert "bot7-test" in text
    assert "ok" in text  # last_result 0 → ok mapping
    assert "Total: 1" in text
