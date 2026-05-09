"""Adaptive intervention rules — пороги масштабируются от текущей волатильности.

Стандартный PauseEntriesOnUnrealizedThreshold имеет фиксированный порог
(-$30 для combined). На high-vol днях это слишком чувствительно (паузится
на нормальном шуме), на low-vol днях слишком позднее (ждём крупный убыток).

AdaptivePauseEntries использует ATR(14) на 1h для масштабирования:
  threshold = base_threshold × (atr_pct / atr_baseline)
где atr_baseline = 0.4% (типичный медианный ATR для BTC 1h).

То же для AdaptivePartialUnload: retracement_from_peak_pct тоже масштабируется
volatility — на high-vol днях ждём более глубокий ретрейс перед фиксацией.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intervention_rules import InterventionRule, InterventionDecision
from .models import BotState, InterventionType, MarketSnapshot


# Baseline ATR для нормировки. ATR_normalized из RegimeClassifier — это
# средний true range / close. Для BTC 1h типично ~0.003-0.006.
ATR_BASELINE = 0.004
MIN_VOL_MULTIPLIER = 0.5   # порог не ниже 50% от base
MAX_VOL_MULTIPLIER = 2.5   # и не выше 250% (cap)


def _vol_multiplier(atr_normalized: float) -> float:
    """Возвращает множитель для адаптивных порогов."""
    if atr_normalized <= 0:
        return 1.0
    raw = atr_normalized / ATR_BASELINE
    return max(MIN_VOL_MULTIPLIER, min(MAX_VOL_MULTIPLIER, raw))


class AdaptivePauseEntriesOnUnrealizedThreshold(InterventionRule):
    """Pause new IN orders когда unrealized ниже adaptive threshold.

    threshold_actual = base_threshold × volatility_multiplier
      (high vol → чувствительность снижается, требуется больший убыток)
    """

    def __init__(
        self,
        base_threshold_usd: float,
        hold_time_minutes: int,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.base_threshold_usd = base_threshold_usd
        self.hold_time_minutes = hold_time_minutes

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState,
        recent_states: list[BotState]
    ) -> InterventionDecision | None:
        if not self.applies_to(bot_state) or not bot_state.is_active:
            return None
        if bot_state.hold_time_minutes < self.hold_time_minutes:
            return None

        mult = _vol_multiplier(snapshot.atr_normalized)
        # threshold_usd is negative for SHORT bot (loss); we widen on high vol.
        threshold = self.base_threshold_usd * mult
        if bot_state.unrealized_pnl_usd <= threshold:
            return InterventionDecision(
                intervention_type=InterventionType.PAUSE_NEW_ENTRIES,
                reason=f"unrealized < {threshold:.2f} (base {self.base_threshold_usd}, "
                       f"vol_mult={mult:.2f}, atr={snapshot.atr_normalized:.4f})",
            )
        return None


class AdaptivePartialUnloadOnRetracement(InterventionRule):
    """Частичная выгрузка с adaptive retracement threshold.

    Если ATR высокая (волатильный день), ждём более глубокий ретрейс прежде
    чем фиксировать частично — иначе выходим на нормальном шуме и теряем
    edge.
    """

    def __init__(
        self,
        base_unrealized_threshold_usd: float,
        base_retracement_pct: float,
        unload_fraction: float,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.base_unrealized_threshold_usd = base_unrealized_threshold_usd
        self.base_retracement_pct = base_retracement_pct
        self.unload_fraction = unload_fraction

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState,
        recent_states: list[BotState]
    ) -> InterventionDecision | None:
        if not self.applies_to(bot_state) or len(recent_states) < 2:
            return None
        peak = max(state.max_unrealized_pnl_usd for state in recent_states)
        threshold = self.base_unrealized_threshold_usd
        if bot_state.unrealized_pnl_usd <= threshold or peak <= 0:
            return None

        mult = _vol_multiplier(snapshot.atr_normalized)
        # На high-vol днях retracement_pct растёт — выходим позже
        retracement_threshold = self.base_retracement_pct * mult
        retracement = (peak - bot_state.unrealized_pnl_usd) / peak * 100.0
        if retracement >= retracement_threshold:
            return InterventionDecision(
                intervention_type=InterventionType.PARTIAL_UNLOAD,
                reason=f"retracement {retracement:.1f}% >= {retracement_threshold:.1f}% "
                       f"(base {self.base_retracement_pct}, vol_mult={mult:.2f})",
                partial_unload_fraction=self.unload_fraction,
            )
        return None
