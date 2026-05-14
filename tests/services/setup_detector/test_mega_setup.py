"""Tests for Stage B5 mega-setup detector."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from services.setup_detector.models import SetupType
from services.setup_detector import mega_setup as ms


@dataclass
class _Ctx:
    pair: str = "BTCUSDT"
    current_price: float = 80000.0
    regime_label: str = "range_wide"
    session_label: str = "ny_am"
    ohlcv_1m: pd.DataFrame = field(default_factory=pd.DataFrame)
    ohlcv_1h: pd.DataFrame = field(default_factory=pd.DataFrame)
    ohlcv_15m: pd.DataFrame = field(default_factory=pd.DataFrame)
    ict_context: dict = field(default_factory=dict)


def _setup_record(setup_type: str, pair: str, ts: datetime, strength: int = 8) -> str:
    return json.dumps({
        "setup_id": f"id-{ts.timestamp()}",
        "setup_type": setup_type,
        "detected_at": ts.isoformat(),
        "pair": pair,
        "strength": strength,
        "confidence_pct": 70.0,
    }) + "\n"


def _write_setups(path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def test_no_fire_when_setups_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "SETUPS_PATH", tmp_path / "missing.jsonl")
    assert ms.detect_long_mega_dump_bounce(_Ctx()) is None


def test_no_fire_when_only_dump_reversal(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    _write_setups(p, [_setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=5))])
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    assert ms.detect_long_mega_dump_bounce(_Ctx()) is None


def test_no_fire_when_only_pdl_bounce(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    _write_setups(p, [_setup_record("long_pdl_bounce", "BTCUSDT", now - timedelta(minutes=5))])
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    assert ms.detect_long_mega_dump_bounce(_Ctx()) is None


def test_fire_when_both_within_window(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        _setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=30)),
        _setup_record("long_pdl_bounce", "BTCUSDT", now - timedelta(minutes=10)),
    ]
    _write_setups(p, lines)
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    setup = ms.detect_long_mega_dump_bounce(_Ctx())
    assert setup is not None
    assert setup.setup_type == SetupType.LONG_MEGA_DUMP_BOUNCE
    assert setup.strength == 10
    assert setup.confidence_pct == 85.0


def test_no_fire_when_one_constituent_outside_window(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        # dump_reversal too old (90 min ago)
        _setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=90)),
        _setup_record("long_pdl_bounce", "BTCUSDT", now - timedelta(minutes=5)),
    ]
    _write_setups(p, lines)
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    assert ms.detect_long_mega_dump_bounce(_Ctx()) is None


def test_no_fire_when_constituents_on_different_pairs(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        _setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=10)),
        _setup_record("long_pdl_bounce", "ETHUSDT", now - timedelta(minutes=10)),
    ]
    _write_setups(p, lines)
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    assert ms.detect_long_mega_dump_bounce(_Ctx(pair="BTCUSDT")) is None


def test_dedup_blocks_within_4h(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        _setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=20)),
        _setup_record("long_pdl_bounce", "BTCUSDT", now - timedelta(minutes=10)),
        # Mega already fired 2h ago for same pair
        _setup_record("long_mega_dump_bounce", "BTCUSDT", now - timedelta(hours=2)),
    ]
    _write_setups(p, lines)
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    assert ms.detect_long_mega_dump_bounce(_Ctx()) is None


def test_fire_after_dedup_window_clears(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    lines = [
        # Old mega 5h ago — outside MEGA_DEDUP_HOURS=4
        _setup_record("long_mega_dump_bounce", "BTCUSDT", now - timedelta(hours=5)),
        _setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=20)),
        _setup_record("long_pdl_bounce", "BTCUSDT", now - timedelta(minutes=10)),
    ]
    _write_setups(p, lines)
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    # Note: 5h-old record may be outside the 256KB tail read window if file
    # is very large — but for small test file all entries are read.
    setup = ms.detect_long_mega_dump_bounce(_Ctx())
    assert setup is not None


def test_basis_includes_constituent_timestamps(monkeypatch, tmp_path):
    p = tmp_path / "setups.jsonl"
    now = datetime.now(timezone.utc)
    dump_ts = (now - timedelta(minutes=30)).isoformat()
    bounce_ts = (now - timedelta(minutes=10)).isoformat()
    lines = [
        _setup_record("long_dump_reversal", "BTCUSDT", now - timedelta(minutes=30)),
        _setup_record("long_pdl_bounce", "BTCUSDT", now - timedelta(minutes=10)),
    ]
    _write_setups(p, lines)
    monkeypatch.setattr(ms, "SETUPS_PATH", p)
    setup = ms.detect_long_mega_dump_bounce(_Ctx())
    assert setup is not None
    labels = {b.label for b in setup.basis}
    assert "dump_reversal_ts" in labels
    assert "pdl_bounce_ts" in labels
    assert "backtest_boost_pp" in labels
