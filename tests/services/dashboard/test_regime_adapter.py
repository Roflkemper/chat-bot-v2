"""Tests for services.dashboard.regime_adapter.

Covers:
- All 6 Classifier A primary states → 3-state projection.
- Confidence formula edge cases.
- Stability formula edge cases.
- pending_primary projection (None / valid / unknown).
- Missing / corrupted / empty file handling.
- Live snapshot regression on a state/regime_state.json shape.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from services.dashboard.regime_adapter import (
    HYSTERESIS_THRESHOLD,
    STABILITY_SATURATION,
    _PRIMARY_TO_3STATE,
    _compute_confidence,
    _compute_stability,
    adapt_regime_state,
)


def _write_state(path: Path, btc: dict, *, version: int = 1) -> None:
    payload = {
        "version": version,
        "manual_blackout_until": None,
        "symbols": {"BTCUSDT": btc},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _btc_state(
    *,
    primary: str = "RANGE",
    primary_since: str = "2026-05-06T05:39:10.658814Z",
    age: int = 25,
    pending: str | None = None,
    counter: int = 0,
) -> dict:
    return {
        "current_primary": primary,
        "primary_since": primary_since,
        "regime_age_bars": age,
        "pending_primary": pending,
        "hysteresis_counter": counter,
        "active_modifiers": {},
        "atr_history_1h": [],
        "bb_width_history_1h": [],
    }


# ── Projection: all 6 primary states ────────────────────────────────────────


@pytest.mark.parametrize(
    "primary, expected_3state",
    [
        ("TREND_UP", "MARKUP"),
        ("CASCADE_UP", "MARKUP"),
        ("TREND_DOWN", "MARKDOWN"),
        ("CASCADE_DOWN", "MARKDOWN"),
        ("RANGE", "RANGE"),
        ("COMPRESSION", "RANGE"),
    ],
)
def test_primary_projection_all_six(tmp_path: Path, primary: str, expected_3state: str) -> None:
    p = tmp_path / "regime_state.json"
    _write_state(p, _btc_state(primary=primary))
    out = adapt_regime_state(path=p)
    assert out is not None
    assert out["regime"] == expected_3state


def test_projection_table_matches_classifier_authority_v1() -> None:
    """All 6 Classifier A primary states must have a projection per §1."""
    expected_keys = {"TREND_UP", "CASCADE_UP", "TREND_DOWN", "CASCADE_DOWN", "RANGE", "COMPRESSION"}
    assert set(_PRIMARY_TO_3STATE.keys()) == expected_keys


def test_unknown_primary_returns_none(tmp_path: Path) -> None:
    """Don't silently mislabel unknown states."""
    p = tmp_path / "regime_state.json"
    _write_state(p, _btc_state(primary="UNKNOWN_STATE"))
    assert adapt_regime_state(path=p) is None


# ── Confidence formula ──────────────────────────────────────────────────────


def test_confidence_no_pending_is_one() -> None:
    """No pending transition → fully confirmed regime → confidence = 1.0."""
    assert _compute_confidence(0, None) == 1.0
    assert _compute_confidence(5, None) == 1.0


def test_confidence_pending_counter_zero() -> None:
    assert _compute_confidence(0, "TREND_UP") == 0.0


def test_confidence_pending_counter_at_threshold() -> None:
    assert _compute_confidence(HYSTERESIS_THRESHOLD, "TREND_UP") == 1.0


def test_confidence_pending_counter_below_threshold() -> None:
    """counter=1 with threshold=2 → 0.5."""
    assert _compute_confidence(1, "TREND_UP") == 0.5


def test_confidence_pending_counter_above_threshold_clamped() -> None:
    assert _compute_confidence(HYSTERESIS_THRESHOLD * 5, "TREND_UP") == 1.0


# ── Stability formula ───────────────────────────────────────────────────────


def test_stability_age_zero() -> None:
    assert _compute_stability(0) == 0.0


def test_stability_age_at_saturation() -> None:
    assert _compute_stability(STABILITY_SATURATION) == 1.0


def test_stability_age_below_saturation() -> None:
    assert _compute_stability(STABILITY_SATURATION // 2) == 0.5


def test_stability_age_above_saturation_clamped() -> None:
    assert _compute_stability(STABILITY_SATURATION * 10) == 1.0


def test_stability_negative_age_floored() -> None:
    assert _compute_stability(-5) == 0.0


# ── Pending state projection ────────────────────────────────────────────────


def test_pending_none_yields_none_candidate(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    _write_state(p, _btc_state(pending=None))
    out = adapt_regime_state(path=p)
    assert out is not None
    assert out["candidate_regime"] is None


def test_pending_projected_to_3state(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    _write_state(p, _btc_state(primary="RANGE", pending="TREND_DOWN", counter=1))
    out = adapt_regime_state(path=p)
    assert out is not None
    assert out["candidate_regime"] == "MARKDOWN"
    assert out["candidate_bars"] == 1
    # Confidence reflects pending (mid-confirmation)
    assert out["regime_confidence"] == 0.5


# ── Missing / corrupted file handling ───────────────────────────────────────


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert adapt_regime_state(path=tmp_path / "does_not_exist.json") is None


def test_corrupted_file_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert adapt_regime_state(path=p) is None


def test_empty_symbols_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    p.write_text(json.dumps({"version": 1, "symbols": {}}), encoding="utf-8")
    assert adapt_regime_state(path=p) is None


def test_missing_symbol_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    _write_state(p, _btc_state())
    assert adapt_regime_state(path=p, symbol="XRPUSDT") is None


# ── bar_time / updated_at ───────────────────────────────────────────────────


def test_bar_time_normalized_to_z_form(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    _write_state(p, _btc_state(primary_since="2026-05-06T05:39:10.658814Z"))
    out = adapt_regime_state(path=p)
    assert out is not None
    # Sub-second precision dropped, Z suffix preserved
    assert out["bar_time"] == "2026-05-06T05:39:10Z"


def test_updated_at_picks_newer_of_primary_since_and_mtime(tmp_path: Path) -> None:
    p = tmp_path / "regime_state.json"
    # primary_since old, file mtime fresh — updated_at should reflect mtime
    _write_state(p, _btc_state(primary_since="2020-01-01T00:00:00Z"))
    out = adapt_regime_state(path=p)
    assert out is not None
    # mtime is "now-ish" so newer than 2020 — exact compare not feasible, just
    # assert it's not the old primary_since
    assert out["updated_at"] != "2020-01-01T00:00:00Z"


# ── Live-shape snapshot test ────────────────────────────────────────────────


def test_live_snapshot_compression_projects_to_range(tmp_path: Path) -> None:
    """Mirrors the CP report finding: COMPRESSION primary, age=25, no pending."""
    p = tmp_path / "regime_state.json"
    _write_state(
        p,
        _btc_state(
            primary="COMPRESSION",
            primary_since="2026-05-06T05:39:10.658814Z",
            age=25,
            pending=None,
            counter=0,
        ),
    )
    out = adapt_regime_state(path=p)
    assert out is not None
    assert out["regime"] == "RANGE"
    assert out["regime_confidence"] == 1.0  # no pending, fully confirmed
    assert out["regime_stability"] == 1.0   # age 25 >> saturation 12
    assert out["bars_in_current_regime"] == 25
    assert out["candidate_regime"] is None
    assert out["candidate_bars"] == 0
