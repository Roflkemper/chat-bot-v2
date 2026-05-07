"""BitMEX REST poller — async loop. См. package __init__ для контекста."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ENV_LOCAL = ROOT / ".env.local"
MARGIN_AUTO_PATH = ROOT / "state" / "margin_automated.jsonl"

POLL_INTERVAL_SEC = 60
BASE_URL = "https://www.bitmex.com"


# ── Auth ──────────────────────────────────────────────────────────────

def _load_credentials() -> tuple[Optional[str], Optional[str]]:
    """Read BITMEX_API_KEY/SECRET from .env.local.

    Returns (key, secret) or (None, None) if not configured.
    """
    if not ENV_LOCAL.exists():
        return None, None
    key = None
    secret = None
    try:
        for line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k == "BITMEX_API_KEY":
                key = v
            elif k == "BITMEX_API_SECRET":
                secret = v
    except OSError:
        return None, None
    return key, secret


def _sign_request(secret: str, verb: str, path: str, expires: int, body: str = "") -> str:
    """BitMEX API HMAC-SHA256 signature."""
    msg = f"{verb}{path}{expires}{body}"
    return hmac.new(
        secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _signed_get(path: str, key: str, secret: str, timeout: float = 10) -> Any | None:
    """Authorized GET request. Returns JSON or None on error."""
    expires = int(time.time()) + 30
    sig = _sign_request(secret, "GET", path, expires)
    headers = {
        "api-expires": str(expires),
        "api-key": key,
        "api-signature": sig,
    }
    try:
        r = requests.get(BASE_URL + path, headers=headers, timeout=timeout)
        if r.status_code == 401:
            logger.error("bitmex.unauthorized — проверь API ключ в .env.local")
            return "unauthorized"
        if r.status_code != 200:
            logger.warning("bitmex.http_status code=%d path=%s body=%s", r.status_code, path, r.text[:200])
            return None
        return r.json()
    except requests.RequestException:
        logger.exception("bitmex.http_failed path=%s", path)
        return None


# ── Account snapshot ──────────────────────────────────────────────────

def fetch_account_snapshot(key: str, secret: str) -> dict | None:
    """One-shot fetch: margin + positions across XBt и USDt wallets.

    BitMEX держит отдельные кошельки для inverse (XBt = BTC nominated) и
    linear USDT (USDt = USDT). Объединяем оба в USD-эквивалент.
    """
    # XBt wallet (BTC inverse perps)
    margin_xbt = _signed_get("/api/v1/user/margin?currency=XBt", key, secret)
    if margin_xbt == "unauthorized":
        return {"_error": "unauthorized"}
    # USDt wallet (linear perps)
    margin_usdt = _signed_get("/api/v1/user/margin?currency=USDt", key, secret)
    if margin_usdt == "unauthorized":
        return {"_error": "unauthorized"}

    if isinstance(margin_xbt, list) and margin_xbt:
        margin_xbt = margin_xbt[0]
    if isinstance(margin_usdt, list) and margin_usdt:
        margin_usdt = margin_usdt[0]

    if not isinstance(margin_xbt, dict):
        margin_xbt = {}
    if not isinstance(margin_usdt, dict):
        margin_usdt = {}

    # Получаем mark price BTC
    instrument = _signed_get("/api/v1/instrument?symbol=XBTUSD&count=1", key, secret)
    btc_mark = 0.0
    if isinstance(instrument, list) and instrument:
        btc_mark = float(instrument[0].get("markPrice", 0) or 0)

    # XBt wallet: 1 unit = 1 satoshi = 1e-8 BTC
    wallet_btc = (margin_xbt.get("walletBalance", 0) or 0) / 1e8
    mb_btc = (margin_xbt.get("marginBalance", 0) or 0) / 1e8
    avail_btc = (margin_xbt.get("availableMargin", 0) or 0) / 1e8

    # USDt wallet: 1 unit = 1e-6 USDT (микро-доллары)
    wallet_usdt = (margin_usdt.get("walletBalance", 0) or 0) / 1e6
    mb_usdt = (margin_usdt.get("marginBalance", 0) or 0) / 1e6
    avail_usdt = (margin_usdt.get("availableMargin", 0) or 0) / 1e6

    # Кошельки независимы (cross-margin per-currency, не по всему аккаунту).
    # Складываем USD-эквиваленты для отображения общего, но coef считаем по
    # худшему из двух кошельков (наиболее загруженному).
    wallet_usd = wallet_btc * btc_mark + wallet_usdt
    margin_balance_usd = mb_btc * btc_mark + mb_usdt
    available_usd = avail_btc * btc_mark + avail_usdt
    used_usd = max(0.0, margin_balance_usd - available_usd)

    # Per-wallet coef
    coef_btc = (avail_btc / mb_btc) if mb_btc > 0 else 1.0
    coef_usdt = (avail_usdt / mb_usdt) if mb_usdt > 0 else 1.0
    # Худший (наименьший) coef = реальный риск-уровень
    coef = min(coef_btc, coef_usdt)
    coef = max(0.0, min(1.0, coef))

    # Positions
    positions = _signed_get("/api/v1/position?filter=%7B%22isOpen%22%3Atrue%7D", key, secret)
    if not isinstance(positions, list):
        positions = []

    pos_summary = []
    min_dist_pct = 100.0
    for p in positions:
        if not isinstance(p, dict):
            continue
        liq = p.get("liquidationPrice")
        try:
            liq_f = float(liq) if liq is not None else 0
        except (ValueError, TypeError):
            liq_f = 0
        cur_qty = p.get("currentQty", 0) or 0
        avg = p.get("avgEntryPrice", 0) or 0
        currency = (p.get("currency") or "").lower()
        unr_raw = p.get("unrealisedPnl", 0) or 0
        # Конверсия в USD: XBt → satoshis × mark; USDt → микро-доллары
        if currency == "xbt":
            unr_usd = (unr_raw / 1e8) * btc_mark if btc_mark > 0 else 0
        elif currency == "usdt":
            unr_usd = unr_raw / 1e6
        else:
            unr_usd = 0
        # homeNotional — позиция в BTC equivalent (для XBTUSDT linear contract = qty / 10000)
        home_notional = p.get("homeNotional") or 0
        if liq_f > 0 and btc_mark > 0:
            dist_pct = abs(btc_mark - liq_f) / btc_mark * 100
            if dist_pct < min_dist_pct:
                min_dist_pct = dist_pct
        else:
            dist_pct = 100.0
        pos_summary.append({
            "symbol": p.get("symbol"),
            "currentQty": cur_qty,
            "homeNotional_btc": round(float(home_notional), 4),
            "avgEntryPrice": avg,
            "liquidationPrice": liq_f,
            "unrealisedPnl_usd": round(unr_usd, 2),
            "distance_to_liq_pct": round(dist_pct, 2),
            "currency": currency,
        })

    return {
        "wallet_balance_usd": round(wallet_usd, 2),
        "margin_balance_usd": round(margin_balance_usd, 2),
        "available_margin_usd": round(available_usd, 2),
        "used_margin_usd": round(used_usd, 2),
        "margin_coefficient": round(coef, 4),
        "btc_mark_price": btc_mark,
        "min_distance_to_liq_pct": round(min_dist_pct, 2),
        "positions_count": len(pos_summary),
        "positions": pos_summary,
    }


# ── Persist ───────────────────────────────────────────────────────────

def write_margin_record(snapshot: dict) -> None:
    """Append MarginRecord-compatible line to state/margin_automated.jsonl."""
    MARGIN_AUTO_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coefficient": snapshot["margin_coefficient"],
        "available_margin_usd": snapshot["available_margin_usd"],
        "distance_to_liquidation_pct": snapshot["min_distance_to_liq_pct"],
        "source": "bitmex_api",
        # Дополнительные поля (не в стандартном MarginRecord, но полезны для диагностики)
        "wallet_balance_usd": snapshot["wallet_balance_usd"],
        "margin_balance_usd": snapshot["margin_balance_usd"],
        "used_margin_usd": snapshot["used_margin_usd"],
        "btc_mark_price": snapshot["btc_mark_price"],
        "positions_count": snapshot["positions_count"],
    }
    try:
        with MARGIN_AUTO_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("bitmex.write_failed")


# ── Loop ───────────────────────────────────────────────────────────────

async def bitmex_poll_loop(stop_event: asyncio.Event, *, interval_sec: int = POLL_INTERVAL_SEC) -> None:
    """Async loop. Polls BitMEX REST every interval_sec until stop_event.

    Если ключ не настроен или unauthorized — loop тихо завершается
    (не крашит app_runner). Достаточно положить ключ в .env.local
    и рестартануть app_runner для активации.
    """
    key, secret = _load_credentials()
    if not key or not secret:
        logger.warning("bitmex.creds_missing — .env.local нет BITMEX_API_KEY/SECRET")
        return

    logger.info("bitmex.poll.start interval=%ds", interval_sec)
    auth_failed_once = False
    consecutive_errors = 0

    while not stop_event.is_set():
        t0 = time.time()
        try:
            snap = fetch_account_snapshot(key, secret)
            if snap and snap.get("_error") == "unauthorized":
                if not auth_failed_once:
                    logger.error("bitmex.unauthorized — поллинг остановлен. Проверь API ключ.")
                    auth_failed_once = True
                # Не уходим из loop'а полностью, на случай если ключ обновят:
                # ждём 5 минут и пробуем снова
                try:
                    await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=300)
                except asyncio.TimeoutError:
                    pass
                continue
            if snap is None:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    logger.warning("bitmex.poll.5_consecutive_errors — ждём 2 мин")
                    try:
                        await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=120)
                    except asyncio.TimeoutError:
                        pass
                    consecutive_errors = 0
                # короткая пауза в случае единичной ошибки
                try:
                    await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
                except asyncio.TimeoutError:
                    pass
                continue

            consecutive_errors = 0
            auth_failed_once = False
            write_margin_record(snap)
            logger.info(
                "bitmex.poll.ok coef=%.4f available=$%.0f dist_liq=%.1f%% positions=%d elapsed=%.1fs",
                snap["margin_coefficient"], snap["available_margin_usd"],
                snap["min_distance_to_liq_pct"], snap["positions_count"],
                time.time() - t0,
            )
        except Exception:
            logger.exception("bitmex.poll.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass

    logger.info("bitmex.poll.stopped")
