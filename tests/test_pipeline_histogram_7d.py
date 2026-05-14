"""Tests for pipeline_histogram_7d."""
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
        "histo", ROOT / "scripts" / "pipeline_histogram_7d.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["histo"] = m
    spec.loader.exec_module(m)
    return m


def test_read_all_sources_filters_old(mod, tmp_path, monkeypatch):
    p = tmp_path / "pipeline_metrics.jsonl"
    monkeypatch.setattr(mod, "METRICS", p)
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    stale = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    lines = [
        json.dumps({"ts": fresh, "stage_outcome": "emitted"}),
        json.dumps({"ts": stale, "stage_outcome": "emitted"}),
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    out = mod._read_all_sources(7)
    assert len(out) == 1
    assert "_date" in out[0]


def test_read_all_sources_combines_archives(mod, tmp_path, monkeypatch):
    """Current + rotated archives both read."""
    main = tmp_path / "pipeline_metrics.jsonl"
    arch = tmp_path / "pipeline_metrics_2026-05-10.jsonl"
    monkeypatch.setattr(mod, "METRICS", main)
    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    ts2 = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    main.write_text(json.dumps({"ts": ts1, "stage_outcome": "emitted"}) + "\n",
                     encoding="utf-8")
    arch.write_text(json.dumps({"ts": ts2, "stage_outcome": "combo_blocked"}) + "\n",
                     encoding="utf-8")
    out = mod._read_all_sources(7)
    assert len(out) == 2
    outcomes = {o["stage_outcome"] for o in out}
    assert outcomes == {"emitted", "combo_blocked"}


def test_read_all_sources_missing_file(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "METRICS", tmp_path / "absent.jsonl")
    assert mod._read_all_sources(7) == []
