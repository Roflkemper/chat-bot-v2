from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .state_builder import OUTPUT_PATH, build_and_save_state

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 60  # bumped from 300 → 60 for live freshness (TZ-DASHBOARD-LIVE-FRESHNESS)


async def dashboard_state_loop(
    *,
    stop_event: asyncio.Event,
    output_path: Path = OUTPUT_PATH,
) -> None:
    while not stop_event.is_set():
        try:
            build_and_save_state(output_path=output_path)
        except Exception:
            logger.exception("dashboard.state_build_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=float(INTERVAL_SECONDS))
        except asyncio.TimeoutError:
            pass
