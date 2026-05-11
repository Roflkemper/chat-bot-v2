"""Tests for check_restart_frequency operator-vs-autonomous classification."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mod():
    spec = importlib.util.spec_from_file_location(
        "check_restart", ROOT / "scripts" / "check_restart_frequency.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["check_restart"] = m
    spec.loader.exec_module(m)
    return m


def test_watchdog_tick_times_filters_other_components(mod, tmp_path, monkeypatch):
    p = tmp_path / "watchdog_audit.jsonl"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    events = [
        {"ts": now_iso, "event": "started", "component": "app_runner"},
        {"ts": now_iso, "event": "started", "component": "tracker"},
        {"ts": now_iso, "event": "alive", "component": "app_runner"},
        {"ts": now_iso, "event": "started", "component": "app_runner"},
    ]
    p.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    monkeypatch.setattr(mod, "WATCHDOG_AUDIT", p)

    times = mod._watchdog_tick_times(cutoff)
    # Only 2 'started' for app_runner — tracker's 'started' and the 'alive'
    # should be filtered out.
    assert len(times) == 2


def test_watchdog_tick_times_missing_file(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "WATCHDOG_AUDIT", tmp_path / "absent.jsonl")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    assert mod._watchdog_tick_times(cutoff) == []
