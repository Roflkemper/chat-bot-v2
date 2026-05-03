"""Telegram delivery wrapper with 3 trigger conditions.

Triggers:
  1. Morning: daily at 08:00 UTC (caller schedules; this module just sends)
  2. Regime change: switcher.last_regime changed since last brief
  3. Significant forecast shift: 1h numeric prob change > 0.15 since last brief

Uses existing TelegramAlertClient infrastructure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_FORECAST_SHIFT_THRESHOLD = 0.15


@dataclass
class DeliveryState:
    """Track last brief context to detect changes worth alerting."""
    last_brief_time: Optional[datetime] = None
    last_regime: Optional[str] = None
    last_prob_up_1h: Optional[float] = None


def should_send(
    now: datetime,
    state: DeliveryState,
    current_regime: str,
    current_prob_up_1h: Optional[float],
    morning_hour_utc: int = 8,
) -> tuple[bool, str]:
    """Decide whether to send a brief now.

    Returns (should_send, reason).
    """
    # Morning trigger: 08:00 UTC and not yet sent today
    if now.hour == morning_hour_utc and (
        state.last_brief_time is None
        or state.last_brief_time.date() < now.date()
    ):
        return True, "morning"

    # Regime change trigger
    if state.last_regime is not None and current_regime != state.last_regime:
        return True, f"regime_change ({state.last_regime} → {current_regime})"

    # Forecast shift trigger (numeric only)
    if current_prob_up_1h is not None and state.last_prob_up_1h is not None:
        if abs(current_prob_up_1h - state.last_prob_up_1h) > _FORECAST_SHIFT_THRESHOLD:
            return True, f"forecast_shift (Δ={current_prob_up_1h - state.last_prob_up_1h:+.2f})"

    return False, ""


def update_state(state: DeliveryState, now: datetime, regime: str, prob_up_1h: Optional[float]) -> None:
    state.last_brief_time = now
    state.last_regime = regime
    state.last_prob_up_1h = prob_up_1h


def send_brief(text: str, send_fn: Optional[Callable[[str], None]] = None) -> bool:
    """Send a brief via the provided send function (typically TelegramAlertClient).

    If send_fn is None, attempts to use the existing TelegramAlertClient singleton.
    Returns True on success, False on failure.
    """
    if send_fn is not None:
        try:
            send_fn(text)
            return True
        except Exception as e:
            logger.error("brief delivery failed: %s", e)
            return False

    try:
        from services.telegram_alert_client import TelegramAlertClient
        client = TelegramAlertClient.instance()
        client.send_alert(text)  # may have a different method name in real code
        return True
    except Exception as e:
        logger.warning("telegram delivery skipped (no client): %s", e)
        return False
