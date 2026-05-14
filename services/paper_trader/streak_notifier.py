"""Streak notifier — шлёт TG-алерт при переходе streak_guard в pause/resume.

Хранит состояние в state/paper_trader_streak_notify.json чтобы не спамить
оператора повторными уведомлениями каждые 60s loop-tick.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from services.paper_trader.streak_guard import should_pause

logger = logging.getLogger(__name__)

STATE_PATH = Path("state/paper_trader_streak_notify.json")


def _read_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict, path: Path = STATE_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.exception("streak_notifier.write_failed path=%s", path)


def check_and_notify(
    send_fn: Callable[[str], None] | None,
    *,
    now: datetime | None = None,
    state_path: Path = STATE_PATH,
) -> dict:
    """Сравнивает текущее paused с сохранённым. Шлёт TG при переходе.

    Returns dict с {"paused": bool, "streak": int, "notified": bool}.
    """
    paused, streak, reason = should_pause(now=now)
    prev = _read_state(state_path)
    prev_paused = bool(prev.get("paused", False))
    notified = False

    if paused and not prev_paused:
        # OFF → ON: пауза включилась
        msg = (
            "🛑 paper_trader приостановлен\n"
            f"Причина: {reason}\n"
            "Авто-разблок: либо TP, либо 3h timeout."
        )
        if send_fn:
            try:
                send_fn(msg)
                notified = True
            except Exception:
                logger.exception("streak_notifier.send_failed")
        logger.info("streak_notifier.activated streak=%d", streak)
    elif (not paused) and prev_paused:
        # ON → OFF: пауза снялась
        prev_streak = int(prev.get("streak", 0))
        msg = (
            "✅ paper_trader возобновлён\n"
            f"Streak до этого: {prev_streak} SL подряд.\n"
            f"Текущая причина разблока: {reason or 'TP закрыл серию'}"
        )
        if send_fn:
            try:
                send_fn(msg)
                notified = True
            except Exception:
                logger.exception("streak_notifier.send_failed")
        logger.info("streak_notifier.deactivated prev_streak=%d", prev_streak)

    _write_state(
        {"paused": paused, "streak": streak, "ts": (now or datetime.now(timezone.utc)).isoformat()},
        state_path,
    )
    return {"paused": paused, "streak": streak, "notified": notified}
