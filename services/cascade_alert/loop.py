"""Live cascade alert loop. См. package __init__ для контекста."""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"
DEDUP_PATH = ROOT / "state" / "cascade_alert_dedup.json"

POLL_INTERVAL_SEC = 60
WINDOW_MINUTES = 5
THRESHOLD_BTC = 5.0  # main threshold (high-confidence edge)
THRESHOLD_BTC_MEDIUM = 2.0  # medium threshold (separate alert with weaker edge)
DEDUP_COOLDOWN_SEC = 1800  # 30 min between alerts per side

# Backtest results (POST_LIQUIDATION_CASCADE_2026-05-07.md, n=103/102)
EDGE_TEXT = {
    ("long", 5.0): {
        "title": "⚡ КАСКАД LONG-ликвидаций (>=5 BTC за 5 мин)",
        "stats": "Исторически (n=103, фев-июнь 2024):\n"
                 "  +4ч: 67% случаев цена выше, средний +0.46%\n"
                 "  +12ч: 73% случаев выше, средний +1.14%\n"
                 "  +24ч: 64%, средний +1.50%",
        "play": "СЕТАП: BUY на стабилизации после каскада\n"
                "Цель: +1.14% (12ч)\n"
                "Стоп: -0.5%\n"
                "EV после комиссий: ~+0.5% за сделку",
    },
    ("long", 2.0): {
        "title": "⚡ Каскад LONG-ликвидаций (>=2 BTC, среднее)",
        "stats": "Исторически (n=297):\n"
                 "  +12ч: 63% случаев выше, средний +0.68%",
        "play": "Слабее основного сетапа — рассматривай как контекст.",
    },
    ("short", 5.0): {
        "title": "⚡ КАСКАД SHORT-ликвидаций (>=5 BTC за 5 мин)",
        "stats": "Исторически (n=102):\n"
                 "  +24ч: 61% случаев выше, средний +1.02%\n"
                 "  +12ч: 57%, средний +0.29% (слабее)",
        "play": "Тренд продолжается вверх обычно.\n"
                "Если есть SHORT-позиция — НЕ агрессивно докидывать.\n"
                "Sell pressure высокая, но реверс маловероятен.",
    },
    ("short", 2.0): {
        "title": "⚡ Каскад SHORT-ликвидаций (>=2 BTC, среднее)",
        "stats": "Исторически (n=296):\n"
                 "  +24ч: 61% выше, средний +1.06%",
        "play": "Контекст для оценки давления на шортов.",
    },
}


def _load_dedup() -> dict:
    if not DEDUP_PATH.exists():
        return {}
    try:
        return json.loads(DEDUP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_dedup(d: dict) -> None:
    DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        DEDUP_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("cascade_alert.dedup_save_failed")


def _liquidation_window_sums(now_utc: datetime, window_min: int) -> tuple[float, float, float | None]:
    """Read last N min from liquidations.csv. Returns (long_btc, short_btc, last_price)."""
    if not LIQ_CSV.exists():
        return 0.0, 0.0, None
    cutoff = now_utc - timedelta(minutes=window_min)
    long_btc = 0.0
    short_btc = 0.0
    last_price = None
    try:
        with LIQ_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_str = row.get("ts_utc", "")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
                try:
                    qty = float(row.get("qty") or 0)
                    price = float(row.get("price") or 0)
                except (ValueError, TypeError):
                    continue
                if qty <= 0:
                    continue
                side = (row.get("side") or "").lower()
                if side == "long":
                    long_btc += qty
                elif side == "short":
                    short_btc += qty
                if price > 0:
                    last_price = price
    except OSError:
        logger.exception("cascade_alert.liq_read_failed")
    return long_btc, short_btc, last_price


def _format_alert(side: str, threshold: float, qty_btc: float, last_price: float | None) -> str:
    info = EDGE_TEXT.get((side, threshold)) or EDGE_TEXT.get((side, 5.0))
    lines = [info["title"]]
    lines.append("")
    lines.append(f"Ликвидировано: {qty_btc:.2f} BTC за {WINDOW_MINUTES} мин")
    if last_price:
        lines.append(f"Цена: ~${last_price:,.0f}")
    lines.append("")
    lines.append(info["stats"])
    lines.append("")
    lines.append(info["play"])
    return "\n".join(lines)


async def cascade_alert_loop(stop_event: asyncio.Event, *, send_fn=None, interval_sec: int = POLL_INTERVAL_SEC) -> None:
    """Async loop. Каждые 60 сек проверяет cascade в last 5min window.

    send_fn: callable(text) — будет вызвана с alert текстом если каскад обнаружен.
    """
    if send_fn is None:
        logger.warning("cascade_alert.no_send_fn — alerts будут только в логе")

    logger.info("cascade_alert.start interval=%ds threshold_high=%.1fBTC threshold_medium=%.1fBTC window=%dmin",
                interval_sec, THRESHOLD_BTC, THRESHOLD_BTC_MEDIUM, WINDOW_MINUTES)

    while not stop_event.is_set():
        try:
            now = datetime.now(timezone.utc)
            long_btc, short_btc, last_price = _liquidation_window_sums(now, WINDOW_MINUTES)
            dedup = _load_dedup()

            for side, qty in (("long", long_btc), ("short", short_btc)):
                # Определяем threshold (high имеет приоритет)
                if qty >= THRESHOLD_BTC:
                    threshold = THRESHOLD_BTC
                elif qty >= THRESHOLD_BTC_MEDIUM:
                    threshold = THRESHOLD_BTC_MEDIUM
                else:
                    continue

                key = f"{side}_{threshold}"
                last_sent_str = dedup.get(key)
                if last_sent_str:
                    try:
                        last_sent = datetime.fromisoformat(last_sent_str.replace("Z", "+00:00"))
                        if (now - last_sent).total_seconds() < DEDUP_COOLDOWN_SEC:
                            continue
                    except ValueError:
                        pass

                # Триггер alert
                text = _format_alert(side, threshold, qty, last_price)
                logger.info("cascade_alert.triggered side=%s threshold=%.1f qty=%.2f", side, threshold, qty)
                if send_fn is not None:
                    try:
                        send_fn(text)
                    except Exception:
                        logger.exception("cascade_alert.send_failed")

                # Auto paper trade (B2): открываем виртуальную позицию для
                # forward-validation edge'а. Через 1-2 месяца проверим точность.
                try:
                    from services.paper_trader.cascade_trade import open_cascade_trade
                    trade = open_cascade_trade(side, threshold, qty, last_price or 0)
                    if trade and send_fn:
                        send_fn(
                            f"📋 Paper trade открыт автоматически\n"
                            f"trade_id: {trade['trade_id']}\n"
                            f"{trade['side'].upper()} @ ${trade['entry']:,.0f} | TP ${trade['tp1']:,.0f} | SL ${trade['sl']:,.0f}"
                        )
                except Exception:
                    logger.exception("cascade_alert.paper_trade_failed")

                dedup[key] = now.isoformat(timespec="seconds")
                _save_dedup(dedup)
        except Exception:
            logger.exception("cascade_alert.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass

    logger.info("cascade_alert.stopped")
