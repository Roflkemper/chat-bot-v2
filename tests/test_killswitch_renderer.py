from __future__ import annotations

from renderers.killswitch_renderer import render_killswitch_alert


def test_render_killswitch_alert_margin_drawdown():
    text = render_killswitch_alert("MARGIN_DRAWDOWN", 18.5)
    assert "KILLSWITCH" in text
    assert "18.50%" in text


def test_render_killswitch_alert_manual():
    text = render_killswitch_alert("MANUAL", "operator")
    assert "РУЧНАЯ ОСТАНОВКА" in text
