"""Out Stop Group — port of engine_v2/group.py for calibration sim.

Provenance:
  source: engine_v2/group.py (`OutStopGroup` class).
  PROJECT_CONTEXT §2 confirmed by operator 2026-05-02:
    * IN-orders that hit target_profit_pct → join trailing group.
    * Trailing stop = extreme_price × (1 ± max_stop_pct%); only moves
      in profit direction.
    * effective_stop = max(combo_stop, base_stop) for SHORT,
                       min(combo_stop, base_stop) for LONG
      where base_stop = trigger_price (when max_stop_pct=0) or per-order
      stop_price aggregate (when max_stop_pct>0).
    * On close_all: each order PnL is computed at close_price independently;
      sum is the realized PnL contribution. Early-IN orders may be in
      profit and late-IN in loss (or vice versa); weighted total must be
      positive in normal regime.
    * max_stop_pct = 0 → stop sits exactly at the triggering price (closes
      on first touch, equivalent to legacy immediate-close behavior).

Used by `services.calibration.sim.GridBotSim` when `use_out_stop_group=True`.
The sim's `_Order` is (entry, qty, tp) — `tp` plays the role of trigger_price.
A "stop_price" per order is computed as entry × (1 ± min_stop_pct/100).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["SHORT", "LONG"]


@dataclass
class GroupOrder:
    """Triggered IN order joined into an Out Stop Group.

    `entry` and `qty` mirror sim._Order.entry/qty. `trigger_price` was the
    `tp` field of the sim _Order at the moment the bot decided to TP-trigger.
    `stop_price` is the per-order min_stop floor/ceiling used by base_stop
    when max_stop_pct > 0; for max_stop_pct == 0 we keep the trigger price
    as the de facto stop.
    """
    entry: float
    qty: float
    trigger_price: float
    stop_price: float


@dataclass
class OutStopGroup:
    side: Side
    max_stop_pct: float                      # 0 → no trailing, exit on trigger
    orders: list[GroupOrder] = field(default_factory=list)
    combo_stop_price: float = 0.0
    extreme_price: float = 0.0
    base_stop: float = 0.0

    # ---------- construction -------------------------------------------------

    @classmethod
    def from_triggered(
        cls,
        orders: list[GroupOrder],
        current_price: float,
        side: Side,
        max_stop_pct: float,
    ) -> "OutStopGroup":
        assert orders, "at least one order required"
        if side == "SHORT":
            extreme = min(min(o.trigger_price for o in orders), current_price)
            if max_stop_pct == 0.0:
                init_stop = min(o.trigger_price for o in orders)
                init_base = init_stop
            else:
                raw_stop = extreme * (1.0 + max_stop_pct / 100.0)
                entry_cap = min(o.entry for o in orders)
                init_stop = min(raw_stop, entry_cap)
                init_base = max(o.stop_price for o in orders)
        else:
            extreme = max(max(o.trigger_price for o in orders), current_price)
            if max_stop_pct == 0.0:
                init_stop = max(o.trigger_price for o in orders)
                init_base = init_stop
            else:
                raw_stop = extreme * (1.0 - max_stop_pct / 100.0)
                entry_floor = max(o.entry for o in orders)
                init_stop = max(raw_stop, entry_floor)
                init_base = min(o.stop_price for o in orders)

        return cls(
            side=side,
            max_stop_pct=max_stop_pct,
            orders=list(orders),
            combo_stop_price=init_stop,
            extreme_price=extreme,
            base_stop=init_base,
        )

    def add_order(self, order: GroupOrder) -> None:
        self.orders.append(order)
        if self.side == "SHORT":
            if self.max_stop_pct == 0.0:
                if order.trigger_price < self.base_stop:
                    self.base_stop = order.trigger_price
            else:
                if order.stop_price > self.base_stop:
                    self.base_stop = order.stop_price
            if order.trigger_price < self.extreme_price:
                self.extreme_price = order.trigger_price
        else:
            if self.max_stop_pct == 0.0:
                if order.trigger_price > self.base_stop:
                    self.base_stop = order.trigger_price
            else:
                if order.stop_price < self.base_stop:
                    self.base_stop = order.stop_price
            if order.trigger_price > self.extreme_price:
                self.extreme_price = order.trigger_price

    # ---------- per-tick updates --------------------------------------------

    def update_trailing(self, price: float) -> None:
        """Trail combo_stop in profit direction. No-op when max_stop_pct=0."""
        if self.max_stop_pct == 0.0:
            return
        if self.side == "SHORT":
            if price < self.extreme_price:
                self.extreme_price = price
                new_stop = self.extreme_price * (1.0 + self.max_stop_pct / 100.0)
                if new_stop < self.combo_stop_price:
                    self.combo_stop_price = new_stop
        else:
            if price > self.extreme_price:
                self.extreme_price = price
                new_stop = self.extreme_price * (1.0 - self.max_stop_pct / 100.0)
                if new_stop > self.combo_stop_price:
                    self.combo_stop_price = new_stop

    def should_close(self, price: float) -> bool:
        if self.side == "SHORT":
            return price >= max(self.combo_stop_price, self.base_stop)
        return price <= min(self.combo_stop_price, self.base_stop)

    # ---------- close --------------------------------------------------------

    def close_all(self, close_price: float) -> tuple[float, float, int]:
        """Close all orders at close_price.

        Returns (total_realized_pnl, total_volume_usd, num_closed).
        For SHORT (USDT-M): pnl = qty × (entry - close); volume = qty × (entry + close).
        For LONG (COIN-M):  pnl = qty × (1/entry - 1/close) (BTC); volume = qty × 2.
        Per-order PnL is summed AS-IS; early orders may be in loss while late
        orders are in profit (or vice versa) — the sum reflects weighted
        outcome of the trailing-stop close.
        """
        total_pnl = 0.0
        total_vol = 0.0
        n = 0
        if self.side == "SHORT":
            for o in self.orders:
                total_pnl += o.qty * (o.entry - close_price)
                total_vol += o.qty * (o.entry + close_price)
                n += 1
        else:
            for o in self.orders:
                total_pnl += o.qty * (1.0 / o.entry - 1.0 / close_price)
                total_vol += o.qty * 2.0
                n += 1
        return total_pnl, total_vol, n
