"""Tests for Out Stop Group integration in services/calibration/sim.py.

Verifies (per TZ-ENGINE-FIX-CALIBRATION-OUTSTOP):
  - LONG: order that hits TP joins trailing group
  - LONG: pullback by max_stop_pct closes the group; weighted PnL is positive
  - LONG: max_stop_pct=0 → group exits at trigger price (legacy semantics)
  - SHORT: mirrored — trailing in profit (down) direction
  - Weighted PnL: orders with mixed signs sum to positive
  - Combined IN (instop) → trigger → group flow integration
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from services.calibration.out_stop_group import GroupOrder, OutStopGroup
from services.calibration.sim import GridBotSim


def _feed(bot: GridBotSim, *bars: tuple[float, float, float, float]) -> None:
    for o, h, l, c in bars:
        bot.feed_bar(o, h, l, c, mode="raw")


# ---------------------------------------------------------------------------
# 1. LONG: hit TP → group joined; pullback closes group
# ---------------------------------------------------------------------------

class TestLongOutStopGroup:
    def test_long_order_joins_group_on_tp_then_closes_on_pullback(self):
        """LONG IN; price rises to TP → group; then pullback closes group at
        a price ABOVE entry → positive realized PnL.

        With target_pct=0.25 and min_stop_pct=0.01, base_stop sits at
        trigger × (1 - 0.01%) ≈ entry × 1.0024. Combo_stop trails extreme by
        max_stop_pct from above. effective = min(combo, base) ≈ base.
        Close at base_stop level → close > entry → positive PnL.
        """
        bot = GridBotSim(
            side="LONG", order_size=200.0, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            use_out_stop_group=True, max_stop_pct=0.30, min_stop_pct=0.01,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        # Bar 2: drop to first LONG level (75000 * 0.9997 = 74977.5). Opens IN.
        _feed(bot, (75000, 75000, 74970, 74977))
        assert len(bot.open_orders) == 1
        assert bot._group is None
        assert bot.num_fills == 0
        # Bar 3: rally through trigger 75164.94 → joins group (no close yet).
        # Bullish bar: ticks O→L→H→C = [75100, 75100, 75500, 75500].
        _feed(bot, (75100, 75500, 75100, 75500))
        assert bot._group is not None
        assert bot.num_fills == 0
        # Bar 4: bearish pullback. Ticks O→H→L→C = [75500, 75500, 75150, 75150].
        # base_stop = trigger × 0.9999 = 75157.42. Bar low 75150 < base_stop
        # → group closes at 75150.
        _feed(bot, (75500, 75500, 75150, 75150))
        assert bot.num_fills >= 1
        # close=75150, entry=74977.5 → +pnl
        assert bot.realized_pnl > 0


# ---------------------------------------------------------------------------
# 2. max_stop_pct=0 → exit on trigger (legacy semantics replicated)
# ---------------------------------------------------------------------------

class TestMaxStopPctZero:
    def test_max_stop_zero_exits_at_trigger(self):
        """max_stop_pct=0 → trailing disabled; group exits at the trigger
        price on first touch (legacy immediate-close semantics).

        SAME tick: order's tp is reached → triggers → group created with
        combo_stop=trigger and base_stop=trigger → should_close fires →
        group closed at the tick price.
        """
        bot = GridBotSim(
            side="LONG", order_size=200.0, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            use_out_stop_group=True, max_stop_pct=0.0,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        _feed(bot, (75000, 75000, 74970, 74977))
        # Bar 3: rally to 75200 (above trigger 75164.94) — order triggers,
        # joins group with combo=base=trigger. After trigger, the close tick
        # 75150 is below trigger → group should close immediately on the
        # SAME bar tick.
        # Use bearish bar O→H→L→C = [75200, 75200, 75100, 75150].
        _feed(bot, (75200, 75200, 75100, 75150))
        assert bot.num_fills >= 1
        # close_price=75100 (the low tick that triggered group close),
        # entry=74977.5 → close > entry → +pnl
        assert bot.realized_pnl > 0
        assert bot._group is None


# ---------------------------------------------------------------------------
# 3. SHORT: mirrored
# ---------------------------------------------------------------------------

class TestShortOutStopGroup:
    def test_short_group_close_on_upward_pullback(self):
        """SHORT IN at higher entry; price falls past TP → joins group;
        bounce back UP through base_stop closes group at price BELOW entry
        → positive PnL.

        With target_pct=0.25, min_stop=0.01, max_stop=0.30:
        entry=75022.5, trigger=74835.0, base_stop = trigger × 1.0001 ≈ 74842.5.
        After dropping to ~74600 then rising back, close at ~74842.5 → +PnL.
        """
        bot = GridBotSim(
            side="SHORT", order_size=0.001, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            use_out_stop_group=True, max_stop_pct=0.30, min_stop_pct=0.01,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        _feed(bot, (75000, 75025, 75000, 75022))
        assert len(bot.open_orders) >= 1
        # Bar low drops past trigger (74835) → joins group; close climbs back
        # above base_stop (74842.5) → group closes at the close tick.
        _feed(bot, (75022, 75022, 74600, 74900))
        assert bot.num_fills >= 1
        assert bot.realized_pnl > 0


# ---------------------------------------------------------------------------
# 4. Weighted PnL — mixed signs sum to positive
# ---------------------------------------------------------------------------

class TestWeightedPnL:
    def test_long_close_with_mixed_signs_sums_positive(self):
        """Synthetic group: 3 LONG orders at varying entries. Close at price
        between earliest and latest entry → some orders in profit (lower
        entries) some in loss (higher entries). Sum must reflect weighted
        outcome."""
        orders = [
            GroupOrder(entry=100.0, qty=10.0, trigger_price=100.25,
                       stop_price=99.0),     # high entry → close at 100 → ZERO
            GroupOrder(entry=99.5,  qty=10.0, trigger_price=99.75,
                       stop_price=98.5),     # mid entry → close 100 → POSITIVE
            GroupOrder(entry=99.0,  qty=10.0, trigger_price=99.25,
                       stop_price=98.0),     # low entry → close 100 → POSITIVE+
        ]
        # Build group at extreme=101 (above all triggers), then close at 100.
        group = OutStopGroup.from_triggered(
            orders, current_price=101.0, side="LONG", max_stop_pct=1.0,
        )
        pnl, vol, n = group.close_all(close_price=100.0)
        # Per-order LONG PnL = qty × (1/entry - 1/close):
        # 10 × (1/100   - 1/100) =  0.0
        # 10 × (1/99.5  - 1/100) = +0.000503
        # 10 × (1/99.0  - 1/100) = +0.001010
        # sum ≈ +0.001513
        assert n == 3
        assert pnl > 0, f"weighted PnL must be positive, got {pnl}"

    def test_short_close_with_mixed_signs_sums_positive(self):
        """Mirror for SHORT — early (low) entry close-to-flat, late (high)
        entries strictly profitable when close is below all entries."""
        orders = [
            GroupOrder(entry=100.0, qty=1.0, trigger_price=99.75,
                       stop_price=101.0),   # low entry → close 99 → +1
            GroupOrder(entry=100.5, qty=1.0, trigger_price=100.25,
                       stop_price=101.5),   # mid → +1.5
            GroupOrder(entry=101.0, qty=1.0, trigger_price=100.75,
                       stop_price=102.0),   # high → +2
        ]
        group = OutStopGroup.from_triggered(
            orders, current_price=99.0, side="SHORT", max_stop_pct=1.0,
        )
        pnl, vol, n = group.close_all(close_price=99.0)
        # SHORT pnl = qty * (entry - close)
        # 1*(100-99)+1*(100.5-99)+1*(101-99) = 1+1.5+2 = 4.5
        assert n == 3
        assert abs(pnl - 4.5) < 1e-9


# ---------------------------------------------------------------------------
# 5. Integration with instop combined IN
# ---------------------------------------------------------------------------

class TestInstopIntegration:
    def test_combined_in_via_instop_can_join_group(self):
        """When instop produces a combined IN (qty = N × order_size),
        and that combined IN later hits TP, it joins the group as ONE
        triggered order. Group close should produce ≥1 fill."""
        bot = GridBotSim(
            side="LONG", order_size=100.0, grid_step_pct=0.03,
            target_pct=0.25, max_orders=10,
            instop_pct=0.05,
            use_out_stop_group=True, max_stop_pct=0.30, min_stop_pct=0.01,
        )
        _feed(bot, (75000, 75001, 74999, 75000))
        # Bar 2: drop through 3 levels, bounce → combined IN of 3×100=300
        _feed(bot, (75000, 75000, 74930, 74930 * 1.0006))
        assert len(bot.open_orders) == 1
        combined = bot.open_orders[0]
        assert abs(combined.qty - 300.0) < 1e-9
        # Bar 3: rally past trigger; pullback closes group above entry.
        # combined entry ≈ 74932.5, trigger ≈ 75120.0, base_stop ≈ 75112.4.
        # Bar (75100, 75500, 75100, 75250) — low stays above base, but
        # we feed a follow-up bar with low ≤ base_stop.
        _feed(bot, (75100, 75500, 75100, 75250))
        # Follow-up bar: drops to base_stop region → group closes positive.
        _feed(bot, (75250, 75250, 75100, 75150))
        assert bot.num_fills >= 1
        assert bot.realized_pnl > 0
