"""Tests for adaptive intervention rules (B3)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.managed_grid_sim.intervention_rules_adaptive import (
    AdaptivePauseEntriesOnUnrealizedThreshold,
    AdaptivePartialUnloadOnRetracement,
    _vol_multiplier,
    ATR_BASELINE,
    MIN_VOL_MULTIPLIER,
    MAX_VOL_MULTIPLIER,
)
from services.managed_grid_sim.models import (
    BotState, InterventionType, MarketSnapshot, RegimeLabel, TrendType,
)


def _make_snap(atr_normalized: float = 0.004, regime: RegimeLabel = RegimeLabel.RANGE) -> MarketSnapshot:
    return MarketSnapshot(
        bar_idx=100, ts=datetime.now(timezone.utc),
        ohlcv=(80000, 80100, 79900, 80050, 100),
        regime=regime, trend_type=TrendType.UNCERTAIN,
        delta_price_5m_pct=0, delta_price_1h_pct=0, delta_price_4h_pct=0,
        atr_normalized=atr_normalized, pdh=None, pdl=None,
        volume_ratio_to_avg=1.0, bars_since_last_pivot=10,
    )


def _make_bot_state(unrealized: float = 0, hold_min: int = 0, max_unr: float = 0) -> BotState:
    return BotState(
        bot_id="b1", bot_alias="b1", side="short", contract_type="linear",
        is_active=True, position_size_native=0.001, position_size_usd=80,
        avg_entry_price=80000, unrealized_pnl_usd=unrealized,
        hold_time_minutes=hold_min, bar_count_in_drawdown=0,
        max_unrealized_pnl_usd=max_unr, min_unrealized_pnl_usd=0,
        params_current={}, params_original={},
    )


def test_vol_multiplier_baseline():
    """ATR на baseline → multiplier = 1."""
    assert _vol_multiplier(ATR_BASELINE) == 1.0


def test_vol_multiplier_high_vol_capped():
    """Очень высокий ATR → multiplier capped at MAX."""
    assert _vol_multiplier(ATR_BASELINE * 10) == MAX_VOL_MULTIPLIER


def test_vol_multiplier_low_vol_capped():
    """Очень низкий ATR → multiplier capped at MIN."""
    assert _vol_multiplier(ATR_BASELINE * 0.01) == MIN_VOL_MULTIPLIER


def test_vol_multiplier_zero_atr():
    assert _vol_multiplier(0.0) == 1.0


def test_adaptive_pause_fires_on_normal_vol():
    """Базовое поведение: -$30 при vol=baseline → срабатывает."""
    rule = AdaptivePauseEntriesOnUnrealizedThreshold(
        base_threshold_usd=-30, hold_time_minutes=5)
    snap = _make_snap(atr_normalized=ATR_BASELINE)
    state = _make_bot_state(unrealized=-35, hold_min=10)
    decision = rule.evaluate(snap, state, [])
    assert decision is not None
    assert decision.intervention_type == InterventionType.PAUSE_NEW_ENTRIES
    assert "vol_mult=1.00" in decision.reason


def test_adaptive_pause_NOT_fire_on_high_vol():
    """High volatility → threshold расширен → -$35 уже не срабатывает.

    base=-30, vol=2× → threshold=-60 → unrealized=-35 НЕ срабатывает.
    """
    rule = AdaptivePauseEntriesOnUnrealizedThreshold(
        base_threshold_usd=-30, hold_time_minutes=5)
    snap = _make_snap(atr_normalized=ATR_BASELINE * 2)
    state = _make_bot_state(unrealized=-35, hold_min=10)
    decision = rule.evaluate(snap, state, [])
    assert decision is None  # high vol = wider threshold


def test_adaptive_pause_FIRES_on_high_vol_with_big_loss():
    """High vol + большой убыток → срабатывает (-70 < threshold -60)."""
    rule = AdaptivePauseEntriesOnUnrealizedThreshold(
        base_threshold_usd=-30, hold_time_minutes=5)
    snap = _make_snap(atr_normalized=ATR_BASELINE * 2)
    state = _make_bot_state(unrealized=-70, hold_min=10)
    decision = rule.evaluate(snap, state, [])
    assert decision is not None


def test_adaptive_pause_FIRES_earlier_on_low_vol():
    """Low vol → threshold уменьшен → срабатывает раньше.

    base=-30, vol=0.5× → threshold=-15 → unrealized=-20 срабатывает.
    """
    rule = AdaptivePauseEntriesOnUnrealizedThreshold(
        base_threshold_usd=-30, hold_time_minutes=5)
    snap = _make_snap(atr_normalized=ATR_BASELINE * 0.5)
    state = _make_bot_state(unrealized=-20, hold_min=10)
    decision = rule.evaluate(snap, state, [])
    assert decision is not None


def test_adaptive_pause_skip_short_hold():
    """Pause требует hold >= 5 мин — иначе skip."""
    rule = AdaptivePauseEntriesOnUnrealizedThreshold(
        base_threshold_usd=-30, hold_time_minutes=5)
    snap = _make_snap()
    state = _make_bot_state(unrealized=-100, hold_min=2)
    assert rule.evaluate(snap, state, []) is None


def test_adaptive_partial_unload_basic():
    """40% базовый retracement при normal vol."""
    rule = AdaptivePartialUnloadOnRetracement(
        base_unrealized_threshold_usd=5,
        base_retracement_pct=40.0,
        unload_fraction=0.3,
    )
    snap = _make_snap(atr_normalized=ATR_BASELINE)
    # Peak was $20, current $10 → retracement 50%, выше 40
    state = _make_bot_state(unrealized=10, max_unr=20)
    recent = [_make_bot_state(unrealized=20, max_unr=20),
              _make_bot_state(unrealized=18, max_unr=20)]
    decision = rule.evaluate(snap, state, recent)
    assert decision is not None
    assert decision.partial_unload_fraction == 0.3


def test_adaptive_partial_unload_high_vol_waits_deeper():
    """High vol → требуется более глубокий ретрейс перед фиксацией.

    base=40%, vol=2× → threshold=80%. retracement=50% теперь не срабатывает.
    """
    rule = AdaptivePartialUnloadOnRetracement(
        base_unrealized_threshold_usd=5,
        base_retracement_pct=40.0,
        unload_fraction=0.3,
    )
    snap = _make_snap(atr_normalized=ATR_BASELINE * 2)
    state = _make_bot_state(unrealized=10, max_unr=20)  # 50% retracement
    recent = [_make_bot_state(unrealized=20, max_unr=20),
              _make_bot_state(unrealized=18, max_unr=20)]
    assert rule.evaluate(snap, state, recent) is None


def test_adaptive_partial_unload_low_vol_fires_earlier():
    """Low vol → меньший ретрейс достаточно.

    base=40%, vol=0.5× → threshold=20%. retracement=25% срабатывает.
    """
    rule = AdaptivePartialUnloadOnRetracement(
        base_unrealized_threshold_usd=5,
        base_retracement_pct=40.0,
        unload_fraction=0.3,
    )
    snap = _make_snap(atr_normalized=ATR_BASELINE * 0.5)
    state = _make_bot_state(unrealized=15, max_unr=20)  # 25% retracement
    recent = [_make_bot_state(unrealized=20, max_unr=20),
              _make_bot_state(unrealized=18, max_unr=20)]
    decision = rule.evaluate(snap, state, recent)
    assert decision is not None


def test_adaptive_pause_inactive_bot_skipped():
    rule = AdaptivePauseEntriesOnUnrealizedThreshold(-30, 5)
    snap = _make_snap()
    state = BotState(
        bot_id="b1", bot_alias="b1", side="short", contract_type="linear",
        is_active=False,  # not active
        position_size_native=0, position_size_usd=0,
        avg_entry_price=80000, unrealized_pnl_usd=-100,
        hold_time_minutes=10, bar_count_in_drawdown=2,
        max_unrealized_pnl_usd=0, min_unrealized_pnl_usd=-100,
        params_current={}, params_original={},
    )
    assert rule.evaluate(snap, state, []) is None
