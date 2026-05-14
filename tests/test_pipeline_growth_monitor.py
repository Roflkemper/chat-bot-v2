"""Tests for pipeline_growth_monitor."""
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
        "growth", ROOT / "scripts" / "pipeline_growth_monitor.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["growth"] = m
    spec.loader.exec_module(m)
    return m


def test_read_checkpoints_handles_missing(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "GROWTH_LOG", tmp_path / "absent.jsonl")
    assert mod._read_checkpoints() == []


def test_read_checkpoints_skips_bad_lines(mod, tmp_path, monkeypatch):
    p = tmp_path / "log.jsonl"
    p.write_text('{"ts":"2026-05-11T00:00:00Z","size_bytes":1000}\nbad json\n',
                  encoding="utf-8")
    monkeypatch.setattr(mod, "GROWTH_LOG", p)
    out = mod._read_checkpoints()
    assert len(out) == 1
    assert out[0]["size_bytes"] == 1000


def test_append_checkpoint(mod, tmp_path, monkeypatch):
    p = tmp_path / "log.jsonl"
    monkeypatch.setattr(mod, "GROWTH_LOG", p)
    mod._append_checkpoint({"ts": "x", "size_bytes": 100})
    mod._append_checkpoint({"ts": "y", "size_bytes": 200})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["size_bytes"] == 100
