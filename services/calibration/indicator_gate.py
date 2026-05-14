"""Price% indicator gate — port of engine_v2/indicator.py for calibration sim.

Provenance:
  source: engine_v2/indicator.py (`PricePercentIndicator`)
  reset semantics: engine_v2/bot.py `is_indicator_passed` flag, reset in
                  `_check_full_close()` (full-close = position fully exited).
  PROJECT_CONTEXT §2 confirmed by operator 2026-05-02:
    - Indicator fires once per cycle ("Разовая проверка")
    - Reset only on full-close (no remaining IN orders), NOT on Out Stop
      that leaves opens.

Used by `services/calibration/sim.py::GridBotSim` when `indicator_period > 0`.
"""
from __future__ import annotations

from collections import deque
from typing import Literal

Side = Literal["SHORT", "LONG"]


class PricePercentIndicator:
    """Price% close-to-close over `period` bars.

    SHORT: fires when Price% > +threshold (price moved up → short opportunity).
    LONG : fires when Price% < -threshold (price moved down → long opportunity).
    """

    def __init__(self, period: int, threshold_pct: float, side: Side) -> None:
        self.period = period
        self.threshold_pct = threshold_pct
        self.side = side
        self._closes: deque[float] = deque(maxlen=max(period, 1))

    def push(self, close: float) -> None:
        self._closes.append(close)

    def value(self) -> float | None:
        if len(self._closes) < self.period:
            return None
        first = self._closes[0]
        if first == 0.0:
            return None
        return (self._closes[-1] - first) / first * 100.0

    def is_triggered(self) -> bool:
        v = self.value()
        if v is None:
            return False
        if self.side == "SHORT":
            return v > self.threshold_pct
        return v < -self.threshold_pct
