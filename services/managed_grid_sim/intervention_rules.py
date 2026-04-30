from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .models import BotState, InterventionType, MarketSnapshot, RegimeLabel


@dataclass(frozen=True, slots=True)
class InterventionDecision:
    intervention_type: InterventionType
    reason: str
    params_modification: dict[str, Any] | None = None
    partial_unload_fraction: float | None = None
    booster_config: dict[str, Any] | None = None


class InterventionRule(ABC):
    def __init__(self, affected_bots: list[str] | None = None) -> None:
        self.affected_bots = set(affected_bots or [])

    def applies_to(self, bot_state: BotState) -> bool:
        return not self.affected_bots or bot_state.bot_id in self.affected_bots

    @abstractmethod
    def evaluate(
        self,
        snapshot: MarketSnapshot,
        bot_state: BotState,
        recent_states: list[BotState],
    ) -> InterventionDecision | None:
        raise NotImplementedError


class PauseEntriesOnUnrealizedThreshold(InterventionRule):
    def __init__(
        self,
        unrealized_threshold_pct_of_depo: float,
        hold_time_minutes: int,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.unrealized_threshold_pct_of_depo = unrealized_threshold_pct_of_depo
        self.hold_time_minutes = hold_time_minutes

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState, recent_states: list[BotState]
    ) -> InterventionDecision | None:
        del snapshot, recent_states
        if not self.applies_to(bot_state) or not bot_state.is_active:
            return None
        if bot_state.hold_time_minutes < self.hold_time_minutes:
            return None
        if bot_state.unrealized_pnl_usd <= self.unrealized_threshold_pct_of_depo:
            return InterventionDecision(
                intervention_type=InterventionType.PAUSE_NEW_ENTRIES,
                reason="unrealized threshold crossed",
            )
        return None


class ResumeEntriesOnPullback(InterventionRule):
    def __init__(
        self,
        pullback_from_peak_pct: float,
        hold_minutes_after_peak: int,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.pullback_from_peak_pct = pullback_from_peak_pct
        self.hold_minutes_after_peak = hold_minutes_after_peak

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState, recent_states: list[BotState]
    ) -> InterventionDecision | None:
        del snapshot
        if not self.applies_to(bot_state) or bot_state.is_active or len(recent_states) < 2:
            return None
        peak = max(state.max_unrealized_pnl_usd for state in recent_states)
        if peak <= 0:
            return None
        pullback_pct = (peak - bot_state.unrealized_pnl_usd) / peak * 100.0
        if pullback_pct >= self.pullback_from_peak_pct and bot_state.hold_time_minutes >= self.hold_minutes_after_peak:
            return InterventionDecision(
                intervention_type=InterventionType.RESUME_NEW_ENTRIES,
                reason="pullback after peak",
            )
        return None


class PartialUnloadOnRetracement(InterventionRule):
    def __init__(
        self,
        unrealized_pct_threshold: float,
        retracement_from_peak_pct: float,
        unload_fraction: float,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.unrealized_pct_threshold = unrealized_pct_threshold
        self.retracement_from_peak_pct = retracement_from_peak_pct
        self.unload_fraction = unload_fraction

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState, recent_states: list[BotState]
    ) -> InterventionDecision | None:
        del snapshot
        if not self.applies_to(bot_state) or len(recent_states) < 2:
            return None
        peak = max(state.max_unrealized_pnl_usd for state in recent_states)
        if bot_state.unrealized_pnl_usd <= self.unrealized_pct_threshold or peak <= 0:
            return None
        retracement = (peak - bot_state.unrealized_pnl_usd) / peak * 100.0
        if retracement >= self.retracement_from_peak_pct:
            return InterventionDecision(
                intervention_type=InterventionType.PARTIAL_UNLOAD,
                reason="retracement from peak",
                partial_unload_fraction=self.unload_fraction,
            )
        return None


