from __future__ import annotations

import copy

import pytest

from services.advise_v2 import (
    CurrentExposure,
    LiqLevel,
    MarketContext,
    Recommendation,
    SetupMatch,
    TrendHandling,
    build_recommendation,
)


@pytest.fixture
def market_context() -> MarketContext:
    return MarketContext.model_validate(
        {
            "price_btc": 76000.0,
            "regime_label": "trend_up",
            "regime_modifiers": [],
            "rsi_1h": 55.0,
            "rsi_5m": 52.0,
            "price_change_5m_30bars_pct": -0.5,
            "price_change_1h_pct": 1.0,
            "nearest_liq_below": None,
            "nearest_liq_above": None,
        }
    )


@pytest.fixture
def current_exposure() -> CurrentExposure:
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


@pytest.fixture
def trend_handling() -> TrendHandling:
    return TrendHandling(
        current_trend_strength=0.8,
        if_trend_continues_aligned="continue",
        if_trend_reverses_against="reverse",
        de_risking_rule="rule",
    )


def _match(pattern_id: str, confidence: float, direction: str = "long") -> SetupMatch:
    return SetupMatch(
        pattern_id=pattern_id,
        pattern_name=pattern_id,
        confidence=confidence,
        direction=direction,
        matched_conditions=["ok"],
        missing_conditions=[],
    )


def test_p2_long_recommendation_basic(market_context, current_exposure, trend_handling):
    result = build_recommendation(_match("P-2", 0.8, "long"), market_context, current_exposure, trend_handling)
    assert result.primary_action == "increase_long_manual"
    assert result.size_usd_inverse is not None


def test_p6_short_recommendation_basic(market_context, current_exposure, trend_handling):
    result = build_recommendation(_match("P-6", 0.8, "short"), market_context, current_exposure, trend_handling)
    assert result.primary_action == "increase_short_manual"
    assert result.size_usd_inverse is None


def test_size_conservative_when_low_margin(market_context, current_exposure, trend_handling):
    exposure = current_exposure.model_copy(update={"free_margin_pct": 20.0})
    result = build_recommendation(_match("P-2", 1.0), market_context, exposure, trend_handling)
    assert result.size_btc_equivalent == pytest.approx(0.05)


def test_size_aggressive_when_high_margin(market_context, current_exposure, trend_handling):
    exposure = current_exposure.model_copy(update={"free_margin_pct": 70.0})
    result = build_recommendation(_match("P-2", 1.0), market_context, exposure, trend_handling)
    assert result.size_btc_equivalent == pytest.approx(0.18)


def test_size_normal_default(market_context, current_exposure, trend_handling):
    result = build_recommendation(_match("P-2", 1.0), market_context, current_exposure, trend_handling)
    assert result.size_btc_equivalent == pytest.approx(0.10)


def test_entry_zone_long_extended_by_liq_below(market_context, current_exposure, trend_handling):
    mc = market_context.model_copy(update={"nearest_liq_below": LiqLevel(price=75500.0, size_usd=400000.0)})
    result = build_recommendation(_match("P-2", 0.8), mc, current_exposure, trend_handling)
    assert result.entry_zone[0] == 75500.0


def test_entry_zone_short_extended_by_liq_above(market_context, current_exposure, trend_handling):
    mc = market_context.model_copy(update={"nearest_liq_above": LiqLevel(price=76500.0, size_usd=400000.0)})
    result = build_recommendation(_match("P-6", 0.8, "short"), mc, current_exposure, trend_handling)
    assert result.entry_zone[1] == 76500.0


def test_targets_sum_to_100_pct(market_context, current_exposure, trend_handling):
    result = build_recommendation(_match("P-2", 0.8), market_context, current_exposure, trend_handling)
    assert sum(target.size_pct for target in result.targets) == 100


def test_invalidation_format(market_context, current_exposure, trend_handling):
    long_result = build_recommendation(_match("P-2", 0.8), market_context, current_exposure, trend_handling)
    short_result = build_recommendation(_match("P-6", 0.8, "short"), market_context, current_exposure, trend_handling)
    assert long_result.invalidation.rule.startswith("5m close below ")
    assert short_result.invalidation.rule.startswith("5m close above ")


def test_max_hold_hours_per_pattern(market_context, current_exposure, trend_handling):
    assert build_recommendation(_match("P-2", 0.8), market_context, current_exposure, trend_handling).max_hold_hours == 4
    assert build_recommendation(_match("P-1", 0.8, "short"), market_context, current_exposure, trend_handling).max_hold_hours == 6
    assert build_recommendation(_match("P-3", 0.8, "short"), market_context, current_exposure, trend_handling).max_hold_hours == 8


def test_zero_confidence_raises(market_context, current_exposure, trend_handling):
    with pytest.raises(ValueError):
        build_recommendation(_match("P-2", 0.0), market_context, current_exposure, trend_handling)


def test_pure_function_no_input_mutation(market_context, current_exposure, trend_handling):
    match = _match("P-2", 0.8)
    match_before = copy.deepcopy(match.model_dump())
    market_before = copy.deepcopy(market_context.model_dump())
    exposure_before = copy.deepcopy(current_exposure.model_dump())
    trend_before = copy.deepcopy(trend_handling.model_dump())
    result = build_recommendation(match, market_context, current_exposure, trend_handling)
    Recommendation.model_validate(result.model_dump())
    assert match.model_dump() == match_before
    assert market_context.model_dump() == market_before
    assert current_exposure.model_dump() == exposure_before
    assert trend_handling.model_dump() == trend_before
