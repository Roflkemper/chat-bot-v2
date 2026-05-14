"""Hyperliquid liquidation collector — trades stream, liquidation field detection."""
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
    HL_COINS,
    HL_SYMBOL_MAP,
    HL_WS_URL,
)
from collectors.storage import get_buffer

log = logging.getLogger(__name__)


def _parse(msg: dict) -> list[dict] | None:
    """Parse HL trades message. Only emit rows where liquidation field is present."""
    channel = msg.get("channel", "")
    if channel != "trades":
        return None

    data = msg.get("data", [])
    if isinstance(data, dict):
        data = [data]

    rows = []
    for record in data:
        # liquidation field absent → regular trade, skip
        if record.get("liquidation") is None:
            continue

        coin = record.get("coin", "")
        symbol = HL_SYMBOL_MAP.get(coin)
        if symbol is None:
            continue

        side_raw = record.get("side", "")   # "B" = buy/long liq, "A" = ask/short liq
        side = "long" if side_raw == "A" else "short"   # ask-side fill = long liquidated
        qty = float(record.get("sz", 0) or 0)
        price = float(record.get("px", 0) or 0)
        ts_ms = int(record.get("time", time.time() * 1000))

        rows.append({
            "ts_ms": ts_ms,
            "exchange": "hyperliquid",
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
    subs = [{"method": "subscribe", "subscription": {"type": "trades", "coin": coin}}
            for coin in HL_COINS]

    while True:
        try:
            async with websockets.connect(HL_WS_URL, ping_interval=30) as ws:
                log.info("hyperliquid liq: connected, subscribing %s", HL_COINS)
                backoff = BACKOFF_MIN_S
                for sub in subs:
                    await ws.send(json.dumps(sub))

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        rows = _parse(msg)
                        if rows:
                            for row in rows:
                                buf = get_buffer("hyperliquid", row["symbol"], "liquidations")
                                buf.append(row)
                                if buf.should_flush():
                                    buf.flush()
                    except Exception:
                        log.exception("hyperliquid liq: parse error")
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("hyperliquid liq: disconnected, retry in %.1fs", delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
