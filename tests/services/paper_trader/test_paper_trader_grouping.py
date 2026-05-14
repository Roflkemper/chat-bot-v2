"""Tests for grouped close-event TG alerts (2026-05-09 fix)."""
from __future__ import annotations

from services.paper_trader.loop import _format_close_alert, _format_grouped_alert


def _make_close_event(action="TP1", setup_type="long_multi_divergence", side="long",
                      pnl=100.0, rr=1.0, hours=23.5):
    return {
        "action": action, "setup_type": setup_type, "side": side,
        "realized_pnl_usd": pnl, "rr_realized": rr, "hours_in_trade": hours,
    }


def test_grouped_alert_single_event_falls_back_to_individual():
    ev = _make_close_event()
    result = _format_grouped_alert([ev])
    expected = _format_close_alert(ev)
    assert result == expected
    assert "×" not in result  # no multiplier suffix


def test_grouped_alert_multiple_events_collapsed():
    events = [_make_close_event(pnl=100.0, rr=1.0, hours=20 + i * 0.1) for i in range(10)]
    result = _format_grouped_alert(events)
    assert "×10" in result
    assert "total +$1000" in result
    assert "avg RR +1.00" in result
    # После humanize: long_multi_divergence → "Множественная дивергенция (LONG)"
    assert "Множественная дивергенция" in result


def test_grouped_alert_mixed_pnl_uses_total():
    events = [
        _make_close_event(pnl=200.0, rr=2.0),
        _make_close_event(pnl=-50.0, rr=-0.5),
        _make_close_event(pnl=100.0, rr=1.0),
    ]
    result = _format_grouped_alert(events)
    assert "×3" in result
    assert "total +$250" in result
    # avg RR (2.0 + -0.5 + 1.0) / 3 = 0.83
    assert "+0.83" in result


def test_grouped_alert_negative_total_no_plus():
    events = [_make_close_event(action="SL", pnl=-78.0, rr=-1.0) for _ in range(2)]
    result = _format_grouped_alert(events)
    assert "×2" in result
    assert "total $-156" in result
    assert "🛑" in result  # SL icon


def test_grouped_alert_empty_returns_empty():
    assert _format_grouped_alert([]) == ""


def test_grouped_alert_uses_first_event_metadata():
    events = [_make_close_event(action="EXPIRE", setup_type="short_pdh_rejection",
                                  side="short") for _ in range(3)]
    result = _format_grouped_alert(events)
    assert "EXPIRE" in result
    # short_pdh_rejection → "Отбой от вчерашнего хая (SHORT)"
    assert "Отбой от вчерашнего хая" in result
    assert "(short)" in result
    assert "⏱️" in result
