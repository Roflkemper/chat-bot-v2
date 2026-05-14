"""Confluence boost — increment confidence when multiple edges align.

Backtest 2026-05-12 (CONFLUENCE_BACKTEST.md):
  K≥4 detectors aligned in same direction within 4-6h window:
    - PF 2.0 - 41 across windows
    - 80-93% WR
    - But N is only 10-15 over 2y (rare event)
  K≥3 aligned: too noisy, PF<1.

Strategy: not a standalone detector, but a confidence-boost.
When >=2 already-validated detectors fire same direction within 6h:
  → existing setup confidence × 1.25 (small bump)
When >=3 align:
  → existing setup confidence × 1.5 (significant bump)

Caller code stores recent setups in ring buffer, queries this module at emit time.

Live wiring is a separate task — this module just provides the scoring logic.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque

WINDOW_HOURS = 6
BOOST_K2 = 1.25
BOOST_K3 = 1.5
BOOST_K4_PLUS = 1.75   # cap; backtest showed PF saturates


@dataclass
class _RecentSetup:
    ts: datetime
    detector: str
    side: str   # "long" / "short"


class ConfluenceTracker:
    """Ring buffer of recent setups, queryable for confluence at emit time.

    Thread-safe? No — meant for single-threaded setup_detector loop.
    Memory: bounded by WINDOW_HOURS * typical emit rate. At 1 setup/hour
    we store ~6 items. Even at heavy 20/hr → 120 items.
    """

    def __init__(self, window_hours: int = WINDOW_HOURS) -> None:
        self._window = timedelta(hours=window_hours)
        self._items: Deque[_RecentSetup] = deque(maxlen=500)

    def record(self, ts: datetime, detector: str, side: str) -> None:
        """Add a new setup to the buffer."""
        self._items.append(_RecentSetup(ts=ts, detector=detector, side=side))

    def _prune(self, now: datetime) -> None:
        """Drop items older than window."""
        cutoff = now - self._window
        while self._items and self._items[0].ts < cutoff:
            self._items.popleft()

    def count_distinct(self, now: datetime, side: str,
                       exclude_detector: str | None = None) -> int:
        """Count distinct detectors active in window for given side.

        exclude_detector: omit self when called from inside a detector
        (we want N other detectors, not counting ourselves).
        """
        self._prune(now)
        seen: set[str] = set()
        for item in self._items:
            if item.side != side:
                continue
            if exclude_detector and item.detector == exclude_detector:
                continue
            seen.add(item.detector)
        return len(seen)

    def boost_factor(self, now: datetime, side: str,
                     own_detector: str | None = None) -> float:
        """Return multiplier to apply to confidence based on confluence.

        0 other detectors → 1.0 (no boost)
        1 other → 1.0 (still not "confluence", just a single confirmation)
        2 others → 1.25
        3 others → 1.5
        4+ others → 1.75
        """
        n = self.count_distinct(now, side, exclude_detector=own_detector)
        if n >= 4:
            return BOOST_K4_PLUS
        if n >= 3:
            return BOOST_K3
        if n >= 2:
            return BOOST_K2
        return 1.0


# Module-level singleton — shared across detectors in the same process.
_GLOBAL_TRACKER: ConfluenceTracker | None = None


def get_tracker() -> ConfluenceTracker:
    global _GLOBAL_TRACKER
    if _GLOBAL_TRACKER is None:
        _GLOBAL_TRACKER = ConfluenceTracker()
    return _GLOBAL_TRACKER


def record_setup(ts: datetime, detector: str, side: str) -> None:
    """Convenience: append to global tracker."""
    get_tracker().record(ts, detector, side)


def apply_boost(now: datetime, base_confidence: float,
                side: str, own_detector: str | None = None) -> float:
    """Return base_confidence × confluence_factor, capped at 100."""
    boost = get_tracker().boost_factor(now, side, own_detector=own_detector)
    boosted = base_confidence * boost
    return min(boosted, 100.0)
