"""Tests for watchdog audit log helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "watchdog_mod", ROOT / "scripts" / "watchdog.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["watchdog_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_extract_int_pid():
    mod = _load()
    assert mod._extract_int("alive pid=12345 age=0.5min", "pid=") == 12345


def test_extract_int_old_pid():
    mod = _load()
    assert mod._extract_int("REVIVED old=111 new=222", "old=") == 111


def test_extract_int_new_pid():
    mod = _load()
    assert mod._extract_int("REVIVED old=111 new=222", "new=") == 222


def test_extract_int_missing_prefix():
    mod = _load()
    assert mod._extract_int("alive pid=123", "old=") is None


def test_extract_int_no_digits():
    mod = _load()
    assert mod._extract_int("pid=", "pid=") is None
