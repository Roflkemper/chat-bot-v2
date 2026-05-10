"""Tests for pipeline_metrics: structured drop tracking."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.setup_detector import pipeline_metrics
from services.setup_detector.models import SetupBasis, SetupType, make_setup


@pytest.fixture
def temp_metrics_path(tmp_path, monkeypatch):
    p = tmp_path / "pipeline_metrics.jsonl"
    monkeypatch.setattr(pipeline_metrics, "_METRICS_PATH", p)
    return p


def test_record_writes_jsonl(temp_metrics_path):
    pipeline_metrics.record(stage_outcome="emitted", pair="BTCUSDT",
                            setup_type="long_pdl_bounce")
    lines = temp_metrics_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["stage_outcome"] == "emitted"
    assert obj["pair"] == "BTCUSDT"
    assert obj["setup_type"] == "long_pdl_bounce"
    assert "ts" in obj


def test_record_omits_none_fields(temp_metrics_path):
    pipeline_metrics.record(stage_outcome="combo_blocked")
    obj = json.loads(temp_metrics_path.read_text(encoding="utf-8").strip())
    assert obj["stage_outcome"] == "combo_blocked"
    assert "pair" not in obj
    assert "drop_reason" not in obj


def test_record_setup_extracts_fields(temp_metrics_path):
    setup = make_setup(
        setup_type=SetupType.LONG_PDL_BOUNCE,
        pair="BTCUSDT", current_price=80000.0,
        regime_label="trend_down", session_label="asia",
        entry_price=80000.0, stop_price=79500.0,
        tp1_price=80500.0, tp2_price=81000.0, risk_reward=1.0,
        strength=9, confidence_pct=70.0,
        basis=(SetupBasis(label="rsi", value=30.0, weight=1.0),),
        cancel_conditions=(), window_minutes=120,
    )
    pipeline_metrics.record_setup(setup, "emitted")
    obj = json.loads(temp_metrics_path.read_text(encoding="utf-8").strip())
    assert obj["pair"] == "BTCUSDT"
    assert obj["setup_type"] == "long_pdl_bounce"
    assert obj["side"] == "long"
    assert obj["regime"] == "trend_down"
    assert obj["session"] == "asia"
    assert obj["strength"] == 9
    assert obj["confidence"] == 70.0


def test_record_setup_short_side(temp_metrics_path):
    setup = make_setup(
        setup_type=SetupType.SHORT_PDH_REJECTION,
        pair="BTCUSDT", current_price=80000.0,
        regime_label="trend_up", session_label="ny_am",
        entry_price=80000.0, stop_price=80500.0,
        tp1_price=79500.0, tp2_price=79000.0, risk_reward=1.0,
        strength=9, confidence_pct=72.0,
        basis=(SetupBasis(label="rsi", value=72.0, weight=1.0),),
        cancel_conditions=(), window_minutes=240,
    )
    pipeline_metrics.record_setup(setup, "gc_blocked", drop_reason="misaligned-blocked")
    obj = json.loads(temp_metrics_path.read_text(encoding="utf-8").strip())
    assert obj["side"] == "short"
    assert obj["drop_reason"] == "misaligned-blocked"


def test_record_with_extra(temp_metrics_path):
    pipeline_metrics.record(stage_outcome="gc_blocked",
                            extra={"gc_upside": 4, "gc_downside": 0})
    obj = json.loads(temp_metrics_path.read_text(encoding="utf-8").strip())
    assert obj["gc_upside"] == 4
    assert obj["gc_downside"] == 0


def test_record_swallows_oserror(temp_metrics_path, monkeypatch):
    """Pipeline metrics writes are best-effort — never raise into the loop."""
    def _broken_open(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(Path, "open", _broken_open)
    # Should not raise
    pipeline_metrics.record(stage_outcome="emitted")
