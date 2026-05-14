"""Tests for orchestrator anti-flipflop guard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.orchestrator.anti_flipflop import record_change, should_suppress


def test_first_change_not_suppressed(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    suppress, _ = should_suppress("btc_short", state_path=p)
    assert suppress is False


def test_recent_change_suppressed(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    now = datetime(2026, 5, 13, 3, 18, tzinfo=timezone.utc)
    record_change("btc_short", "RUN", "REDUCE", now=now, state_path=p)
    # Through 4 minutes (как в реальной ситуации 03:18→03:22)
    later = now + timedelta(minutes=4)
    suppress, elapsed = should_suppress("btc_short", now=later, state_path=p)
    assert suppress is True
    assert 200 < elapsed < 300


def test_unblocked_after_min_dwell(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    now = datetime(2026, 5, 13, 3, 18, tzinfo=timezone.utc)
    record_change("btc_short", "RUN", "REDUCE", now=now, state_path=p)
    # Через 31 минуту → разблокирован
    later = now + timedelta(minutes=31)
    suppress, _ = should_suppress("btc_short", now=later, state_path=p, min_dwell_sec=30 * 60)
    assert suppress is False


def test_different_categories_independent(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    now = datetime(2026, 5, 13, 3, 18, tzinfo=timezone.utc)
    record_change("btc_short", "RUN", "REDUCE", now=now, state_path=p)
    # btc_long свой счётчик
    suppress, _ = should_suppress("btc_long", now=now, state_path=p)
    assert suppress is False


def test_corrupt_state_treated_as_empty(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text("not-json")
    suppress, _ = should_suppress("btc_short", state_path=p)
    assert suppress is False
