"""TZ-048 dev smoke: measure RSS growth with threshold rotation enabled.

Patches WRITER_MAX_AGE_S=10 to force rapid rotation, runs collectors for 90s,
samples RSS every 15s. Confirms growth stays bounded.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT7_LIVE_PATH", str(ROOT / "market_live_profiler"))

# Patch rotation threshold to 10 seconds to force rapid rotation in dev
import collectors.config as _cfg
_cfg.WRITER_MAX_AGE_S = 10.0
_cfg.WRITER_MAX_ROWS = 999_999

import collectors.storage as _sto
_sto.WRITER_MAX_AGE_S = 10.0
_sto.WRITER_MAX_ROWS = 999_999

import psutil

import collectors.liquidations.binance as liq_binance
import collectors.liquidations.bybit as liq_bybit
import collectors.liquidations.hyperliquid as liq_hl
import collectors.liquidations.bitmex as liq_bitmex
import collectors.liquidations.okx as liq_okx
import collectors.orderbook.binance as ob_binance
import collectors.trades.binance as trades_binance
from collectors.config import LIVE_PATH, SYMBOLS
from collectors.storage import flush_loop

import logging
logging.basicConfig(level=logging.WARNING)  # suppress noise

DURATION_S = 90
SAMPLE_INTERVAL = 15

samples: list[tuple[float, float]] = []


async def _run() -> None:
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(liq_binance.run(), name="liq-binance"),
        asyncio.create_task(liq_bybit.run(), name="liq-bybit"),
        asyncio.create_task(liq_hl.run(), name="liq-hyperliquid"),
        asyncio.create_task(liq_bitmex.run(), name="liq-bitmex"),
        asyncio.create_task(liq_okx.run(), name="liq-okx"),
        *[asyncio.create_task(ob_binance.run(sym), name=f"ob-{sym}") for sym in SYMBOLS],
        *[asyncio.create_task(trades_binance.run(sym), name=f"tr-{sym}") for sym in SYMBOLS],
        asyncio.create_task(flush_loop(stop_event), name="flush-loop"),
    ]

    start = time.monotonic()
    proc = psutil.Process()

    while time.monotonic() - start < DURATION_S:
        elapsed = time.monotonic() - start
        rss = proc.memory_info().rss / 1024 / 1024
        samples.append((elapsed, rss))
        print(f"t={elapsed:4.0f}s RSS={rss:.1f}MB", flush=True)
        await asyncio.sleep(SAMPLE_INTERVAL)

    stop_event.set()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(_run())

    if len(samples) >= 2:
        first_rss = samples[0][1]
        last_rss = samples[-1][1]
        growth = last_rss - first_rss
        duration_min = samples[-1][0] / 60
        rate = growth / duration_min if duration_min > 0 else 0

        print(f"\n── RSS summary ──")
        print(f"first={first_rss:.1f}MB  last={last_rss:.1f}MB")
        print(f"growth={growth:+.1f}MB over {duration_min:.1f}min ({rate:+.1f}MB/min)")

        # Scale to 30min to compare with acceptance criterion (≤5MB/30min)
        projected_30min = rate * 30
        print(f"projected 30min growth: {projected_30min:+.1f}MB (limit: ≤5MB)")
        if projected_30min <= 5.0:
            print("PASS ✓")
        else:
            print("FAIL ✗ — above threshold")
