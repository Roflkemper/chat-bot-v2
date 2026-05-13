"""Weekly audit loop — еженедельный TG-отчёт по эффективности фильтров.

Запускается раз в неделю (понедельник 10:00 UTC). Шлёт оператору
сводку: сколько сделок было заблокировано, сколько PnL сохранено,
есть ли false positives.

State хранится в state/paper_trader_weekly_audit.json чтобы не
повторять отправку при перезапуске.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

STATE_PATH = Path("state/paper_trader_weekly_audit.json")
CHECK_INTERVAL_SEC = 3600  # check every hour, send weekly
TARGET_WEEKDAY = 0          # Monday (0=Mon, 6=Sun)
TARGET_HOUR_UTC = 10        # 10:00 UTC


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
        logger.exception("weekly_audit.write_failed path=%s", path)


def _should_send_now(now: datetime, last_sent_iso: str | None) -> bool:
    """True если сейчас понедельник 10:00 UTC ± 1h и не отправляли в этот же день."""
    if now.weekday() != TARGET_WEEKDAY:
        return False
    if now.hour != TARGET_HOUR_UTC:
        return False
    if last_sent_iso:
        try:
            last = datetime.fromisoformat(last_sent_iso)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last.date() == now.date():
                return False
        except (ValueError, TypeError):
            pass
    return True


def check_and_send(
    send_fn: Callable[[str], None] | None,
    *,
    now: datetime | None = None,
    state_path: Path = STATE_PATH,
) -> bool:
    """Returns True if a report was sent on this tick."""
    if now is None:
        now = datetime.now(timezone.utc)
    state = _read_state(state_path)
    if not _should_send_now(now, state.get("last_sent")):
        return False
    try:
        from services.paper_trader.audit_report import build_filter_audit
        text = "📅 Еженедельный аудит фильтров\n\n" + build_filter_audit(days=7)
    except Exception:
        logger.exception("weekly_audit.build_failed")
        return False
    if send_fn is not None:
        try:
            send_fn(text)
        except Exception:
            logger.exception("weekly_audit.send_failed")
            return False
    state["last_sent"] = now.isoformat()
    _write_state(state, state_path)
    return True


async def weekly_audit_loop(
    stop_event: asyncio.Event,
    *,
    send_fn: Callable[[str], None] | None = None,
    interval_sec: int = CHECK_INTERVAL_SEC,
) -> None:
    """Async loop: каждый час проверяем — пора ли слать. По понедельникам 10:00 UTC."""
    logger.info("weekly_audit_loop.start interval=%ds", interval_sec)
    while not stop_event.is_set():
        try:
            check_and_send(send_fn)
        except Exception:
            logger.exception("weekly_audit_loop.iteration_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
    logger.info("weekly_audit_loop.stopped")
