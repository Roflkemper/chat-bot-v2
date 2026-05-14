"""Watchlist async loop — раз в 60 сек проверяет rules и шлёт alerts."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .rules import load_rules, save_rules, evaluate_rules

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 60
DEDUP_COOLDOWN_SEC = 1800  # 30 мин между повторными alerts одного правила


async def watchlist_loop(stop_event: asyncio.Event, *, send_fn=None, interval_sec: int = POLL_INTERVAL_SEC) -> None:
    logger.info("watchlist.start interval=%ds", interval_sec)
    while not stop_event.is_set():
        try:
            rules = load_rules()
            fired = evaluate_rules(rules)
            if fired:
                now = datetime.now(timezone.utc)
                changed = False
                for rule, value in fired:
                    # Dedup: не шлём чаще чем раз в 30 мин
                    if rule.last_fired:
                        try:
                            last = datetime.fromisoformat(rule.last_fired.replace("Z", "+00:00"))
                            if (now - last).total_seconds() < DEDUP_COOLDOWN_SEC:
                                continue
                        except ValueError:
                            pass
                    text = (
                        f"🔔 WATCHLIST правило сработало\n"
                        f"  {rule.field} {rule.op} {rule.threshold}\n"
                        f"  Текущее значение: {value:.4f}\n"
                        f"  Rule ID: {rule.id}"
                    )
                    logger.info("watchlist.fired rule=%s value=%.4f", rule.id, value)
                    if send_fn:
                        try:
                            send_fn(text)
                        except Exception:
                            logger.exception("watchlist.send_failed")
                    rule.last_fired = now.isoformat(timespec="seconds")
                    rule.fire_count += 1
                    changed = True
                if changed:
                    save_rules(rules)
        except Exception:
            logger.exception("watchlist.tick_failed")

        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass

    logger.info("watchlist.stopped")
