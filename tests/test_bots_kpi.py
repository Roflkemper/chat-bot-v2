"""Unit tests for services.bots_kpi.builder."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from services.bots_kpi import builder


def _fake_snap_row(ts: datetime, bot_id: int, name: str, alias: str,
                   profit: float, current_profit: float, in_count: int,
                   out_count: int, vol: float) -> dict:
    return {
        "ts_utc": ts.isoformat(),
        "bot_id": bot_id,
        "bot_name": name,
        "alias": alias,
        "status": 2,
        "position": 0,
        "profit": profit,
        "current_profit": current_profit,
        "in_filled_count": in_count,
        "in_filled_qty": "",
        "out_filled_count": out_count,
        "out_filled_qty": "",
        "trigger_count": 0,
        "trigger_qty": "",
        "average_price": 70000.0,
        "trade_volume": vol,
        "balance": 1000.0,
        "liquidation_price": 96000.0,
        "schema_version": 3,
    }


def _build_snap(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_builder_handles_missing_snap(monkeypatch, tmp_path):
    monkeypatch.setattr(builder, "SNAP_PATH", tmp_path / "missing.csv")
    out = builder.build_bots_kpi_report(7.0)
    assert "snapshots not found" in out


def test_builder_basic_table(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    snap = tmp_path / "snap.csv"
    rows = [
        _fake_snap_row(now - timedelta(days=6), 5196832375, "TEST 1 ", "TEST_1",
                       100.0, -10.0, 1000, 500, 25000.0),
        _fake_snap_row(now - timedelta(hours=1), 5196832375, "TEST 1 ", "TEST_1",
                       125.0, -5.0, 1100, 550, 30000.0),
        _fake_snap_row(now - timedelta(days=6), 5017849873, "TEST 2", "TEST_2",
                       200.0, -20.0, 800, 400, 20000.0),
        _fake_snap_row(now - timedelta(hours=1), 5017849873, "TEST 2", "TEST_2",
                       230.0, -15.0, 900, 450, 25000.0),
    ]
    _build_snap(rows).to_csv(snap, index=False)
    monkeypatch.setattr(builder, "SNAP_PATH", snap)
    monkeypatch.setattr(builder, "ALIASES_PATH", tmp_path / "aliases.json")  # missing
    out = builder.build_bots_kpi_report(7.0)
    assert "TEST_1" in out
    assert "TEST_2" in out
    # realized: TEST_1 = 25, TEST_2 = 30 → TEST_2 first
    lines = [l for l in out.split("\n") if "TEST_" in l]
    assert lines[0].split()[0] == "TEST_2"
    assert lines[1].split()[0] == "TEST_1"


def test_builder_filters_zero_volume(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    snap = tmp_path / "snap.csv"
    rows = [
        _fake_snap_row(now - timedelta(days=6), 1, "real", "REAL", 0.0, 0.0, 0, 0, 0.0),
        _fake_snap_row(now - timedelta(hours=1), 1, "real", "REAL", 0.0, 0.0, 0, 0, 0.0),
        _fake_snap_row(now - timedelta(days=6), 2, "active", "ACT", 100.0, 0.0, 50, 25, 10000.0),
        _fake_snap_row(now - timedelta(hours=1), 2, "active", "ACT", 120.0, 0.0, 60, 30, 12000.0),
    ]
    _build_snap(rows).to_csv(snap, index=False)
    monkeypatch.setattr(builder, "SNAP_PATH", snap)
    monkeypatch.setattr(builder, "ALIASES_PATH", tmp_path / "aliases.json")
    out = builder.build_bots_kpi_report(7.0)
    assert "ACT" in out
    assert "REAL" not in out


def test_builder_uses_aliases_json(monkeypatch, tmp_path):
    import json
    now = datetime.now(timezone.utc)
    snap = tmp_path / "snap.csv"
    rows = [
        _fake_snap_row(now - timedelta(days=2), 999, "raw bot name", "",
                       50.0, 0.0, 10, 5, 5000.0),
        _fake_snap_row(now - timedelta(hours=1), 999, "raw bot name", "",
                       70.0, 0.0, 12, 6, 6000.0),
    ]
    _build_snap(rows).to_csv(snap, index=False)
    aliases = tmp_path / "aliases.json"
    aliases.write_text(json.dumps({"999": "MY_ALIAS"}), encoding="utf-8")
    monkeypatch.setattr(builder, "SNAP_PATH", snap)
    monkeypatch.setattr(builder, "ALIASES_PATH", aliases)
    out = builder.build_bots_kpi_report(7.0)
    assert "MY_ALIAS" in out


def test_builder_window_excludes_old_data(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    snap = tmp_path / "snap.csv"
    rows = [
        # too old (15 days back) — outside 7d window
        _fake_snap_row(now - timedelta(days=15), 1, "old", "OLD", 0.0, 0.0, 0, 0, 0.0),
        _fake_snap_row(now - timedelta(days=14), 1, "old", "OLD", 100.0, 0.0, 50, 25, 50000.0),
    ]
    _build_snap(rows).to_csv(snap, index=False)
    monkeypatch.setattr(builder, "SNAP_PATH", snap)
    monkeypatch.setattr(builder, "ALIASES_PATH", tmp_path / "aliases.json")
    out = builder.build_bots_kpi_report(7.0)
    assert "no snapshots" in out or "no active bots" in out
