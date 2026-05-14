"""Tests for services.calibration.sim and models."""
from __future__ import annotations

import math
import pytest

from services.calibration.sim import GridBotSim, _tick_sequence, SimResult


# ---------------------------------------------------------------------------
# _tick_sequence
# ---------------------------------------------------------------------------

class TestTickSequence:
    def test_bullish_raw(self):
        ticks = _tick_sequence(100, 105, 98, 104, "raw")
        assert ticks == [100, 98, 105, 104]

    def test_bearish_raw(self):
        ticks = _tick_sequence(100, 105, 95, 96, "raw")
        assert ticks == [100, 105, 95, 96]

    def test_bullish_intra_bar_has_5_ticks(self):
        ticks = _tick_sequence(100, 110, 90, 105, "intra_bar")
        assert len(ticks) == 5
        assert ticks[0] == 100   # open
        assert ticks[-1] == 105  # close
        assert ticks[2] == 100.0  # midpoint of (90+110)/2

    def test_bearish_intra_bar_has_5_ticks(self):
        ticks = _tick_sequence(100, 108, 92, 95, "intra_bar")
        assert len(ticks) == 5
        assert ticks[1] == 108   # high first for bearish
        assert ticks[3] == 92    # low last


# ---------------------------------------------------------------------------
# GridBotSim — SHORT LINEAR
# ---------------------------------------------------------------------------

class TestShortLinearGridBot:
    def _make_bot(self, target_pct=1.0, step=3.0, max_orders=10):
        return GridBotSim(
            side="SHORT",
            order_size=0.003,
            grid_step_pct=step,
            target_pct=target_pct,
            max_orders=max_orders,
        )

    def test_first_bar_initialises_base_price(self):
        bot = self._make_bot()
        bot.feed_bar(100, 103, 99, 100, "raw")  # bar 1 just sets base
        assert bot.last_in_price == pytest.approx(100.0)
        assert bot.realized_pnl == pytest.approx(0.0)
        assert bot.num_fills == 0

    def test_short_opens_when_price_rises_one_step(self):
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")  # base=100
        # Bullish bar: ticks=[100, 102, 104, 103]. Opens short at 103 (tp=101.97).
        # Close=103 > tp=101.97 → order stays open.
        bot.feed_bar(100, 104, 102, 103, "raw")
        assert len(bot.open_orders) == 1
        assert bot.open_orders[0].entry == pytest.approx(103.0)

    def test_short_tp_fires_on_price_drop(self):
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")   # base=100
        bot.feed_bar(100, 104, 102, 103, "raw")   # open short at 103; close=103 stays open
        assert len(bot.open_orders) == 1

        # entry=103, tp=103*(1-0.01)=101.97; drop price below tp on next bar
        tp = bot.open_orders[0].tp
        bot.feed_bar(103, 103, tp - 0.01, tp - 0.01, "raw")
        assert bot.num_fills == 1
        assert bot.realized_pnl > 0

    def test_short_pnl_formula_linear(self):
        """PnL = qty * (entry - tp_price)."""
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")
        bot.feed_bar(100, 104, 102, 103, "raw")   # open at 103, close=103 stays open
        order = bot.open_orders[0]
        tp = order.tp
        bot.feed_bar(order.entry, order.entry, tp - 0.01, tp - 0.01, "raw")

        expected_pnl = order.qty * (order.entry - tp)
        assert bot.realized_pnl == pytest.approx(expected_pnl, rel=1e-9)

    def test_grid_resets_after_full_close(self):
        """After all positions close, last_in_price resets to current price."""
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")
        bot.feed_bar(100, 104, 102, 103, "raw")   # open at 103
        tp = bot.open_orders[0].tp
        bot.feed_bar(103, 103, tp - 0.01, tp - 0.01, "raw")  # close TP
        assert len(bot.open_orders) == 0
        assert bot.last_in_price is not None


# ---------------------------------------------------------------------------
# GridBotSim — LONG INVERSE
# ---------------------------------------------------------------------------

class TestLongInverseGridBot:
    def _make_bot(self, target_pct=1.0, step=3.0):
        return GridBotSim(
            side="LONG",
            order_size=200.0,    # 200 USD contracts
            grid_step_pct=step,
            target_pct=target_pct,
            max_orders=10,
        )

    def test_long_opens_when_price_falls_one_step(self):
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")  # base=100
        # Price falls to 97 (3% below 100)
        bot.feed_bar(100, 100, 96.9, 97, "raw")
        assert len(bot.open_orders) == 1
        assert bot.open_orders[0].entry == pytest.approx(97.0)

    def test_long_tp_fires_when_price_rises(self):
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")
        bot.feed_bar(100, 100, 96.9, 97, "raw")  # open long at 97
        tp = bot.open_orders[0].tp   # 97 * 1.01 = 97.97
        bot.feed_bar(97, tp + 0.01, 97, tp + 0.01, "raw")
        assert bot.num_fills == 1
        assert bot.realized_pnl > 0

    def test_long_pnl_formula_inverse(self):
        """PnL = qty * (1/entry - 1/tp_price), in BTC."""
        bot = self._make_bot(target_pct=1.0, step=3.0)
        bot.feed_bar(100, 100, 100, 100, "raw")
        bot.feed_bar(100, 100, 96.9, 97, "raw")
        order = bot.open_orders[0]
        tp = order.tp
        bot.feed_bar(97, tp + 0.01, 97, tp + 0.01, "raw")
        expected = order.qty * (1.0 / order.entry - 1.0 / tp)
        assert bot.realized_pnl == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# SimResult sanity
# ---------------------------------------------------------------------------

class TestSimResult:
    def test_result_has_all_fields(self):
        bot = GridBotSim("SHORT", 0.003, 3.0, 0.21, 10)
        r = bot.result()
        assert isinstance(r, SimResult)
        assert r.side == "SHORT"
        assert r.realized_pnl == 0.0
        assert r.num_fills == 0
        assert r.last_price == 0.0
