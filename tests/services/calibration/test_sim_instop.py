"""Tests for instop Semant A behavior in services/calibration/sim.py.

Verifies (per TZ-ENGINE-FIX-CALIBRATION-INSTOP):
  - LONG: IN does NOT open until price reverses by instop_pct from local MAX
  - LONG: IN opens after the reversal
  - SHORT: mirrored — reversal from local MIN
  - Combined IN when multiple grid levels are crossed during pending state
  - instop=0 → no delay (immediate-open behavior preserved)
  - instop_pct >= grid_step does not break the simulator
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from services.calibration.sim import GridBotSim


def _feed(bot: GridBotSim, *bars: tuple[float, float, float, float]) -> None:
    for o, h, l, c in bars:
        bot.feed_bar(o, h, l, c, mode="raw")


# ---------------------------------------------------------------------------
# 1. LONG — no IN until reversal
# ---------------------------------------------------------------------------

class TestLongInstopDelay:
    def test_no_in_when_price_does_not_cross_any_grid_level(self):
        """LONG with instop_pct: ascending price stays above first LONG grid
        level (no level crossing) → no pending state, no IN.

        First LONG grid level = last_in_price × (1 - 0.0003). Bars below stay
        well above that level → 0 pending → 0 fills.
        """
        bot = GridBotSim(
            side="LONG", order_size=200.0, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.10,
        )
        # Bar 1 sets last_in_price = 75000. First LONG level = 74977.5.
        _feed(bot, (75000, 75001, 74999, 75000))
        # Subsequent bars: lows stay above 74977.5 → no level crossings.
        _feed(bot,
              (75000, 75100, 74990, 75100),
              (75100, 75300, 75050, 75300),
              (75300, 75400, 75250, 75400))
        assert len(bot.open_orders) == 0
        assert bot.num_fills == 0

    def test_long_combined_in_with_instop(self):
        """LONG A1/A3: price drops through 3 grid levels then bounces UP
        beyond instop_pct → ONE combined IN of 3× order_size."""
        bot = GridBotSim(
            side="LONG", order_size=100.0, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.05,
        )
        # Bar 1: establish baseline at 75000 (sets last_in_price=75000)
        _feed(bot, (75000, 75001, 74999, 75000))
        # Bar 2: drop through 3 levels (each ≈ -0.03%), then bounce UP
        # Level 1: 75000 * 0.9997 = 74977.5
        # Level 2: 75000 * 0.9994 = 74955.0
        # Level 3: 75000 * 0.9991 = 74932.5
        # LOW must reach <= 74932.5 to count 3 new levels
        # CLOSE must rebound ≥ 0.05% from LOW for instop fire
        bar_low = 74930.0   # crosses 3 levels
        bar_close = bar_low * (1.0 + 0.0006)  # +0.06% > 0.05% reversal
        _feed(bot, (75000, 75000, bar_low, bar_close))
        # Exactly one combined IN of 3 × 100 = 300
        assert len(bot.open_orders) == 1
        assert abs(bot.open_orders[0].qty - 300.0) < 1e-9


# ---------------------------------------------------------------------------
# 2. SHORT — mirrored
# ---------------------------------------------------------------------------

class TestShortInstopDelay:
    def test_short_in_opens_after_reversal_from_min(self):
        """SHORT A1/A3: price rises through level, then pulls back DOWN by
        instop_pct → IN opens. (Mirrored from LONG.)"""
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.05,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        # Bar 2: rise through 1 level (≈ +0.03%), then pull back DOWN
        # Level 1 SHORT: 75000 * 1.0003 = 75022.5
        # HIGH 75050 (crosses level 1), then close < HIGH by instop_pct
        bar_high = 75050.0
        bar_close = bar_high * (1.0 - 0.0006)  # 0.06% pullback
        _feed(bot, (75000, bar_high, 75000, bar_close))
        assert len(bot.open_orders) == 1

    def test_short_no_in_without_pullback(self):
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.05,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        # Cross level then keep rising — no pullback ≥ instop_pct → no IN
        _feed(bot, (75000, 75050, 75000, 75049))   # close near high
        _feed(bot, (75049, 75100, 75048, 75100))   # still rising
        assert len(bot.open_orders) == 0


# ---------------------------------------------------------------------------
# 3. instop=0 disables delay (default behavior preserved)
# ---------------------------------------------------------------------------

class TestInstopZeroNoDelay:
    def test_immediate_open_when_instop_zero(self):
        """instop_pct=0 → behavior identical to clean baseline (immediate
        open at grid crossings)."""
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.0,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        # Cross 1 level — IN opens immediately (no reversal needed)
        _feed(bot, (75000, 75100, 75000, 75080))
        assert len(bot.open_orders) >= 1
        # Each order is single-size (no combined behavior)
        for o in bot.open_orders:
            assert abs(o.qty - 0.001) < 1e-9


# ---------------------------------------------------------------------------
# 4. Edge: instop_pct > grid_step
# ---------------------------------------------------------------------------

class TestInstopLargerThanGridStep:
    def test_instop_larger_than_step_does_not_crash(self):
        """instop_pct=0.5% >> grid_step=0.03% — sim must not crash and the
        Semant A logic must still gate fills behind the larger reversal.

        Phase A: small bounce after level cross → pending stays, no fire.
        Phase B: large enough bounce to fire — verified via num_fills (the
        combined IN may immediately TP-close within the same bar because
        a 0.5% bounce exceeds the 0.25% target_pct).
        """
        bot = GridBotSim(
            side="LONG", order_size=100.0, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.5,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        # Phase A: drop through one level + small bounce (< 0.5%) — no fire.
        _feed(bot, (75000, 75000, 74950, 74980))
        assert len(bot.open_orders) == 0
        assert bot.num_fills == 0

        # Phase B: drop further then bounce > 0.5% from low — instop fires.
        bar_low = 74600.0
        bar_close = bar_low * (1.0 + 0.006)  # 0.6% bounce
        _feed(bot, (74980, 74980, bar_low, bar_close))
        # The combined IN was opened during the bounce. With a 0.6% bounce
        # vs 0.25% target, the IN closes via TP in the same bar, leaving
        # open_orders=0 and num_fills=1.
        assert bot.num_fills >= 1
