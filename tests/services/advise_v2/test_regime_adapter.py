from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from services.advise_v2 import CurrentExposure, MarketContext, SessionContext, map_regime_to_advise_label
from services.advise_v2.regime_adapter import is_valid_advise_regime_label
from core.orchestrator.regime_classifier import (
    PRIMARY_CASCADE_DOWN,
    PRIMARY_CASCADE_UP,
    PRIMARY_COMPRESSION,
    PRIMARY_RANGE,
    PRIMARY_TREND_DOWN,
    PRIMARY_TREND_UP,
    RegimeMetrics,
    RegimeSnapshot,
)


def _metrics(**updates) -> RegimeMetrics:
    payload = {
        "atr_pct_1h": 1.0,
        "atr_pct_4h": 1.2,
        "atr_pct_5m": 0.2,
        "bb_width_pct_1h": 2.0,
        "bb_upper_1h": 101.0,
        "bb_mid_1h": 100.0,
        "bb_lower_1h": 99.0,
        "adx_1h": 25.0,
        "adx_slope_1h": 0.5,
        "ema20_1h": 100.0,
        "ema50_1h": 99.0,
        "ema200_1h": 95.0,
        "ema_stack_1h": 2,
        "dist_to_ema200_pct": 3.0,
        "ema50_slope_1h": 0.4,
        "range_position": 0.6,
        "last_move_pct_5m": 0.2,
        "last_move_pct_15m": 0.5,
        "last_move_pct_1h": 1.0,
        "last_move_pct_4h": 2.0,
        "funding_rate": 0.01,
        "volume_ratio_24h": 1.1,
        "weekday": 2,
        "hour_utc": 12,
        "minute_in_hour": 0,
        "close": 100.0,
    }
    payload.update(updates)
    return RegimeMetrics(**payload)


def _snapshot(primary: str, **metric_updates) -> RegimeSnapshot:
    return RegimeSnapshot(
        primary_regime=primary,
        modifiers=[],
        regime_age_bars=5,
        metrics=_metrics(**metric_updates),
        bias_score=10,
        session="US",
        ts=datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
        symbol="BTCUSDT",
        reasoning={},
        hysteresis_state={},
    )


def test_trend_up_maps_correctly() -> None:
    assert map_regime_to_advise_label(_snapshot(PRIMARY_TREND_UP)) == "trend_up"


def test_trend_down_maps_correctly() -> None:
    assert map_regime_to_advise_label(_snapshot(PRIMARY_TREND_DOWN)) == "trend_down"


def test_range_tight_maps_correctly() -> None:
    assert map_regime_to_advise_label(_snapshot(PRIMARY_RANGE, bb_width_pct_1h=2.5)) == "range_tight"


def test_range_wide_maps_correctly() -> None:
    assert map_regime_to_advise_label(_snapshot(PRIMARY_RANGE, bb_width_pct_1h=4.2)) == "range_wide"


def test_impulse_up_with_exhaustion_maps_to_exhausting() -> None:
    label = map_regime_to_advise_label(
        _snapshot(PRIMARY_CASCADE_UP, adx_1h=45.0, adx_slope_1h=-1.5)
    )
    assert label == "impulse_up_exhausting"


def test_impulse_up_without_exhaustion_maps_to_impulse_up() -> None:
    label = map_regime_to_advise_label(
        _snapshot(PRIMARY_CASCADE_UP, adx_1h=35.0, adx_slope_1h=0.2)
    )
    assert label == "impulse_up"


def test_consolidation_maps_correctly() -> None:
    assert map_regime_to_advise_label(_snapshot(PRIMARY_COMPRESSION)) == "consolidation"


def test_unknown_input_returns_unknown() -> None:
    assert map_regime_to_advise_label(_snapshot("SOMETHING_ELSE")) == "unknown"


def test_pure_function_no_input_mutation() -> None:
    snapshot = _snapshot(PRIMARY_CASCADE_DOWN, adx_1h=50.0, adx_slope_1h=-2.0)
    before = deepcopy(snapshot)
    map_regime_to_advise_label(snapshot)
    assert snapshot == before


def test_returned_label_is_valid_literal_value() -> None:
    label = map_regime_to_advise_label(_snapshot(PRIMARY_CASCADE_DOWN, adx_1h=20.0, adx_slope_1h=0.3))
    market = MarketContext(
        price_btc=76000.0,
        regime_label=label,
        regime_modifiers=[],
        rsi_1h=50.0,
        rsi_5m=50.0,
        price_change_5m_30bars_pct=0.0,
        price_change_1h_pct=0.0,
        nearest_liq_below=None,
        nearest_liq_above=None,
        session=SessionContext(),
    )
    assert market.regime_label == "impulse_down"
    assert is_valid_advise_regime_label(label) is True
