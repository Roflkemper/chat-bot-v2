"""Tests for pipeline_analyzer."""
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
        "pipeline_analyzer", ROOT / "scripts" / "pipeline_analyzer.py",
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_analyzer"] = m
    spec.loader.exec_module(m)
    return m


def test_analyze_counts_emit_and_drops(mod):
    metrics = [
        {"stage_outcome": "emitted", "setup_type": "X"},
        {"stage_outcome": "emitted", "setup_type": "X"},
        {"stage_outcome": "combo_blocked", "setup_type": "X"},
        {"stage_outcome": "semantic_dedup_skip", "setup_type": "X"},
        {"stage_outcome": "combo_blocked", "setup_type": "Y"},
    ]
    per_det, totals, n = mod._analyze(metrics)
    assert n == 5
    assert per_det["X"]["fired"] == 4
    assert per_det["X"]["emit"] == 2
    assert per_det["X"]["combo"] == 1
    assert per_det["X"]["dedup"] == 1
    assert per_det["Y"]["fired"] == 1
    assert per_det["Y"]["combo"] == 1
    assert totals["emitted"] == 2


def test_env_disabled_attributed_via_drop_reason(mod):
    """env_disabled events lack setup_type but carry detect_<name> in drop_reason."""
    metrics = [
        {"stage_outcome": "env_disabled", "drop_reason": "detect_short_pdh_rejection"},
        {"stage_outcome": "env_disabled", "drop_reason": "detect_short_pdh_rejection"},
    ]
    per_det, _, _ = mod._analyze(metrics)
    assert per_det["short_pdh_rejection"]["fired"] == 2
    assert per_det["short_pdh_rejection"]["env_dis"] == 2


def test_format_table_renders_basic_rows(mod):
    per_det = {
        "long_dump_reversal": {
            "fired": 100, "strength": 50, "combo": 40, "env_dis": 0,
            "dedup": 8, "gc_blk": 0, "emit": 2,
        }
    }
    text = mod._format_table(per_det)
    assert "long_dump_reversal" in text
    assert "100" in text
    assert "2.0" in text  # yield%


def test_yield_zero_safe_on_empty_fired(mod):
    per_det = {"Z": {"fired": 0, "strength": 0, "combo": 0,
                     "env_dis": 0, "dedup": 0, "gc_blk": 0, "emit": 0}}
    text = mod._format_table(per_det)
    assert "Z" in text
    assert "0.0" in text
