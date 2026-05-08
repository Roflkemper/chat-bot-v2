"""Tests for services.regime_classifier_v2.classify_v2."""
from __future__ import annotations

import pytest

from services.regime_classifier_v2.classify_v2 import (
    ClassifierInputs,
    classify_bar,
    project_3state,
)


def _base(**overrides) -> ClassifierInputs:
    base = dict(
        close=80000, ema50=79500, ema200=79000,
        ema50_slope_pct=0.5, adx_proxy=15, atr_pct_1h=1.0,
        bb_width_pct=2.0, bb_width_p20_30d=1.5,
        move_15m_pct=0.0, move_1h_pct=0.0, move_4h_pct=0.0, move_24h_pct=0.0,
        dist_to_ema200_pct=1.0,
    )
    base.update(overrides)
    return ClassifierInputs(**base)


def test_cascade_up_15m() -> None:
    assert classify_bar(_base(move_15m_pct=4.0)) == "CASCADE_UP"


def test_cascade_down_1h() -> None:
    assert classify_bar(_base(move_1h_pct=-6.0)) == "CASCADE_DOWN"


def test_cascade_up_4h() -> None:
    assert classify_bar(_base(move_4h_pct=10.0)) == "CASCADE_UP"


def test_strong_up_high_adx() -> None:
    assert classify_bar(_base(
        ema50=80500, ema200=78000, ema50_slope_pct=1.5, adx_proxy=30,
        dist_to_ema200_pct=3.0,
    )) == "STRONG_UP"


def test_strong_down_high_adx() -> None:
    assert classify_bar(_base(
        ema50=77500, ema200=80000, ema50_slope_pct=-1.5, adx_proxy=30,
        dist_to_ema200_pct=-3.0,
    )) == "STRONG_DOWN"


def test_slow_up_low_adx_high_dist() -> None:
    """Operator's case — bull drift with weak ADX, but EMA stack + slope + dist > 1.5%."""
    result = classify_bar(_base(
        ema50=80500, ema200=78000, ema50_slope_pct=0.5, adx_proxy=10,
        dist_to_ema200_pct=3.0,
    ))
    assert result == "SLOW_UP"


def test_slow_down_low_adx() -> None:
    assert classify_bar(_base(
        ema50=77500, ema200=80000, ema50_slope_pct=-0.5, adx_proxy=10,
        dist_to_ema200_pct=-3.0,
    )) == "SLOW_DOWN"


def test_drift_up_low_atr_positive_24h() -> None:
    assert classify_bar(_base(
        ema50=79500, ema200=79000,  # weak EMA stack
        ema50_slope_pct=0.1, dist_to_ema200_pct=0.5,  # below SLOW threshold
        atr_pct_1h=1.0, move_24h_pct=3.0,
    )) == "DRIFT_UP"


def test_drift_down_low_atr_negative_24h() -> None:
    assert classify_bar(_base(
        ema50=79000, ema200=79500,
        ema50_slope_pct=-0.1, dist_to_ema200_pct=-0.5,
        atr_pct_1h=1.0, move_24h_pct=-3.0,
    )) == "DRIFT_DOWN"


def test_compression_low_bb_width() -> None:
    assert classify_bar(_base(
        bb_width_pct=1.0, bb_width_p20_30d=1.5, atr_pct_1h=0.5,
        ema50=79500, ema200=79000, ema50_slope_pct=0, dist_to_ema200_pct=0.5,
        move_24h_pct=0.5,
    )) == "COMPRESSION"


def test_range_default() -> None:
    assert classify_bar(_base()) == "RANGE"


def test_no_ema200_returns_range() -> None:
    assert classify_bar(_base(ema200=None)) == "RANGE"


def test_project_3state_markup() -> None:
    for state in ("STRONG_UP", "SLOW_UP", "DRIFT_UP", "CASCADE_UP"):
        assert project_3state(state) == "MARKUP"


def test_project_3state_markdown() -> None:
    for state in ("STRONG_DOWN", "SLOW_DOWN", "DRIFT_DOWN", "CASCADE_DOWN"):
        assert project_3state(state) == "MARKDOWN"


def test_project_3state_range() -> None:
    for state in ("RANGE", "COMPRESSION"):
        assert project_3state(state) == "RANGE"


def test_operator_4_6_may_scenario() -> None:
    """Reproduces the case from operator's screenshot — 4-6 May bull drift.

    Per calibration on live data: dist_ema200 ≈ +3%, slope ≈ +0.5%/12h,
    adx ≈ 9 (low), move_24h ≈ +1.0%. v1 says RANGE, v2 must say SLOW_UP.
    """
    result = classify_bar(_base(
        close=82000, ema50=81000, ema200=79500,
        ema50_slope_pct=0.5, adx_proxy=9, atr_pct_1h=1.3,
        dist_to_ema200_pct=3.14, move_24h_pct=1.0,
    ))
    assert result == "SLOW_UP", f"Expected SLOW_UP, got {result}"
