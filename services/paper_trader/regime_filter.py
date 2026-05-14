"""Regime instability filter — блокирует paper_trader входы при просадке
устойчивости режима.

Источник: state/decision_log/decisions.jsonl, событие R-3 regime_instability.
Сегодня 12.05 18:02 stability упала до 0.17 — в этом промежутке (18:02-19:55)
paper_trader получил ещё 2 SL подряд. Эти проигрыши были предсказуемы.

Логика: если за последние WINDOW_MIN минут было хоть одно R-3 событие
(`event_type == "regime_instability"`), блокируем новые входы. Окно
короткое (15 мин), потому что регрессия должна закрыться быстро.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DECISIONS_PATH = ROOT / "state" / "decision_log" / "decisions.jsonl"

WINDOW_MIN = 15


def recent_instability_stability(
    *,
    now: datetime | None = None,
    window_min: int = WINDOW_MIN,
    path: Path = DECISIONS_PATH,
) -> float | None:
    """Returns lowest stability from R-3 events in last `window_min` minutes,
    or None if no R-3 events.
    """
    if not path.exists():
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_min)
    lowest: float | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event_type") != "regime_instability":
                continue
            ts_str = ev.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if ts < cutoff or ts > now:
                continue
            stab = (ev.get("payload") or {}).get("stability")
            if stab is None:
                continue
            try:
                stab_f = float(stab)
            except (TypeError, ValueError):
                continue
            if lowest is None or stab_f < lowest:
                lowest = stab_f
    except OSError:
        logger.exception("regime_filter.read_failed path=%s", path)
        return None
    return lowest


def should_block_for_instability(
    *,
    now: datetime | None = None,
    window_min: int = WINDOW_MIN,
    path: Path = DECISIONS_PATH,
) -> tuple[bool, float | None]:
    """Returns (blocked, lowest_stability).

    Блокируем если в окне был R-3 (regime_instability). Сам факт события
    означает что stability < REGIME_STABILITY_INSTABILITY (0.40) —
    decision_layer уже отфильтровал шум, нам остаётся просто реагировать.
    """
    lowest = recent_instability_stability(now=now, window_min=window_min, path=path)
    return (lowest is not None), lowest
