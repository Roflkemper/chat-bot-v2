"""Tests for cascade_filter — блокировка LONG-входов после крупного каскада."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.paper_trader.cascade_filter import (
    clear_cache,
    recent_cascade_volume_btc,
    should_block_entry,
    should_block_long_entry,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_cache()
    yield
    clear_cache()


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
        # within 30 min — bybit, qty as BTC
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "20.0", "price": "80000"},
        {"ts_utc": (now - timedelta(minutes=15)).isoformat(), "exchange": "bybit", "side": "short", "qty": "10.0", "price": "80000"},
        # older than 30 min — must be excluded
        {"ts_utc": (now - timedelta(minutes=45)).isoformat(), "exchange": "bybit", "side": "long", "qty": "100.0", "price": "80000"},
    ])
    vol = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert vol == pytest.approx(30.0)


def test_skips_rows_with_missing_qty(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "", "price": ""},
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "5.5", "price": "80000"},
    ])
    vol = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert vol == pytest.approx(5.5)


def test_blocks_when_threshold_exceeded(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "60.0", "price": "80000"},
    ])
    blocked, vol = should_block_long_entry(now=now, csv_path=csv_path, threshold_btc=50.0)
    assert blocked is True
    assert vol == pytest.approx(60.0)


def test_excludes_future_timestamps(tmp_path: Path) -> None:
    """Retrospective query: ts > now нельзя учитывать (audit-script use case)."""
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        # past — в окне 30 мин до now
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "10.0", "price": "80000"},
        # future — после now, не должно учитываться
        {"ts_utc": (now + timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "999.0", "price": "80000"},
    ])
    vol = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert vol == pytest.approx(10.0)


def test_cache_avoids_second_read(tmp_path: Path) -> None:
    """Второй вызов с тем же ключом не читает CSV (даже если файл изменился)."""
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "10.0", "price": "80000"},
    ])
    v1 = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert v1 == pytest.approx(10.0)
    # Подменяем содержимое CSV — кеш должен вернуть старое значение
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "999.0", "price": "80000"},
    ])
    v2 = recent_cascade_volume_btc(now=now, csv_path=csv_path)
    assert v2 == pytest.approx(10.0)


def test_cache_can_be_bypassed(tmp_path: Path) -> None:
    """use_cache=False всегда читает CSV свежим."""
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "10.0", "price": "80000"},
    ])
    v1 = recent_cascade_volume_btc(now=now, csv_path=csv_path, use_cache=False)
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "999.0", "price": "80000"},
    ])
    v2 = recent_cascade_volume_btc(now=now, csv_path=csv_path, use_cache=False)
    assert v1 == pytest.approx(10.0)
    assert v2 == pytest.approx(999.0)


def test_does_not_block_below_threshold(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "20.0", "price": "80000"},
    ])
    blocked, vol = should_block_long_entry(now=now, csv_path=csv_path, threshold_btc=50.0)
    assert blocked is False
    assert vol == pytest.approx(20.0)


def test_btc_pair_blocked_normally(tmp_path: Path) -> None:
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "200.0", "price": "80000"},
    ])
    blocked, vol = should_block_entry("long", pair="BTCUSDT", now=now, csv_path=csv_path, threshold_btc=150.0)
    assert blocked is True
    assert vol == pytest.approx(200.0)


def test_xbt_pair_treated_as_btc(tmp_path: Path) -> None:
    """BitMEX inverse uses XBTUSD."""
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "200.0", "price": "80000"},
    ])
    blocked, _ = should_block_entry("long", pair="XBTUSD", now=now, csv_path=csv_path, threshold_btc=150.0)
    assert blocked is True


def test_non_btc_pairs_not_blocked(tmp_path: Path) -> None:
    """ETH/XRP/SOL — фильтр не применяется."""
    now = datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc)
    csv_path = tmp_path / "liq.csv"
    _write_csv(csv_path, [
        {"ts_utc": (now - timedelta(minutes=5)).isoformat(), "exchange": "bybit", "side": "long", "qty": "9999.0", "price": "80000"},
    ])
    for pair in ("ETHUSDT", "XRPUSDT", "SOLUSDT"):
        blocked, vol = should_block_entry("long", pair=pair, now=now, csv_path=csv_path, threshold_btc=150.0)
        assert blocked is False, f"{pair} should not be blocked by BTC cascade"
        assert vol == 0.0


def test_invalid_side_returns_false(tmp_path: Path) -> None:
    blocked, vol = should_block_entry("grid", pair="BTCUSDT", csv_path=tmp_path / "missing.csv")
    assert blocked is False
    assert vol == 0.0
