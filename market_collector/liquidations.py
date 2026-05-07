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
    """Bybit liquidation WS с keepalive ping каждые 20с (per Bybit docs)."""
    import websocket  # websocket-client

    backoff = WS_RECONNECT_BASE_SEC
    while not stop_event.is_set():
        try:
            ws = websocket.WebSocket()
            ws.connect(BYBIT_WS_URL, timeout=10)
            # Read timeout — без него recv() блокируется навсегда, idle connection
            # закрывается сервером и наша сторона не узнаёт.
            ws.settimeout(30)
            ws.send(json.dumps({"op": "subscribe", "args": ["allLiquidation.BTCUSDT"]}))
            backoff = WS_RECONNECT_BASE_SEC
            last_ping = time.time()
            logger.info("bybit_ws.connected")
            while not stop_event.is_set():
                # Keepalive: Bybit требует ping каждые 20s, иначе закрывает.
                if time.time() - last_ping >= 20:
                    try:
                        ws.send(json.dumps({"op": "ping"}))
                        last_ping = time.time()
                    except Exception:
                        logger.warning("bybit_ws.ping_failed", exc_info=True)
                        break
                try:
                    msg = ws.recv()
                except (websocket.WebSocketTimeoutException, TimeoutError, OSError):
                    # Read timeout — норма, продолжаем (даём шанс отправить ping).
                    # OSError ловит низкоуровневые SSL timeouts.
                    continue
                if not msg:
                    continue
                try:
                    data = json.loads(msg)
                    # Pong от Bybit на наш ping — пропускаем тихо.
                    if data.get("op") == "pong" or data.get("ret_msg") == "pong":
                        continue
                    if data.get("topic") == "allLiquidation.BTCUSDT":
                        liq = data.get("data", {})
                        side = "long" if str(liq.get("side", "")).lower() == "sell" else "short"
                        _write_liq({
                            "ts_utc": _ts_utc_now(),
                            "exchange": "bybit",
                            "side": side,
                            "qty": liq.get("size", ""),
                            "price": liq.get("price", ""),
                        })
                except Exception:
                    logger.warning("bybit_ws.parse_error", exc_info=True)
                    continue  # parse-ошибка не должна закрывать соединение
            try:
                ws.close()
            except Exception:
                pass
        except Exception:
            logger.warning("bybit_ws.connect_failed backoff=%.1fs", backoff, exc_info=True)
            stop_event.wait(backoff)
            backoff = min(backoff * 2, WS_RECONNECT_MAX_SEC)


def _run_binance_ws(stop_event: threading.Event) -> None:
    """Binance forceOrder WS — отвечаем pong на их ping (per Binance docs)."""
    import websocket  # websocket-client

    backoff = WS_RECONNECT_BASE_SEC
    while not stop_event.is_set():
        try:
            ws = websocket.WebSocket()
            ws.connect(BINANCE_WS_URL, timeout=10)
            ws.settimeout(190)  # Binance ping interval ≈ 3 min
            backoff = WS_RECONNECT_BASE_SEC
            logger.info("binance_ws.connected")
            while not stop_event.is_set():
                try:
                    opcode, frame_data = ws.recv_data()
                except (websocket.WebSocketTimeoutException, TimeoutError, OSError):
                    # Read timeout — норма (даём шанс отправить pong/продолжить).
                    # OSError ловит низкоуровневые SSL timeouts на Windows.
                    continue
                # Binance шлёт ping (opcode 0x9) — отвечаем pong (opcode 0xA)
                if opcode == 0x9:
                    try:
                        ws.pong(frame_data)
                    except Exception:
                        logger.warning("binance_ws.pong_failed", exc_info=True)
                        break
                    continue
                if opcode != 0x1 and opcode != 0x2:  # not text/binary
                    continue
                if not frame_data:
                    continue
                try:
                    data = json.loads(frame_data)
                    order = data.get("o", {})
                    side = "long" if order.get("S") == "SELL" else "short"
                    _write_liq({
                        "ts_utc": _ts_utc_now(),
                        "exchange": "binance",
                        "side": side,
                        "qty": order.get("q", ""),
                        "price": order.get("p", ""),
                    })
                except Exception:
                    logger.warning("binance_ws.parse_error", exc_info=True)
                    continue
            try:
                ws.close()
            except Exception:
                pass
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
