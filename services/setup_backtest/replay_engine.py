from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from services.setup_detector.loop import _run_detectors_once
from services.setup_detector.models import Setup
from services.setup_detector.storage import SetupStorage

from .historical_context import HistoricalContextBuilder

logger = logging.getLogger(__name__)

_DEFAULT_STEP_MINUTES = 5
_MIN_STRENGTH = 6


class _NullStorage(SetupStorage):
    """In-memory storage for backtest — no disk I/O."""

    def __init__(self) -> None:
        from pathlib import Path
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        super().__init__(jsonl_path=tmp / "setups.jsonl", active_path=tmp / "setups_active.json")
        self._collected: list[Setup] = []

    def write(self, setup: Setup) -> None:
        self._collected.append(setup)

    def list_active(self) -> list[Setup]:
        return []

    def update_status(self, setup_id: str, new_status) -> None:  # type: ignore[override]
        pass


class SetupBacktestReplay:
    """Iterates historical timestamps, runs detector functions, collects Setup objects."""

    def __init__(
        self,
        context_builder: HistoricalContextBuilder,
        step_minutes: int = _DEFAULT_STEP_MINUTES,
    ) -> None:
        self._ctx = context_builder
        self._step = step_minutes

    def run(
        self,
        start_ts: datetime,
        end_ts: datetime,
        *,
        progress_callback: Callable[[datetime, int], None] | None = None,
        max_setups: int | None = None,
    ) -> list[Setup]:
        """Iterate timestamps in [start_ts, end_ts] and collect all detected setups."""
        if start_ts.tzinfo is None:
            start_ts = start_ts.replace(tzinfo=timezone.utc)
        if end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=timezone.utc)

        # Clamp to available data
        data_start = self._ctx.start_ts
        data_end = self._ctx.end_ts
        start_ts = max(start_ts, data_start + timedelta(hours=2))
        end_ts = min(end_ts, data_end)
        if start_ts >= end_ts:
            logger.warning("replay_engine.empty_range start=%s end=%s data_start=%s data_end=%s",
                           start_ts, end_ts, data_start, data_end)
            return []

        all_setups: list[Setup] = []
        store = _NullStorage()
        ts = start_ts
        step = timedelta(minutes=self._step)
        total_steps = int((end_ts - start_ts).total_seconds() / (self._step * 60))
        step_count = 0

        logger.info("replay_engine.start start=%s end=%s step=%dmin total_steps=%d",
                    start_ts, end_ts, self._step, total_steps)

        while ts <= end_ts:
            ctx = self._ctx.build_context_at(ts)
            if ctx is not None:
                new_setups = _run_detectors_once(ctx, store, None)
                all_setups.extend(new_setups)

            step_count += 1
            if progress_callback is not None:
                progress_callback(ts, step_count)

            if max_setups is not None and len(all_setups) >= max_setups:
                logger.info("replay_engine.max_setups_reached n=%d at ts=%s", len(all_setups), ts)
                break

            ts += step

        logger.info("replay_engine.done total_setups=%d steps=%d", len(all_setups), step_count)
        return all_setups
