"""Tests for TZ-DASHBOARD-POSITION-DEDUP — bot_id deduplication in state_builder."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from services.dashboard.state_builder import (
    _normalize_bot_id, _read_csv_latest_by_bot, _build_positions,
)


# ── _normalize_bot_id ─────────────────────────────────────────────────────────

def test_normalize_strips_dot_zero_suffix():
    assert _normalize_bot_id("5196832375.0") == "5196832375"


def test_normalize_keeps_clean_id():
    assert _normalize_bot_id("5196832375") == "5196832375"


def test_normalize_doesnt_strip_dot_zero_from_alphanumeric():
    """If bot_id is non-numeric (shouldn't happen but defensive), don't mangle."""
    assert _normalize_bot_id("abc.0") == "abc.0"


def test_normalize_handles_empty():
    assert _normalize_bot_id("") == ""
    assert _normalize_bot_id(None) == ""


# ── _read_csv_latest_by_bot deduplication ─────────────────────────────────────

def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "ts_utc", "bot_id", "bot_name", "alias", "status", "position",
        "profit", "current_profit", "in_filled_count", "in_filled_qty",
        "out_filled_count", "out_filled_qty", "trigger_count", "trigger_qty",
        "average_price", "trade_volume", "balance", "liquidation_price", "schema_version",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_legacy_dot_zero_and_clean_id_dedup_to_one(tmp_path):
    """Old rows with '5196832375.0' and new rows with '5196832375' must merge."""
    p = tmp_path / "snapshots.csv"
    _write_csv(p, [
        {"ts_utc": "2026-04-28T00:00:00+00:00", "bot_id": "5196832375.0",
         "alias": "TEST_1", "status": "2", "position": "-0.183", "current_profit": "-95.44"},
        {"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": "5196832375",
         "alias": "TEST_1", "status": "2", "position": "-0.22", "current_profit": "-431.54"},
    ])
    out = _read_csv_latest_by_bot(p)
    assert len(out) == 1
    # Latest ts wins
    assert out[0]["position"] == "-0.22"


def test_duplicate_alias_same_timestamp_one_record(tmp_path):
    """Same bot_id appearing twice at the same ts → only one record kept."""
    p = tmp_path / "snapshots.csv"
    _write_csv(p, [
        {"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": "111",
         "alias": "TEST_X", "status": "2", "position": "-0.5", "current_profit": "-100"},
        {"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": "111",
         "alias": "TEST_X", "status": "2", "position": "-0.5", "current_profit": "-100"},
    ])
    out = _read_csv_latest_by_bot(p)
    assert len(out) == 1


def test_different_bot_ids_preserved(tmp_path):
    """Distinct bot_ids stay as distinct records — even with same alias."""
    p = tmp_path / "snapshots.csv"
    _write_csv(p, [
        {"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": "111",
         "alias": "TEST_X", "status": "2", "position": "-0.5", "current_profit": "-100"},
        {"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": "222",
         "alias": "TEST_X", "status": "2", "position": "-0.3", "current_profit": "-50"},
    ])
    out = _read_csv_latest_by_bot(p)
    assert len(out) == 2
    bot_ids = sorted(r["bot_id"] for r in out)
    assert bot_ids == ["111", "222"]


def test_empty_csv_returns_empty(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text(
        "ts_utc,bot_id,bot_name,alias,status,position\n",
        encoding="utf-8",
    )
    assert _read_csv_latest_by_bot(p) == []


def test_missing_file_returns_empty(tmp_path):
    assert _read_csv_latest_by_bot(tmp_path / "nope.csv") == []


def test_dedup_preserves_latest_by_timestamp(tmp_path):
    """Three rows for same bot at different ts → only newest kept."""
    p = tmp_path / "snapshots.csv"
    _write_csv(p, [
        {"ts_utc": "2026-05-04T20:00:00+00:00", "bot_id": "111",
         "alias": "X", "status": "2", "position": "-0.1", "current_profit": "-10"},
        {"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": "111.0",  # legacy format
         "alias": "X", "status": "2", "position": "-0.5", "current_profit": "-50"},
        {"ts_utc": "2026-05-04T20:30:00+00:00", "bot_id": "111",
         "alias": "X", "status": "2", "position": "-0.3", "current_profit": "-30"},
    ])
    out = _read_csv_latest_by_bot(p)
    assert len(out) == 1
    # 21:00 wins (newest ts)
    assert out[0]["position"] == "-0.5"


# ── _build_positions invariants ──────────────────────────────────────────────

def test_build_positions_net_btc_invariant():
    """sum of shorts (negative) + sum of longs_btc-equivalent ≈ net_btc input."""
    snapshots = [
        {"alias": "TEST_1", "bot_id": "111", "position": "-0.22", "current_profit": "-100"},
        {"alias": "TEST_2", "bot_id": "222", "position": "-0.22", "current_profit": "-100"},
        {"alias": "SHORT_X", "bot_id": "333", "position": "-0.5", "current_profit": "-200"},
    ]
    out = _build_positions(snapshots, net_btc=-0.94, free_margin_pct=50.0, drawdown_pct=0.0)
    assert out["shorts"]["total_btc"] == round(-0.22 - 0.22 - 0.5, 4)
    assert len(out["shorts"]["active_bots"]) == 3


def test_build_positions_empty_snapshots():
    """Empty input returns valid empty structure (graceful)."""
    out = _build_positions([], net_btc=0.0, free_margin_pct=None, drawdown_pct=0.0)
    assert out["shorts"]["total_btc"] == 0
    assert out["longs"]["total_usd"] == 0
    assert out["shorts"]["active_bots"] == []
    assert out["longs"]["active_bots"] == []


# ── Regression test: real-world scenario from production ─────────────────────

def test_regression_legacy_plus_modern_short_bots(tmp_path):
    """Reproduces the production bug: 8 entries collapsing to 4 unique bots.

    Pre-fix this CSV produced shorts.total_btc = -2.241 (sum of 8 entries).
    Post-fix it produces -1.296 (sum of 4 latest unique entries).
    """
    p = tmp_path / "snapshots.csv"
    rows = []
    # Legacy '.0' rows for 4 SHORT bots (older snapshot)
    for bid, alias, pos in [
        ("5196832375.0", "TEST_1", "-0.183"),
        ("5017849873.0", "TEST_2", "-0.181"),
        ("4524162672.0", "TEST_3", "-0.186"),
        ("6399265299.0", "SHORT_1.1%", "-0.395"),
    ]:
        rows.append({"ts_utc": "2026-04-28T00:00:00+00:00", "bot_id": bid,
                     "alias": alias, "status": "2", "position": pos, "current_profit": "0"})
    # Modern (no '.0') rows for SAME 4 bots, newer ts, different positions
    for bid, alias, pos in [
        ("5196832375", "TEST_1", "-0.22"),
        ("5017849873", "TEST_2", "-0.22"),
        ("4524162672", "TEST_3", "-0.22"),
        ("6399265299", "SHORT_1.1%", "-0.636"),
    ]:
        rows.append({"ts_utc": "2026-05-04T21:00:00+00:00", "bot_id": bid,
                     "alias": alias, "status": "2", "position": pos, "current_profit": "0"})

    _write_csv(p, rows)
    snapshots = _read_csv_latest_by_bot(p)
    assert len(snapshots) == 4, "Should dedup to 4 unique bots"

    out = _build_positions(snapshots, net_btc=-1.296, free_margin_pct=None, drawdown_pct=0.0)
    assert out["shorts"]["total_btc"] == round(-0.22 - 0.22 - 0.22 - 0.636, 4)  # -1.296
    assert len(out["shorts"]["active_bots"]) == 4
