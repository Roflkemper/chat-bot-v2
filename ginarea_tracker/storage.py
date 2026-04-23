"""Append-only CSV writers for snapshots, events, and params.

Schema version = 2.  If an existing file has a different header,
a new file with suffix _v{N}.csv is created instead.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

SNAPSHOTS_HEADERS: list[str] = [
    "ts_utc", "bot_id", "bot_name", "alias", "status", "position", "profit", "current_profit",
    "in_filled_count", "in_filled_qty", "out_filled_count", "out_filled_qty",
    "trigger_count", "trigger_qty", "average_price", "trade_volume",
    "balance", "liquidation_price", "stat_updated_at", "schema_version",
]

EVENTS_HEADERS: list[str] = [
    "ts_utc", "bot_id", "bot_name", "event_type", "delta_count", "delta_qty",
    "price_last", "position_after", "profit_after", "schema_version",
]

PARAMS_HEADERS: list[str] = [
    "ts_utc", "bot_id", "bot_name", "strategy_id", "side", "grid_step", "grid_step_ratio",
    "max_opened_orders", "border_top", "border_bottom", "instop", "minstop", "maxstop",
    "target", "total_sl", "total_tp", "raw_params_json", "schema_version",
]


def _read_header(path: Path) -> list[str] | None:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return next(csv.reader(fh), None)
    except OSError:
        return None


def _resolve_path(base: Path, headers: list[str]) -> Path:
    """Return the CSV path to append to, creating a versioned file if schema differs."""
    if not base.exists():
        return base

    if _read_header(base) == headers:
        return base

    # Schema mismatch: find or create _v{N}.csv
    n = 2
    while True:
        candidate = base.parent / f"{base.stem}_v{n}{base.suffix}"
        if not candidate.exists():
            return candidate
        if _read_header(candidate) == headers:
            return candidate
        n += 1


class CsvWriter:
    def __init__(self, base_path: Path, headers: list[str]) -> None:
        self._headers = headers
        self._path = _resolve_path(base_path, headers)
        is_new = not self._path.exists()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if is_new:
            self._writer.writerow(headers)
            self._file.flush()

    @property
    def path(self) -> Path:
        return self._path

    def write(self, row: dict) -> None:
        self._writer.writerow([row.get(h, "") for h in self._headers])
        self._file.flush()

    def close(self) -> None:
        self._file.close()


class StorageManager:
    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots = CsvWriter(output_dir / "snapshots.csv", SNAPSHOTS_HEADERS)
        self.events = CsvWriter(output_dir / "events.csv", EVENTS_HEADERS)
        self.params = CsvWriter(output_dir / "params.csv", PARAMS_HEADERS)
        logger.info(
            "Storage opened: %s | %s | %s",
            self.snapshots.path.name, self.events.path.name, self.params.path.name,
        )

    def write_snapshot(self, row: dict) -> None:
        row["schema_version"] = SCHEMA_VERSION
        self.snapshots.write(row)

    def write_event(self, row: dict) -> None:
        row["schema_version"] = SCHEMA_VERSION
        self.events.write(row)

    def write_params(self, row: dict) -> None:
        row["schema_version"] = SCHEMA_VERSION
        self.params.write(row)

    def close(self) -> None:
        for writer in (self.snapshots, self.events, self.params):
            try:
                writer.close()
            except Exception as exc:
                logger.warning("Error closing writer %s: %s", writer.path, exc)
