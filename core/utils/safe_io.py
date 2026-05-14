from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from contextlib import contextmanager
from typing import Any, Dict

_logger = logging.getLogger(__name__)
_file_locks: dict[str, threading.RLock] = {}
_registry_lock = threading.Lock()


def _normalize_path(path: str) -> str:
    return os.path.abspath(path)


def _get_lock(path: str) -> threading.RLock:
    normalized = _normalize_path(path)
    with _registry_lock:
        lock = _file_locks.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _file_locks[normalized] = lock
        return lock


@contextmanager
def locked_file(path: str):
    lock = _get_lock(path)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(_normalize_path(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    normalized = _normalize_path(path)
    ensure_parent_dir(normalized)
    with locked_file(normalized):
        fd, temp_path = tempfile.mkstemp(prefix='.tmp_', suffix='.json', dir=os.path.dirname(normalized) or None)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, normalized)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def safe_read_json(path: str, default: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_path(path)
    if not os.path.exists(normalized):
        return dict(default)
    with locked_file(normalized):
        try:
            with open(normalized, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                base = dict(default)
                base.update(payload)
                return base
            _logger.warning('JSON in %s is not a dict, using defaults', normalized)
            return dict(default)
        except Exception as exc:
            _logger.exception('Failed to read JSON from %s: %s', normalized, exc)
            return dict(default)
