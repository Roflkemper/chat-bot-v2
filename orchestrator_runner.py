from __future__ import annotations

import asyncio
import logging
import warnings

from config import (
    KILLSWITCH_DRAWDOWN_THRESHOLD_PCT,
    KILLSWITCH_FLASH_THRESHOLD_PCT,
    KILLSWITCH_INITIAL_BALANCE_USD,
    ORCHESTRATOR_DAILY_REPORT_TIME,
    ORCHESTRATOR_ENABLE_AUTO_ALERTS,
    ORCHESTRATOR_LOOP_INTERVAL_SEC,
)
from core.orchestrator.orchestrator_loop import OrchestratorLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    warnings.warn(
        "orchestrator_runner.py is deprecated. "
        "Use app_runner.py (TZ-010) to run Telegram bot + Orchestrator in one process. "
        "This runner starts only the orchestrator, without interactive Telegram commands.",
        DeprecationWarning,
        stacklevel=2,
    )
    config = {
        "ORCHESTRATOR_LOOP_INTERVAL_SEC": ORCHESTRATOR_LOOP_INTERVAL_SEC,
        "ORCHESTRATOR_DAILY_REPORT_TIME": ORCHESTRATOR_DAILY_REPORT_TIME,
        "ORCHESTRATOR_ENABLE_AUTO_ALERTS": ORCHESTRATOR_ENABLE_AUTO_ALERTS,
        "KILLSWITCH_INITIAL_BALANCE_USD": KILLSWITCH_INITIAL_BALANCE_USD,
        "KILLSWITCH_DRAWDOWN_THRESHOLD_PCT": KILLSWITCH_DRAWDOWN_THRESHOLD_PCT,
        "KILLSWITCH_FLASH_THRESHOLD_PCT": KILLSWITCH_FLASH_THRESHOLD_PCT,
    }
    loop = OrchestratorLoop(config)
    try:
        await loop.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt")
        loop.stop()


if __name__ == "__main__":
    asyncio.run(main())
