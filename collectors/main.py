"""Collector supervisor — runs all WS tasks as asyncio coroutines.

Usage:
    python -m collectors.main

Environment:
    BOT7_LIVE_PATH — output root directory (default: C:/bot7/market_live)

Tasks (11 total):
    Liquidations:  Binance (!forceOrder@arr), Bybit (x3), Hyperliquid (x3), BitMEX, OKX
    Orderbook L2:  Binance BTCUSDT/ETHUSDT/XRPUSDT
    Trades:        Binance BTCUSDT/ETHUSDT/XRPUSDT
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.config import LIVE_PATH, SYMBOLS
from collectors.pidlock import PidLock
from collectors.storage import flush_loop

# Liquidations
import collectors.liquidations.binance as liq_binance
import collectors.liquidations.bybit as liq_bybit
import collectors.liquidations.hyperliquid as liq_hl
import collectors.liquidations.bitmex as liq_bitmex
import collectors.liquidations.okx as liq_okx

# Orderbook + trades
import collectors.orderbook.binance as ob_binance
import collectors.trades.binance as trades_binance

# Use unified logging — writes to logs/current/collectors.log directly (not via stdout)
# so the file is reachable regardless of how stdout is redirected by the supervisor launcher.
try:
    from src.utils.logging_config import setup_logging
    _root_logger = setup_logging("collectors")
except Exception:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

log = logging.getLogger("collectors.main")

_PID_PATH = Path("run/collectors_lock.pid")


async def _main() -> None:
    lock = PidLock(_PID_PATH)
    if not lock.acquire():
        log.error("Another collectors process is running. Exiting.")
        sys.exit(1)

    stop_event = asyncio.Event()

    def _handle_signal(*_: object) -> None:
        log.info("shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGTERM
            signal.signal(sig, _handle_signal)

    log.info("collectors starting — output: %s", LIVE_PATH)

    tasks = [
        asyncio.create_task(liq_binance.run(), name="liq-binance"),
        asyncio.create_task(liq_bybit.run(), name="liq-bybit"),
        asyncio.create_task(liq_hl.run(), name="liq-hyperliquid"),
        asyncio.create_task(liq_bitmex.run(), name="liq-bitmex"),
        asyncio.create_task(liq_okx.run(), name="liq-okx"),
        *[asyncio.create_task(ob_binance.run(sym), name=f"ob-binance-{sym}") for sym in SYMBOLS],
        *[asyncio.create_task(trades_binance.run(sym), name=f"trades-binance-{sym}") for sym in SYMBOLS],
        asyncio.create_task(flush_loop(stop_event), name="flush-loop"),
    ]

    try:
        await stop_event.wait()
    finally:
        log.info("cancelling %d tasks...", len(tasks))
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        lock.release()
        log.info("collectors stopped cleanly")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
