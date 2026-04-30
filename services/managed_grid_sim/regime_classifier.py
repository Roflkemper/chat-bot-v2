from __future__ import annotations

from dataclasses import dataclass
from math import fabs
from typing import Any, Sequence

from .models import RegimeLabel, TrendType


def _close(bar: Any) -> float:
    return float(bar.close)


def _high(bar: Any) -> float:
    return float(bar.high)


def _low(bar: Any) -> float:
    return float(bar.low)


def _volume(bar: Any) -> float:
    return float(getattr(bar, "volume", 0.0))


@dataclass(slots=True)
class RegimeClassifier:
    atr_window: int = 14
    trend_window_bars: int = 30
    compression_atr_threshold: float = 0.004
    cascade_volume_multiplier: float = 3.0

    def classify(self, bars_window: Sequence[Any]) -> tuple[RegimeLabel, TrendType]:
        if len(bars_window) < 2:
            return RegimeLabel.UNCERTAIN, TrendType.UNCERTAIN

        delta_1h = self.delta_pct(bars_window, min(60, len(bars_window) - 1))
        atr_normalized = self.atr_normalized(bars_window)
        volume_ratio = self.volume_ratio(bars_window)

        if fabs(delta_1h) < 0.005 and atr_normalized < self.compression_atr_threshold:
            return RegimeLabel.COMPRESSION, TrendType.SMOOTH_TRENDING
        if delta_1h > 0.02 and volume_ratio > self.cascade_volume_multiplier:
            return RegimeLabel.CASCADE_UP, TrendType.CASCADE_DRIVEN
        if delta_1h < -0.02 and volume_ratio > self.cascade_volume_multiplier:
            return RegimeLabel.CASCADE_DOWN, TrendType.CASCADE_DRIVEN
        if delta_1h > 0.005:
            return RegimeLabel.TREND_UP, self._trend_type(bars_window)
        if delta_1h < -0.005:
            return RegimeLabel.TREND_DOWN, self._trend_type(bars_window)
        return RegimeLabel.RANGE, TrendType.SMOOTH_TRENDING

    def delta_pct(self, bars_window: Sequence[Any], lookback: int) -> float:
        if len(bars_window) <= lookback:
            lookback = len(bars_window) - 1
        first = _close(bars_window[-lookback - 1])
        last = _close(bars_window[-1])
        if first == 0:
            return 0.0
        return (last - first) / first

    def atr_normalized(self, bars_window: Sequence[Any]) -> float:
        bars = bars_window[-self.atr_window :]
        if not bars:
            return 0.0
        tr_values = [_high(bar) - _low(bar) for bar in bars]
        close = _close(bars[-1])
        if close == 0:
            return 0.0
        return (sum(tr_values) / len(tr_values)) / close

    def volume_ratio(self, bars_window: Sequence[Any]) -> float:
        current = _volume(bars_window[-1])
        prev = bars_window[-self.trend_window_bars :]
        avg = sum(_volume(bar) for bar in prev) / len(prev)
        if avg == 0:
            return 0.0
        return current / avg

    def _trend_type(self, bars_window: Sequence[Any]) -> TrendType:
        closes = [_close(bar) for bar in bars_window[-self.trend_window_bars :]]
        if len(closes) < 3:
            return TrendType.UNCERTAIN
        peak = closes[0]
        max_pullback = 0.0
        for price in closes[1:]:
            if price > peak:
                peak = price
                continue
            if peak != 0:
                max_pullback = max(max_pullback, (peak - price) / peak)
        if max_pullback > 0.01:
            return TrendType.VOLATILE_TRENDING
        return TrendType.SMOOTH_TRENDING
