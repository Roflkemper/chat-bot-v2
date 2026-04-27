"""Feature manifest: hash-based stale detection for pipeline partitions.

Manifest tracks:
  - engine_hash: SHA256 of all feature module source files
  - params_hash: SHA256 of pipeline parameters (symbols, date range, etc.)
  - partition_dates: set of UTC date strings that are up to date

If engine_hash or params_hash changes, ALL partitions are marked stale.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MODULE_FILES = [
    "calendar.py",
    "killzones.py",
    "dwm.py",
    "technical.py",
    "derivatives.py",
    "cross_asset.py",
    "pipeline.py",
]

_MANIFEST_FILENAME = "manifest.json"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except FileNotFoundError:
        h.update(b"<missing>")
    return h.hexdigest()


def _compute_engine_hash(features_dir: Path) -> str:
    h = hashlib.sha256()
    for name in _MODULE_FILES:
        file_hash = _hash_file(features_dir / name)
        h.update(f"{name}:{file_hash}\n".encode())
    return h.hexdigest()


def _compute_params_hash(params: dict) -> str:
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


class Manifest:
    """Tracks which feature partitions are up to date."""

    def __init__(self, output_dir: Path, features_dir: Path, params: dict):
        self._path = output_dir / _MANIFEST_FILENAME
        self._engine_hash = _compute_engine_hash(features_dir)
        self._params_hash = _compute_params_hash(params)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt manifest, resetting: %s", self._path)
        return {}

    def _hashes_match(self) -> bool:
        return (
            self._data.get("engine_hash") == self._engine_hash
            and self._data.get("params_hash") == self._params_hash
        )

    def is_fresh(self, symbol: str, date_str: str, parquet_path: "Path | None" = None) -> bool:
        """Return True if partition for (symbol, date_str) is up to date and file exists."""
        if not self._hashes_match():
            return False
        in_manifest = date_str in self._data.get("partitions", {}).get(symbol, set())
        if not in_manifest:
            return False
        if parquet_path is not None and not parquet_path.exists():
            return False
        return True

    def mark_done(self, symbol: str, date_str: str) -> None:
        """Record that partition (symbol, date_str) is built."""
        if not self._hashes_match():
            self._data = {
                "engine_hash": self._engine_hash,
                "params_hash": self._params_hash,
                "partitions": {},
            }
        parts = self._data.setdefault("partitions", {})
        parts.setdefault(symbol, [])
        if date_str not in parts[symbol]:
            parts[symbol].append(date_str)
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, default=list), encoding="utf-8"
        )

    def invalidate(self) -> None:
        """Force all partitions stale (e.g. force_rebuild flag)."""
        self._data = {}
        if self._path.exists():
            self._path.unlink()
        logger.info("Manifest invalidated — full rebuild required")
