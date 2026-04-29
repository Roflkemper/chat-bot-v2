"""Binance futures liquidation collector — !forceOrder@arr stream.

Rate-limit note: Binance aggregates forced-order events and delivers them at most once per second
per symbol on the !forceOrder@arr stream. Multiple liquidations within the same second are batched
into a single message, so the Feature Engine must treat records from this source as coarse-grained.
source_rate_limited=True is written to parquet to signal this to downstream consumers.
"""
from __future__ import annotations

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
    LIVE_PATH,
    SYMBOLS,
)
from collectors.storage import get_buffer

log = logging.getLogger(__name__)

_STREAM = "!forceOrder@arr"
_URL = f"{BINANCE_WS_BASE}?streams={_STREAM}"

_SYMBOL_SET = set(SYMBOLS)

# Log a warning if no events received for this many seconds (silence detection)
_SILENCE_WARN_S = 300


def _ensure_output_dirs() -> None:
    """Create output directories for all symbols at startup (don't wait for first event)."""
    for symbol in SYMBOLS:
        out_dir = LIVE_PATH / "liquidations" / "binance" / symbol
        out_dir.mkdir(parents=True, exist_ok=True)
    log.info("binance liq: output dirs ready under %s/liquidations/binance/", LIVE_PATH)


def _parse(msg: dict) -> list[dict] | None:
    """Parse forceOrder message → list of liquidation rows (filtered to SYMBOLS)."""
    data = msg.get("data", {})
    order = data.get("o", {})
    symbol = order.get("s", "")
    if symbol not in _SYMBOL_SET:
        return None

    side_raw = order.get("S", "")   # "SELL" = long liq, "BUY" = short liq
    side = "long" if side_raw == "SELL" else "short"
    qty = float(order.get("q", 0) or 0)
    price = float(order.get("ap", 0) or 0)   # average price
    ts_ms = int(order.get("T", time.time() * 1000))

    return [{
        "ts_ms": ts_ms,
        "exchange": "binance",
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "value_usd": qty * price,
        "source_rate_limited": True,
    }]


async def run() -> None:
    import asyncio
    _ensure_output_dirs()
    backoff = BACKOFF_MIN_S
    while True:
        try:
            async with websockets.connect(_URL, ping_interval=30) as ws:
                log.info("binance liq: connected")
                backoff = BACKOFF_MIN_S
                events_total = 0
                last_event_t = time.monotonic()
                last_silence_warn_t = time.monotonic()
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        rows = _parse(msg)
                        if rows:
                            events_total += len(rows)
                            last_event_t = time.monotonic()
                            for row in rows:
                                buf = get_buffer("binance", row["symbol"], "liquidations")
                                buf.append(row)
                                if buf.should_flush():
                                    buf.flush()
                                    log.debug(
                                        "binance liq: flushed %s total_events=%d",
                                        row["symbol"], events_total,
                                    )
                        else:
                            # Periodic silence warning so we know the stream is alive but quiet
                            now = time.monotonic()
                            if now - last_silence_warn_t >= _SILENCE_WARN_S:
                                silent_s = int(now - last_event_t)
                                log.warning(
                                    "binance liq: no matching events for %ds "
                                    "(total_events=%d, stream alive)",
                                    silent_s, events_total,
                                )
                                last_silence_warn_t = now
                    except Exception:
                        log.exception("binance liq: parse error")
        except Exception:
            jitter = random.uniform(1 - BACKOFF_JITTER, 1 + BACKOFF_JITTER)
            delay = min(backoff * jitter, BACKOFF_MAX_S)
            log.warning("binance liq: disconnected, retry in %.1fs", delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
