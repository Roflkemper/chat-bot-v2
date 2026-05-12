"""Tests for regime_filter."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.paper_trader.regime_filter import (
    recent_instability_stability,
    should_block_for_instability,
)


def _write_decisions(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def test_returns_none_when_no_events(tmp_path: Path) -> None:
    p = tmp_path / "d.jsonl"
    p.write_text("")
    assert recent_instability_stability(path=p) is None


def test_ignores_non_r3_events(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 18, 30, tzinfo=timezone.utc)
    p = tmp_path / "d.jsonl"
    _write_decisions(p, [
        {"event_type": "regulation_status", "payload": {"stability": 0.92}, "ts": (now - timedelta(minutes=5)).isoformat()},
    ])
    assert recent_instability_stability(now=now, path=p) is None


def test_picks_lowest_within_window(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 18, 30, tzinfo=timezone.utc)
    p = tmp_path / "d.jsonl"
    _write_decisions(p, [
        {"event_type": "regime_instability", "payload": {"stability": 0.35}, "ts": (now - timedelta(minutes=5)).isoformat()},
        {"event_type": "regime_instability", "payload": {"stability": 0.17}, "ts": (now - timedelta(minutes=10)).isoformat()},
        # Out of window — must be ignored
        {"event_type": "regime_instability", "payload": {"stability": 0.05}, "ts": (now - timedelta(minutes=30)).isoformat()},
    ])
    assert recent_instability_stability(now=now, path=p) == pytest.approx(0.17)


def test_excludes_future_events(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 18, 30, tzinfo=timezone.utc)
    p = tmp_path / "d.jsonl"
    _write_decisions(p, [
        {"event_type": "regime_instability", "payload": {"stability": 0.20}, "ts": (now + timedelta(minutes=5)).isoformat()},
    ])
    assert recent_instability_stability(now=now, path=p) is None


def test_should_block_returns_true_when_event_present(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 18, 30, tzinfo=timezone.utc)
    p = tmp_path / "d.jsonl"
    _write_decisions(p, [
        {"event_type": "regime_instability", "payload": {"stability": 0.17}, "ts": (now - timedelta(minutes=5)).isoformat()},
    ])
    blocked, low = should_block_for_instability(now=now, path=p)
    assert blocked is True
    assert low == pytest.approx(0.17)


def test_handles_z_suffix_timestamps(tmp_path: Path) -> None:
    """decisions.jsonl использует ISO с Z-суффиксом."""
    now = datetime(2026, 5, 12, 18, 30, tzinfo=timezone.utc)
    p = tmp_path / "d.jsonl"
    ts_str = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    _write_decisions(p, [
        {"event_type": "regime_instability", "payload": {"stability": 0.20}, "ts": ts_str},
    ])
    assert recent_instability_stability(now=now, path=p) == pytest.approx(0.20)
