"""Tests for storage.py CSV writers."""
import csv
from pathlib import Path

import pytest

from ginarea_tracker.storage import (
    CsvWriter,
    StorageManager,
    SNAPSHOTS_HEADERS,
    EVENTS_HEADERS,
    PARAMS_HEADERS,
    SCHEMA_VERSION,
    _resolve_path,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


def _snapshot_row(**kwargs) -> dict:
    defaults = {
        "ts_utc": "2024-01-01T00:00:00+00:00",
        "bot_id": "111",
        "bot_name": "TEST",
        "alias": "T1",
        "status": "active",
        "position": "0.5",
        "profit": "10.0",
        "current_profit": "5.0",
        "in_filled_count": "3",
        "in_filled_qty": "30.0",
        "out_filled_count": "2",
        "out_filled_qty": "20.0",
        "trigger_count": "0",
        "trigger_qty": "0",
        "average_price": "45000",
        "trade_volume": "1000000",
        "balance": "14000",
        "liquidation_price": "0",
        "stat_updated_at": "2024-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return defaults


def _event_row(**kwargs) -> dict:
    defaults = {
        "ts_utc": "2024-01-01T00:00:00+00:00",
        "bot_id": "111",
        "bot_name": "TEST",
        "event_type": "IN_FILLED",
        "delta_count": "1",
        "delta_qty": "10.0",
        "price_last": "45000",
        "position_after": "0.6",
        "profit_after": "12.0",
    }
    defaults.update(kwargs)
    return defaults


# ── CsvWriter ─────────────────────────────────────────────────────────────────

class TestCsvWriter:
    def test_creates_file_with_header(self, tmp_path):
        path = tmp_path / "test.csv"
        w = CsvWriter(path, ["a", "b", "c"])
        w.close()
        rows = _read_csv(path)
        assert rows[0] == ["a", "b", "c"]

    def test_append_row(self, tmp_path):
        path = tmp_path / "test.csv"
        w = CsvWriter(path, ["x", "y"])
        w.write({"x": "1", "y": "2"})
        w.close()
        rows = _read_csv(path)
        assert len(rows) == 2
        assert rows[1] == ["1", "2"]

    def test_missing_keys_written_as_empty(self, tmp_path):
        path = tmp_path / "test.csv"
        w = CsvWriter(path, ["a", "b", "c"])
        w.write({"a": "hello"})
        w.close()
        rows = _read_csv(path)
        assert rows[1] == ["hello", "", ""]

    def test_append_to_existing_compatible_file(self, tmp_path):
        path = tmp_path / "test.csv"
        # First writer creates file
        w1 = CsvWriter(path, ["a", "b"])
        w1.write({"a": "1", "b": "2"})
        w1.close()
        # Second writer appends
        w2 = CsvWriter(path, ["a", "b"])
        w2.write({"a": "3", "b": "4"})
        w2.close()
        rows = _read_csv(path)
        assert len(rows) == 3  # header + 2 data rows
        assert rows[2] == ["3", "4"]

    def test_schema_mismatch_creates_versioned_file(self, tmp_path):
        base = tmp_path / "data.csv"
        # Write with old schema
        w1 = CsvWriter(base, ["old_col"])
        w1.write({"old_col": "x"})
        w1.close()
        # Write with new schema
        w2 = CsvWriter(base, ["new_col_1", "new_col_2"])
        w2.write({"new_col_1": "a", "new_col_2": "b"})
        w2.close()
        assert not (tmp_path / "data.csv") == w2.path
        assert w2.path.name == "data_v2.csv"
        rows = _read_csv(w2.path)
        assert rows[0] == ["new_col_1", "new_col_2"]
        assert rows[1] == ["a", "b"]

    def test_schema_mismatch_reuses_existing_versioned_file(self, tmp_path):
        base = tmp_path / "data.csv"
        headers_v2 = ["x", "y"]
        # Create base with different schema
        w0 = CsvWriter(base, ["z"])
        w0.close()
        # Create _v2 with headers_v2
        w1 = CsvWriter(base, headers_v2)
        w1.write({"x": "1", "y": "2"})
        w1.close()
        # Another writer with same headers_v2 should reuse _v2
        w2 = CsvWriter(base, headers_v2)
        w2.write({"x": "3", "y": "4"})
        w2.close()
        assert w2.path.name == "data_v2.csv"
        rows = _read_csv(w2.path)
        assert len(rows) == 3  # header + 2 data rows


# ── _resolve_path ─────────────────────────────────────────────────────────────

class TestResolvePath:
    def test_returns_base_if_not_exists(self, tmp_path):
        base = tmp_path / "new.csv"
        assert _resolve_path(base, ["a"]) == base

    def test_returns_base_if_schema_matches(self, tmp_path):
        base = tmp_path / "data.csv"
        CsvWriter(base, ["a", "b"]).close()
        assert _resolve_path(base, ["a", "b"]) == base

    def test_increments_version_on_mismatch(self, tmp_path):
        base = tmp_path / "data.csv"
        CsvWriter(base, ["old"]).close()
        result = _resolve_path(base, ["new"])
        assert result.name == "data_v2.csv"


# ── StorageManager ────────────────────────────────────────────────────────────

class TestStorageManager:
    def test_creates_three_csv_files(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.close()
        assert (tmp_path / "snapshots.csv").exists()
        assert (tmp_path / "events.csv").exists()
        assert (tmp_path / "params.csv").exists()

    def test_snapshot_headers_match_schema(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.close()
        rows = _read_csv(tmp_path / "snapshots.csv")
        assert rows[0] == SNAPSHOTS_HEADERS

    def test_events_headers_match_schema(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.close()
        rows = _read_csv(tmp_path / "events.csv")
        assert rows[0] == EVENTS_HEADERS

    def test_params_headers_match_schema(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.close()
        rows = _read_csv(tmp_path / "params.csv")
        assert rows[0] == PARAMS_HEADERS

    def test_write_snapshot_injects_schema_version(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.write_snapshot(_snapshot_row())
        mgr.close()
        rows = _read_csv(tmp_path / "snapshots.csv")
        assert len(rows) == 2
        idx = SNAPSHOTS_HEADERS.index("schema_version")
        assert rows[1][idx] == str(SCHEMA_VERSION)

    def test_write_event_injects_schema_version(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.write_event(_event_row())
        mgr.close()
        rows = _read_csv(tmp_path / "events.csv")
        idx = EVENTS_HEADERS.index("schema_version")
        assert rows[1][idx] == str(SCHEMA_VERSION)

    def test_multiple_snapshots_appended(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.write_snapshot(_snapshot_row(bot_id="aaa"))
        mgr.write_snapshot(_snapshot_row(bot_id="bbb"))
        mgr.close()
        rows = _read_csv(tmp_path / "snapshots.csv")
        assert len(rows) == 3
        bot_ids = {rows[1][SNAPSHOTS_HEADERS.index("bot_id")],
                   rows[2][SNAPSHOTS_HEADERS.index("bot_id")]}
        assert bot_ids == {"aaa", "bbb"}

    def test_write_params_fields(self, tmp_path):
        mgr = StorageManager(tmp_path)
        mgr.write_params({
            "ts_utc": "2024-01-01T00:00:00+00:00",
            "bot_id": "999",
            "bot_name": "BOT",
            "strategy_id": "grid",
            "side": "short",
            "grid_step": "0.5",
            "raw_params_json": "{}",
        })
        mgr.close()
        rows = _read_csv(tmp_path / "params.csv")
        idx_side = PARAMS_HEADERS.index("side")
        assert rows[1][idx_side] == "short"
