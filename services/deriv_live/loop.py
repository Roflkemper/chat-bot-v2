"""Live deriv poll loop. See package __init__ for context."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

DERIV_LIVE_PATH = Path("state/deriv_live.json")
HISTORY_PATH = Path("state/deriv_live_history.jsonl")  # append-only за час для расчёта delta
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
POLL_INTERVAL_SEC = 300  # 5 min


def _binance_get(path: str, params: dict[str, Any], timeout: float = 10) -> Any | None:
    url = f"https://fapi.binance.com{path}"
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("deriv_live.http_status code=%d path=%s", resp.status_code, path)
            return None
        return resp.json()
    except requests.RequestException:
        logger.exception("deriv_live.http_failed path=%s", path)
        return None


def _fetch_oi(symbol: str) -> dict | None:
    """GET /fapi/v1/openInterest (current OI in BTC)."""
    data = _binance_get("/fapi/v1/openInterest", {"symbol": symbol})
    if not data:
        return None
    try:
        return {"oi_native": float(data["openInterest"]), "ts_ms": int(data.get("time", 0))}
    except (KeyError, ValueError, TypeError):
        return None


def _fetch_funding(symbol: str) -> dict | None:
    """GET /fapi/v1/premiumIndex (current funding + premium + mark)."""
    data = _binance_get("/fapi/v1/premiumIndex", {"symbol": symbol})
    if not data:
        return None
    try:
        return {
            "funding_rate_8h": float(data.get("lastFundingRate", 0)),
            "next_funding_time_ms": int(data.get("nextFundingTime", 0)),
            "mark_price": float(data.get("markPrice", 0)),
            "index_price": float(data.get("indexPrice", 0)),
        }
    except (ValueError, TypeError):
        return None


def _fetch_oi_hist_1h(symbol: str) -> float | None:
    """GET /futures/data/openInterestHist limit=2 → compute 1h-ago OI for delta."""
    data = _binance_get(
        "/futures/data/openInterestHist",
        {"symbol": symbol, "period": "1h", "limit": 2},
    )
    if not data or not isinstance(data, list) or len(data) < 1:
        return None
    try:
        # data[0] = oldest, data[-1] = newest
        # We want oldest one (1h ago)
        return float(data[0].get("sumOpenInterest", 0))
    except (KeyError, ValueError, TypeError):
        return None


def build_snapshot() -> dict:
    """Build single snapshot of all 3 symbols. Returns dict ready to write."""
    out = {
        "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for sym in SYMBOLS:
        oi = _fetch_oi(sym)
        funding = _fetch_funding(sym)
        oi_1h_ago = _fetch_oi_hist_1h(sym)

        sym_data = {}
        if oi:
            sym_data["oi_native"] = oi["oi_native"]
            if oi_1h_ago and oi_1h_ago > 0:
                pct = (oi["oi_native"] / oi_1h_ago - 1) * 100
                sym_data["oi_change_1h_pct"] = round(pct, 3)
        if funding:
            sym_data["funding_rate_8h"] = funding["funding_rate_8h"]
            sym_data["mark_price"] = funding["mark_price"]
            sym_data["index_price"] = funding["index_price"]
            if funding["index_price"] > 0:
                premium = (funding["mark_price"] / funding["index_price"] - 1) * 100
                sym_data["premium_pct"] = round(premium, 4)
            sym_data["next_funding_time_ms"] = funding["next_funding_time_ms"]

        if sym_data:
            out[sym] = sym_data
        else:
            out[sym] = {"_error": "fetch_failed"}

    return out


def write_snapshot(snapshot: dict) -> None:
    DERIV_LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DERIV_LIVE_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # Append history line for trend analysis
    try:
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("deriv_live.history_write_failed")


async def deriv_live_loop(stop_event: asyncio.Event, *, interval_sec: int = POLL_INTERVAL_SEC) -> None:
    """Async loop. Polls Binance REST every interval_sec until stop_event."""
    logger.info("deriv_live.loop.start interval=%ds symbols=%s", interval_sec, SYMBOLS)
    while not stop_event.is_set():
        t0 = time.time()
        try:
            snap = build_snapshot()
            write_snapshot(snap)
            errors = [k for k, v in snap.items() if isinstance(v, dict) and v.get("_error")]
            logger.info(
                "deriv_live.snapshot ok=%d errors=%d elapsed=%.1fs",
                len(SYMBOLS) - len(errors), len(errors), time.time() - t0,
            )
        except Exception:
            logger.exception("deriv_live.poll_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass
    logger.info("deriv_live.loop.stopped")
