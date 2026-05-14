"""Tests for indicator gate behavior in services/calibration/sim.py.

Verifies (per TZ-ENGINE-FIX-CALIBRATION-INSTOP):
  - Indicator fires once per cycle (no re-fire while bot is active)
  - Reset on full-close (no remaining IN orders)
  - Out Stop / partial-close ≠ full-close → indicator stays "passed"
  - is_indicator_passed flag persists across bars
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
# 1. Indicator gates the FIRST IN
# ---------------------------------------------------------------------------

class TestIndicatorGatesFirstIN:
    def test_no_in_until_indicator_passes(self):
        """SHORT with indicator: until Price% > +0.3% over 3 bars, no IN
        opens even on grid crossings."""
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.0,                      # bypass instop delay
            indicator_period=3, indicator_threshold_pct=0.3,
        )
        # 3 flat bars — Price% = 0% < 0.3% → indicator should not fire
        _feed(bot,
              (75000, 75100, 74990, 75050),
              (75050, 75150, 75000, 75080),
              (75080, 75180, 75050, 75100))
        assert not bot._is_indicator_passed
        assert len(bot.open_orders) == 0

    def test_indicator_fires_when_price_pct_exceeds_threshold(self):
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.0,
            indicator_period=3, indicator_threshold_pct=0.3,
        )
        # 3 bars: 75000 → 75100 → 75300 → 75400 — Price% over 3 bars =
        # (75400 - 75000) / 75000 * 100 = 0.533% > 0.3% → fire on bar 3.
        _feed(bot,
              (74900, 75001, 74899, 75000),
              (75000, 75100, 74999, 75100),
              (75100, 75300, 75100, 75300),
              (75300, 75400, 75300, 75400))   # Price% (3 closes back) > 0.3%
        assert bot._is_indicator_passed


# ---------------------------------------------------------------------------
# 2. Reset on full-close
# ---------------------------------------------------------------------------

class TestIndicatorResetOnFullClose:
    def test_reset_when_position_fully_closed(self):
        """After indicator fires + every IN closes (full-close), the gate
        resets — `_is_indicator_passed` returns to False.

        The simulator cycles intra-bar: every level crossing is then
        TP-checked. We construct a SHORT bar whose LOW is below ALL TP
        levels of the orders just opened, achieving full-close in one bar.
        """
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.0,
            indicator_period=3, indicator_threshold_pct=0.3,
        )
        # Bars 1-3: indicator pushes closes. Bar 3 close fires the gate
        # (Price% (75300-75000)/75000=0.4% > threshold 0.3%).
        _feed(bot,
              (74900, 75001, 74899, 75000),
              (75000, 75100, 74999, 75100),
              (75100, 75300, 75100, 75300))
        assert bot._is_indicator_passed
        assert bot.last_in_price == 75300.0
        # No ticks processed on bar 3 (early-return on indicator fire).

        # Bar 4: HIGH crosses ~1 level, LOW closes it via TP, CLOSE stays
        # below the post-reset level-1 threshold so no fresh orders open.
        # - Level 1 from 75300: 75300*1.0003 ≈ 75322.59. TP: ≈ 75134.28.
        # - Bar HIGH = 75330 → 1 SHORT order opens at 75322.59.
        # - Bar LOW = 75100 < 75134.28 → that order closes via TP. Full close,
        #   last_in_price reset to 75100, indicator resets.
        # - Bar CLOSE = 75110 < 75122.53 (level 1 from 75100) → no new open.
        _feed(bot, (75300, 75330, 75100, 75110))
        assert bot.num_fills >= 1, f"expected ≥1 fill, got {bot.num_fills}"
        assert len(bot.open_orders) == 0, (
            f"expected full close (orders=0), got {len(bot.open_orders)}"
        )
        assert not bot._is_indicator_passed, "indicator should reset on full close"


# ---------------------------------------------------------------------------
# 3. Indicator stays passed when partial open remains
# ---------------------------------------------------------------------------

class TestIndicatorPersistsAcrossBars:
    def test_flag_persists_until_full_close(self):
        """Once indicator passes and an IN is open, the flag persists across
        bars (no re-fire even if Price% threshold remains exceeded)."""
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.0,
            indicator_period=3, indicator_threshold_pct=0.3,
        )
        _feed(bot,
              (74900, 75001, 74899, 75000),
              (75000, 75100, 74999, 75100),
              (75100, 75300, 75100, 75300),
              (75300, 75400, 75300, 75400))
        assert bot._is_indicator_passed

        # Open an IN on next bar (level cross), but price doesn't TP →
        # IN remains open → flag must remain True.
        _feed(bot, (75400, 75500, 75400, 75440))   # H=75500 crosses level
        assert len(bot.open_orders) >= 1
        assert bot._is_indicator_passed       # still True

        # Another bar with no full-close → flag still True
        _feed(bot, (75440, 75450, 75420, 75430))
        assert bot._is_indicator_passed


# ---------------------------------------------------------------------------
# 4. Default behavior (no indicator config) preserved
# ---------------------------------------------------------------------------

class TestIndicatorDisabledByDefault:
    def test_no_indicator_means_immediate_open(self):
        """Without indicator_period/threshold, sim opens IN on first level
        crossing (legacy behavior)."""
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            # no indicator params → defaults to 0/0 → gate disabled
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        _feed(bot, (75000, 75100, 75000, 75080))   # crosses level
        assert len(bot.open_orders) >= 1
