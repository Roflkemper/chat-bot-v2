"""Two-sided coordinated grid simulator.

Runs a LONG bot and SHORT bot simultaneously over 1m OHLCV bars.
Implements:
  1. Combined PnL tracking (USD-denominated)
  2. Coordinated close when combined PnL >= threshold
  3. Re-entry delay + price offset gate
  4. Asymmetric trim (cancel orders on losing side)

Builds on services.calibration.sim.GridBotSim for per-bot grid mechanics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

from services.calibration.sim import GridBotSim, _Order
from .models import BotConfig, CloseEvent, CoordinatedConfig, CoordinatedRunResult


def _combined_pnl_usd(
    long_bot: GridBotSim,
    short_bot: GridBotSim,
    price: float,
) -> float:
    """Combined unrealized+realized PnL in USD at given price."""
    long_usd  = (long_bot.realized_pnl  + long_bot._unrealized(price))  * price
    short_usd =  short_bot.realized_pnl + short_bot._unrealized(price)
    return long_usd + short_usd


def _force_close_bot(bot: GridBotSim, price: float) -> None:
    """Force-close all open orders at given price. Updates realized_pnl in place."""
    for o in list(bot.open_orders):
        if bot.side == "SHORT":
            pnl = o.qty * (o.entry - price)
            vol = o.qty * price + o.qty * o.entry
        else:  # LONG inverse
            pnl = o.qty * (1.0 / o.entry - 1.0 / price)
            vol = o.qty * 2
        bot.realized_pnl        += pnl
        bot.trading_volume_usd  += vol
        bot.num_fills           += 1
    bot.open_orders.clear()
    bot.last_in_price = None  # re-initialize grid on next bar


def _trim_losing_side(
    bot: GridBotSim,
    price: float,
    combined_notional: float,
    threshold_pct: float,
    trim_size_pct: float,
) -> bool:
    """Cancel worst open orders on the losing side. Returns True if trim happened."""
    unreal = bot._unrealized(price)
    if unreal >= 0 or combined_notional <= 0:
        return False
    loss_pct = abs(unreal if bot.side == "SHORT" else unreal * price) / combined_notional * 100
    if loss_pct < threshold_pct:
        return False
    n = max(1, int(len(bot.open_orders) * trim_size_pct / 100))
    if bot.side == "SHORT":
        # Worst SHORT orders = lowest entry (furthest from TP, deepest in loss)
        bot.open_orders.sort(key=lambda o: o.entry)
        bot.open_orders = bot.open_orders[n:]
    else:
        # Worst LONG orders = highest entry (price fell, these are worst)
        bot.open_orders.sort(key=lambda o: o.entry, reverse=True)
        bot.open_orders = bot.open_orders[n:]
    return True


class MultiGridSim:
    """Two-sided coordinated grid simulator.

    Combined PnL threshold is checked against the CURRENT CYCLE's PnL only.
    On each coordinated close, per-bot realized_pnl is swept into MultiGridSim
    accumulators and reset to zero, so the threshold is not re-triggered by
    prior-cycle gains.
    """

    def __init__(self, config: CoordinatedConfig) -> None:
        self.config = config
        self.long_bot  = GridBotSim(
            side="LONG",
            order_size=config.long_bot.order_size,
            grid_step_pct=config.long_bot.grid_step_pct,
            target_pct=config.long_bot.target_pct,
            max_orders=config.long_bot.max_orders,
        )
        self.short_bot = GridBotSim(
            side="SHORT",
            order_size=config.short_bot.order_size,
            grid_step_pct=config.short_bot.grid_step_pct,
            target_pct=config.short_bot.target_pct,
            max_orders=config.short_bot.max_orders,
        )
        self._pause_bars: int   = 0
        self._close_price: float | None = None
        self._bar_idx: int      = 0

        # Accumulated totals across all closed cycles (not reset on close)
        self._cum_short_realized: float = 0.0
        self._cum_long_realized: float  = 0.0
        self._cum_short_vol: float      = 0.0
        self._cum_long_vol: float       = 0.0
        self._cum_short_fills: int      = 0
        self._cum_long_fills: int       = 0

        self._peak_combined: float   = -math.inf
        self._max_dd: float          = 0.0
        self._close_events: list[CloseEvent] = []
        self._n_coord_closes: int    = 0
        self._prices: list[float]    = []   # for avg_close_price

    # ------------------------------------------------------------------
    def feed_bar(self, o: float, h: float, l: float, c: float) -> None:
        self._bar_idx += 1
        self._prices.append(c)

        if self._pause_bars > 0:
            self._pause_bars -= 1
            if self._price_offset_met(c):
                self._pause_bars = 0
            else:
                return  # both bots idle during pause

        self.long_bot.feed_bar(o, h, l, c, "raw")
        self.short_bot.feed_bar(o, h, l, c, "raw")

        combined = _combined_pnl_usd(self.long_bot, self.short_bot, c)
        self._update_dd(combined)

        # coordinated close trigger
        if combined >= self.config.combined_close_threshold_usd:
            self._do_coordinated_close(c, combined)
            return

        # asymmetric trim
        if self.config.asymmetric_trim_enabled:
            notional = self._combined_notional()
            if notional > 0:
                _trim_losing_side(
                    self.long_bot, c, notional,
                    self.config.asymmetric_trim_threshold_pct,
                    self.config.asymmetric_trim_size_pct,
                )
                _trim_losing_side(
                    self.short_bot, c, notional,
                    self.config.asymmetric_trim_threshold_pct,
                    self.config.asymmetric_trim_size_pct,
                )

    # ------------------------------------------------------------------
    def _do_coordinated_close(self, price: float, combined: float) -> None:
        ev = CloseEvent(
            bar_idx=self._bar_idx,
            price=price,
            combined_pnl_usd_at_close=combined,
            short_realized_usd=self.short_bot.realized_pnl,
            long_realized_btc=self.long_bot.realized_pnl,
            n_short_orders=len(self.short_bot.open_orders),
            n_long_orders=len(self.long_bot.open_orders),
        )
        _force_close_bot(self.short_bot, price)
        _force_close_bot(self.long_bot,  price)
        self._close_events.append(ev)
        self._n_coord_closes += 1
        self._close_price = price
        self._pause_bars  = self.config.re_entry_delay_bars

        # Sweep cycle PnL into accumulators; reset bots to zero for next cycle
        self._cum_short_realized += self.short_bot.realized_pnl
        self._cum_long_realized  += self.long_bot.realized_pnl
        self._cum_short_vol      += self.short_bot.trading_volume_usd
        self._cum_long_vol       += self.long_bot.trading_volume_usd
        self._cum_short_fills    += self.short_bot.num_fills
        self._cum_long_fills     += self.long_bot.num_fills

        self.short_bot.realized_pnl       = 0.0
        self.short_bot.trading_volume_usd = 0.0
        self.short_bot.num_fills          = 0
        self.long_bot.realized_pnl        = 0.0
        self.long_bot.trading_volume_usd  = 0.0
        self.long_bot.num_fills           = 0

    def _price_offset_met(self, price: float) -> bool:
        if self._close_price is None or self.config.re_entry_price_offset_pct == 0:
            return True
        move_pct = abs(price - self._close_price) / self._close_price * 100
        return move_pct >= self.config.re_entry_price_offset_pct

    def _combined_notional(self) -> float:
        short_n = sum(o.qty * o.entry for o in self.short_bot.open_orders)
        long_n  = sum(o.qty           for o in self.long_bot.open_orders)  # USD contracts
        return short_n + long_n

    def _update_dd(self, combined: float) -> None:
        if combined > self._peak_combined:
            self._peak_combined = combined
        if self._peak_combined > -math.inf:
            dd = self._peak_combined - combined
            if dd > self._max_dd:
                self._max_dd = dd

    # ------------------------------------------------------------------
    def result(self) -> CoordinatedRunResult:
        avg_p  = mean(self._prices) if self._prices else 0.0
        last_p = self._prices[-1]   if self._prices else 0.0

        # Total = cumulative (swept on each close) + current open cycle
        total_short_usd = self._cum_short_realized + self.short_bot.realized_pnl
        total_long_btc  = self._cum_long_realized  + self.long_bot.realized_pnl
        combined_realized = total_short_usd + total_long_btc * avg_p

        combined_unrealized = _combined_pnl_usd(
            self.long_bot, self.short_bot, last_p
        ) - (self.long_bot.realized_pnl * last_p + self.short_bot.realized_pnl)

        return CoordinatedRunResult(
            config=self.config,
            short_realized_usd=total_short_usd,
            long_realized_btc=total_long_btc,
            combined_realized_usd=combined_realized,
            combined_unrealized_usd=combined_unrealized,
            total_volume_usd=(
                self._cum_short_vol + self.short_bot.trading_volume_usd
                + self._cum_long_vol + self.long_bot.trading_volume_usd
            ),
            max_combined_dd_usd=self._max_dd,
            n_coordinated_closes=self._n_coord_closes,
            n_short_fills=self._cum_short_fills + self.short_bot.num_fills,
            n_long_fills=self._cum_long_fills  + self.long_bot.num_fills,
            avg_close_price=avg_p,
            close_events=self._close_events,
        )


def run_sim(
    bars: list[tuple[float, float, float, float]],
    config: CoordinatedConfig,
) -> CoordinatedRunResult:
    sim = MultiGridSim(config)
    for o, h, l, c in bars:
        sim.feed_bar(o, h, l, c)
    return sim.result()