class ModifyParamsOnRegimeChange(InterventionRule):
    def __init__(
        self,
        target_regime: RegimeLabel,
        modifications: dict[str, Any],
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.target_regime = target_regime
        self.modifications = modifications

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState, recent_states: list[BotState]
    ) -> InterventionDecision | None:
        del recent_states
        if not self.applies_to(bot_state):
            return None
        if snapshot.regime == self.target_regime:
            return InterventionDecision(
                intervention_type=InterventionType.MODIFY_PARAMS,
                reason=f"regime changed to {snapshot.regime.value}",
                params_modification=self.modifications,
            )
        return None


class ActivateBoosterOnImpulseExhaustion(InterventionRule):
    def __init__(
        self,
        impulse_min_pct: float,
        exhaustion_atr_drop_pct: float,
        liq_cluster_distance_pct: float | None,
        booster_border_top_offset_pct: float,
        booster_qty_factor: float,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.impulse_min_pct = impulse_min_pct
        self.exhaustion_atr_drop_pct = exhaustion_atr_drop_pct
        self.liq_cluster_distance_pct = liq_cluster_distance_pct
        self.booster_border_top_offset_pct = booster_border_top_offset_pct
        self.booster_qty_factor = booster_qty_factor

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState, recent_states: list[BotState]
    ) -> InterventionDecision | None:
        del recent_states
        if not self.applies_to(bot_state):
            return None
        if snapshot.delta_price_1h_pct * 100.0 < self.impulse_min_pct:
            return None
        if snapshot.atr_normalized * 100.0 > self.exhaustion_atr_drop_pct:
            return None
        if self.liq_cluster_distance_pct is not None and snapshot.pdh is not None:
            distance_pct = abs(snapshot.ohlcv[3] - snapshot.pdh) / snapshot.ohlcv[3] * 100.0
            if distance_pct > self.liq_cluster_distance_pct:
                return None
        return InterventionDecision(
            intervention_type=InterventionType.ACTIVATE_BOOSTER,
            reason="impulse exhaustion near cluster",
            booster_config={
                "border_top_offset_pct": self.booster_border_top_offset_pct,
                "qty_factor": self.booster_qty_factor,
            },
        )


class RaiseBoundaryOnConfirmedTrend(InterventionRule):
    def __init__(
        self,
        delta_1h_threshold_pct: float,
        hold_above_boundary_minutes: int,
        new_boundary_offset_pct: float,
        affected_bots: list[str] | None = None,
    ) -> None:
        super().__init__(affected_bots)
        self.delta_1h_threshold_pct = delta_1h_threshold_pct
        self.hold_above_boundary_minutes = hold_above_boundary_minutes
        self.new_boundary_offset_pct = new_boundary_offset_pct

    def evaluate(
        self, snapshot: MarketSnapshot, bot_state: BotState, recent_states: list[BotState]
    ) -> InterventionDecision | None:
        del recent_states
        if not self.applies_to(bot_state):
            return None
        if snapshot.delta_price_1h_pct * 100.0 < self.delta_1h_threshold_pct:
            return None
        if bot_state.hold_time_minutes < self.hold_above_boundary_minutes:
            return None
        new_boundary = snapshot.ohlcv[3] * (1.0 + self.new_boundary_offset_pct / 100.0)
        return InterventionDecision(
            intervention_type=InterventionType.RAISE_BOUNDARY,
            reason="confirmed trend above threshold",
            params_modification={"boundaries_upper": new_boundary},
        )


RULE_TYPES: dict[str, type[InterventionRule]] = {
    "PauseEntriesOnUnrealizedThreshold": PauseEntriesOnUnrealizedThreshold,
    "ResumeEntriesOnPullback": ResumeEntriesOnPullback,
    "PartialUnloadOnRetracement": PartialUnloadOnRetracement,
    "ModifyParamsOnRegimeChange": ModifyParamsOnRegimeChange,
    "ActivateBoosterOnImpulseExhaustion": ActivateBoosterOnImpulseExhaustion,
    "RaiseBoundaryOnConfirmedTrend": RaiseBoundaryOnConfirmedTrend,
}
