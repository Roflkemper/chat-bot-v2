from __future__ import annotations

import copy

import pytest

from services.advise_v2 import CurrentExposure, LiqLevel, MarketContext, SetupMatch, match_setups


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
            "margin_coef_pct": 15.0,
        }
    )


def _replace_model(model, **updates):
    return model.model_copy(update=updates)


def _by_id(matches: list[SetupMatch], pattern_id: str) -> SetupMatch:
    return next(match for match in matches if match.pattern_id == pattern_id)


def test_returns_12_patterns(base_market_context, base_exposure):
    matches = match_setups(base_market_context, base_exposure)
    assert len(matches) == 12
    assert {match.pattern_id for match in matches} == {f"P-{idx}" for idx in range(1, 13)}


def test_sorted_by_confidence_desc(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=25.0,
        price_change_5m_30bars_pct=-1.2,
        nearest_liq_below=LiqLevel(price=76050.0, size_usd=500000.0),
        price_btc=76100.0,
        regime_modifiers=["volume_spike_5m"],
    )
    matches = match_setups(market, base_exposure)
    confidences = [match.confidence for match in matches]
    assert confidences == sorted(confidences, reverse=True)


def test_p2_reversal_long_strong_match(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down",
        rsi_1h=20.0,
        price_change_5m_30bars_pct=-1.5,
        nearest_liq_below=LiqLevel(price=76000.0, size_usd=600000.0),
        price_btc=76180.0,
        regime_modifiers=["volume_spike_5m", "liq_cluster_breached_below"],
    )
    match = _by_id(match_setups(market, base_exposure), "P-2")
    assert match.confidence > 0.7


def test_p2_no_liq_below_partial_match(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="impulse_down_exhausting",
        rsi_1h=30.0,
        price_change_5m_30bars_pct=-1.3,
    )
    match = _by_id(match_setups(market, base_exposure), "P-2")
    assert 0 < match.confidence < 0.7


def test_p5_hard_ban_always_zero(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="trend_down", rsi_1h=40.0, price_change_1h_pct=-2.0)
    match = _by_id(match_setups(market, base_exposure), "P-5")
    assert match.confidence == 0.0


def test_p8_hard_ban_always_zero(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="trend_up", rsi_1h=65.0, price_change_1h_pct=2.0)
    match = _by_id(match_setups(market, base_exposure), "P-8")
    assert match.confidence == 0.0


def test_p10_hard_ban_zero_with_missing_session(base_market_context, base_exposure):
    match = _by_id(match_setups(base_market_context, base_exposure), "P-10")
    assert match.confidence == 0.0
    assert match.missing_conditions == ["session_history_required"]


def test_exposure_long_heavy_dampens_long_patterns(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="trend_up",
        rsi_1h=50.0,
        price_change_5m_30bars_pct=-0.6,
        regime_modifiers=["pullback_to_ema"],
    )
    light = _by_id(match_setups(market, base_exposure), "P-4").confidence
    heavy = _by_id(
        match_setups(market, _replace_model(base_exposure, net_btc=0.6, longs_btc=0.6)),
        "P-4",
    ).confidence
    assert heavy == pytest.approx(light * 0.5)


def test_exposure_short_heavy_dampens_short_patterns(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="trend_down",
        rsi_1h=50.0,
        price_change_5m_30bars_pct=0.6,
        regime_modifiers=["pullback_to_ema"],
    )
    light = _by_id(match_setups(market, base_exposure), "P-3").confidence
    heavy = _by_id(
        match_setups(market, _replace_model(base_exposure, net_btc=-0.6, shorts_btc=-0.6)),
        "P-3",
    ).confidence
    assert heavy == pytest.approx(light * 0.5)


def test_exposure_neutral_no_dampening(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="consolidation", rsi_1h=45.0, price_change_1h_pct=0.1)
    neutral = _by_id(match_setups(market, base_exposure), "P-11").confidence
    same = _by_id(
        match_setups(market, _replace_model(base_exposure, net_btc=0.4, longs_btc=0.4)),
        "P-11",
    ).confidence
    assert same == pytest.approx(neutral)


def test_p1_range_fade_short_match(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="range_wide",
        rsi_1h=70.0,
        price_change_5m_30bars_pct=0.7,
        regime_modifiers=["upper_band_test", "volume_decline"],
    )
    match = _by_id(match_setups(market, base_exposure), "P-1")
    assert match.confidence > 0.6


def test_p7_range_fade_long_match(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="range_tight",
        rsi_1h=30.0,
        price_change_5m_30bars_pct=-0.8,
        regime_modifiers=["lower_band_test"],
    )
    match = _by_id(match_setups(market, base_exposure), "P-7")
    assert match.confidence > 0.6


def test_p3_trend_pullback_short(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="trend_down", rsi_1h=50.0, price_change_5m_30bars_pct=0.5)
    match = _by_id(match_setups(market, base_exposure), "P-3")
    assert match.confidence > 0.6


def test_p4_trend_pullback_long(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="trend_up", rsi_1h=55.0, price_change_5m_30bars_pct=-0.6)
    match = _by_id(match_setups(market, base_exposure), "P-4")
    assert match.confidence > 0.6


def test_p9_breakout_long(base_market_context, base_exposure):
    market = _replace_model(
        base_market_context,
        regime_label="trend_up",
        rsi_1h=60.0,
        price_change_5m_30bars_pct=1.0,
        nearest_liq_above=LiqLevel(price=76100.0, size_usd=400000.0),
        price_btc=76200.0,
        regime_modifiers=["volume_spike_5m"],
    )
    match = _by_id(match_setups(market, base_exposure), "P-9")
    assert match.confidence > 0.55


def test_p11_range_continuation_long(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="consolidation", rsi_1h=45.0, price_change_1h_pct=0.2)
    match = _by_id(match_setups(market, base_exposure), "P-11")
    assert match.confidence == pytest.approx(0.5)


def test_p12_range_continuation_short(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="consolidation", rsi_1h=55.0, price_change_1h_pct=0.2)
    match = _by_id(match_setups(market, base_exposure), "P-12")
    assert match.confidence == pytest.approx(0.5)


def test_all_patterns_pure(base_market_context, base_exposure):
    market = _replace_model(base_market_context, regime_label="trend_up", rsi_1h=60.0, price_change_5m_30bars_pct=1.0)
    first = match_setups(market, base_exposure)
    second = match_setups(market, base_exposure)
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]


def test_input_not_mutated(base_market_context, base_exposure):
    market_before = copy.deepcopy(base_market_context.model_dump())
    exposure_before = copy.deepcopy(base_exposure.model_dump())
    match_setups(base_market_context, base_exposure)
    assert base_market_context.model_dump() == market_before
    assert base_exposure.model_dump() == exposure_before
