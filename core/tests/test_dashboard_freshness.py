"""Tests for state_builder freshness layer + stale-handling."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.dashboard.state_builder import (
    _file_age_minutes, _build_freshness, build_state,
)


_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)


# ── _file_age_minutes ────────────────────────────────────────────────────────

def test_file_age_missing_returns_none(tmp_path):
    assert _file_age_minutes(tmp_path / "nope.json", _NOW) is None


def test_file_age_recent(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{}", encoding="utf-8")
    # File mtime is now-ish; should be < 1 min
    age = _file_age_minutes(p, datetime.now(tz=timezone.utc))
    assert age is not None
    assert age < 1


def test_file_age_old(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{}", encoding="utf-8")
    # Set mtime to 1 hour ago via os.utime
    old_time = time.time() - 3600
    os.utime(p, (old_time, old_time))
    age = _file_age_minutes(p, datetime.now(tz=timezone.utc))
    assert age is not None
    assert 55 < age < 65  # ~60 min


# ── _build_freshness levels ──────────────────────────────────────────────────

def test_freshness_all_missing_yields_red(tmp_path):
    out = _build_freshness(
        now=_NOW,
        snapshots_path=tmp_path / "snap.csv",
        latest_forecast_path=tmp_path / "fc.json",
        regime_state_path=tmp_path / "regime.json",
    )
    assert out["level"] == "red"
    assert any("missing" in n for n in out["notes"])


def test_freshness_all_recent_yields_ok(tmp_path):
    for name in ("snap.csv", "fc.json", "regime.json"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    out = _build_freshness(
        now=datetime.now(tz=timezone.utc),
        snapshots_path=tmp_path / "snap.csv",
        latest_forecast_path=tmp_path / "fc.json",
        regime_state_path=tmp_path / "regime.json",
    )
    assert out["level"] == "ok"


def test_freshness_old_snapshots_yields_red(tmp_path):
    snap = tmp_path / "snap.csv"
    snap.write_text("x", encoding="utf-8")
    # 3 hours old
    old_time = time.time() - 3 * 3600
    os.utime(snap, (old_time, old_time))
    out = _build_freshness(
        now=datetime.now(tz=timezone.utc),
        snapshots_path=snap,
        latest_forecast_path=tmp_path / "fc.json",  # missing
        regime_state_path=tmp_path / "regime.json",  # missing
    )
    assert out["level"] == "red"
    assert any("stale" in n.lower() or "tracker" in n for n in out["notes"])


def test_freshness_yellow_when_snapshots_15min(tmp_path):
    snap = tmp_path / "snap.csv"
    fc = tmp_path / "fc.json"
    regime = tmp_path / "regime.json"
    for p in (snap, fc, regime):
        p.write_text("x", encoding="utf-8")
    # Snapshots 15 min old; others recent
    old_time = time.time() - 15 * 60
    os.utime(snap, (old_time, old_time))
    out = _build_freshness(
        now=datetime.now(tz=timezone.utc),
        snapshots_path=snap,
        latest_forecast_path=fc,
        regime_state_path=regime,
    )
    assert out["level"] == "yellow"


def test_freshness_data_source_documented(tmp_path):
    """data_source field documents the v1 live source decision (snapshots.csv)."""
    out = _build_freshness(
        now=_NOW,
        snapshots_path=tmp_path / "snap.csv",
        latest_forecast_path=tmp_path / "fc.json",
        regime_state_path=tmp_path / "regime.json",
    )
    assert "data_source" in out
    assert "snapshots.csv" in out["data_source"]


def test_freshness_corrupted_snapshots_recent_mtime_stays_ok(tmp_path):
    """Corruption test: snapshots.csv exists with fresh mtime but is zero-byte.

    Documented behavior: freshness layer judges by mtime, not content.
    A zero-byte file with recent mtime reports level=ok BUT the downstream
    snapshots reader returns []. This is intentional — the corruption shows
    up downstream as "no positions" rather than as a freshness alert.

    The test exists to pin this behavior so future changes are deliberate.
    """
    snap = tmp_path / "snap.csv"
    snap.write_bytes(b"")  # zero-byte (corruption proxy)
    fc = tmp_path / "fc.json"
    fc.write_text("{}", encoding="utf-8")
    regime = tmp_path / "regime.json"
    regime.write_text("{}", encoding="utf-8")
    out = _build_freshness(
        now=datetime.now(tz=timezone.utc),
        snapshots_path=snap,
        latest_forecast_path=fc,
        regime_state_path=regime,
    )
    # All three files exist with fresh mtime → level stays ok.
    # Content corruption surfaces downstream, not in freshness layer.
    assert out["level"] == "ok"
    # If we wanted content-aware checks, that would be a separate _build_*_health
    # function — out of scope for v1.


def test_freshness_forecast_24h_stale_yields_red(tmp_path):
    snap = tmp_path / "snap.csv"
    fc = tmp_path / "fc.json"
    snap.write_text("x", encoding="utf-8")
    fc.write_text("{}", encoding="utf-8")
    # Forecast 25 hours old
    old_time = time.time() - 25 * 3600
    os.utime(fc, (old_time, old_time))
    out = _build_freshness(
        now=datetime.now(tz=timezone.utc),
        snapshots_path=snap,
        latest_forecast_path=fc,
        regime_state_path=tmp_path / "regime.json",
    )
    assert out["level"] == "red"
    assert any("forecast" in n.lower() for n in out["notes"])


# ── build_state integration ──────────────────────────────────────────────────

def test_build_state_includes_freshness_key(tmp_path):
    empty = tmp_path / "missing.jsonl"
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
    assert "freshness" in state
    assert state["freshness"]["level"] == "red"  # all missing
    assert "ages_min" in state["freshness"]
    assert "data_source" in state["freshness"]
