"""Binance futures aggTrade collector — one connection per symbol."""
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
    BINANCE_WS_BASE,
)
from collectors.storage import get_buffer

log = logging.getLogger(__name__)


def _build_url(symbol: str) -> str:
    stream = f"{symbol.lower()}@aggTrade"
    return f"{BINANCE_WS_BASE}?streams={stream}"


def _parse(msg: dict) -> dict | None:
    """Parse aggTrade message → trade row. m=True means maker is buyer → taker sold → side=sell."""
    data = msg.get("data", msg)
    if data.get("e") != "aggTrade":
        return None

    symbol = data.get("s", "")
    side = "sell" if data.get("m", False) else "buy"
    qty = float(data.get("q", 0) or 0)
    price = float(data.get("p", 0) or 0)
    ts_ms = int(data.get("T", time.time() * 1000))

    return {
        "ts_ms": ts_ms,
        "exchange": "binance",
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "is_liquidation": False,
    }


async def run(symbol: str) -> None:
    url = _build_url(symbol)
    backoff = BACKOFF_MIN_S
    while True:
        try:
            async with websockets.connect(url, ping_interval=30) as ws:
                log.info("binance trades %s: connected", symbol)
                backoff = BACKOFF_MIN_S
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        row = _parse(msg)
                        if row:
                            buf = get_buffer("binance", symbol, "trades")
                            buf.append(row)
                            if buf.should_flush():
                                buf.flush()
                    except Exception:
                        log.exception("binance trades %s: parse error", symbol)
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("binance trades %s: disconnected, retry in %.1fs", symbol, delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
