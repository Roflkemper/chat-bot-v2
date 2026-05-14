"""Binance futures orderbook L2 collector — depth20@100ms stream per symbol."""
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
    stream = f"{symbol.lower()}@depth20@100ms"
    return f"{BINANCE_WS_BASE}?streams={stream}"


def _parse(symbol: str, msg: dict) -> list[dict] | None:
    """Flatten bids + asks into individual level rows."""
    data = msg.get("data", msg)
    ts_ms = int(data.get("T", time.time() * 1000))
    rows = []
    for level, (price_str, qty_str) in enumerate(data.get("b", []), start=1):
        rows.append({
            "ts_ms": ts_ms,
            "exchange": "binance",
            "symbol": symbol,
            "side": "bid",
            "price": float(price_str),
            "qty": float(qty_str),
            "level": level,
        })
    for level, (price_str, qty_str) in enumerate(data.get("a", []), start=1):
        rows.append({
            "ts_ms": ts_ms,
            "exchange": "binance",
            "symbol": symbol,
            "side": "ask",
            "price": float(price_str),
            "qty": float(qty_str),
            "level": level,
        })
    return rows if rows else None


async def run(symbol: str) -> None:
    url = _build_url(symbol)
    backoff = BACKOFF_MIN_S
    while True:
        try:
            async with websockets.connect(url, ping_interval=30) as ws:
                log.info("binance ob %s: connected", symbol)
                backoff = BACKOFF_MIN_S
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        rows = _parse(symbol, msg)
                        if rows:
                            buf = get_buffer("binance", symbol, "orderbook")
                            for row in rows:
                                buf.append(row)
                            if buf.should_flush():
                                buf.flush()
                    except Exception:
                        log.exception("binance ob %s: parse error", symbol)
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("binance ob %s: disconnected, retry in %.1fs", symbol, delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
