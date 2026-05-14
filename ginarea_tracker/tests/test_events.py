"""Tests for events.py event detector."""
import pytest
from ginarea_tracker.events import detect_events, BotEvent


def _stat(in_count=0, out_count=0, in_qty=0.0, out_qty=0.0,
          avg_price=0.0, position=0.0, profit=0.0):
    return {
        "inFilledCount": in_count,
        "outFilledCount": out_count,
        "inFilledQty": in_qty,
        "outFilledQty": out_qty,
        "averagePrice": avg_price,
        "position": position,
        "profit": profit,
    }


class TestNoEvents:
    def test_identical_stats(self):
        s = _stat(in_count=5, out_count=3)
        assert detect_events(s, s) == []

    def test_empty_prev_and_curr(self):
        assert detect_events({}, {}) == []

    def test_counts_zero(self):
        assert detect_events(_stat(), _stat()) == []

    def test_counts_decreased(self):
        # Should never happen in practice; defensively no event
        prev = _stat(in_count=10, out_count=5)
        curr = _stat(in_count=9, out_count=4)
        assert detect_events(prev, curr) == []


class TestInFilledEvent:
    def test_single_in_filled(self):
        prev = _stat(in_count=5, in_qty=100.0, avg_price=45000.0, position=0.5, profit=10.0)
        curr = _stat(in_count=6, in_qty=110.0, avg_price=45000.0, position=0.6, profit=12.0)
        events = detect_events(prev, curr)
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "IN_FILLED"
        assert ev.delta_count == 1
        assert ev.delta_qty == pytest.approx(10.0)
        assert ev.price_last == pytest.approx(45000.0)
        assert ev.position_after == pytest.approx(0.6)
        assert ev.profit_after == pytest.approx(12.0)

    def test_multiple_in_filled_in_one_cycle(self):
        prev = _stat(in_count=3, in_qty=30.0)
        curr = _stat(in_count=6, in_qty=60.0)
        events = detect_events(prev, curr)
        assert len(events) == 1
        assert events[0].event_type == "IN_FILLED"
        assert events[0].delta_count == 3
        assert events[0].delta_qty == pytest.approx(30.0)


class TestOutFilledEvent:
    def test_single_out_filled(self):
        prev = _stat(out_count=2, out_qty=20.0, position=0.5)
        curr = _stat(out_count=3, out_qty=30.0, position=0.4)
        events = detect_events(prev, curr)
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == "OUT_FILLED"
        assert ev.delta_count == 1
        assert ev.delta_qty == pytest.approx(10.0)

    def test_out_filled_profit(self):
        prev = _stat(out_count=0, profit=0.0)
        curr = _stat(out_count=1, profit=5.5, out_qty=50.0)
        events = detect_events(prev, curr)
        assert events[0].profit_after == pytest.approx(5.5)


class TestBothEvents:
    def test_both_events_in_one_cycle(self):
        prev = _stat(in_count=5, out_count=3, in_qty=50.0, out_qty=30.0)
        curr = _stat(in_count=6, out_count=4, in_qty=60.0, out_qty=40.0)
        events = detect_events(prev, curr)
        assert len(events) == 2
        types = {ev.event_type for ev in events}
        assert types == {"IN_FILLED", "OUT_FILLED"}


class TestNoneValues:
    def test_none_in_curr(self):
        prev = _stat(in_count=5)
        curr = {
            "inFilledCount": None,
            "outFilledCount": None,
            "inFilledQty": None,
            "outFilledQty": None,
        }
        # None → treated as 0, so 0 - 5 = -5 → no event
        events = detect_events(prev, curr)
        assert events == []

    def test_none_in_prev(self):
        prev = {"inFilledCount": None}
        curr = {"inFilledCount": 3, "inFilledQty": 30.0, "averagePrice": 100.0}
        events = detect_events(prev, curr)
        assert len(events) == 1
        assert events[0].delta_count == 3
