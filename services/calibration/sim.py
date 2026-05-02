"""Standalone grid bot sim for calibration against GinArea ground truth.

Default mode: clean baseline (no indicator gate, no instop, no trailing-stop
group) — historical behavior preserved for existing callers.

Optional mode (TZ-ENGINE-FIX-CALIBRATION-INSTOP, 2026-05-02): when
`instop_pct > 0` and/or `indicator_period > 0`, the sim adds Semant A
delay-from-extremum + once-per-cycle indicator gate. Provenance:
  - instop Semant A — engine_v2/instop.py (operator-confirmed 2026-05-02
    via TZ-CLOSE-GAP-05).
  - indicator gate — engine_v2/bot.py + indicator.py + PROJECT_CONTEXT §2
    (operator-confirmed 2026-05-02). Reset on full-close (no remaining IN).

Two bar-resolution modes:
  'raw'       - 4 ticks per bar: O→L→H→C (bullish) / O→H→L→C (bearish)
  'intra_bar' - 5 ticks: adds midpoint between the two extremes

Contract types
  SHORT LINEAR  (USDT-M): order_size in BTC, PnL/volume in USDT
  LONG  INVERSE (COIN-M): order_size in USD contracts, PnL in BTC, volume in USD
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from .indicator_gate import PricePercentIndicator
from .instop_semant_a import InstopTracker
from .out_stop_group import GroupOrder, OutStopGroup

Mode = Literal["raw", "intra_bar"]
Side = Literal["SHORT", "LONG"]


@dataclass
class _Order:
    entry: float
    qty: float
    tp: float


@dataclass
class SimResult:
    side: Side
    target_pct: float
    realized_pnl: float        # USDT for SHORT, BTC for LONG
    trading_volume_usd: float  # total USD notional (IN + OUT fills)
    num_fills: int             # completed (closed) cycles
    unrealized_pnl: float      # at last bar's close
    last_price: float


class GridBotSim:
    def __init__(
        self,
        side: Side,
        order_size: float,
        grid_step_pct: float,
        target_pct: float,
        max_orders: int,
        *,
        instop_pct: float = 0.0,
        indicator_period: int = 0,
        indicator_threshold_pct: float = 0.0,
        use_out_stop_group: bool = False,
        max_stop_pct: float = 0.0,
        min_stop_pct: float = 0.0,
    ) -> None:
        self.side = side
        self.order_size = order_size
        self.step = grid_step_pct / 100.0
        self.tp_dist = target_pct / 100.0
        self.max_orders = max_orders

        self.last_in_price: float | None = None
        self.open_orders: list[_Order] = []
        self.realized_pnl: float = 0.0
        self.trading_volume_usd: float = 0.0
        self.num_fills: int = 0
        self._last_close: float = 0.0

        # ---- optional instop / indicator (defaults preserve old behavior) ----
        # Provenance for both: engine_v2/{instop.py, indicator.py, bot.py},
        # operator-confirmed 2026-05-02 via TZ-CLOSE-GAP-05 (Semant A) and
        # PROJECT_CONTEXT §2 (indicator once-per-cycle, reset on full-close).
        self._use_indicator = indicator_period > 0 and indicator_threshold_pct > 0
        self._use_instop = instop_pct > 0
        self._indicator: PricePercentIndicator | None = (
            PricePercentIndicator(indicator_period, indicator_threshold_pct, side)
            if self._use_indicator else None
        )
        self._is_indicator_passed: bool = not self._use_indicator
        self._instop: InstopTracker | None = (
            InstopTracker(side, instop_pct, grid_step_pct)
            if self._use_instop else None
        )

        # ---- Out Stop Group (opt-in) ---------------------------------------
        # Provenance: engine_v2/group.py + PROJECT_CONTEXT §2 (operator
        # confirmed 2026-05-02). When enabled, orders that hit their `tp`
        # are added to a trailing group instead of being closed immediately.
        self._use_out_stop = use_out_stop_group
        self._max_stop_pct = max_stop_pct
        self._min_stop_pct = min_stop_pct
        self._group: OutStopGroup | None = None

    # ------------------------------------------------------------------
    def feed_bar(self, o: float, h: float, l: float, c: float, mode: Mode) -> None:
        self._last_close = c

        # ---- Indicator: push close, gate first IN per cycle ------------------
        if self._indicator is not None:
            self._indicator.push(c)
            if not self._is_indicator_passed and self._indicator.is_triggered():
                self._is_indicator_passed = True
                if self.last_in_price is None:
                    self.last_in_price = c
                # Seed first pending level so A2 fires on instop_pct reversal.
                if self._instop is not None:
                    self._instop.init_extremum(c)
                    self._instop.pending_levels = 1
                # Don't process this bar's OHLC — indicator fired at close,
                # OHLC prices are stale. Start fresh from next bar.
                return
            if not self._is_indicator_passed:
                return  # still waiting for indicator signal

        # ---- Default flow (no indicator OR indicator passed) -----------------
        if self.last_in_price is None:
            self.last_in_price = c
            return
        for price in _tick_sequence(o, h, l, c, mode):
            self._on_tick(price)

    def result(self) -> SimResult:
        return SimResult(
            side=self.side,
            target_pct=self.tp_dist * 100.0,
            realized_pnl=self.realized_pnl,
            trading_volume_usd=self.trading_volume_usd,
            num_fills=self.num_fills,
            unrealized_pnl=self._unrealized(self._last_close),
            last_price=self._last_close,
        )

    # ------------------------------------------------------------------
    def _on_tick(self, price: float) -> None:
        # Update instop extremum first so should_fire / new-level logic
        # has the latest extremum.
        if self._instop is not None:
            self._instop.update_extremum(price)
        # Out-stop-group trailing: must update BEFORE the close check so
        # the new extreme is reflected on this tick.
        if self._use_out_stop and self._group is not None:
            self._group.update_trailing(price)
            if self._group.should_close(price):
                self._close_group(price)
        self._check_tp(price)
        self._check_open(price)

    def _check_tp(self, price: float) -> None:
        if not self.open_orders:
            return
        # Triggered orders: orders whose tp boundary has been crossed.
        triggered: list[_Order] = []
        surviving: list[_Order] = []
        if self.side == "SHORT":
            if price > self.open_orders[-1].tp:
                return
            for o in self.open_orders:
                if price <= o.tp:
                    triggered.append(o)
                else:
                    surviving.append(o)
        else:
            if price < self.open_orders[-1].tp:
                return
            for o in self.open_orders:
                if price >= o.tp:
                    triggered.append(o)
                else:
                    surviving.append(o)
        if not triggered:
            return

        if self._use_out_stop:
            # Convert to GroupOrder and add to (or create) the trailing group.
            group_orders = [self._to_group_order(o) for o in triggered]
            if self._group is None:
                self._group = OutStopGroup.from_triggered(
                    group_orders, current_price=price,
                    side=self.side, max_stop_pct=self._max_stop_pct,
                )
            else:
                for go in group_orders:
                    self._group.add_order(go)
            self.open_orders = surviving
            # max_stop_pct == 0 → group fires on first touch (this same tick).
            if self._group.should_close(price):
                self._close_group(price)
            return

        # ---- Legacy: immediate-close at tp ----------------------------------
        if self.side == "SHORT":
            for o in triggered:
                self.realized_pnl       += o.qty * (o.entry - o.tp)
                self.trading_volume_usd += o.qty * (o.tp + o.entry)
                self.num_fills          += 1
        else:
            for o in triggered:
                self.realized_pnl       += o.qty * (1.0 / o.entry - 1.0 / o.tp)
                self.trading_volume_usd += o.qty * 2
                self.num_fills          += 1
        self.open_orders = surviving
        if not self.open_orders:
            self._on_full_close(price)

    def _to_group_order(self, o: _Order) -> GroupOrder:
        """Translate sim _Order → GroupOrder.

        stop_price is derived from the TRIGGER (not entry), matching
        engine_v2/order.py:59-70. For SHORT, stop sits ABOVE trigger by
        min_stop_pct%; for LONG, BELOW trigger by min_stop_pct%.
        """
        if self.side == "SHORT":
            stop_price = o.tp * (1.0 + self._min_stop_pct / 100.0)
        else:
            stop_price = o.tp * (1.0 - self._min_stop_pct / 100.0)
        return GroupOrder(entry=o.entry, qty=o.qty, trigger_price=o.tp,
                          stop_price=stop_price)

    def _close_group(self, price: float) -> None:
        """Close the active trailing group at `price`. Updates realized
        PnL, volume, num_fills and triggers _on_full_close path."""
        if self._group is None:
            return
        pnl, vol, n = self._group.close_all(price)
        self.realized_pnl += pnl
        self.trading_volume_usd += vol
        self.num_fills += n
        self._group = None
        if not self.open_orders:
            self._on_full_close(price)

    def _on_full_close(self, price: float) -> None:
        """Common full-close handling: restart grid + reset indicator+instop."""
        self.last_in_price = price
        if self._indicator is not None:
            self._is_indicator_passed = False
        if self._instop is not None:
            self._instop.reset(price)

    def _check_open(self, price: float) -> None:
        if self.last_in_price is None:
            return
        if len(self.open_orders) >= self.max_orders:
            return

        # ---- Default path (no instop): immediate open at grid crossings ----
        if self._instop is None:
            if self.side == "SHORT":
                next_lvl = self.last_in_price * (1.0 + self.step)
                while price >= next_lvl and len(self.open_orders) < self.max_orders:
                    self._open_in(next_lvl)
                    next_lvl = self.last_in_price * (1.0 + self.step)
            else:
                next_lvl = self.last_in_price * (1.0 - self.step)
                while price <= next_lvl and len(self.open_orders) < self.max_orders:
                    self._open_in(next_lvl)
                    next_lvl = self.last_in_price * (1.0 - self.step)
            return

        # ---- Semant A path: count crossed levels into pending, fire on reversal
        new_levels = self._instop.count_new_levels(price, self.last_in_price)
        if new_levels > 0:
            self._instop.pending_levels += new_levels
            # Transition to A1/A3: track continuation extremum from here.
            self._instop._above_base = True
            self._instop.local_extremum = price

        if self._instop.should_fire(price):
            # Open ONE combined IN sized = pending_levels × order_size.
            # Entry price = the deepest pending grid level.
            n = self._instop.pending_levels
            if n > 0 and len(self.open_orders) < self.max_orders:
                # Deepest level = grid_step^n from last_in_price
                if self.side == "SHORT":
                    entry = self.last_in_price * ((1.0 + self.step) ** n)
                    tp = entry * (1.0 - self.tp_dist)
                else:
                    entry = self.last_in_price * ((1.0 - self.step) ** n)
                    tp = entry * (1.0 + self.tp_dist)
                qty = self.order_size * n
                self.open_orders.append(_Order(entry=entry, qty=qty, tp=tp))
                self.last_in_price = entry
                self._instop.reset(price)

    def _open_in(self, level: float) -> None:
        """Open single IN order at grid level (default path, no instop)."""
        if self.side == "SHORT":
            tp = level * (1.0 - self.tp_dist)
        else:
            tp = level * (1.0 + self.tp_dist)
        self.open_orders.append(_Order(entry=level, qty=self.order_size, tp=tp))
        self.last_in_price = level

    def _unrealized(self, price: float) -> float:
        if not price:
            return 0.0
        total = 0.0
        for o in self.open_orders:
            if self.side == "SHORT":
                total += o.qty * (o.entry - price)
            else:
                total += o.qty * (1.0 / o.entry - 1.0 / price)
        return total


def _tick_sequence(o: float, h: float, l: float, c: float, mode: Mode) -> list[float]:
    """Bullish bar: O→L→H→C; bearish: O→H→L→C.  intra_bar adds midpoint."""
    if c >= o:
        base = [o, l, h, c]
        return [o, l, (l + h) / 2, h, c] if mode == "intra_bar" else base
    else:
        base = [o, h, l, c]
        return [o, h, (h + l) / 2, l, c] if mode == "intra_bar" else base


# ---------------------------------------------------------------------------
# OHLCV loader (reads the frozen 1m or 1s CSV)
# ---------------------------------------------------------------------------

def load_ohlcv_bars(
    path: Path,
    start_iso: str,
    end_iso: str,
) -> list[tuple[float, float, float, float]]:
    """Return list of (open, high, low, close) within [start, end] (ISO 8601)."""
    start_ms = int(datetime.fromisoformat(start_iso).timestamp() * 1000)
    end_ms   = int(datetime.fromisoformat(end_iso).timestamp()   * 1000)
    bars: list[tuple[float, float, float, float]] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_ms = int(float(row["ts"]))
            if ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                break
            bars.append((
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            ))
    return bars


def run_sim(
    bars: list[tuple[float, float, float, float]],
    side: Side,
    order_size: float,
    grid_step_pct: float,
    target_pct: float,
    max_orders: int,
    mode: Mode = "raw",
    *,
    instop_pct: float = 0.0,
    indicator_period: int = 0,
    indicator_threshold_pct: float = 0.0,
    use_out_stop_group: bool = False,
    max_stop_pct: float = 0.0,
    min_stop_pct: float = 0.0,
) -> SimResult:
    bot = GridBotSim(
        side, order_size, grid_step_pct, target_pct, max_orders,
        instop_pct=instop_pct,
        indicator_period=indicator_period,
        indicator_threshold_pct=indicator_threshold_pct,
        use_out_stop_group=use_out_stop_group,
        max_stop_pct=max_stop_pct,
        min_stop_pct=min_stop_pct,
    )
    for o, h, l, c in bars:
        bot.feed_bar(o, h, l, c, mode)
    return bot.result()
