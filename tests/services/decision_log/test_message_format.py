from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from services.decision_log.manual_annotation import build_event_keyboard, format_event_message
from services.decision_log.models import CapturedEvent, EventSeverity, EventType, MarketContext, PortfolioContext


def _market_context() -> MarketContext:
    return MarketContext(
        price_btc=75927.0,
        regime_label="consolidation",
        regime_modifiers=[],
        price_change_1h_pct=-0.1,
        session_kz="NY_AM",
    )


def _portfolio_context() -> PortfolioContext:
    return PortfolioContext(
        depo_total=15000.0,
        shorts_unrealized_usd=-1269.0,
        longs_unrealized_usd=0.0,
        net_unrealized_usd=-1269.0,
        free_margin_pct=0.0,
        drawdown_pct=8.3,
        shorts_position_btc=0.45,
        longs_position_usd=0.0,
    )


def _event(
    *,
    event_type: EventType,
    severity: EventSeverity = EventSeverity.WARNING,
    bot_id: str | None = "TEST_2",
    summary: str = "summary",
    payload: dict[str, object] | None = None,
) -> CapturedEvent:
    return CapturedEvent(
        event_id="evt-20260430-0001",
        ts=datetime(2026, 4, 30, 18, 11, tzinfo=timezone.utc),
        event_type=event_type,
        severity=severity,
        bot_id=bot_id,
        summary=summary,
        payload=payload or {},
        market_context=_market_context(),
        portfolio_context=_portfolio_context(),
    )


def test_pnl_event_message_format() -> None:
    message = format_event_message(
        _event(
            event_type=EventType.PNL_EVENT,
            payload={
                "delta_pnl_usd": 774.0,
                "window_minutes": 15,
                "bot_alias": "TEST_2",
            },
        )
    )
    assert "🟡" in message
    assert "PNL +$774" in message
    assert "за 15м" in message
    assert "TEST_2" in message
    assert "consolidation" in message
    assert "$75,927" in message
    assert "Это было твоё решение?" not in message
    assert "Сильное изменение нереализованного" not in message


def test_boundary_breach_above_format() -> None:
    message = format_event_message(
        _event(
            event_type=EventType.BOUNDARY_BREACH,
            bot_id="SHORT_1%",
            payload={
                "price": 75927.0,
                "border_top": 75800.0,
            },
        )
    )
    assert "⬆" in message
    assert "BREACH сверху" in message
    assert "+0.17%" in message


def test_pnl_extreme_format() -> None:
    message = format_event_message(
        _event(
            event_type=EventType.PNL_EXTREME,
            bot_id=None,
            payload={"extreme": "low", "value": -576.0},
        )
    )
    assert "PNL_EXTREME" in message
    assert "новый минимум $576" in message
    assert "Тренд за 24ч" in message


def test_severity_emoji_warning() -> None:
    message = format_event_message(_event(event_type=EventType.PARAM_CHANGE, severity=EventSeverity.WARNING))
    assert message.startswith("🟡")


def test_severity_emoji_critical() -> None:
    message = format_event_message(_event(event_type=EventType.MARGIN_ALERT, severity=EventSeverity.CRITICAL))
    assert message.startswith("🔴")


def test_inline_buttons_short_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    class Button:
        def __init__(self, text: str, callback_data: str) -> None:
            self.text = text
            self.callback_data = callback_data

    class Keyboard:
        def __init__(self) -> None:
            self.keyboard: list[list[Button]] = []

        def row(self, *buttons: Button) -> None:
            self.keyboard.append(list(buttons))

    fake_types = SimpleNamespace(
        InlineKeyboardMarkup=Keyboard,
        InlineKeyboardButton=Button,
    )
    fake_module = ModuleType("telebot")
    fake_module_any = fake_module  # type: Any
    fake_module_any.types = fake_types
    monkeypatch.setitem(sys.modules, "telebot", fake_module_any)

    keyboard = build_event_keyboard("evt-20260430-0001")
    assert keyboard is not None
    keyboard_any = cast(Any, keyboard)
    labels = [btn.text for btn in keyboard_any.keyboard[0]]
    assert labels[0] == "✅ Я"
    assert labels[1] == "🤖 Автомат"
    second_row = [btn.text for btn in keyboard_any.keyboard[1]]
    assert second_row[0] == "➕ Заметка"
    assert second_row[1] == "👀 Skip"


def test_recent_context_shown_when_similar_event_within_1h() -> None:
    message = format_event_message(
        _event(
            event_type=EventType.PNL_EVENT,
            payload={
                "delta_pnl_usd": 774.0,
                "similar_event_summary": "PNL +$680",
                "similar_event_hhmm": "17:21",
            },
        )
    )
    assert "🔁 Похожее: PNL +$680 в 17:21" in message


def test_recent_context_omitted_when_no_similar() -> None:
    message = format_event_message(
        _event(
            event_type=EventType.PNL_EVENT,
            payload={"delta_pnl_usd": 774.0},
        )
    )
    assert "Похожее:" not in message


def test_drift_line_shown_when_recent_trough_present() -> None:
    message = format_event_message(
        _event(
            event_type=EventType.PNL_EVENT,
            payload={
                "delta_pnl_usd": 774.0,
                "recent_trough_usd": -520.0,
                "recent_trough_minutes_ago": 12,
            },
        )
    )
    assert "📉 Дно -$520 (12м назад)" in message
