from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CapturedEvent, EventSeverity, EventType, ManualAnnotation
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
        return {"status": "ignored", "message": "Неизвестный callback."}
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
    return {"status": "ignored", "message": "Неизвестное действие."}


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
        types.InlineKeyboardButton("✅ Я", callback_data=make_callback_data("intentional", event_id)),
        types.InlineKeyboardButton("🤖 Автомат", callback_data=make_callback_data("automatic", event_id)),
    )
    keyboard.row(
        types.InlineKeyboardButton("➕ Заметка", callback_data=make_callback_data("reason", event_id)),
        types.InlineKeyboardButton("👀 Skip", callback_data=make_callback_data("ignore", event_id)),
    )
    return keyboard


def _severity_emoji(severity: EventSeverity) -> str:
    return {
        EventSeverity.INFO: "🟢",
        EventSeverity.NOTICE: "🟢",
        EventSeverity.WARNING: "🟡",
        EventSeverity.CRITICAL: "🔴",
    }[severity]


def _format_money(value: float, *, signed: bool = False) -> str:
    if signed:
        if value > 0:
            return f"+${value:,.0f}"
        if value < 0:
            return f"-${abs(value):,.0f}"
    return f"${value:,.0f}"


def _format_pct(value: float) -> str:
    return f"{value:+.1f}%"


def _format_margin(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 0.05:
        return f"{rounded:.0f}%"
    return f"{value:.1f}%"


def _bot_alias(event: CapturedEvent) -> str | None:
    alias = event.payload.get("bot_alias")
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    if event.bot_id and event.bot_id != "multiple":
        return event.bot_id
    return None


def _header_for_event(event: CapturedEvent) -> str:
    emoji = _severity_emoji(event.severity)
    alias = _bot_alias(event)
    payload = event.payload

    if event.event_type == EventType.PNL_EVENT:
        delta = float(payload.get("delta_pnl_usd", 0.0))
        window = int(payload.get("window_minutes", 15))
        alias_part = f" — {alias}" if alias else ""
        return f"{emoji} PNL {_format_money(delta, signed=True)} за {window}м{alias_part}"

    if event.event_type == EventType.BOUNDARY_BREACH:
        if "border_top" in payload:
            return f"{emoji} ⬆ BREACH сверху — {alias or 'бот'}"
        if "border_bottom" in payload:
            return f"{emoji} ⬇ BREACH снизу — {alias or 'бот'}"

    if event.event_type == EventType.PNL_EXTREME:
        extreme = str(payload.get("extreme", "")).lower()
        value = abs(float(payload.get("value", 0.0)))
        label = "новый максимум" if extreme == "high" else "новый минимум"
        return f"{emoji} PNL_EXTREME — {label} {_format_money(value)} за 24ч"

    if event.event_type == EventType.PARAM_CHANGE:
        return f"{emoji} PARAM CHANGE — {alias or 'бот'}"

    if event.event_type == EventType.MARGIN_ALERT:
        margin = float(payload.get("new_margin_pct", event.portfolio_context.free_margin_pct))
        return f"{emoji} Маржа {_format_margin(margin)} — риск сжатия"

    if event.event_type == EventType.MARGIN_RECOVERY:
        margin = float(payload.get("new_margin_pct", event.portfolio_context.free_margin_pct))
        return f"{emoji} Маржа {_format_margin(margin)} — восстановление"

    if event.event_type == EventType.POSITION_CHANGE:
        return f"{emoji} POSITION CHANGE — {alias or 'бот'}"

    if event.event_type == EventType.BOT_STATE_CHANGE:
        return f"{emoji} STATE CHANGE — {alias or 'бот'}"

    if event.event_type == EventType.REGIME_CHANGE:
        return f"{emoji} REGIME CHANGE — {event.market_context.regime_label}"

    return f"{emoji} {event.event_type.value} — {alias or event.summary}"


def _context_lines(event: CapturedEvent) -> list[str]:
    market = event.market_context
    portfolio = event.portfolio_context
    lines = [
        f"📊 BTC ${market.price_btc:,.0f} (1ч: {_format_pct(market.price_change_1h_pct)}) | {market.regime_label}",
        f"💼 Шорты {_format_money(abs(portfolio.shorts_unrealized_usd))} | маржа {_format_margin(portfolio.free_margin_pct)}",
    ]

    if event.event_type == EventType.BOUNDARY_BREACH:
        price = float(event.payload.get("price", market.price_btc))
        if "border_top" in event.payload:
            boundary = float(event.payload["border_top"])
            breach_pct = ((price - boundary) / boundary * 100) if boundary else 0.0
            lines.append(f"📐 Граница ${boundary:,.0f} → пробой {breach_pct:+.2f}%")
        elif "border_bottom" in event.payload:
            boundary = float(event.payload["border_bottom"])
            breach_pct = ((price - boundary) / boundary * 100) if boundary else 0.0
            lines.append(f"📐 Граница ${boundary:,.0f} → пробой {breach_pct:+.2f}%")

    if event.event_type == EventType.PARAM_CHANGE:
        changes = event.payload.get("changes")
        if isinstance(changes, list) and changes:
            first = changes[0]
            if isinstance(first, dict):
                field = str(first.get("field", "param"))
                old = first.get("old")
                new = first.get("new")
                lines.insert(0, f"📐 {field}: {old} → {new}")

    if event.event_type == EventType.PNL_EXTREME:
        depo = event.portfolio_context.depo_total
        value = float(event.payload.get("value", 0.0))
        if depo > 0:
            lines.append(f"📉 Тренд за 24ч: {value / depo * 100:+.1f}% депо")

    return lines


def _drift_line(event: CapturedEvent) -> str | None:
    payload = event.payload
    peak_value = payload.get("recent_peak_usd")
    peak_minutes = payload.get("recent_peak_minutes_ago")
    trough_value = payload.get("recent_trough_usd")
    trough_minutes = payload.get("recent_trough_minutes_ago")

    if isinstance(peak_value, (int, float)) and isinstance(peak_minutes, (int, float)):
        return f"📈 Пик {_format_money(float(peak_value), signed=True)} ({int(peak_minutes)}м назад)"
    if isinstance(trough_value, (int, float)) and isinstance(trough_minutes, (int, float)):
        return f"📉 Дно {_format_money(float(trough_value), signed=True)} ({int(trough_minutes)}м назад)"
    return None


def _recent_context_line(event: CapturedEvent) -> str | None:
    payload = event.payload
    summary = payload.get("similar_event_summary")
    hhmm = payload.get("similar_event_hhmm")
    if isinstance(summary, str) and summary.strip():
        if isinstance(hhmm, str) and hhmm.strip():
            return f"🔁 Похожее: {summary.strip()} в {hhmm.strip()}"
        return f"🔁 Похожее: {summary.strip()}"
    return None


def _prompt_for_event(event: CapturedEvent) -> str:
    if event.event_type == EventType.PARAM_CHANGE:
        return "🎯 Кто менял?"
    return "🎯 Что это было?"


def format_event_message(event: CapturedEvent) -> str:
    lines = [_header_for_event(event), ""]
    lines.extend(_context_lines(event))
    drift_line = _drift_line(event)
    if drift_line:
        lines.append(drift_line)
    recent_line = _recent_context_line(event)
    if recent_line:
        lines.append(recent_line)
    lines.extend(["", _prompt_for_event(event)])
    return "\n".join(lines)


def pending_event_ids(annotations_path: Path = ANNOTATIONS_PATH) -> set[str]:
    return {item.event_id for item in iter_annotations(annotations_path)}
