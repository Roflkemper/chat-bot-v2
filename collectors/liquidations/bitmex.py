"""BitMEX liquidation collector — liquidation:XBTUSD topic.

BitMEX publishes individual liquidation orders in real time (no batching).
XBTUSD is an inverse perpetual: leavesQty is denominated in USD contracts,
so value_usd = leavesQty directly.
"""
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
    BITMEX_PING_INTERVAL_S,
    BITMEX_SYMBOL_MAP,
    BITMEX_TOPICS,
    BITMEX_WS_URL,
)
from collectors.storage import get_buffer

log = logging.getLogger(__name__)


def _parse(msg: dict) -> list[dict] | None:
    """Parse BitMEX liquidation table message → list of rows."""
    if msg.get("table") != "liquidation" or msg.get("action") != "insert":
        return None

    rows = []
    for item in msg.get("data", []):
        bitmex_sym = item.get("symbol", "")
        symbol = BITMEX_SYMBOL_MAP.get(bitmex_sym)
        if symbol is None:
            continue

        # "Buy" order = closing a short position → short was liquidated
        # "Sell" order = closing a long position → long was liquidated
        side_raw = item.get("side", "")
        side = "short" if side_raw == "Buy" else "long"

        leaves_qty = float(item.get("leavesQty", 0) or 0)
        price = float(item.get("price", 0) or 0)
        # XBTUSD inverse: leavesQty is in USD contracts (1 contract = 1 USD).
        # qty must be in base asset (BTC) for consistency with linear-exchange rows.
        qty_btc = leaves_qty / price if price > 0 else 0.0

        rows.append({
            "ts_ms": int(time.time() * 1000),   # BitMEX liquidation push has no explicit ts
            "exchange": "bitmex",
            "symbol": symbol,
            "side": side,
            "qty": qty_btc,                      # BTC, consistent with linear exchanges
            "price": price,
            "value_usd": leaves_qty,             # USD = contract count for inverse
            "source_rate_limited": False,
        })
    return rows if rows else None


async def run() -> None:
    sub_msg = json.dumps({"op": "subscribe", "args": BITMEX_TOPICS})
    backoff = BACKOFF_MIN_S

    while True:
        try:
            async with websockets.connect(BITMEX_WS_URL, ping_interval=None) as ws:
                log.info("bitmex liq: connected, subscribing %s", BITMEX_TOPICS)
                backoff = BACKOFF_MIN_S
                await ws.send(sub_msg)

                ping_task = asyncio.create_task(_ping_loop(ws))
                try:
                    async for raw in ws:
                        try:
                            if isinstance(raw, (bytes, str)) and raw in ("pong", b"pong"):
                                continue
                            msg = json.loads(raw)
                            # Log subscribe ACK/error — BitMEX sends {"subscribe":"liquidation:XBTUSD","success":true}
                            if "subscribe" in msg or "error" in msg:
                                level = logging.WARNING if "error" in msg else logging.INFO
                                log.log(level, "bitmex liq ACK: %s", msg)
                            rows = _parse(msg)
                            if rows:
                                for row in rows:
                                    buf = get_buffer("bitmex", row["symbol"], "liquidations")
                                    buf.append(row)
                                    if buf.should_flush():
                                        buf.flush()
                        except Exception:
                            log.exception("bitmex liq: parse error")
                finally:
                    ping_task.cancel()
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("bitmex liq: disconnected, retry in %.1fs", delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)


async def _ping_loop(ws: websockets.WebSocketClientProtocol) -> None:
    while True:
        await asyncio.sleep(BITMEX_PING_INTERVAL_S)
        try:
            await ws.send("ping")
        except Exception:
            break
