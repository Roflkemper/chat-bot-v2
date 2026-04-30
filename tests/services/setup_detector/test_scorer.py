from __future__ import annotations

import pytest

from services.setup_detector.models import SetupBasis, SetupType
from services.setup_detector.scorer import compute_confidence, compute_strength


def _basis(*weights: float) -> tuple[SetupBasis, ...]:
    return tuple(SetupBasis(label=f"b{i}", value=float(i), weight=w) for i, w in enumerate(weights))


# ── compute_strength ──────────────────────────────────────────────────────────

def test_compute_strength_full_basis() -> None:
    basis = _basis(1.0, 1.0, 1.0, 1.0, 1.0)
    assert compute_strength(basis) == 10


def test_compute_strength_partial() -> None:
    basis = _basis(0.5, 0.5, 0.5)
    strength = compute_strength(basis)
    assert strength == 5


def test_compute_strength_empty_returns_one() -> None:
    assert compute_strength(()) == 1


def test_compute_strength_range() -> None:
    for ws in [(0.1,), (0.5, 0.5), (1.0, 0.8, 0.9)]:
        s = compute_strength(_basis(*ws))
        assert 1 <= s <= 10


# ── compute_confidence ────────────────────────────────────────────────────────

def test_confidence_ny_open_boost() -> None:
    basis = _basis(0.8, 0.8, 0.8)
    c_ny = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, "consolidation", "NY_AM")
    c_none = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, "consolidation", "NONE")
    assert c_ny > c_none


def test_confidence_asia_penalty() -> None:
    basis = _basis(0.8, 0.8, 0.8)
    c_asia = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, "consolidation", "ASIA")
    c_none = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, "consolidation", "NONE")
    assert c_asia < c_none


def test_confidence_regime_mismatch_penalty() -> None:
    basis = _basis(0.9, 0.9)
    # LONG setup in trend_down = contra-trend penalty
    c_down = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, "trend_down", "NONE")
    c_neutral = compute_confidence(SetupType.LONG_DUMP_REVERSAL, basis, "consolidation", "NONE")
    assert c_down < c_neutral


def test_confidence_regime_alignment_boost() -> None:
    basis = _basis(0.8, 0.8)
    # SHORT setup in trend_down = aligned = +5
    c_trend = compute_confidence(SetupType.SHORT_RALLY_FADE, basis, "trend_down", "NONE")
    c_neutral = compute_confidence(SetupType.SHORT_RALLY_FADE, basis, "consolidation", "NONE")
    assert c_trend > c_neutral


def test_confidence_clamped_0_100() -> None:
    basis = _basis(*([1.0] * 10))
    for st in (SetupType.LONG_DUMP_REVERSAL, SetupType.SHORT_RALLY_FADE):
        for regime in ("trend_up", "trend_down", "consolidation"):
            c = compute_confidence(st, basis, regime, "NY_AM")
            assert 0.0 <= c <= 100.0
