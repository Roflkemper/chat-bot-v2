"""Streak guard — авто-пауза paper_trader после N SL подряд.

Эмпирика 2026-05-12: 6 paper-SL подряд за 8 часов — система продолжала
открывать сделки в неподходящий режим рынка. Этот модуль читает journal,
смотрит последние закрытия и блокирует новые входы если streak проигрышей
≥ MAX_LOSS_STREAK.

Логика разблокировки: первый же TP сбрасывает streak. Также пауза
автоматически снимается через PAUSE_HOURS часов от последнего SL —
чтобы не зависнуть навсегда.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.paper_trader import journal

logger = logging.getLogger(__name__)

# Эмпирически подобрано после audit_paper_trader_filters.py за 7 дней:
# - max=3 ложно блокировал кучу winning серий (08.05: 3 SL за 6h → 14h winning)
# - max=5 тоже резал хорошие фазы
# - max=6 + 3h pause: блокирует только настоящий кризис типа 12.05 13:00-18:30
#   (6 SL за 8h в одном режиме рынка)
MAX_LOSS_STREAK = 6
PAUSE_HOURS = 3


def _exit_actions() -> set[str]:
    return {"SL", "TP1", "TP2", "EXPIRE"}


def recent_loss_streak(*, path: Path | None = None) -> tuple[int, datetime | None]:
    """Returns (streak_len, last_sl_ts).

    Идём с конца журнала, считаем подряд SL без TP/EXPIRE между ними.
    `last_sl_ts` — время самого недавнего SL (для расчёта PAUSE_HOURS).
    """
    events = journal.read_all(path=path)
    streak = 0
    last_sl_ts: datetime | None = None
    exit_set = _exit_actions()
    for e in reversed(events):
        action = e.get("action")
        if action not in exit_set:
            continue
        if action == "SL":
            streak += 1
            if last_sl_ts is None:
                ts_str = e.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    last_sl_ts = ts
                except (ValueError, TypeError):
                    pass
        else:
            # TP1/TP2/EXPIRE breaks the streak
            break
    return streak, last_sl_ts


def should_pause(
    *,
    now: datetime | None = None,
    max_streak: int = MAX_LOSS_STREAK,
    pause_hours: int = PAUSE_HOURS,
    path: Path | None = None,
) -> tuple[bool, int, str]:
    """Returns (paused, streak_len, reason).

    Пауза активна когда streak ≥ max_streak И от последнего SL прошло
    < pause_hours часов. После pause_hours пауза снимается даже без TP —
    рынок мог поменяться.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    streak, last_sl_ts = recent_loss_streak(path=path)
    if streak < max_streak:
        return False, streak, ""
    if last_sl_ts is None:
        return False, streak, ""
    elapsed_h = (now - last_sl_ts).total_seconds() / 3600
    if elapsed_h >= pause_hours:
        return False, streak, f"streak={streak} но прошло {elapsed_h:.1f}h ≥ {pause_hours}h — авто-разблок"
    return True, streak, f"streak={streak} SL подряд, последний {elapsed_h:.1f}h назад"
