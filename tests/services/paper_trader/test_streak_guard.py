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


def _mk(action: str, ts: datetime, tid: str = "t1", pnl: float | None = None) -> dict:
    rec = {"ts": ts.isoformat(), "trade_id": tid, "action": action}
    # Default pnl: -100 for real SL, +100 for TP. Tests can override with pnl=0
    # to simulate break-even / mis-classified close events.
    if pnl is not None:
        rec["realized_pnl_usd"] = pnl
    elif action == "SL":
        rec["realized_pnl_usd"] = -100.0
    elif action in ("TP1", "TP2"):
        rec["realized_pnl_usd"] = 100.0
    return rec


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


def test_per_pair_streak_filter(tmp_path: Path) -> None:
    """XRP-streak не блокирует BTC paper-входы."""
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    # 6 SL для XRPUSDT + 1 SL для BTCUSDT
    events = []
    for h in range(6, 0, -1):
        events.append({
            "ts": (now - timedelta(hours=h)).isoformat(),
            "trade_id": f"xrp-{h}",
            "action": "OPEN",
            "pair": "XRPUSDT",
        })
        events.append({
            "ts": (now - timedelta(hours=h, minutes=-1)).isoformat(),
            "trade_id": f"xrp-{h}",
            "action": "SL",
            "realized_pnl_usd": -50.0,
        })
    # один BTC-SL
    events.append({
        "ts": (now - timedelta(hours=2)).isoformat(),
        "trade_id": "btc-1",
        "action": "OPEN",
        "pair": "BTCUSDT",
    })
    events.append({
        "ts": (now - timedelta(hours=1, minutes=59)).isoformat(),
        "trade_id": "btc-1",
        "action": "SL",
        "realized_pnl_usd": -100.0,
    })
    _write_journal(p, events)

    # XRP-streak = 6 → пауза
    streak_xrp, _ = recent_loss_streak(path=p, pair="XRPUSDT")
    assert streak_xrp == 6

    # BTC-streak = 1 → пауза НЕ активна
    streak_btc, _ = recent_loss_streak(path=p, pair="BTCUSDT")
    assert streak_btc == 1

    # Глобальный streak = 7 (но пауза вызывается per-pair)
    streak_all, _ = recent_loss_streak(path=p)
    assert streak_all == 7


def test_zero_pnl_sl_does_not_count(tmp_path: Path) -> None:
    """SL с pnl=0 — это break-even / mis-classified close. Не учитываем."""
    now = datetime(2026, 5, 12, 20, 0, tzinfo=timezone.utc)
    p = tmp_path / "j.jsonl"
    _write_journal(p, [
        _mk("SL", now - timedelta(hours=5), "t1", pnl=0),
        _mk("SL", now - timedelta(hours=4), "t2", pnl=0),
        _mk("SL", now - timedelta(hours=3), "t3", pnl=0),
        _mk("SL", now - timedelta(hours=2), "t4", pnl=-50.0),  # реальный SL
    ])
    streak, _ = recent_loss_streak(path=p)
    assert streak == 1  # только один с pnl<0


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
