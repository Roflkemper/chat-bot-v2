from __future__ import annotations

import pytest

from services.advise_v2 import CurrentExposure, MarketContext, TrendHandling, compute_trend_handling


def _market_context(**overrides: object) -> MarketContext:
    data = {
        "price_btc": 76200.0,
        "regime_label": "trend_up",
        "regime_modifiers": ["session_open"],
        "rsi_1h": 55.0,
        "rsi_5m": 52.0,
        "price_change_5m_30bars_pct": 0.4,
        "price_change_1h_pct": 1.2,
        "nearest_liq_below": None,
        "nearest_liq_above": None,
    }
    data.update(overrides)
    return MarketContext.model_validate(data)


def _current_exposure(**overrides: object) -> CurrentExposure:
    data = {
        "net_btc": 0.1,
        "shorts_btc": -0.1,
        "longs_btc": 0.2,
        "free_margin_pct": 40.0,
        "available_usd": 1800.0,
        "margin_coef_pct": 15.0,
    }
    data.update(overrides)
    return CurrentExposure.model_validate(data)


def test_trend_up_aligned_long():
    result = compute_trend_handling(_market_context(regime_label="trend_up"), _current_exposure(net_btc=0.1))
    assert result.current_trend_strength >= 0.8
    assert "Hold" in result.de_risking_rule


def test_trend_down_aligned_short():
    result = compute_trend_handling(
        _market_context(regime_label="trend_down", price_change_1h_pct=-1.2),
        _current_exposure(net_btc=-0.5, shorts_btc=-0.5, longs_btc=0.0),
    )
    assert "No de-risking trigger" in result.de_risking_rule


def test_trend_up_against_short():
    result = compute_trend_handling(
        _market_context(regime_label="trend_up", price_change_1h_pct=1.2),
        _current_exposure(net_btc=-0.5, shorts_btc=-0.5, longs_btc=0.0),
    )
    assert "1.0%" in result.de_risking_rule
    assert "25%" in result.de_risking_rule


def test_trend_down_against_long():
    result = compute_trend_handling(
        _market_context(regime_label="trend_down", price_change_1h_pct=-1.1),
        _current_exposure(net_btc=0.3, shorts_btc=0.0, longs_btc=0.3),
    )
    assert "against down trend" in result.de_risking_rule


def test_neutral_position_under_threshold():
    result = compute_trend_handling(
        _market_context(regime_label="trend_up", price_change_1h_pct=1.0),
        _current_exposure(net_btc=-0.03, shorts_btc=-0.03, longs_btc=0.0),
    )
    assert "near neutral" in result.de_risking_rule


def test_neutral_trend_unknown():
    result = compute_trend_handling(
        _market_context(regime_label="unknown", price_change_1h_pct=0.0),
        _current_exposure(net_btc=0.5, shorts_btc=0.0, longs_btc=0.5),
    )
    assert "trend direction unclear" in result.de_risking_rule


def test_strength_with_strong_price_change():
    result = compute_trend_handling(
        _market_context(regime_label="trend_up", price_change_1h_pct=3.0),
        _current_exposure(),
    )
    assert result.current_trend_strength == pytest.approx(0.95)


def test_strength_with_moderate_price_change():
    result = compute_trend_handling(
        _market_context(regime_label="impulse_up", price_change_1h_pct=1.0),
        _current_exposure(),
    )
    assert result.current_trend_strength == pytest.approx(0.75)


def test_strength_capped_at_1():
    result = compute_trend_handling(
        _market_context(regime_label="trend_up", price_change_1h_pct=5.0),
        _current_exposure(),
    )
    assert result.current_trend_strength == pytest.approx(0.95)


def test_returns_valid_trendhandling_model():
    result = compute_trend_handling(_market_context(), _current_exposure())
    TrendHandling.model_validate(result.model_dump())


def test_realized_buffer_in_text():
    result = compute_trend_handling(
        _market_context(regime_label="trend_up", price_change_1h_pct=1.1),
        _current_exposure(net_btc=-0.5, shorts_btc=-0.5, longs_btc=0.0, available_usd=1800.0),
    )
    assert "$1800" in result.de_risking_rule


def test_pure_function_no_mutation():
    market_context = _market_context()
    current_exposure = _current_exposure()
    market_before = market_context.model_dump()
    exposure_before = current_exposure.model_dump()
    compute_trend_handling(market_context, current_exposure)
    assert market_context.model_dump() == market_before
    assert current_exposure.model_dump() == exposure_before
