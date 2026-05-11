"""Tests for daily_kpi_report._compute_alerts.

Verifies all 5 alert paths fire correctly so we don't lose them to
silent regressions.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def kpi_module():
    spec = importlib.util.spec_from_file_location(
        "kpi", ROOT / "scripts" / "daily_kpi_report.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kpi"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


def test_alert_zero_pipeline_events_critical(kpi_module, now):
    alerts = kpi_module._compute_alerts([], [], [], now)
    assert any("CRIT" in a and "0 pipeline events" in a for a in alerts)


def test_alert_zero_emitted_setups(kpi_module, now):
    metrics = [{"stage_outcome": "combo_blocked"}] * 10
    alerts = kpi_module._compute_alerts(metrics, [], [], now)
    assert any("0 setups emitted" in a for a in alerts)


def test_alert_quiet_market_info(kpi_module, now):
    metrics = [{"stage_outcome": "emitted"}] * 2
    alerts = kpi_module._compute_alerts(metrics, [], [], now)
    assert any("[INFO]" in a and "2 setup" in a for a in alerts)


def test_alert_bug_many_detector_failures(kpi_module, now):
    metrics = (
        [{"stage_outcome": "detector_failed", "drop_reason": "detect_X"}] * 15
        + [{"stage_outcome": "emitted"}] * 5
    )
    alerts = kpi_module._compute_alerts(metrics, [], [], now)
    assert any("[BUG]" in a and "15 detector exceptions" in a for a in alerts)


def test_alert_p15_dd_age(kpi_module, now):
    legs = [
        {"pair": "BTCUSDT", "direction": "long", "alert": True,
         "dd_pct": 2.5, "age_h": 30.0}
    ]
    metrics = [{"stage_outcome": "emitted"}] * 10
    alerts = kpi_module._compute_alerts(metrics, [], legs, now)
    assert any("[P15]" in a and "BTCUSDT" in a and "manual close" in a for a in alerts)


def test_alert_p15_significant_loss(kpi_module, now):
    metrics = [{"stage_outcome": "emitted"}] * 10
    events = [{"realized_pnl_usd": -60.0}]
    alerts = kpi_module._compute_alerts(metrics, events, [], now)
    assert any("[P15]" in a and "$-60.00" in a for a in alerts)


def test_alert_no_false_positive_when_healthy(kpi_module, now):
    """Healthy: 5+ emits, no failures, no DD legs, positive PnL."""
    metrics = [{"stage_outcome": "emitted"}] * 10
    events = [{"realized_pnl_usd": 10.0}, {"realized_pnl_usd": 5.0}]
    legs = [{"pair": "BTCUSDT", "direction": "long", "alert": False,
             "dd_pct": 0.3, "age_h": 1.0}]
    alerts = kpi_module._compute_alerts(metrics, events, legs, now)
    assert alerts == [], f"Expected no alerts on healthy state, got: {alerts}"
