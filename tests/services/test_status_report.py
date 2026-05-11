"""Tests for services.status_report — smoke + edge cases."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import status_report


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Redirect all status_report file paths to tmp_path."""
    monkeypatch.setattr(status_report, "_APP_LOG", tmp_path / "app.log")
    monkeypatch.setattr(status_report, "_SETUPS", tmp_path / "setups.jsonl")
    monkeypatch.setattr(status_report, "_GC_FIRES", tmp_path / "gc.jsonl")
    monkeypatch.setattr(status_report, "_P15_STATE", tmp_path / "p15.json")
    monkeypatch.setattr(status_report, "_APP_RUNNER_STARTS", tmp_path / "starts.jsonl")
    return tmp_path


def test_build_report_when_everything_empty(isolated_paths):
    """No files → still produces a readable report, not a crash."""
    text = status_report.build_status_report()
    # Russian-only header (rewritten 2026-05-11 for operator readability).
    assert "СТАТУС БОТА" in text
    # No legs → friendly Russian message
    assert "АКТИВНЫХ ПОЗИЦИЙ P-15 нет" in text
    # No setups → friendly Russian message
    assert "нет за сутки" in text
    # Always has a Выводы section
    assert "ВЫВОДЫ" in text


def test_heartbeat_age_parsed_from_log(isolated_paths):
    """Heartbeat age computed from t=<iso> field in log line."""
    now = datetime.now(timezone.utc)
    recent_iso = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    log_line = (f"2026-05-10 23:30:54,647 | INFO | app_runner | "
                f"heartbeat.tick t={recent_iso}\n")
    (isolated_paths / "app.log").write_text(log_line, encoding="utf-8")
    age, ts = status_report._heartbeat_age(now)
    assert age is not None
    assert 1.5 < age < 2.5
    assert ts == recent_iso


def test_p15_legs_only_in_pos(isolated_paths):
    state = {
        "BTCUSDT:long":  {"direction": "long", "in_pos": True, "layers": 2,
                          "total_size_usd": 1500.0, "cum_dd_pct": 0.5,
                          "opened_at_ts": "2026-05-10T20:00:00Z"},
        "BTCUSDT:short": {"direction": "short", "in_pos": False, "layers": 0},
        "XRPUSDT:long":  {"direction": "long", "in_pos": True, "layers": 3,
                          "total_size_usd": 600.0, "cum_dd_pct": 1.2,
                          "opened_at_ts": "2026-05-10T15:00:00Z"},
    }
    (isolated_paths / "p15.json").write_text(json.dumps(state), encoding="utf-8")
    now = datetime(2026, 5, 10, 22, 0, tzinfo=timezone.utc)
    legs = status_report._p15_legs(now)
    assert len(legs) == 2
    pairs = {l["pair"] for l in legs}
    assert pairs == {"BTCUSDT", "XRPUSDT"}


def test_restarts_last_hour_counts_within_window(isolated_paths):
    now = datetime(2026, 5, 10, 22, 0, tzinfo=timezone.utc)
    lines = [
        json.dumps({"ts": (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")}),
        json.dumps({"ts": (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")}),
        json.dumps({"ts": (now - timedelta(minutes=90)).isoformat().replace("+00:00", "Z")}),  # outside
    ]
    (isolated_paths / "starts.jsonl").write_text("\n".join(lines), encoding="utf-8")
    assert status_report._restarts_last_hour(now) == 2


def test_last_setup_reads_latest(isolated_paths):
    setups = [
        json.dumps({"setup_type": "long_pdl_bounce", "pair": "BTCUSDT",
                    "detected_at": "2026-05-10T20:00:00Z", "strength": 9,
                    "confidence_pct": 75.0}),
        json.dumps({"setup_type": "short_rally_fade", "pair": "ETHUSDT",
                    "detected_at": "2026-05-10T21:30:00Z", "strength": 9,
                    "confidence_pct": 72.0}),
    ]
    (isolated_paths / "setups.jsonl").write_text("\n".join(setups), encoding="utf-8")
    now = datetime(2026, 5, 10, 22, 0, tzinfo=timezone.utc)
    last = status_report._last_setup(now)
    assert last is not None
    assert last["type"] == "short_rally_fade"
    assert last["pair"] == "ETHUSDT"
    assert 25 < last["age_min"] < 35
