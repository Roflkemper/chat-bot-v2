from __future__ import annotations

import copy
import re

import pytest

import services.advise_v2.signal_generator as signal_generator_module
from services.advise_v2 import (
    CurrentExposure,
    LiqLevel,
    MarketContext,
    SignalEnvelope,
    compute_trend_handling,
    SetupMatch,
    generate_signal,
)


@pytest.fixture
def base_market_context() -> MarketContext:
    return MarketContext.model_validate(
        {
            "price_btc": 76200.0,
            "regime_label": "unknown",
            "regime_modifiers": [],
            "rsi_1h": 50.0,
            "rsi_5m": 48.0,
            "price_change_5m_30bars_pct": 0.0,
            "price_change_1h_pct": 0.0,
            "nearest_liq_below": None,
            "nearest_liq_above": None,
        }
    )


@pytest.fixture
def base_exposure() -> CurrentExposure:
    return CurrentExposure.model_validate(
        {
            "net_btc": 0.0,
            "shorts_btc": 0.0,
            "longs_btc": 0.0,
            "free_margin_pct": 50.0,
            "available_usd": 2500.0,
            "margin_coef_pct": 20.0,
        }
    )


def _replace_model(model, **updates):
    return model.model_copy(update=updates)


def test_strong_p2_setup_returns_envelope(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
        regime_modifiers=["volume_spike_5m", "liq_cluster_breached_below"],
    )
    signal = generate_signal(market, base_exposure)
    assert isinstance(signal, SignalEnvelope)
    assert signal.setup_id == "P-2"
    assert signal.recommendation.primary_action == "increase_long_manual"


def test_no_match_above_threshold_returns_none(base_market_context, base_exposure):
    signal = generate_signal(base_market_context, base_exposure)
    assert signal is None


def test_only_banned_patterns_match_returns_none(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="trend_down",
        rsi_1h=40.0,
        price_change_1h_pct=-2.0,
        price_change_5m_30bars_pct=0.0,
    )
    signal = generate_signal(market, base_exposure)
    assert signal is None


def test_signal_id_format(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
    )
    signal = generate_signal(market, base_exposure)
    assert signal is not None
    assert re.fullmatch(r"^adv_\d{4}-\d{2}-\d{2}_\d{6}_\d{3}$", signal.signal_id)


def test_signal_id_counter_increment(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
    )
    signal_1 = generate_signal(market, base_exposure, signal_counter=1)
    signal_2 = generate_signal(market, base_exposure, signal_counter=2)
    assert signal_1 is not None and signal_2 is not None
    assert signal_1.signal_id != signal_2.signal_id


def test_alternatives_populated(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="trend_up",
        rsi_1h=58.0,
        price_change_5m_30bars_pct=1.0,
        price_change_1h_pct=1.6,
        nearest_liq_above=None,
        regime_modifiers=["volume_spike_5m", "pullback_to_ema"],
    )
    signal = generate_signal(market, base_exposure)
    assert signal is not None
    assert 1 <= len(signal.alternatives_considered) <= 4
    assert signal.alternatives_considered[0].action.startswith("consider_")


def test_alternatives_fallback_do_nothing(base_market_context, base_exposure, monkeypatch):
    monkeypatch.setattr(
        signal_generator_module,
        "match_setups",
        lambda _market, _exposure: [
            SetupMatch(
                pattern_id="P-9",
                pattern_name="Breakout long",
                confidence=0.8,
                direction="long",
                matched_conditions=["mocked"],
                missing_conditions=[],
            )
        ],
    )
    market = _replace_model(base_market_context, regime_label="trend_up", rsi_1h=70.0)
    signal = generate_signal(market, base_exposure)
    assert signal is not None
    assert signal.setup_id == "P-9"
    assert signal.alternatives_considered[0].action == "do_nothing"


def test_envelope_passes_pydantic_validation(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
    )
    signal = generate_signal(market, base_exposure)
    assert signal is not None
    restored = SignalEnvelope.model_validate_json(signal.model_dump_json())
    assert restored == signal


def test_pure_no_input_mutation(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
    )
    market_before = copy.deepcopy(market.model_dump())
    exposure_before = copy.deepcopy(base_exposure.model_dump())
    generate_signal(market, base_exposure)
    assert market.model_dump() == market_before
    assert base_exposure.model_dump() == exposure_before


def test_threshold_boundary(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="consolidation",
        rsi_1h=45.0,
        price_change_1h_pct=0.0,
    )
    signal = generate_signal(market, base_exposure)
    assert signal is not None
    assert signal.setup_id == "P-11"


def test_long_heavy_dampening_reduces_long_signal_below_threshold(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
    )
    heavy_exposure = _replace_model(base_exposure, net_btc=0.6, longs_btc=0.6)
    signal = generate_signal(market, heavy_exposure)
    assert signal is None


def test_envelope_trend_handling_matches_compute_trend_handling(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=28.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
    )
    signal = generate_signal(market, base_exposure)
    assert signal is not None
    expected = compute_trend_handling(market, base_exposure)
    assert signal.trend_handling == expected
