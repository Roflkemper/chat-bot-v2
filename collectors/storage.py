"""Parquet buffer — accumulates events per (exchange, symbol, datatype) and flushes to disk."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from collectors.config import (
    BUFFER_MAX_EVENTS,
    FLUSH_INTERVAL_S,
    LIVE_PATH,
    PARQUET_COMPRESSION,
    PARQUET_COMPRESSION_LEVEL,
    PARQUET_ROW_GROUP_SIZE,
)

log = logging.getLogger(__name__)

# ── Schemas ───────────────────────────────────────────────────────────────────

SCHEMA_LIQUIDATIONS = pa.schema([
    pa.field("ts_ms", pa.int64()),
    pa.field("exchange", pa.string()),
    pa.field("symbol", pa.string()),
    pa.field("side", pa.string()),               # "long" | "short"
    pa.field("qty", pa.float64()),
    pa.field("price", pa.float64()),
    pa.field("value_usd", pa.float64()),
    pa.field("source_rate_limited", pa.bool_()), # True = exchange throttles delivery (e.g. Binance 1/sec)
])

SCHEMA_ORDERBOOK = pa.schema([
    pa.field("ts_ms", pa.int64()),
    pa.field("exchange", pa.string()),
    pa.field("symbol", pa.string()),
    pa.field("side", pa.string()),      # "bid" | "ask"
    pa.field("price", pa.float64()),
    pa.field("qty", pa.float64()),
    pa.field("level", pa.int32()),
])

SCHEMA_TRADES = pa.schema([
    pa.field("ts_ms", pa.int64()),
    pa.field("exchange", pa.string()),
    pa.field("symbol", pa.string()),
    pa.field("side", pa.string()),      # "buy" | "sell"
    pa.field("qty", pa.float64()),
    pa.field("price", pa.float64()),
    pa.field("is_liquidation", pa.bool_()),
])

_SCHEMAS: dict[str, pa.Schema] = {
    "liquidations": SCHEMA_LIQUIDATIONS,
    "orderbook": SCHEMA_ORDERBOOK,
    "trades": SCHEMA_TRADES,
}

# ── Path helpers ──────────────────────────────────────────────────────────────

def _parquet_path(exchange: str, symbol: str, datatype: str, day: str) -> Path:
    """Return path for today's parquet file, using _N suffix if file exists from prior run."""
    base_dir = LIVE_PATH / datatype / exchange / symbol
    base_dir.mkdir(parents=True, exist_ok=True)
    base = base_dir / f"{day}.parquet"
    if not base.exists():
        return base
    # mid-day restart: find next available suffix
    n = 2
    while True:
        candidate = base_dir / f"{day}_{n}.parquet"
        if not candidate.exists():
            return candidate
        n += 1


# ── Buffer ────────────────────────────────────────────────────────────────────

class ParquetBuffer:
    """Thread-safe (asyncio) buffer for a single (exchange, symbol, datatype) stream.

    Uses a persistent ParquetWriter per day to append row groups without ever
    reading the existing file back into memory.  The previous approach read the
    full file on every flush → O(n²) memory growth (TZ-046 root cause).
    """

    def __init__(self, exchange: str, symbol: str, datatype: str) -> None:
        self.exchange = exchange
        self.symbol = symbol
        self.datatype = datatype
        self._schema = _SCHEMAS[datatype]
        self._rows: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._current_day = _utc_day()
        self._path = _parquet_path(exchange, symbol, datatype, self._current_day)
        self._writer: pq.ParquetWriter | None = None

    # ── Writer lifecycle ──────────────────────────────────────────────────────

    def _open_writer(self) -> pq.ParquetWriter:
        return pq.ParquetWriter(
            self._path,
            schema=self._schema,
            compression=PARQUET_COMPRESSION,
            compression_level=PARQUET_COMPRESSION_LEVEL,
        )

    def _close_writer(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None

    def close(self) -> None:
        """Flush remaining rows and close the writer. Call on shutdown."""
        if self._rows:
            self._do_flush(self._rows)
            self._rows = []
        self._close_writer()

    def __del__(self) -> None:
        self._close_writer()

    # ── Public interface ──────────────────────────────────────────────────────

    def append(self, row: dict[str, Any]) -> None:
        self._rows.append(row)

    def should_flush(self) -> bool:
        return (
            len(self._rows) >= BUFFER_MAX_EVENTS
            or (time.monotonic() - self._last_flush) >= FLUSH_INTERVAL_S
        )

    def flush(self) -> None:
        """Write accumulated rows to parquet using a persistent streaming writer."""
        if not self._rows:
            self._last_flush = time.monotonic()
            return

        today = _utc_day()
        if today != self._current_day:
            # Day rotated — close old writer, open new file
            self._close_writer()
            self._current_day = today
            self._path = _parquet_path(self.exchange, self.symbol, self.datatype, today)

        rows = self._rows
        self._rows = []
        self._last_flush = time.monotonic()
        self._do_flush(rows)

    def _do_flush(self, rows: list[dict[str, Any]]) -> None:
        try:
            table = pa.Table.from_pylist(rows, schema=self._schema)
            if self._writer is None:
                self._writer = self._open_writer()
            self._writer.write_table(table, row_group_size=PARQUET_ROW_GROUP_SIZE)
            log.debug(
                "flushed %d rows → %s/%s/%s %s",
                len(rows), self.datatype, self.exchange, self.symbol, self._path.name,
            )
        except Exception:
            log.exception(
                "flush error for %s/%s/%s — %d rows dropped",
                self.datatype, self.exchange, self.symbol, len(rows),
            )
            self._close_writer()  # reset on error so next flush opens fresh


def _utc_day() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _fill_missing_columns(table: pa.Table, schema: pa.Schema) -> pa.Table:
    """Add columns present in schema but missing from table, filled with null."""
    for field in schema:
        if field.name not in table.schema.names:
            null_col = pa.array([None] * len(table), type=field.type)
            table = table.append_column(field, null_col)
    return table.select(schema.names)  # reorder to match schema


# ── Registry + flush loop ─────────────────────────────────────────────────────

_registry: dict[tuple[str, str, str], ParquetBuffer] = {}


def get_buffer(exchange: str, symbol: str, datatype: str) -> ParquetBuffer:
    key = (exchange, symbol, datatype)
    if key not in _registry:
        _registry[key] = ParquetBuffer(exchange, symbol, datatype)
    return _registry[key]


async def flush_loop(stop_event: asyncio.Event) -> None:
    """Periodically flush all registered buffers. Runs until stop_event is set."""
    cycle = 0
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=FLUSH_INTERVAL_S)
        except asyncio.TimeoutError:
            pass
        bufs = list(_registry.values())
        for buf in bufs:
            buf.flush()
        cycle += 1
        log.info("heartbeat cycle=%d buffers=%d", cycle, len(bufs))

    # Final flush + close writers on shutdown
    for buf in list(_registry.values()):
        buf.close()
    log.info("flush_loop: final flush complete")
