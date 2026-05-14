"""Bybit liquidation collector — allLiquidation topic per symbol."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time

import websockets

from collectors.config import (
    BACKOFF_FACTOR,
    BACKOFF_JITTER,
    BACKOFF_MAX_S,
    BACKOFF_MIN_S,
    BYBIT_PING_INTERVAL_S,
    BYBIT_WS_URL,
    SYMBOLS,
)
from collectors.storage import get_buffer

log = logging.getLogger(__name__)


def _parse(msg: dict) -> list[dict] | None:
    """Parse Bybit allLiquidation message → liquidation rows. data is a list."""
    topic = msg.get("topic", "")
    if not topic.startswith("allLiquidation."):
        return None

    raw_data = msg.get("data", [])
    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    rows = []
    for data in raw_data:
        symbol = data.get("symbol", "")
        side_raw = data.get("side", "")     # "Buy" = short liq, "Sell" = long liq
        side = "long" if side_raw == "Sell" else "short"
        qty = float(data.get("size", 0) or 0)
        price = float(data.get("price", 0) or 0)
        ts_ms = int(data.get("updateTime", time.time() * 1000))
        rows.append({
            "ts_ms": ts_ms,
            "exchange": "bybit",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "value_usd": qty * price,
            "source_rate_limited": False,
        })
    return rows if rows else None


async def run() -> None:
    backoff = BACKOFF_MIN_S
    topics = [f"allLiquidation.{s}" for s in SYMBOLS]
    sub_msg = json.dumps({"op": "subscribe", "args": topics})
    ping_msg = json.dumps({"op": "ping"})

    while True:
        try:
            async with websockets.connect(BYBIT_WS_URL, ping_interval=None) as ws:
                log.info("bybit liq: connected, subscribing %s", topics)
                backoff = BACKOFF_MIN_S
                await ws.send(sub_msg)

                ping_task = asyncio.create_task(_ping_loop(ws, ping_msg))
                try:
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            rows = _parse(msg)
                            if rows:
                                for row in rows:
                                    buf = get_buffer("bybit", row["symbol"], "liquidations")
                                    buf.append(row)
                                    if buf.should_flush():
                                        buf.flush()
                        except Exception:
                            log.exception("bybit liq: parse error")
                finally:
                    ping_task.cancel()
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("bybit liq: disconnected, retry in %.1fs", delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)


async def _ping_loop(ws: websockets.WebSocketClientProtocol, ping_msg: str) -> None:
    while True:
        await asyncio.sleep(BYBIT_PING_INTERVAL_S)
        try:
            await ws.send(ping_msg)
        except Exception:
            break
