"""Tests for dashboard state_builder regime/forecast/virtual_trader sections."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.dashboard.state_builder import (
    _brier_band,
    _build_regime,
    _build_forecast,
    _build_virtual_trader,
    build_state,
)


# ── _brier_band classification ────────────────────────────────────────────────

def test_brier_band_green():
    assert _brier_band(0.18) == "green"
    assert _brier_band(0.22) == "green"


def test_brier_band_yellow():
    assert _brier_band(0.23) == "yellow"
    assert _brier_band(0.265) == "yellow"


def test_brier_band_red():
    assert _brier_band(0.28) == "red"
    assert _brier_band(0.40) == "red"


def test_brier_band_qualitative_when_none():
    assert _brier_band(None) == "qualitative"


# ── _build_regime ─────────────────────────────────────────────────────────────

def test_build_regime_empty():
    out = _build_regime({})
    assert out["label"] is None
    assert "note" in out


def test_build_regime_full():
    out = _build_regime({
        "regime": "MARKDOWN", "regime_confidence": 0.85, "regime_stability": 0.80,
        "bars_in_current_regime": 14, "candidate_regime": None, "candidate_bars": 0,
        "updated_at": "2026-05-05T10:00:00Z",
    })
    assert out["label"] == "MARKDOWN"
    assert out["confidence"] == 0.85
    assert out["stable_bars"] == 14
    assert out["switch_pending"] is False


def test_build_regime_pending_switch():
    out = _build_regime({
        "regime": "RANGE", "regime_confidence": 0.6, "regime_stability": 0.7,
        "bars_in_current_regime": 5, "candidate_regime": "MARKDOWN", "candidate_bars": 8,
        "updated_at": "2026-05-05T10:00:00Z",
    })
    assert out["switch_pending"] is True
    assert out["candidate_regime"] == "MARKDOWN"


# ── _build_forecast ───────────────────────────────────────────────────────────

def test_forecast_live_source_passes_through():
    live = {
        "regime": "MARKDOWN", "bar_time": "2026-05-05T10:00:00Z",
        "horizons": {
            "1h": {"mode": "numeric", "value": 0.42, "brier": 0.20},
            "4h": {"mode": "numeric", "value": 0.45, "brier": 0.23},
            "1d": {"mode": "qualitative", "value": "lean_down", "brier": 0.28, "caveat": "qual per matrix"},
        },
    }
    out = _build_forecast(live, regime="MARKDOWN")
    assert out["source"] == "live"
    assert out["horizons"]["1h"]["band"] == "green"      # 0.20 ≤ 0.22
    assert out["horizons"]["4h"]["band"] == "yellow"     # 0.23
    assert out["horizons"]["1d"]["band"] == "qualitative"  # mode → qualitative


def test_forecast_falls_back_to_cv_matrix():
    out = _build_forecast({}, regime="MARKDOWN")
    assert out["source"] == "cv_matrix"
    # MARKDOWN-1h mean Brier 0.2042 → green band (≤0.22)
    assert out["horizons"]["1h"]["mode"] == "numeric"
    assert out["horizons"]["1h"]["band"] == "green"
    # MARKDOWN-1d is qualitative per matrix
    assert out["horizons"]["1d"]["mode"] == "qualitative"
    assert out["horizons"]["1d"]["band"] == "qualitative"


def test_forecast_markup_1d_is_gated():
    out = _build_forecast({}, regime="MARKUP")
    assert out["horizons"]["1d"]["mode"] == "gated"
    assert "regime_stability" in out["horizons"]["1d"]["caveat"]


def test_forecast_no_regime_returns_qualitative():
    out = _build_forecast({}, regime=None)
    for hz in ("1h", "4h", "1d"):
        assert out["horizons"][hz]["mode"] == "qualitative"


# ── _build_virtual_trader ─────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)


def test_vt_empty():
    out = _build_virtual_trader([], _now())
    assert out["signals_7d"] == 0
    assert out["win_rate_pct"] is None


def test_vt_aggregates_decided_only():
    rows = [
        # win
        {"position_id": "p1", "entry_time": (_now() - timedelta(days=1)).isoformat(),
         "status": "closed_tp2", "r_realized": 2.25},
        # loss
        {"position_id": "p2", "entry_time": (_now() - timedelta(days=2)).isoformat(),
         "status": "closed_sl", "r_realized": -1.0},
        # open
        {"position_id": "p3", "entry_time": (_now() - timedelta(hours=2)).isoformat(),
         "status": "open", "direction": "long", "entry_price": 67000,
         "sl": 66640, "tp1": 67540, "tp2": 68080, "half_closed": False},
        # too old (8 days) — excluded
        {"position_id": "p4", "entry_time": (_now() - timedelta(days=8)).isoformat(),
         "status": "closed_tp2", "r_realized": 3.0},
    ]
    out = _build_virtual_trader(rows, _now())
    assert out["wins"] == 1
    assert out["losses"] == 1
    assert out["open"] == 1
    assert out["signals_7d"] == 3
    assert out["win_rate_pct"] == 50.0
    assert abs(out["avg_rr"] - 0.62) < 1e-3  # (2.25 + -1.0) / 2 rounded to 2 dp
    assert len(out["open_positions"]) == 1
    assert out["open_positions"][0]["direction"] == "long"


def test_vt_only_latest_record_per_position():
    """Same position_id appearing twice (open then closed) counts only the latest."""
    rows = [
        {"position_id": "p1", "entry_time": (_now() - timedelta(days=1)).isoformat(),
         "status": "open"},
        {"position_id": "p1", "entry_time": (_now() - timedelta(days=1)).isoformat(),
         "status": "closed_tp2", "r_realized": 1.5},
    ]
    out = _build_virtual_trader(rows, _now())
    assert out["wins"] == 1
    assert out["open"] == 0


# ── build_state integration ───────────────────────────────────────────────────

def test_build_state_includes_new_keys(tmp_path):
    """build_state returns regime/forecast/virtual_trader keys even with empty inputs."""
    empty = tmp_path / "missing.jsonl"  # doesn't exist
    state = build_state(
        snapshots_path=empty,
        state_latest_path=empty,
        signals_path=empty,
        null_signals_path=empty,
        events_path=empty,
        liq_path=empty,
        competition_path=empty,
        engine_path=empty,
        regime_state_path=empty,
        latest_forecast_path=empty,
        virtual_trader_log_path=empty,
    )
    assert "regime" in state
    assert "forecast" in state
    assert "virtual_trader" in state
    # All-empty inputs → graceful nulls
    assert state["regime"]["label"] is None
    assert state["forecast"]["source"] == "cv_matrix"  # fallback path even when regime is None


def test_build_state_with_live_files(tmp_path):
    # Write small live files
    regime_file = tmp_path / "switcher.json"
    regime_file.write_text(json.dumps({
        "regime": "MARKDOWN", "regime_confidence": 0.9, "regime_stability": 0.85,
        "bars_in_current_regime": 20, "candidate_regime": None, "candidate_bars": 0,
        "updated_at": "2026-05-05T10:00:00Z",
    }), encoding="utf-8")
    forecast_file = tmp_path / "forecast.json"
    forecast_file.write_text(json.dumps({
        "regime": "MARKDOWN",
        "horizons": {
            "1h": {"mode": "numeric", "value": 0.40, "brier": 0.20},
            "4h": {"mode": "numeric", "value": 0.43, "brier": 0.23},
            "1d": {"mode": "qualitative", "value": "lean_down", "brier": 0.28},
        },
    }), encoding="utf-8")
    empty = tmp_path / "missing.jsonl"
    state = build_state(
        snapshots_path=empty, state_latest_path=empty, signals_path=empty,
        null_signals_path=empty, events_path=empty, liq_path=empty,
        competition_path=empty, engine_path=empty,
        regime_state_path=regime_file,
        latest_forecast_path=forecast_file,
        virtual_trader_log_path=empty,
    )
    assert state["regime"]["label"] == "MARKDOWN"
    assert state["forecast"]["source"] == "live"
    assert state["forecast"]["horizons"]["1h"]["band"] == "green"
    assert state["forecast"]["horizons"]["1d"]["band"] == "qualitative"
