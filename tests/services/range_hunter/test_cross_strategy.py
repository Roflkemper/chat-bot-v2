"""Tests for cross-strategy cascade confirmation in hedge advisor."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.range_hunter.loop import _check_cross_strategy_confirmation


@pytest.fixture
def dedup_file(tmp_path: Path) -> Path:
    p = tmp_path / "cascade_alert_dedup.json"
    return p


def _write_dedup(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_no_dedup_file_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    assert _check_cross_strategy_confirmation("LONG", dedup_path=missing) == []


def test_long_orphan_confirmed_by_recent_short_cascade(dedup_file: Path) -> None:
    now = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=15)).isoformat()
    _write_dedup(dedup_file, {"short_5.0": recent})
    result = _check_cross_strategy_confirmation("LONG", now=now, dedup_path=dedup_file)
    assert len(result) == 1
    assert result[0]["key"] == "short_5.0"
    assert 10 <= result[0]["age_min"] <= 20


def test_short_orphan_confirmed_by_recent_long_cascade(dedup_file: Path) -> None:
    now = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=20)).isoformat()
    _write_dedup(dedup_file, {"long_5.0": recent})
    result = _check_cross_strategy_confirmation("SHORT", now=now, dedup_path=dedup_file)
    assert len(result) == 1
    assert result[0]["key"] == "long_5.0"


def test_stale_cascade_ignored(dedup_file: Path) -> None:
    """Cascade fired >60 мин назад уже не считается подтверждением."""
    now = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    stale = (now - timedelta(hours=3)).isoformat()
    _write_dedup(dedup_file, {"short_5.0": stale, "long_5.0": stale})
    assert _check_cross_strategy_confirmation("LONG", now=now, dedup_path=dedup_file) == []
    assert _check_cross_strategy_confirmation("SHORT", now=now, dedup_path=dedup_file) == []


def test_wrong_direction_ignored(dedup_file: Path) -> None:
    """LONG-cascade НЕ подтверждает LONG-orphan (в 2026 long cascade = price down)."""
    now = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=10)).isoformat()
    _write_dedup(dedup_file, {"long_5.0": recent})
    assert _check_cross_strategy_confirmation("LONG", now=now, dedup_path=dedup_file) == []
    # А SHORT-orphan — подтверждается
    assert len(_check_cross_strategy_confirmation("SHORT", now=now, dedup_path=dedup_file)) == 1


def test_mega_cascades_ignored(dedup_file: Path) -> None:
    """mega 10BTC сигналы исключены (другой edge, скоринг отдельно)."""
    now = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=10)).isoformat()
    _write_dedup(dedup_file, {"short_10.0_mega": recent, "long_10.0_mega": recent})
    assert _check_cross_strategy_confirmation("LONG", now=now, dedup_path=dedup_file) == []
    assert _check_cross_strategy_confirmation("SHORT", now=now, dedup_path=dedup_file) == []


def test_multiple_confirmations_returned(dedup_file: Path) -> None:
    """Если оба short_2 и short_5 свежие — возвращаем оба."""
    now = datetime(2026, 5, 15, 22, 0, tzinfo=timezone.utc)
    t1 = (now - timedelta(minutes=10)).isoformat()
    t2 = (now - timedelta(minutes=30)).isoformat()
    _write_dedup(dedup_file, {"short_2.0": t1, "short_5.0": t2})
    result = _check_cross_strategy_confirmation("LONG", now=now, dedup_path=dedup_file)
    assert len(result) == 2
    keys = {r["key"] for r in result}
    assert keys == {"short_2.0", "short_5.0"}
