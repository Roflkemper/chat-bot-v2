"""OKX liquidation collector — liquidation-orders channel, SWAP instruments.

OKX delivers individual liquidation records per fill, no batching delay.
Subscribes once to instType=SWAP and filters to configured instruments.
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
    OKX_SYMBOL_MAP,
    OKX_WS_URL,
)
from collectors.storage import get_buffer

log = logging.getLogger(__name__)

_SUB_MSG = json.dumps({
    "op": "subscribe",
    "args": [{"channel": "liquidation-orders", "instType": "SWAP"}],
})


def _parse(msg: dict) -> list[dict] | None:
    """Parse OKX liquidation-orders push → list of rows."""
    if msg.get("arg", {}).get("channel") != "liquidation-orders":
        return None

    rows = []
    for instrument in msg.get("data", []):
        inst_id = instrument.get("instId", "")
        symbol = OKX_SYMBOL_MAP.get(inst_id)
        if symbol is None:
            continue

        for detail in instrument.get("details", []):
            # OKX side: "buy" = forced buy to close short → short liquidated
            #           "sell" = forced sell to close long → long liquidated
            side_raw = detail.get("side", "")
            side = "short" if side_raw == "buy" else "long"
            qty = float(detail.get("sz", 0) or 0)
            price = float(detail.get("bkPx", 0) or 0)  # bankruptcy price
            ts_ms = int(detail.get("ts", time.time() * 1000))

            rows.append({
                "ts_ms": ts_ms,
                "exchange": "okx",
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

    while True:
        try:
            async with websockets.connect(OKX_WS_URL, ping_interval=25) as ws:
                log.info("okx liq: connected, subscribing liquidation-orders SWAP")
                backoff = BACKOFF_MIN_S
                await ws.send(_SUB_MSG)

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        # Log subscribe ACK/error to detect auth issues on first connect
                        if msg.get("event") in ("subscribe", "error"):
                            level = logging.WARNING if msg.get("event") == "error" else logging.INFO
                            log.log(level, "okx liq ACK: %s", msg)
                        rows = _parse(msg)
                        if rows:
                            for row in rows:
                                buf = get_buffer("okx", row["symbol"], "liquidations")
                                buf.append(row)
                                if buf.should_flush():
                                    buf.flush()
                    except Exception:
                        log.exception("okx liq: parse error")
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("okx liq: disconnected, retry in %.1fs", delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
