"""Smoke tests for setup_detector.constants — sanity ranges only.

These constants are imported into setup_types.py. Tests verify no
silent regressions (e.g., RSI_OVERBOUGHT accidentally set to 30).
"""
from __future__ import annotations

from services.setup_detector import constants as C


def test_rsi_thresholds_ordered():
    assert C.RSI_OVERSOLD_STRICT < C.RSI_OVERSOLD < C.RSI_NEUTRAL_LOW
    assert C.RSI_NEUTRAL_LOW < C.RSI_MID < C.RSI_NEUTRAL_HIGH
    assert C.RSI_NEUTRAL_HIGH < C.RSI_MOMENTUM_HIGH < C.RSI_OVERBOUGHT
    assert C.RSI_OVERBOUGHT < C.RSI_OVERBOUGHT_STRICT


def test_rsi_in_valid_range():
    for name in ("RSI_OVERSOLD_STRICT", "RSI_OVERSOLD", "RSI_NEUTRAL_LOW",
                 "RSI_MID", "RSI_NEUTRAL_HIGH", "RSI_MOMENTUM_HIGH",
                 "RSI_OVERBOUGHT", "RSI_OVERBOUGHT_STRICT"):
        v = getattr(C, name)
        assert 0 < v < 100, f"{name}={v} out of [0,100]"


def test_long_multipliers_correct_direction():
    """LONG side: entry below market, stop below entry, etc."""
    assert C.LONG_ENTRY_PREMIUM < 1.0
    assert C.LONG_ENTRY_NEAR_LEVEL < 1.0
    assert C.LONG_STOP_BUFFER_BELOW < 1.0
    assert C.LONG_STOP_BUFFER_DEEP < C.LONG_STOP_BUFFER_BELOW
    assert C.LONG_REJECTION_TOLERANCE > 1.0  # close above level by margin
    assert C.LONG_RECLAIM_MIN > 1.0


def test_short_multipliers_correct_direction():
    """SHORT side: entry above market, stop above entry."""
    assert C.SHORT_ENTRY_PREMIUM > 1.0
    assert C.SHORT_ENTRY_NEAR_LEVEL > 1.0
    assert C.SHORT_STOP_BUFFER_ABOVE > 1.0
    assert C.SHORT_STOP_BUFFER_DEEP > C.SHORT_STOP_BUFFER_ABOVE
    assert C.SHORT_REJECTION_TOLERANCE < 1.0
    assert C.SHORT_REJECT_MIN < 1.0


def test_grid_multipliers():
    assert C.GRID_BOUNDARY_TRIGGER > 1.0
    assert C.GRID_BOUNDARY_PREMIUM > C.GRID_BOUNDARY_TRIGGER


def test_min_strength_lives_in_combo_filter_only():
    """2026-05-12: MIN_ALLOWED_STRENGTH was duplicated in constants.py — moved
    to single source of truth (combo_filter.py). Verify constants.py no longer
    exports it (so future readers know where to look)."""
    assert not hasattr(C, "MIN_ALLOWED_STRENGTH"), (
        "MIN_ALLOWED_STRENGTH should live ONLY in combo_filter.py"
    )
    # Sanity: combo_filter version exists and is sane.
    from services.setup_detector.combo_filter import MIN_ALLOWED_STRENGTH
    assert isinstance(MIN_ALLOWED_STRENGTH, int)
    assert 5 <= MIN_ALLOWED_STRENGTH <= 10


def test_confidence_floors_ordered():
    assert C.MIN_CONFIDENCE_DEFAULT < C.MIN_CONFIDENCE_STRONG
    assert C.MIN_CONFIDENCE_STRONG < C.MIN_CONFIDENCE_VERY_STRONG
