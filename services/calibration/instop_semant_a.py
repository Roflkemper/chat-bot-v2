"""Instop Semantics A — port of engine_v2/instop.py for calibration sim.

Provenance:
  source: engine_v2/instop.py:114-148  (`InstopTracker.should_fire`)
  source: engine_v2/instop.py:47-69    (`update_extremum`)
  confirmed by operator 2026-05-02 (TZ-CLOSE-GAP-05) via Semant A screen
  for LONG; SHORT mirrored.

Three scenarios:
  A1 — price runs through a grid level → bot transitions to "above_base":
       tracks continuation extremum, fires on pullback toward grid.
  A2 — first IN after indicator pass: bot tracks adverse extremum, fires
       on reversal back toward grid direction.
  A3 — multi-level run during pending state → one combined IN of N levels.

Used by `services/calibration/sim.py::GridBotSim` when `instop_pct > 0`.
"""
from __future__ import annotations

from typing import Literal

Side = Literal["SHORT", "LONG"]


class InstopTracker:
    """Tracks local extremum + pending grid count for one bot.

    Mirrors `engine_v2.instop.InstopTracker`. Method names and semantics
    are identical so the engine_v2 unit tests would also exercise this
    port (modulo the separate Side enum).
    """

    def __init__(self, side: Side, instop_pct: float, grid_step_pct: float) -> None:
        self.side = side
        self.instop_pct = instop_pct
        self.grid_step_pct = grid_step_pct

        self.local_extremum: float | None = None
        self.pending_levels: int = 0
        # A2 phase: False = track adverse extremum, fire on reversal back
        #           toward grid.
        # True       = price crossed a grid level (A1/A3), track continuation
        #              extremum, fire on pullback.
        self._above_base: bool = False

    # ---------- state reset ---------------------------------------------------

    def reset(self, price: float) -> None:
        """Call after opening an IN (instop fired or immediate open)."""
        self.local_extremum = price
        self.pending_levels = 0
        self._above_base = False

    def init_extremum(self, price: float) -> None:
        """Indicator just fired — set starting extremum, no pending levels."""
        self.local_extremum = price
        self.pending_levels = 0
        self._above_base = False

    # ---------- per-price-point update ---------------------------------------

    def update_extremum(self, price: float) -> None:
        if self.local_extremum is None:
            self.local_extremum = price
            return
        if self.side == "SHORT":
            if self._above_base:
                # A1/A3: track MAX
                if price > self.local_extremum:
                    self.local_extremum = price
            else:
                # A2: track MIN
                if price < self.local_extremum:
                    self.local_extremum = price
        else:
            if self._above_base:
                # LONG A1/A3: track MIN
                if price < self.local_extremum:
                    self.local_extremum = price
            else:
                # LONG A2: track MAX
                if price > self.local_extremum:
                    self.local_extremum = price

    def count_new_levels(self, price: float, last_in_price: float) -> int:
        """Number of NEW grid levels above pending_levels crossed since
        last_in_price. Levels: last_in_price × (1 ± gs%)^k.
        """
        if last_in_price <= 0:
            return 0
        step = self.grid_step_pct / 100.0
        new = 0
        k = self.pending_levels + 1
        if self.side == "SHORT":
            while True:
                lvl = last_in_price * ((1.0 + step) ** k)
                if price >= lvl:
                    new += 1
                    k += 1
                else:
                    break
        else:
            while True:
                lvl = last_in_price * ((1.0 - step) ** k)
                if price <= lvl:
                    new += 1
                    k += 1
                else:
                    break
        return new

    def next_grid_level(self, last_in_price: float) -> float:
        step = self.grid_step_pct / 100.0
        k = self.pending_levels + 1
        if self.side == "SHORT":
            return last_in_price * ((1.0 + step) ** k)
        return last_in_price * ((1.0 - step) ** k)

    # ---------- fire check ---------------------------------------------------

    def should_fire(self, price: float) -> bool:
        """Fires when price reverses from local_extremum by instop_pct AND
        pending_levels > 0."""
        if self.instop_pct == 0.0:
            return False
        if self.local_extremum is None or self.pending_levels == 0:
            return False
        if self.side == "SHORT":
            if self._above_base:
                return (
                    (self.local_extremum - price) / self.local_extremum * 100.0
                    >= self.instop_pct
                )
            return (
                (price - self.local_extremum) / self.local_extremum * 100.0
                >= self.instop_pct
            )
        # LONG
        if self._above_base:
            return (
                (price - self.local_extremum) / self.local_extremum * 100.0
                >= self.instop_pct
            )
        return (
            (self.local_extremum - price) / self.local_extremum * 100.0
            >= self.instop_pct
        )
