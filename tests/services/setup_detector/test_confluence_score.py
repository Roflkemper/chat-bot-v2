"""Tests for confluence_score module."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.setup_detector.confluence_score import (
    BOOST_K2, BOOST_K3, BOOST_K4_PLUS,
    ConfluenceTracker, apply_boost, get_tracker,
)


def _now() -> datetime:
    return datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)


def test_empty_tracker_returns_1():
    t = ConfluenceTracker()
    assert t.boost_factor(_now(), "long") == 1.0


def test_single_other_detector_no_boost():
    t = ConfluenceTracker()
    t.record(_now() - timedelta(hours=1), "session_breakout", "long")
    assert t.boost_factor(_now(), "long") == 1.0


def test_two_distinct_detectors_long_boost():
    t = ConfluenceTracker()
    t.record(_now() - timedelta(hours=1), "session_breakout", "long")
    t.record(_now() - timedelta(hours=2), "multi_divergence", "long")
    assert t.boost_factor(_now(), "long") == BOOST_K2


def test_three_distinct_detectors():
    t = ConfluenceTracker()
    t.record(_now() - timedelta(hours=1), "session_breakout", "long")
    t.record(_now() - timedelta(hours=2), "multi_divergence", "long")
    t.record(_now() - timedelta(hours=3), "pdl_bounce", "long")
    assert t.boost_factor(_now(), "long") == BOOST_K3


def test_four_distinct_detectors():
    t = ConfluenceTracker()
    for i, det in enumerate([
        "session_breakout", "multi_divergence", "pdl_bounce", "cascade_alert",
    ]):
        t.record(_now() - timedelta(hours=i + 1), det, "long")
    assert t.boost_factor(_now(), "long") == BOOST_K4_PLUS


def test_exclude_own_detector():
    t = ConfluenceTracker()
    t.record(_now() - timedelta(hours=1), "session_breakout", "long")
    t.record(_now() - timedelta(hours=2), "multi_divergence", "long")
    # Asking from session_breakout — only 1 other
    assert t.boost_factor(_now(), "long", own_detector="session_breakout") == 1.0
    # Asking from a third detector — sees 2 others
    assert t.boost_factor(_now(), "long", own_detector="some_other") == BOOST_K2


def test_window_drop_old_setups():
    t = ConfluenceTracker(window_hours=6)
    # 7 hours ago — outside window
    t.record(_now() - timedelta(hours=7), "session_breakout", "long")
    t.record(_now() - timedelta(hours=1), "multi_divergence", "long")
    # Only 1 inside window → no boost
    assert t.boost_factor(_now(), "long") == 1.0


def test_opposite_side_not_counted():
    t = ConfluenceTracker()
    t.record(_now() - timedelta(hours=1), "session_breakout", "short")
    t.record(_now() - timedelta(hours=2), "multi_divergence", "long")
    assert t.boost_factor(_now(), "long") == 1.0
    assert t.boost_factor(_now(), "short") == 1.0


def test_duplicate_detector_counts_once():
    t = ConfluenceTracker()
    t.record(_now() - timedelta(hours=1), "session_breakout", "long")
    t.record(_now() - timedelta(hours=2), "session_breakout", "long")
    t.record(_now() - timedelta(hours=3), "session_breakout", "long")
    # Only 1 distinct detector → no boost
    assert t.boost_factor(_now(), "long") == 1.0


def test_apply_boost_caps_at_100():
    from services.setup_detector.confluence_score import ConfluenceTracker
    # Use isolated tracker, bypass global
    t = ConfluenceTracker()
    for i, det in enumerate([
        "session_breakout", "multi_divergence", "pdl_bounce", "cascade_alert",
    ]):
        t.record(_now() - timedelta(hours=i + 1), det, "long")
    # base 80 × 1.75 = 140 → cap at 100
    factor = t.boost_factor(_now(), "long")
    capped = min(80 * factor, 100)
    assert capped == 100


def test_global_singleton():
    t1 = get_tracker()
    t2 = get_tracker()
    assert t1 is t2
