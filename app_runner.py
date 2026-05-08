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


async def _run_dashboard_http(stop_event: asyncio.Event) -> None:
    from services.dashboard.http_server import dashboard_http_server

    await dashboard_http_server(stop_event=stop_event)


async def _run_setup_detector(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Setup detector loop with optional Telegram push on new high-confidence
    setups. send_fn signature matches stale_monitor / paper_trader convention.
    Only setups with confidence >= SETUP_PUSH_MIN_CONFIDENCE get pushed —
    avoids spam from low-strength signals.
    """
    from services.setup_detector.loop import setup_detector_loop

    SETUP_PUSH_MIN_CONFIDENCE = 70.0
    # Push priority types — push regardless of confidence (still backtest-validated).
    PRIORITY_TYPES = {
        "long_div_bos_confirmed",   # PF=4.49 hold_1h, walk-forward stable
        "long_div_bos_15m",          # PF=5.01 hold_4h
    }

    send_fn = None
    if telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(card_text: str, setup=None) -> None:
            """Push a setup card to Telegram. Filters:
              - priority types (LONG_DIV_BOS_*) → always push
              - other types → only if confidence_pct >= SETUP_PUSH_MIN_CONFIDENCE
              - skip GRID_* and DEFENSIVE_* (operator already sees those in /advise)
            """
            if setup is None:
                # Legacy call shape — push without filter.
                pass
            else:
                stype = setup.setup_type.value if hasattr(setup, "setup_type") else ""
                conf = float(getattr(setup, "confidence_pct", 0))
                # Skip noisy categories — operator handles these in /advise.
                if stype.startswith("grid_") or stype.startswith("def_"):
                    return
                if stype not in PRIORITY_TYPES and conf < SETUP_PUSH_MIN_CONFIDENCE:
                    return
            for cid in chat_ids:
                try:
                    bot.send_message(cid, card_text)
                except Exception:
                    logger.exception("setup_detector.telegram_send_failed cid=%s", cid)

        send_fn = _send

    await setup_detector_loop(
        stop_event=stop_event,
        send_fn=send_fn,
    )


async def _run_decision_layer_emitter(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Push Decision Layer PRIMARY events from decisions.jsonl to Telegram.

    Closes the gap from DECISION_LAYER_v1 §2 (TZ-DECISION-LAYER-TELEGRAM,
    step 4 of 7) which never landed. The layer has been emitting PRIMARY
    events to decisions.jsonl since Apr-May 2026 but operator never saw
    them. Cold-start safe: skips backlog, only pushes events going forward.
    """
    from services.decision_layer.telegram_emitter import decision_layer_telegram_loop

    send_fn = None
    if telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(text: str) -> None:
            for cid in chat_ids:
                try:
                    bot.send_message(cid, text)
                except Exception:
                    logger.exception("decision_layer.telegram_send_failed cid=%s", cid)

        send_fn = _send

    await decision_layer_telegram_loop(stop_event=stop_event, send_fn=send_fn)


async def _run_stale_monitor(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Stale data monitor — alerts via Telegram when critical sources go stale."""
    from services.stale_monitor import stale_monitor_loop

    send_fn = None
    if telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(text: str) -> None:
            for cid in chat_ids:
                try:
                    bot.send_message(cid, text)
                except Exception:
                    logger.exception("stale_monitor.telegram_send_failed cid=%s", cid)

        send_fn = _send

    await stale_monitor_loop(stop_event=stop_event, send_fn=send_fn)


async def _run_paper_trader(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Paper trader v0.1 (TZ-PAPER-TRADER 2026-05-07).

    Reads setups.jsonl + current price, opens/closes paper trades, sends
    Telegram alerts via the SHARED bot instance (no second polling client).
    """
    from services.paper_trader.loop import paper_trader_loop

    send_fn = None
    if telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(text: str) -> None:
            for cid in chat_ids:
                try:
                    bot.send_message(cid, text)
                except Exception:
                    logger.exception("paper_trader.telegram_send_failed cid=%s", cid)

        send_fn = _send

    await paper_trader_loop(stop_event=stop_event, send_fn=send_fn)


async def _run_setup_tracker(stop_event: asyncio.Event) -> None:
    from services.setup_detector.tracker import setup_tracker_loop

    await setup_tracker_loop(stop_event=stop_event)


async def _run_exit_advisor(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Exit advisory for live SHORT/LONG positions.

    2026-05-07 morning: ОПАСНЫЙ модуль (operator complaint 14:56). Шлёт 'EMERGENCY:
    Close ALL SHORT' с EV +$2 одинаковым для всех вариантов — scoring сломан.

    2026-05-07 evening: переписан honest_renderer без fake EV. Только факты +
    playbook context + HARD BAN list. Включён по умолчанию.
    Чтобы выключить (если что-то опять не так): EXIT_ADVISOR_SEND_TELEGRAM=0
    """
    import os as _os
    from services.exit_advisor.loop import exit_advisor_loop

    send_fn = None
    enable_telegram = _os.environ.get("EXIT_ADVISOR_SEND_TELEGRAM", "1") == "1"
    if enable_telegram and telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(text: str) -> None:
            for cid in chat_ids:
                try:
                    bot.send_message(cid, text)
                except Exception:
                    logger.exception("exit_advisor.telegram_send_failed cid=%s", cid)

        send_fn = _send
    else:
        logger.warning("exit_advisor.telegram_disabled (set EXIT_ADVISOR_SEND_TELEGRAM=1 to enable)")

    await exit_advisor_loop(stop_event=stop_event, send_fn=send_fn)


async def _run_market_intelligence(stop_event: asyncio.Event) -> None:
    from services.market_intelligence.loop import market_intelligence_loop

    await market_intelligence_loop(stop_event=stop_event)


async def _run_market_forward_analysis(stop_event: asyncio.Event) -> None:
    from services.market_forward_analysis.loop import market_forward_analysis_loop

    await market_forward_analysis_loop(stop_event=stop_event)


async def _run_deriv_live(stop_event: asyncio.Event) -> None:
    """Live OI/funding poll every 5 min — fixes P0 #3 (deriv data was stale 4+ days)."""
    from services.deriv_live import deriv_live_loop

    await deriv_live_loop(stop_event=stop_event)


async def _run_cascade_alert(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Live cascade alert — активация post-cascade edge (TZ 2026-05-07).

    Каждые 60 сек проверяет market_live/liquidations.csv. Если long/short
    cascade ≥5 BTC за 5 мин → push в Telegram с историческими цифрами edge.
    """
    from services.cascade_alert import cascade_alert_loop

    send_fn = None
    if telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(text: str) -> None:
            for cid in chat_ids:
                try:
                    bot.send_message(cid, text)
                except Exception:
                    logger.exception("cascade_alert.telegram_send_failed cid=%s", cid)

        send_fn = _send

    await cascade_alert_loop(stop_event=stop_event, send_fn=send_fn)


async def _run_watchlist(stop_event: asyncio.Event, *, telegram_app=None) -> None:
    """Watchlist — оператор задаёт правила (/watch add ...), бот алертит при срабатывании."""
    from services.watchlist import watchlist_loop

    send_fn = None
    if telegram_app is not None and getattr(telegram_app, "allowed_chat_ids", None):
        chat_ids = list(telegram_app.allowed_chat_ids)
        bot = telegram_app.bot

        def _send(text: str) -> None:
            for cid in chat_ids:
                try:
                    bot.send_message(cid, text)
                except Exception:
                    logger.exception("watchlist.telegram_send_failed cid=%s", cid)

        send_fn = _send

    await watchlist_loop(stop_event=stop_event, send_fn=send_fn)


async def _run_bitmex_account(stop_event: asyncio.Event) -> None:
    """BitMEX read-only account poll: auto-update margin (TZ-BITMEX-AUTO-MARGIN 2026-05-07).

    Заменяет ручной /margin command. Каждые 60 секунд polling БитМЕКС API
    (margin balance, available, positions, liquidation prices) → запись в
    state/margin_automated.jsonl. read_latest_margin() сам выберет более
    свежий между manual override и auto.

    Если ключ не настроен в .env.local — loop тихо завершается.
    """
    from services.bitmex_account import bitmex_poll_loop

    await bitmex_poll_loop(stop_event=stop_event)


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
    dashboard_http_task = asyncio.create_task(_run_dashboard_http(stop_event), name="dashboard_http")
    setup_detector_task = asyncio.create_task(_run_setup_detector(stop_event, telegram_app=app), name="setup_detector")
    paper_trader_task = asyncio.create_task(_run_paper_trader(stop_event, telegram_app=app), name="paper_trader")
    stale_monitor_task = asyncio.create_task(_run_stale_monitor(stop_event, telegram_app=app), name="stale_monitor")
    decision_layer_emitter_task = asyncio.create_task(_run_decision_layer_emitter(stop_event, telegram_app=app), name="decision_layer_emitter")
    setup_tracker_task = asyncio.create_task(_run_setup_tracker(stop_event), name="setup_tracker")
    exit_advisor_task = asyncio.create_task(_run_exit_advisor(stop_event, telegram_app=app), name="exit_advisor")
    market_intelligence_task = asyncio.create_task(_run_market_intelligence(stop_event), name="market_intelligence")
    market_forward_task = asyncio.create_task(_run_market_forward_analysis(stop_event), name="market_forward_analysis")
    deriv_live_task = asyncio.create_task(_run_deriv_live(stop_event), name="deriv_live")
    bitmex_account_task = asyncio.create_task(_run_bitmex_account(stop_event), name="bitmex_account")
    cascade_alert_task = asyncio.create_task(_run_cascade_alert(stop_event, telegram_app=app), name="cascade_alert")
    watchlist_task = asyncio.create_task(_run_watchlist(stop_event, telegram_app=app), name="watchlist")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop_event")

    # Critical tasks: their failure forces full shutdown.
    # Non-critical tasks: log error but keep running (telegram bot must stay live).
    critical_tasks = {polling_task, orchestrator_task, stop_task}
    all_tasks = {
        polling_task, orchestrator_task, protection_task, counter_long_task,
        boundary_expand_task, adaptive_grid_task, paper_journal_task,
        decision_log_task, dashboard_task, dashboard_http_task, setup_detector_task,
        setup_tracker_task, exit_advisor_task, market_intelligence_task,
        market_forward_task, deriv_live_task, bitmex_account_task, cascade_alert_task, watchlist_task, paper_trader_task, stale_monitor_task, stop_task,
    }

    exit_code = 0
    pending = set(all_tasks)
    while True:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        # Collect crashes; only critical task failure ends the loop.
        critical_completed = False
        for task in done:
            if task is stop_task:
                logger.info("app_runner.shutdown_requested_by_signal")
                critical_completed = True
                continue
            exc = task.exception() if not task.cancelled() else None
            if exc:
                logger.error("app_runner.subtask_crashed name=%s exc=%s", task.get_name(), exc, exc_info=exc)
            else:
                logger.warning("app_runner.subtask_finished_unexpectedly name=%s", task.get_name())
            if task in critical_tasks:
                logger.error("app_runner.critical_task_down name=%s — initiating shutdown", task.get_name())
                exit_code = 1
                critical_completed = True
            # Non-critical: just log and let other tasks continue
        if critical_completed:
            break

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
