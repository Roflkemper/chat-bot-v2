"""Tests for weekly_self_report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from services.reports.weekly_self_report import (
    build_report,
    maybe_send_weekly,
    should_send,
    mark_sent,
)


def _summary_fn(by_bucket: dict, total: int = 0):
    def fn(*, min_samples=3):
        return {"total": total or sum(s.get("n", 0) for h in by_bucket.values() for s in h.values()),
                "by_bucket": by_bucket}
    return fn


def _drift_summary(drifted: list):
    def fn():
        return {"drifted_count": len(drifted), "drifted": drifted, "healthy_count": 0}
    return fn


def test_should_send_sunday_after_18(tmp_path: Path) -> None:
    sp = tmp_path / "s.json"
    sunday_18 = datetime(2026, 5, 17, 18, 30, tzinfo=timezone.utc)  # Sun
    assert should_send(sunday_18, state_path=sp) is True


def test_should_not_send_other_days(tmp_path: Path) -> None:
    sp = tmp_path / "s.json"
    monday = datetime(2026, 5, 11, 18, 30, tzinfo=timezone.utc)
    assert should_send(monday, state_path=sp) is False


def test_should_not_send_before_18(tmp_path: Path) -> None:
    sp = tmp_path / "s.json"
    sunday_17 = datetime(2026, 5, 17, 17, 30, tzinfo=timezone.utc)
    assert should_send(sunday_17, state_path=sp) is False


def test_idempotent_within_week(tmp_path: Path) -> None:
    sp = tmp_path / "s.json"
    sunday = datetime(2026, 5, 17, 18, 30, tzinfo=timezone.utc)
    mark_sent(sunday, state_path=sp)
    later = sunday + timedelta(hours=5)
    assert should_send(later, state_path=sp) is False


def test_sends_next_week(tmp_path: Path) -> None:
    sp = tmp_path / "s.json"
    sunday1 = datetime(2026, 5, 17, 18, 30, tzinfo=timezone.utc)
    mark_sent(sunday1, state_path=sp)
    sunday2 = datetime(2026, 5, 24, 18, 30, tzinfo=timezone.utc)
    assert should_send(sunday2, state_path=sp) is True


def test_build_report_contains_sections(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots.csv"
    snap.write_text(
        "ts_utc,bot_id,bot_name,alias,status,position,profit,current_profit,"
        "in_filled_count,in_filled_qty,out_filled_count,out_filled_qty,trigger_count,"
        "trigger_qty,average_price,trade_volume,balance,liquidation_price,schema_version\n"
        "2026-05-13T12:00:00+00:00,b1,SH-T1,,,0.5,,,,,,,,80000,,,,,1\n",
        encoding="utf-8",
    )
    text = build_report(
        summary_fn=_summary_fn({"long": {"12h": {"n": 8, "accuracy": 75.0}}}),
        drift_summary_fn=_drift_summary([]),
        now=datetime(2026, 5, 17, 18, tzinfo=timezone.utc),
        snapshots=snap,
    )
    assert "ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ" in text
    assert "long" in text
    assert "75" in text
    assert "Edge drift" in text


def test_report_flags_over_limit_peak(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots.csv"
    snap.write_text(
        "ts_utc,bot_id,bot_name,alias,status,position,profit,current_profit,"
        "in_filled_count,in_filled_qty,out_filled_count,out_filled_qty,trigger_count,"
        "trigger_qty,average_price,trade_volume,balance,liquidation_price,schema_version\n"
        "2026-05-13T12:00:00+00:00,risky_bot,SH-T1,,,1.5,,,,,,,,80000,,,,,1\n",
        encoding="utf-8",
    )
    text = build_report(
        summary_fn=_summary_fn({}),
        drift_summary_fn=_drift_summary([]),
        now=datetime(2026, 5, 17, 18, tzinfo=timezone.utc),
        snapshots=snap,
    )
    assert "Превышение risk-limit" in text or "risk-limit" in text
    assert "risky_bot" in text


def test_drift_section_includes_drifted(tmp_path: Path) -> None:
    snap = tmp_path / "snapshots.csv"
    snap.write_text("ts_utc,bot_id\n", encoding="utf-8")
    text = build_report(
        summary_fn=_summary_fn({}),
        drift_summary_fn=_drift_summary(["long_12h", "short_24h"]),
        now=datetime(2026, 5, 17, 18, tzinfo=timezone.utc),
        snapshots=snap,
    )
    assert "EDGE DRIFTED" in text
    assert "long_12h" in text


def test_maybe_send_sends_once(tmp_path: Path) -> None:
    sp = tmp_path / "s.json"
    snap = tmp_path / "snapshots.csv"
    snap.write_text("ts_utc,bot_id\n", encoding="utf-8")
    send = MagicMock()
    sunday = datetime(2026, 5, 17, 18, 30, tzinfo=timezone.utc)
    sent1 = maybe_send_weekly(
        send_fn=send,
        summary_fn=_summary_fn({}),
        drift_summary_fn=_drift_summary([]),
        now=sunday, state_path=sp, snapshots=snap,
    )
    assert sent1 is True
    send.assert_called_once()
    # second call same week — no send
    sent2 = maybe_send_weekly(
        send_fn=send,
        summary_fn=_summary_fn({}),
        drift_summary_fn=_drift_summary([]),
        now=sunday + timedelta(hours=2), state_path=sp, snapshots=snap,
    )
    assert sent2 is False
