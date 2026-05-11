"""Tests for ginarea_report — /ginarea TG command."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from services import ginarea_report


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    snap = tmp_path / "snapshots.csv"
    market = tmp_path / "market_1m.csv"
    monkeypatch.setattr(ginarea_report, "_SNAPSHOTS", snap)
    # Also redirect price source — write the expected file path.
    monkeypatch.setattr(ginarea_report, "_ROOT", tmp_path)
    return tmp_path


def _write_snapshots(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("ts_utc,bot_id,bot_name,alias,status,position,profit,current_profit\n",
                         encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_no_snapshots_reports_tracker_down(isolated):
    _write_snapshots(isolated / "snapshots.csv", [])
    text = ginarea_report.build_ginarea_report()
    assert "No bot snapshots" in text


def test_latest_per_bot_picks_last_row(isolated):
    """If same bot_id appears multiple times, last row wins."""
    rows = [
        {"ts_utc": "2026-05-11T08:00:00Z", "bot_id": "B1", "alias": "TEST_1",
         "status": "1", "position": "0.1", "current_profit": "10.0",
         "average_price": "80000", "liquidation_price": ""},
        {"ts_utc": "2026-05-11T09:00:00Z", "bot_id": "B1", "alias": "TEST_1",
         "status": "1", "position": "0.2", "current_profit": "20.0",
         "average_price": "80100", "liquidation_price": ""},
    ]
    _write_snapshots(isolated / "snapshots.csv", rows)
    latest = ginarea_report._latest_snapshot_per_bot()
    assert len(latest) == 1
    assert latest[0]["position"] == "0.2"


def test_total_pnl_sums_current_profit(isolated):
    rows = [
        {"ts_utc": "t", "bot_id": "B1", "alias": "A", "status": "1",
         "position": "0.1", "current_profit": "100.0",
         "average_price": "80000", "liquidation_price": "70000"},
        {"ts_utc": "t", "bot_id": "B2", "alias": "B", "status": "2",
         "position": "-0.05", "current_profit": "-30.0",
         "average_price": "81000", "liquidation_price": "95000"},
    ]
    _write_snapshots(isolated / "snapshots.csv", rows)
    text = ginarea_report.build_ginarea_report()
    assert "Total unrealized PnL: $+70.00" in text


def test_active_count_status_1(isolated):
    rows = [
        {"ts_utc": "t", "bot_id": str(i), "alias": f"A{i}", "status": str(s),
         "position": "0", "current_profit": "0",
         "average_price": "0", "liquidation_price": "0"}
        for i, s in enumerate([1, 1, 2, 3, 0])
    ]
    _write_snapshots(isolated / "snapshots.csv", rows)
    text = ginarea_report.build_ginarea_report()
    assert "active=2" in text
    assert "dd=1" in text
    assert "paused=1" in text
