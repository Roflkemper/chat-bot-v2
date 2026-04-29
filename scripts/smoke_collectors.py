"""TZ-029-A smoke test: run new collectors runtime for N seconds, log to logs/dev/."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Dev output — never touches production market_live/
os.environ.setdefault("BOT7_LIVE_PATH", str(ROOT / "market_live_dev"))

import collectors.liquidations.binance as liq_binance
import collectors.liquidations.bybit as liq_bybit
import collectors.liquidations.hyperliquid as liq_hl
import collectors.liquidations.bitmex as liq_bitmex
import collectors.liquidations.okx as liq_okx
import collectors.orderbook.binance as ob_binance
import collectors.trades.binance as trades_binance
from collectors.config import LIVE_PATH, SYMBOLS
from collectors.storage import flush_loop

DURATION_S = int(os.environ.get("SMOKE_DURATION", "120"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("smoke_collectors")


async def _run() -> None:
    log.info("smoke test starting — output: %s, duration: %ds", LIVE_PATH, DURATION_S)

    stop_event = asyncio.Event()

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

    await asyncio.sleep(DURATION_S)
    log.info("duration elapsed — stopping")
    stop_event.set()

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("smoke test done")


if __name__ == "__main__":
    asyncio.run(_run())
