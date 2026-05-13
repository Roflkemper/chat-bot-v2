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
THRESHOLD_BTC_MEGA = 10.0   # mega-spike: 10+ BTC in 1 min — rare reversal indicator
MEGA_WINDOW_MINUTES = 1    # tight window for mega tier
DEDUP_COOLDOWN_SEC = 1800  # 30 min between alerts per side
MEGA_DEDUP_COOLDOWN_SEC = 3600  # 1h cooldown for rare mega events

# Predicted +12h % move (from EDGE_TEXT stats). Used by accuracy_tracker.
PREDICTED_PCT_12H = {
    ("long", 5.0): 1.14,
    ("long", 2.0): 0.68,
    ("long", 10.0): 2.0,   # rough estimate for mega
    ("short", 5.0): 0.29,
    ("short", 2.0): 1.06,
    ("short", 10.0): -2.0,  # mega short = expected drop
}

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
    ("long", 10.0): {
        "title": "🌋 МЕГА-СПАЙК LONG-ликвидаций (>=10 BTC за 1 мин)",
        "stats": "Очень редкое событие — обычно signal реверса вверх.\n"
                 "Таких спайков ~5-10 в год, корреляция с low в 6-12ч высокая.",
        "play": "СЕТАП: следить за стабилизацией ниже current\n"
                "Через 6-12ч обычно отскок 1.5-3%\n"
                "БУДЬ ОСТОРОЖЕН — может быть продолжение каскада",
    },
    ("short", 10.0): {
        "title": "🌋 МЕГА-СПАЙК SHORT-ликвидаций (>=10 BTC за 1 мин)",
        "stats": "Очень редкое — local high индикатор.\n"
                 "Часто перед коррекцией 2-5%.",
        "play": "СЕТАП: SHORT с tight stop на стабилизации\n"
                "Цель: -2% за 12-24ч\n"
                "Стоп: +0.8%",
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


EVAL_INTERVAL_SEC = 3600  # evaluate_pending запускается раз в час
MARKET_1M_CSV = ROOT / "market_live" / "market_1m.csv"


def _price_at(target: datetime) -> float | None:
    """Lookup close-price for target ts (±2 min). Reads market_1m.csv tail."""
    if not MARKET_1M_CSV.exists():
        return None
    target_floor = target.replace(second=0, microsecond=0)
    window = (target_floor - timedelta(minutes=2), target_floor + timedelta(minutes=2))
    best: tuple[float, float] | None = None  # (abs_dt_sec, close)
    try:
        with MARKET_1M_CSV.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = datetime.fromisoformat(row["ts_utc"])
                except (ValueError, KeyError):
                    continue
                if ts < window[0] or ts > window[1]:
                    continue
                try:
                    close = float(row["close"])
                except (ValueError, KeyError):
                    continue
                dt_sec = abs((ts - target_floor).total_seconds())
                if best is None or dt_sec < best[0]:
                    best = (dt_sec, close)
    except OSError:
        return None
    return best[1] if best else None


async def cascade_accuracy_eval_loop(stop_event: asyncio.Event,
                                     interval_sec: int = EVAL_INTERVAL_SEC) -> None:
    """Background tick: evaluates pending cascade prognoses every hour."""
    from services.cascade_alert.accuracy_tracker import evaluate_pending
    logger.info("cascade_accuracy_eval.start interval=%ds", interval_sec)
    while not stop_event.is_set():
        try:
            n = evaluate_pending(get_price_fn=_price_at)
            if n > 0:
                logger.info("cascade_accuracy_eval.filled n=%d", n)
        except Exception:
            logger.exception("cascade_accuracy_eval.tick_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
    logger.info("cascade_accuracy_eval.stopped")


def _record_cascade_prognosis(side: str, threshold: float, qty_btc: float,
                              last_price: float | None, now: datetime) -> None:
    """Best-effort journal write for accuracy tracker. Never raises."""
    if last_price is None or last_price <= 0:
        return
    try:
        from services.cascade_alert.accuracy_tracker import CascadePrognosis, record_prognosis
        predicted = PREDICTED_PCT_12H.get((side, threshold), 0.0)
        record_prognosis(CascadePrognosis(
            ts=now.isoformat(timespec="seconds"),
            direction=side,
            threshold_btc=float(threshold),
            spot_price=float(last_price),
            qty_btc=float(qty_btc),
            predicted_pct_12h=float(predicted),
        ))
    except Exception:
        logger.exception("cascade_alert.record_prognosis_failed")


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
            # Mega tier: tighter window for rare 10+ BTC bursts
            mega_long, mega_short, _ = _liquidation_window_sums(now, MEGA_WINDOW_MINUTES)
            dedup = _load_dedup()

            # MEGA tier (10+ BTC in 1 min) — fired first, highest priority
            for side, mega_qty in (("long", mega_long), ("short", mega_short)):
                if mega_qty < THRESHOLD_BTC_MEGA:
                    continue
                key = f"{side}_{THRESHOLD_BTC_MEGA}_mega"
                last_sent_str = dedup.get(key)
                if last_sent_str:
                    try:
                        last_sent = datetime.fromisoformat(last_sent_str.replace("Z", "+00:00"))
                        if (now - last_sent).total_seconds() < MEGA_DEDUP_COOLDOWN_SEC:
                            continue
                    except ValueError:
                        pass
                text = _format_alert(side, THRESHOLD_BTC_MEGA, mega_qty, last_price)
                logger.info("cascade_alert.MEGA side=%s qty=%.2f", side, mega_qty)
                if send_fn is not None:
                    try:
                        send_fn(text)
                    except Exception:
                        logger.exception("cascade_alert.mega_send_failed")
                _record_cascade_prognosis(side, THRESHOLD_BTC_MEGA, mega_qty, last_price, now)
                dedup[key] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

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
                _record_cascade_prognosis(side, threshold, qty, last_price, now)

                # Auto paper trade (B2): originally opened a virtual position
                # on every cascade. Disabled 2026-05-08 — live data showed
                # 0W/3L (-90 USD) over 5 days, contradicting the n=103 backtest
                # (73% pct_up). Likely cause: paper trade fires 5+ minutes
                # after the cascade peak, by which time the bounce has already
                # started or finished. Re-enable via env CASCADE_AUTO_OPEN=1
                # once thresholds are re-tuned (e.g. higher BTC qty bar).
                import os as _os
                if _os.environ.get("CASCADE_AUTO_OPEN", "0") == "1":
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
