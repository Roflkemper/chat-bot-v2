from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CapturedEvent, EventSeverity, ManualAnnotation
from .storage import ANNOTATIONS_PATH, append_annotation, iter_annotations

CALLBACK_PREFIX = "decision_log"


def make_callback_data(action: str, event_id: str) -> str:
    return f"{CALLBACK_PREFIX}:{action}:{event_id}"


def make_annotation(
    event_id: str,
    *,
    is_intentional: bool,
    reason: str | None = None,
    now: datetime | None = None,
) -> ManualAnnotation:
    return ManualAnnotation(
        event_id=event_id,
        annotation_ts=now or datetime.now(timezone.utc),
        is_intentional=is_intentional,
        reason=reason,
    )


def handle_callback(
    callback_data: str,
    *,
    pending_reasons: dict[int, str],
    chat_id: int,
    annotations_path: Path = ANNOTATIONS_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    parts = callback_data.split(":", 2)
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
        return {"status": "ignored", "message": "неизвестный callback"}
    action = parts[1]
    event_id = parts[2]
    current_now = now or datetime.now(timezone.utc)
    if action == "intentional":
        append_annotation(make_annotation(event_id, is_intentional=True, now=current_now), annotations_path)
        return {"status": "recorded", "message": "Зафиксировал: это твоё решение."}
    if action == "automatic":
        append_annotation(make_annotation(event_id, is_intentional=False, now=current_now), annotations_path)
        return {"status": "recorded", "message": "Зафиксировал: событие было автоматическим."}
    if action == "reason":
        pending_reasons[chat_id] = event_id
        return {"status": "awaiting_reason", "message": "Напиши одной репликой причину, я привяжу её к событию."}
    if action == "ignore":
        pending_reasons.pop(chat_id, None)
        return {"status": "ignored", "message": "Ок, оставил событие без разметки."}
    return {"status": "ignored", "message": "неизвестное действие"}


def handle_reason_message(
    chat_id: int,
    text: str,
    *,
    pending_reasons: dict[int, str],
    annotations_path: Path = ANNOTATIONS_PATH,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    event_id = pending_reasons.pop(chat_id, None)
    if event_id is None:
        return None
    append_annotation(
        make_annotation(event_id, is_intentional=True, reason=text.strip() or None, now=now),
        annotations_path,
    )
    return {"status": "recorded", "message": "Причина сохранена.", "event_id": event_id}


def build_event_keyboard(event_id: str) -> Any:
    try:
        from telebot import types
    except Exception:
        return None
    keyboard = types.InlineKeyboardMarkup()  # type: ignore[no-untyped-call]
    keyboard.row(
        types.InlineKeyboardButton("✅ Моё решение", callback_data=make_callback_data("intentional", event_id)),
        types.InlineKeyboardButton("🤖 Автомат", callback_data=make_callback_data("automatic", event_id)),
    )
    keyboard.row(
        types.InlineKeyboardButton("➕ Добавить причину", callback_data=make_callback_data("reason", event_id)),
        types.InlineKeyboardButton("👀 Игнорировать", callback_data=make_callback_data("ignore", event_id)),
    )
    return keyboard


def format_event_message(event: CapturedEvent) -> str:
    color = {
        EventSeverity.INFO: "🔵",
        EventSeverity.NOTICE: "🟡",
        EventSeverity.WARNING: "🟡",
        EventSeverity.CRITICAL: "🔴",
    }[event.severity]
    bot_line = f"Бот {event.bot_id}:\n" if event.bot_id else ""
    return (
        f"{color} Зафиксировано: {event.event_type.value}\n\n"
        f"{bot_line}"
        f"{event.summary}\n\n"
        f"📍 Контекст в этот момент:\n"
        f"Цена: ${event.market_context.price_btc:,.0f} ({event.market_context.price_change_1h_pct:+.1f}% за 1ч)\n"
        f"Режим: {event.market_context.regime_label}\n"
        f"Шорты: ${event.portfolio_context.shorts_unrealized_usd:,.0f}\n"
        f"Свободная маржа: {event.portfolio_context.free_margin_pct:.1f}%\n\n"
        f"Это было твоё решение?"
    )


def pending_event_ids(annotations_path: Path = ANNOTATIONS_PATH) -> set[str]:
    return {item.event_id for item in iter_annotations(annotations_path)}
