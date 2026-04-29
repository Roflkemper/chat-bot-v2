"""TZ-048: ParquetWriter threshold rotation tests."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq
import pytest

from collectors.storage import ParquetBuffer, _utc_day


def _make_liq_row() -> dict:
    return {
        "ts_ms": 1_700_000_000_000,
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "side": "long",
        "qty": 0.01,
        "price": 50_000.0,
        "value_usd": 500.0,
        "source_rate_limited": False,
    }


def _make_ob_row() -> dict:
    return {
        "ts_ms": 1_700_000_000_000,
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "side": "bid",
        "price": 50_000.0,
        "qty": 1.0,
        "level": 1,
    }


# ── Test 1: rotation by row count ────────────────────────────────────────────

def test_writer_rotates_after_max_rows(tmp_path):
    with patch("collectors.storage.LIVE_PATH", tmp_path), \
         patch("collectors.storage.WRITER_MAX_ROWS", 5), \
         patch("collectors.storage.WRITER_MAX_AGE_S", 9999.0), \
         patch("collectors.storage.WRITER_MAX_BYTES", 999_999_999):

        buf = ParquetBuffer("binance", "BTCUSDT", "liquidations")
        initial_path = buf._path  # e.g. 2026-04-29.parquet

        # Write 5 rows — should trigger rotation after flush
        for _ in range(5):
            buf.append(_make_liq_row())
        buf.flush()

        # After rotation: writer closed, path updated to next slot
        assert buf._writer is None, "writer must be closed after rotation"
        assert buf._rows_written == 0, "_rows_written reset after rotation"
        rotated_path = buf._path
        assert rotated_path != initial_path, "path must advance after rotation"

        # Write again — opens new file at rotated_path
        buf.append(_make_liq_row())
        buf.flush()
        buf.close()

        # Two distinct parquet files exist
        parquet_files = sorted(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) == 2, f"expected 2 files, got {parquet_files}"
        # Both readable, first has 5 rows, second has 1
        rows_by_file = {pf.name: pq.read_table(pf).num_rows for pf in parquet_files}
        assert sum(rows_by_file.values()) == 6, f"row count mismatch: {rows_by_file}"


# ── Test 2: rotation by age ───────────────────────────────────────────────────

def test_writer_rotates_after_max_age(tmp_path):
    with patch("collectors.storage.LIVE_PATH", tmp_path), \
         patch("collectors.storage.WRITER_MAX_ROWS", 999_999), \
         patch("collectors.storage.WRITER_MAX_AGE_S", 0.0), \
         patch("collectors.storage.WRITER_MAX_BYTES", 999_999_999):

        buf = ParquetBuffer("binance", "ETHUSDT", "liquidations")
        buf.append(_make_liq_row())
        buf.flush()

        assert buf._writer is None, "writer must be closed when age threshold is 0"
        assert buf._rows_written == 0


# ── Test 3: rotated part-files are all valid parquet ─────────────────────────

def test_rotated_files_all_readable(tmp_path):
    with patch("collectors.storage.LIVE_PATH", tmp_path), \
         patch("collectors.storage.WRITER_MAX_ROWS", 3), \
         patch("collectors.storage.WRITER_MAX_AGE_S", 9999.0), \
         patch("collectors.storage.WRITER_MAX_BYTES", 999_999_999):

        buf = ParquetBuffer("binance", "BTCUSDT", "liquidations")
        total_rows = 10

        for _ in range(total_rows):
            buf.append(_make_liq_row())
            if len(buf._rows) >= 3:
                buf.flush()

        buf.close()

        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) >= 2, "expected multiple part-files"

        for pf in parquet_files:
            tbl = pq.read_table(pf)
            assert tbl.num_rows > 0


# ── Test 4: no row loss across rotation boundary ──────────────────────────────

def test_no_row_loss_across_rotation(tmp_path):
    with patch("collectors.storage.LIVE_PATH", tmp_path), \
         patch("collectors.storage.WRITER_MAX_ROWS", 4), \
         patch("collectors.storage.WRITER_MAX_AGE_S", 9999.0), \
         patch("collectors.storage.WRITER_MAX_BYTES", 999_999_999):

        buf = ParquetBuffer("binance", "BTCUSDT", "orderbook")
        total_sent = 13

        for i in range(total_sent):
            row = _make_ob_row()
            row["level"] = i + 1  # unique marker
            buf.append(row)
            if buf.should_flush():
                buf.flush()

        buf.close()

        parquet_files = list(tmp_path.rglob("*.parquet"))
        total_read = sum(pq.read_table(pf).num_rows for pf in parquet_files)
        assert total_read == total_sent, (
            f"row loss detected: sent {total_sent}, got {total_read}"
        )


# ── Test 5: no rotation below threshold ──────────────────────────────────────

def test_no_rotation_below_threshold(tmp_path):
    with patch("collectors.storage.LIVE_PATH", tmp_path), \
         patch("collectors.storage.WRITER_MAX_ROWS", 1000), \
         patch("collectors.storage.WRITER_MAX_AGE_S", 9999.0), \
         patch("collectors.storage.WRITER_MAX_BYTES", 999_999_999):

        buf = ParquetBuffer("binance", "BTCUSDT", "liquidations")

        for _ in range(5):
            buf.append(_make_liq_row())
        buf.flush()

        # Writer stays open — no rotation yet
        assert buf._writer is not None, "writer must stay open below threshold"
        assert buf._rows_written == 5

        buf.close()
