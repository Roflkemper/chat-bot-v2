from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Callable

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
logger = logging.getLogger("app_runner")


def _build_orchestrator_config() -> dict:
    return {
        "ORCHESTRATOR_LOOP_INTERVAL_SEC": ORCHESTRATOR_LOOP_INTERVAL_SEC,
        "ORCHESTRATOR_DAILY_REPORT_TIME": ORCHESTRATOR_DAILY_REPORT_TIME,
        "ORCHESTRATOR_ENABLE_AUTO_ALERTS": ORCHESTRATOR_ENABLE_AUTO_ALERTS,
        "KILLSWITCH_INITIAL_BALANCE_USD": KILLSWITCH_INITIAL_BALANCE_USD,
        "KILLSWITCH_DRAWDOWN_THRESHOLD_PCT": KILLSWITCH_DRAWDOWN_THRESHOLD_PCT,
        "KILLSWITCH_FLASH_THRESHOLD_PCT": KILLSWITCH_FLASH_THRESHOLD_PCT,
    }


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    def _fallback_handler(signum, _frame) -> None:
        logger.info("app_runner.signal_received signum=%s", signum)
        loop.call_soon_threadsafe(stop_event.set)

    try:
        loop.add_signal_handler(signal.SIGINT, stop_event.set)
    except NotImplementedError:
        signal.signal(signal.SIGINT, _fallback_handler)

    if sys.platform != "win32":
        try:
            loop.add_signal_handler(signal.SIGTERM, stop_event.set)
        except NotImplementedError:
            pass


async def _run_polling_in_executor(app) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, app.run_polling_blocking)


async def _run_protection_alerts(stop_event: asyncio.Event) -> None:
    from services.protection_alerts import ProtectionAlerts
    pa = ProtectionAlerts.instance()
    while not stop_event.is_set():
        await pa.tick()
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=30.0)
        except asyncio.TimeoutError:
            pass


async def _run_counter_long(stop_event: asyncio.Event) -> None:
    from services.counter_long_manager import CounterLongManager
    mgr = CounterLongManager()
    while not stop_event.is_set():
        await mgr.tick()
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=30.0)
        except asyncio.TimeoutError:
            pass


async def _run_boundary_expand(stop_event: asyncio.Event) -> None:
    from services.boundary_expand_manager import BoundaryExpandManager
    mgr = BoundaryExpandManager.instance()
    while not stop_event.is_set():
        await mgr.tick()
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=60.0)
        except asyncio.TimeoutError:
            pass


async def _run_adaptive_grid(stop_event: asyncio.Event) -> None:
    from services.adaptive_grid_manager import AdaptiveGridManager
    mgr = AdaptiveGridManager.instance()
    while not stop_event.is_set():
        await mgr.tick()
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=300.0)
        except asyncio.TimeoutError:
            pass


async def _run_paper_journal(stop_event: asyncio.Event) -> None:
    from services.advise_v2.paper_journal import paper_journal_loop
    await paper_journal_loop(stop_event=stop_event)


async def _run_decision_log(stop_event: asyncio.Event) -> None:
    from services.decision_log import decision_log_loop

    await decision_log_loop(stop_event=stop_event)


async def _run_dashboard(stop_event: asyncio.Event) -> None:
    from services.dashboard import dashboard_state_loop

    await dashboard_state_loop(stop_event=stop_event)


async def _run_setup_detector(stop_event: asyncio.Event) -> None:
    from services.setup_detector.loop import setup_detector_loop

    await setup_detector_loop(stop_event=stop_event)


async def _run_setup_tracker(stop_event: asyncio.Event) -> None:
    from services.setup_detector.tracker import setup_tracker_loop

    await setup_tracker_loop(stop_event=stop_event)


async def _shutdown_task(task: asyncio.Task, *, timeout: float) -> None:
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.CancelledError:
        return
    except asyncio.TimeoutError:
        logger.warning("app_runner.task_timeout name=%s, cancelling", task.get_name())
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def main(
    *,
    stop_event: asyncio.Event | None = None,
    signal_handler_installer: Callable[[asyncio.AbstractEventLoop, asyncio.Event], None] = _install_signal_handlers,
    shutdown_timeout: float = 10,
) -> int:
    from services.telegram_runtime import TelegramBotApp

    try:
        app = TelegramBotApp()
    except Exception:
        logger.exception("app_runner.telegram_init_failed")
        return 1

    orchestrator = OrchestratorLoop(_build_orchestrator_config())
    loop = asyncio.get_running_loop()
    stop_event = stop_event or asyncio.Event()
    signal_handler_installer(loop, stop_event)

    polling_task = asyncio.create_task(_run_polling_in_executor(app), name="telegram_polling")
    orchestrator_task = asyncio.create_task(orchestrator.start(), name="orchestrator_loop")
    protection_task = asyncio.create_task(_run_protection_alerts(stop_event), name="protection_alerts")
    counter_long_task = asyncio.create_task(_run_counter_long(stop_event), name="counter_long")
    boundary_expand_task = asyncio.create_task(_run_boundary_expand(stop_event), name="boundary_expand")
    adaptive_grid_task = asyncio.create_task(_run_adaptive_grid(stop_event), name="adaptive_grid")
    paper_journal_task = asyncio.create_task(_run_paper_journal(stop_event), name="paper_journal")
    decision_log_task = asyncio.create_task(_run_decision_log(stop_event), name="decision_log")
    dashboard_task = asyncio.create_task(_run_dashboard(stop_event), name="dashboard")
    setup_detector_task = asyncio.create_task(_run_setup_detector(stop_event), name="setup_detector")
    setup_tracker_task = asyncio.create_task(_run_setup_tracker(stop_event), name="setup_tracker")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop_event")

    done, pending = await asyncio.wait(
        {polling_task, orchestrator_task, protection_task, counter_long_task, boundary_expand_task, adaptive_grid_task, paper_journal_task, decision_log_task, dashboard_task, setup_detector_task, setup_tracker_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 0
    for task in done:
        if task is stop_task:
            logger.info("app_runner.shutdown_requested_by_signal")
            continue
        exc = task.exception() if not task.cancelled() else None
        if exc:
            logger.exception("app_runner.subtask_crashed name=%s", task.get_name(), exc_info=exc)
        else:
            logger.warning("app_runner.subtask_finished_unexpectedly name=%s", task.get_name())
        exit_code = 1

    logger.info("app_runner.shutting_down")
    orchestrator.stop()
    try:
        app.bot.stop_polling()
    except Exception:
        logger.exception("app_runner.stop_polling_failed")

    for task in pending:
        if task is stop_task:
            task.cancel()
            continue
        await _shutdown_task(task, timeout=shutdown_timeout)

    logger.info("app_runner.stopped exit_code=%d", exit_code)
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        logger.info("app_runner.interrupted")
        raise SystemExit(130)
