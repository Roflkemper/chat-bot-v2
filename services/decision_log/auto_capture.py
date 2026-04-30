from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .event_detector import detector_run_once
from .outcome_resolver import outcome_resolver_run_once

logger = logging.getLogger(__name__)


async def decision_log_loop(
    stop_event: asyncio.Event,
    *,
    detector_runner: Callable[[], Any] = detector_run_once,
    outcome_runner: Callable[[], Any] = outcome_resolver_run_once,
    interval_sec: float = 300.0,
) -> None:
    """Main loop, called from app_runner."""
    while not stop_event.is_set():
        try:
            detector_runner()
            outcome_runner()
        except Exception as exc:
            logger.exception("decision_log iteration failed: %s", exc)
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
