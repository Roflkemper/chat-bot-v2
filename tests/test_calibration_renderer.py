from __future__ import annotations

from datetime import date

from renderers.calibration_renderer import render_daily_report


def test_render_daily_report_empty_day():
    text = render_daily_report({"day": date(2026, 4, 18), "total_events": 0})
    assert "DAILY REPORT" in text
    assert "Событий calibration log за этот день нет" in text


def test_render_daily_report_contains_sections():
    text = render_daily_report(
        {
            "day": date(2026, 4, 18),
            "total_events": 4,
            "latest_regime": "TREND_DOWN",
            "event_counts": {
                "ACTION_CHANGE": 1,
                "REGIME_SHIFT": 1,
                "KILLSWITCH_TRIGGER": 1,
                "MANUAL_COMMAND": 1,
            },
            "action_changes": [
                {"category_key": "btc_long", "from_action": "RUN", "to_action": "PAUSE", "reason_ru": "pause"}
            ],
            "manual_commands": [{"reason_ru": "Оператор: /apply"}],
            "killswitch_events": [{"reason_ru": "Killswitch: MANUAL (operator)"}],
            "regime_shifts": [{"reason_ru": "Переход: RANGE → TREND_DOWN"}],
            "categories_changed": ["btc_long"],
            "bots_touched": ["btc_long_l1"],
        }
    )
    assert "TREND_DOWN" in text
    assert "ACTION_CHANGE: 1" in text
    assert "РУЧНЫЕ КОМАНДЫ" in text
    assert "KILLSWITCH" in text
