"""Tests for streak_guard — авто-пауза после N SL подряд."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.paper_trader.streak_guard import recent_loss_streak, should_pause


def _write_journal(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _mk(action: str, ts: datetime, tid: str = "t1") -> dict:
    return {"ts": ts.isoformat(), "trade_id": tid, "action": action}


def test_empty_journal_returns_zero(tmp_path: Path) -> None:
    streak, last = recent_loss_streak(path=tmp_path / "empty.jsonl")
    assert streak == 0
    assert last is None


def test_counts_sl_streak_from_end(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    _write_journal(p, [
        _mk("OPEN", now - timedelta(hours=10), "t1"),
        _mk("TP1",  now - timedelta(hours=9),  "t1"),
        _mk("OPEN", now - timedelta(hours=8),  "t2"),
        _mk("SL",   now - timedelta(hours=7),  "t2"),
        _mk("OPEN", now - timedelta(hours=6),  "t3"),
        _mk("SL",   now - timedelta(hours=5),  "t3"),
        _mk("OPEN", now - timedelta(hours=4),  "t4"),
        _mk("SL",   now - timedelta(hours=1),  "t4"),
    ])
    streak, last = recent_loss_streak(path=p)
    assert streak == 3
    assert last == now - timedelta(hours=1)


def test_tp_breaks_streak(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    _write_journal(p, [
        _mk("SL",  now - timedelta(hours=5), "t1"),
        _mk("SL",  now - timedelta(hours=4), "t2"),
        _mk("TP2", now - timedelta(hours=3), "t3"),
        _mk("SL",  now - timedelta(hours=1), "t4"),
    ])
    streak, _ = recent_loss_streak(path=p)
    assert streak == 1


def test_pause_active_when_streak_reached(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    _write_journal(p, [
        _mk("SL", now - timedelta(hours=3), "t1"),
        _mk("SL", now - timedelta(hours=2), "t2"),
        _mk("SL", now - timedelta(hours=1), "t3"),
    ])
    paused, streak, reason = should_pause(now=now, max_streak=3, pause_hours=6, path=p)
    assert paused is True
    assert streak == 3
    assert "streak=3" in reason


def test_pause_lifts_after_timeout(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    _write_journal(p, [
        _mk("SL", now - timedelta(hours=10), "t1"),
        _mk("SL", now - timedelta(hours=9),  "t2"),
        _mk("SL", now - timedelta(hours=8),  "t3"),
    ])
    paused, _, reason = should_pause(now=now, max_streak=3, pause_hours=6, path=p)
    assert paused is False
    assert "авто-разблок" in reason


def test_no_pause_below_threshold(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    _write_journal(p, [
        _mk("SL", now - timedelta(hours=2), "t1"),
        _mk("SL", now - timedelta(hours=1), "t2"),
    ])
    paused, streak, _ = should_pause(now=now, max_streak=3, pause_hours=6, path=p)
    assert paused is False
    assert streak == 2
