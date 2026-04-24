"""Bybit REST OHLCV collector — 1m/15m/1h candles for BTCUSDT."""
from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from market_collector.config import (
    BYBIT_KLINE_URL, OHLCV_BACKFILL_CANDLES, OHLCV_INTERVALS, SYMBOL,
)

logger = logging.getLogger(__name__)
OHLCV_HEADERS = ["ts_utc", "open", "high", "low", "close", "volume"]


def _ms_to_utc(ms: int | str) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def _iso_to_ms(ts_utc: str) -> int:
    dt = datetime.fromisoformat(ts_utc)
    return int(dt.timestamp() * 1000)


def _fetch_klines(interval: str, limit: int = 200) -> list[list]:
    """Fetch candles from Bybit newest-first; skip [0] (incomplete current candle)."""
    resp = requests.get(
        BYBIT_KLINE_URL,
        params={
            "category": "linear",
            "symbol": SYMBOL,
            "interval": interval,
            "limit": limit + 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    candles = resp.json().get("result", {}).get("list", [])
    return candles[1:]  # drop incomplete current candle; list is descending


def _read_last_ts_ms(path: Path) -> int:
    """Return epoch-ms of the last row in CSV, or 0 if empty/missing."""
    if not path.exists():
        return 0
    try:
        last_ts = None
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # skip header
            for row in reader:
                if row:
                    last_ts = row[0]
        return _iso_to_ms(last_ts) if last_ts else 0
    except Exception:
        return 0


def _append_candles(path: Path, candles_asc: list[list]) -> None:
    """Append candles (chronological order) to CSV, writing header if new file."""
    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(OHLCV_HEADERS)
        for c in candles_asc:
            # Bybit format: [ts_ms, open, high, low, close, volume, ...]
            writer.writerow([_ms_to_utc(c[0]), c[1], c[2], c[3], c[4], c[5]])
        fh.flush()


class OhlcvCollector:
    def __init__(self, stop_event: threading.Event) -> None:
        self._stop = stop_event
        self._last_ts_ms: dict[str, int] = {}

    def _fetch_and_append(self, label: str, interval: str, path: Path) -> None:
        try:
            candles_desc = _fetch_klines(interval, OHLCV_BACKFILL_CANDLES)
            last_ms = self._last_ts_ms.get(label, 0)
            new = [c for c in candles_desc if int(c[0]) > last_ms]
            if not new:
                return
            new.sort(key=lambda c: int(c[0]))
            _append_candles(path, new)
            self._last_ts_ms[label] = int(new[-1][0])
            logger.info("ohlcv.%s: +%d candles (last=%s)", label, len(new), _ms_to_utc(new[-1][0]))
        except Exception:
            logger.exception("ohlcv.%s: fetch failed", label)

    def _collect_loop(self, label: str, interval: str, cycle_sec: int, path: Path) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            self._fetch_and_append(label, interval, path)
            elapsed = time.monotonic() - t0
            self._stop.wait(max(0.0, cycle_sec - elapsed))

    def start_all(self) -> list[threading.Thread]:
        threads: list[threading.Thread] = []
        for label, interval, cycle_sec, path in OHLCV_INTERVALS:
            # Initialize last_ts from existing file
            self._last_ts_ms[label] = _read_last_ts_ms(path)
            # Backfill on startup (synchronous, before starting loop thread)
            self._fetch_and_append(label, interval, path)
            t = threading.Thread(
                target=self._collect_loop,
                args=(label, interval, cycle_sec, path),
                daemon=True,
                name=f"ohlcv-{label}",
            )
            t.start()
            threads.append(t)
        return threads
