"""WebSocket liquidation streams — Bybit + Binance BTCUSDT."""
from __future__ import annotations

import csv
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from market_collector.config import (
    BINANCE_WS_URL,
    BYBIT_WS_URL,
    LIQUIDATIONS_CSV,
    WS_RECONNECT_BASE_SEC,
    WS_RECONNECT_MAX_SEC,
)

logger = logging.getLogger(__name__)
LIQ_HEADERS = ["ts_utc", "exchange", "side", "qty", "price"]
_lock = threading.Lock()


def _ts_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_liq(row: dict) -> None:
    LIQUIDATIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        is_new = not LIQUIDATIONS_CSV.exists()
        with LIQUIDATIONS_CSV.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LIQ_HEADERS, extrasaction="ignore")
            if is_new:
                writer.writeheader()
            writer.writerow(row)
            fh.flush()


def _run_bybit_ws(stop_event: threading.Event) -> None:
    import websocket  # websocket-client

    backoff = WS_RECONNECT_BASE_SEC
    while not stop_event.is_set():
        try:
            ws = websocket.WebSocket()
            ws.connect(BYBIT_WS_URL, timeout=10)
            ws.send(json.dumps({"op": "subscribe", "args": ["allLiquidation.BTCUSDT"]}))
            backoff = WS_RECONNECT_BASE_SEC
            logger.info("bybit_ws.connected")
            while not stop_event.is_set():
                try:
                    msg = ws.recv()
                    if not msg:
                        continue
                    data = json.loads(msg)
                    if data.get("topic") == "allLiquidation.BTCUSDT":
                        liq = data.get("data", {})
                        # Bybit: side="Sell" means a long position was liquidated
                        side = "long" if str(liq.get("side", "")).lower() == "sell" else "short"
                        _write_liq({
                            "ts_utc": _ts_utc_now(),
                            "exchange": "bybit",
                            "side": side,
                            "qty": liq.get("size", ""),
                            "price": liq.get("price", ""),
                        })
                except Exception:
                    logger.warning("bybit_ws.recv_error", exc_info=True)
                    break
            ws.close()
        except Exception:
            logger.warning("bybit_ws.connect_failed backoff=%.1fs", backoff, exc_info=True)
            stop_event.wait(backoff)
            backoff = min(backoff * 2, WS_RECONNECT_MAX_SEC)


def _run_binance_ws(stop_event: threading.Event) -> None:
    import websocket  # websocket-client

    backoff = WS_RECONNECT_BASE_SEC
    while not stop_event.is_set():
        try:
            ws = websocket.WebSocket()
            ws.connect(BINANCE_WS_URL, timeout=10)
            backoff = WS_RECONNECT_BASE_SEC
            logger.info("binance_ws.connected")
            while not stop_event.is_set():
                try:
                    msg = ws.recv()
                    if not msg:
                        continue
                    data = json.loads(msg)
                    order = data.get("o", {})
                    # Binance: S="SELL" means long liquidation
                    side = "long" if order.get("S") == "SELL" else "short"
                    _write_liq({
                        "ts_utc": _ts_utc_now(),
                        "exchange": "binance",
                        "side": side,
                        "qty": order.get("q", ""),
                        "price": order.get("p", ""),
                    })
                except Exception:
                    logger.warning("binance_ws.recv_error", exc_info=True)
                    break
            ws.close()
        except Exception:
            logger.warning("binance_ws.connect_failed backoff=%.1fs", backoff, exc_info=True)
            stop_event.wait(backoff)
            backoff = min(backoff * 2, WS_RECONNECT_MAX_SEC)


def start_liquidation_streams(stop_event: threading.Event) -> list[threading.Thread]:
    threads: list[threading.Thread] = []
    for name, target in [("liq-bybit", _run_bybit_ws), ("liq-binance", _run_binance_ws)]:
        t = threading.Thread(target=target, args=(stop_event,), daemon=True, name=name)
        t.start()
        threads.append(t)
    return threads
