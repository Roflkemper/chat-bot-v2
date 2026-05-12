"""Tests for cascade_filter — блокировка LONG-входов после крупного каскада."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.paper_trader.cascade_filter import (
    recent_cascade_volume_btc,
    should_block_long_entry,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts_utc", "exchange", "side", "qty", "price"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_returns_zero_when_csv_missing(tmp_path: Path) -> None:
    vol = recent_cascade_volume_btc(csv_path=tmp_path / "nope.csv")
    assert vol == 0.0


def test_sums_recent_window_only(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        # within 30 min
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "okx", "side": "long", "qty": "20.0", "price": "80000"},
        {"ts_utc": (now - timedelta(minutes=15)).isoformat(), "exchange": "okx", "side": "short", "qty": "10.0", "price": "80000"},
        # older than 30 min — must be excluded
        {"ts_utc": (now - timedelta(minutes=45)).isoformat(), "exchange": "okx", "side": "long", "qty": "100.0", "price": "80000"},
    ])
    vol = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert vol == pytest.approx(30.0)


def test_skips_rows_with_missing_qty(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "", "price": ""},
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "okx", "side": "long", "qty": "5.5", "price": "80000"},
    ])
    vol = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert vol == pytest.approx(5.5)


def test_blocks_when_threshold_exceeded(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "okx", "side": "long", "qty": "60.0", "price": "80000"},
    ])
    blocked, vol = should_block_long_entry(now=now, csv_path=csv_path, threshold_btc=50.0)
    assert blocked is True
    assert vol == pytest.approx(60.0)


def test_does_not_block_below_threshold(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "okx", "side": "long", "qty": "20.0", "price": "80000"},
    ])
    blocked, vol = should_block_long_entry(now=now, csv_path=csv_path, threshold_btc=50.0)
    assert blocked is False
    assert vol == pytest.approx(20.0)
