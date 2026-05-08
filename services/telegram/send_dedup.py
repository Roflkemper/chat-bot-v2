"""Persistent file-based dedup для Telegram outgoing messages.

Защищает от дублей вне зависимости от source (multiple workers, restart, race condition).
Применяется к LEVEL_BREAK / RSI_EXTREME / любым повторяющимся alert текстам.

Usage:
    from services.telegram.send_dedup import should_send, mark_sent

    if should_send(chat_id, text):
        bot.send_message(chat_id, text)
        mark_sent(chat_id, text)

Persistence: state/telegram_sent_dedup.json
TTL: каждый entry хранится TTL_SECONDS (default 1800 = 30 min)
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEDUP_PATH = Path("state/telegram_sent_dedup.json")
TTL_SECONDS = 1800  # 30 min — same as LEVEL_BREAK cooldown

_lock = threading.Lock()


def _key(chat_id: int, text: str) -> str:
    h = hashlib.sha1(f"{chat_id}|{text}".encode("utf-8")).hexdigest()[:16]
    return h


def _load() -> dict:
    if not DEDUP_PATH.exists():
        return {}
    try:
        return json.loads(DEDUP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(d: dict) -> None:
    DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        DEDUP_PATH.write_text(json.dumps(d), encoding="utf-8")
    except OSError as exc:
        logger.warning("send_dedup.save_failed: %s", exc)


def _prune(d: dict, now: float) -> dict:
    cutoff = now - TTL_SECONDS
    return {k: ts for k, ts in d.items() if ts >= cutoff}


def should_send(chat_id: int, text: str) -> bool:
    """Return True if (chat_id, text) hasn't been sent in last TTL_SECONDS."""
    with _lock:
        now = time.time()
        d = _prune(_load(), now)
        k = _key(chat_id, text)
        if k in d:
            logger.info(
                "telegram.send_dedup.suppressed chat_id=%s ago_sec=%.0f text_prefix=%s",
                chat_id, now - d[k], text[:60],
            )
            return False
        return True


def mark_sent(chat_id: int, text: str) -> None:
    """Record that (chat_id, text) was sent at now."""
    with _lock:
        now = time.time()
        d = _prune(_load(), now)
        k = _key(chat_id, text)
        d[k] = now
        _save(d)
