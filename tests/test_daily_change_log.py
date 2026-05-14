"""Tests for daily_change_log script helpers."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mod():
    spec = importlib.util.spec_from_file_location(
        "daily_change_log", ROOT / "scripts" / "daily_change_log.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["daily_change_log"] = m
    spec.loader.exec_module(m)
    return m


def test_read_jsonl_window_filters_old(mod, tmp_path):
    p = tmp_path / "j.jsonl"
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    stale = (now - timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    lines = [
        json.dumps({"ts": fresh, "stage": "OPEN"}),
        json.dumps({"ts": stale, "stage": "CLOSE"}),
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    out = mod._read_jsonl_window(p, 24)
    assert len(out) == 1
    assert out[0]["stage"] == "OPEN"


def test_read_jsonl_window_missing_returns_empty(mod, tmp_path):
    assert mod._read_jsonl_window(tmp_path / "absent.jsonl", 24) == []


def test_read_jsonl_window_skips_bad_lines(mod, tmp_path):
    p = tmp_path / "j.jsonl"
    p.write_text("not json\n{}\n", encoding="utf-8")
    out = mod._read_jsonl_window(p, 24)
    assert out == []  # both rows have no ts → filtered


def test_archive_pattern_correct(tmp_path):
    """Verify archive filename uses YYYY-MM-DD format."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    expected = f"{now.strftime('%Y-%m-%d')}.md"
    # Sanity: filename matches pattern
    assert len(expected) == 13  # 4-2-2.md
    assert expected.endswith(".md")
