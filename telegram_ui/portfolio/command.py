"""Handler for /portfolio Telegram command."""
from __future__ import annotations

import logging

from .alerts import compute_alerts
from .data_source import load_portfolio_data
from .formatter import format_portfolio

log = logging.getLogger(__name__)


def handle_portfolio_command() -> str:
    """Load data, compute alerts, format, return full text.

    The telegram runtime's split_text_chunks will split on send.
    """
    try:
        bots = load_portfolio_data()
    except Exception as exc:
        log.error("Portfolio data load failed: %s", exc)
        return "❌ Не удалось загрузить данные портфеля."

    if not bots:
        return "⚠️ Нет данных по ботам. Трекер не запущен и API недоступен."

    try:
        alerts = compute_alerts(bots)
        messages = format_portfolio(bots, alerts)
    except Exception as exc:
        log.error("Portfolio format failed: %s", exc)
        return "❌ Ошибка формирования портфеля."

    return "\n\n".join(messages)
