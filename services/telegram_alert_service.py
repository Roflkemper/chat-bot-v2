from __future__ import annotations

import asyncio
from datetime import date
import logging

logger = logging.getLogger(__name__)
_MAX_MESSAGE_LEN = 3800


def _split_chunks(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    while body:
        if len(body) <= limit:
            chunks.append(body)
            break
        cut = body.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(body[:cut].rstrip())
        body = body[cut:].lstrip()
    return chunks


async def send_telegram_alert(text: str) -> None:
    """
    Send an orchestrator alert to Telegram when configured.
    Logging is always kept for audit/debugging.
    """
    logger.info("[ORCHESTRATOR ALERT]\n%s", text)

    from services.telegram_alert_client import TelegramAlertClient

    client = TelegramAlertClient.instance()
    if not client.is_enabled():
        return

    try:
        for chunk in _split_chunks(text):
            await asyncio.to_thread(client.send, chunk)
    except Exception as exc:
        logger.error("[ORCHESTRATOR ALERT] Delivery failed: %s", exc)


async def send_daily_report(day: date) -> None:
    """
    Build and deliver the daily orchestrator report.
    """
    from core.orchestrator.calibration_log import CalibrationLog
    from renderers.calibration_renderer import render_daily_report

    summary = CalibrationLog.instance().summarize_day(day)
    report_text = render_daily_report(summary)
    logger.info("[DAILY REPORT]\n%s", report_text)

    from services.telegram_alert_client import TelegramAlertClient

    client = TelegramAlertClient.instance()
    if not client.is_enabled():
        return

    try:
        for chunk in _split_chunks(report_text):
            await asyncio.to_thread(client.send, chunk)
    except Exception as exc:
        logger.error("[DAILY REPORT] Delivery failed: %s", exc)
