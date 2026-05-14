"""Tests for p15_report — /p15 TG command."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from services import p15_report


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(p15_report, "_P15_STATE", tmp_path / "state.json")
    monkeypatch.setattr(p15_report, "_P15_EQUITY", tmp_path / "equity.jsonl")
    return tmp_path


def test_no_state_returns_friendly_msg(isolated):
    text = p15_report.build_p15_report()
    assert "No leg state yet" in text


def test_open_and_idle_leg_breakdown(isolated):
    now = datetime.now(timezone.utc)
    state = {
        "BTCUSDT:long": {
            "direction": "long", "in_pos": True, "layers": 2,
            "total_size_usd": 2000.0,
            "weighted_entry": 2000.0 * 80000.0,
            "extreme_price": 80500.0, "cum_dd_pct": 0.5,
            "opened_at_ts": (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
            "last_emitted_stage": "REENTRY",
        },
        "BTCUSDT:short": {
            "direction": "short", "in_pos": False, "layers": 0,
            "total_size_usd": 0.0, "weighted_entry": 0,
            "extreme_price": 0.0, "cum_dd_pct": 0.0,
            "opened_at_ts": "", "last_emitted_stage": "CLOSE",
        },
    }
    (isolated / "state.json").write_text(json.dumps(state), encoding="utf-8")

    text = p15_report.build_p15_report()
    assert "Open legs (1)" in text
    assert "Idle legs (1)" in text
    assert "BTCUSDT    long" in text
    assert "REENTRY" in text


def test_24h_pnl_excludes_old_events(isolated):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    fresh = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    events = [
        {"ts": old, "pair": "BTCUSDT", "direction": "long",
         "stage": "HARVEST", "realized_pnl_usd": 100.0},
        {"ts": fresh, "pair": "BTCUSDT", "direction": "long",
         "stage": "HARVEST", "realized_pnl_usd": 5.0},
    ]
    (isolated / "equity.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events), encoding="utf-8"
    )
    (isolated / "state.json").write_text("{}", encoding="utf-8")
    text = p15_report.build_p15_report()
    # Only fresh event should be counted.
    assert "$+5.00 on 1 events" in text


def test_recent_events_attached_to_leg(isolated):
    now = datetime.now(timezone.utc)
    state = {
        "BTCUSDT:long": {
            "direction": "long", "in_pos": True, "layers": 1,
            "total_size_usd": 1000.0, "weighted_entry": 80000000.0,
            "extreme_price": 80100.0, "cum_dd_pct": 0.0,
            "opened_at_ts": now.isoformat().replace("+00:00", "Z"),
            "last_emitted_stage": "OPEN",
        }
    }
    events = [
        {"ts": now.isoformat().replace("+00:00", "Z"),
         "pair": "BTCUSDT", "direction": "long", "stage": "OPEN"}
    ]
    (isolated / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (isolated / "equity.jsonl").write_text(
        json.dumps(events[0]) + "\n", encoding="utf-8"
    )
    text = p15_report.build_p15_report()
    assert "recent events:" in text
    assert "OPEN" in text
