"""Unified logging configuration for bot7 supervisor.

Format: {timestamp_utc} | {level} | {component} | {message}

Usage:
    from src.utils.logging_config import setup_logging
    logger = setup_logging("supervisor")
"""
from __future__ import annotations

import gzip
import logging
import logging.handlers
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR    = ROOT / "logs"
CURRENT_DIR = LOGS_DIR / "current"
ARCHIVE_DIR = LOGS_DIR / "archive"

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

RETENTION_DAYS = 30


class _UTCFormatter(logging.Formatter):
    converter = datetime.utcfromtimestamp  # type: ignore[assignment]

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.strftime(datefmt or DATE_FORMAT)


def _ensure_dirs() -> None:
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(
    component: str,
    level: int = logging.INFO,
    also_stderr: bool = True,
) -> logging.Logger:
    """Configure root logger for the given component.

    Writes to logs/current/{component}.log.
    Returns logger named after component.
    """
    _ensure_dirs()
    log_path = CURRENT_DIR / f"{component}.log"

    formatter = _UTCFormatter(fmt=LOG_FORMAT)

    # File handler — append mode, no auto-rotation (supervisor handles rotation)
    file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    file_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [file_handler]

    if also_stderr:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in handlers:
        root.addHandler(h)

    return logging.getLogger(component)


# ─────────────────────────────────────────────────────────────────────────────
# Daily rotation (called by supervisor daemon at 00:00 UTC)
# ─────────────────────────────────────────────────────────────────────────────

def rotate_logs(date_str: str | None = None) -> None:
    """Move current/*.log → archive/{date}/*.log.gz, prune old archives."""
    _ensure_dirs()
    if date_str is None:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    dest_dir = ARCHIVE_DIR / date_str
    dest_dir.mkdir(parents=True, exist_ok=True)

    for log_file in CURRENT_DIR.glob("*.log"):
        if log_file.stat().st_size == 0:
            continue
        gz_path = dest_dir / (log_file.name + ".gz")
        with log_file.open("rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        # Truncate (don't delete — handlers may still be open)
        log_file.write_text("", encoding="utf-8")

    _prune_archive()


def _prune_archive() -> None:
    """Delete archive subdirs older than RETENTION_DAYS."""
    cutoff = datetime.now(tz=timezone.utc)
    for day_dir in ARCHIVE_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        try:
            dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_days = (cutoff - dir_date).days
            if age_days > RETENTION_DAYS:
                shutil.rmtree(day_dir)
        except ValueError:
            pass
