"""Тесты hysteresis wrapper для TZ-068."""
from __future__ import annotations

import pytest

from services.regime_classifier_v2.classify_v2 import ClassifierInputs
from services.regime_classifier_v2.hysteresis_wrapper import (
    CASCADE_STATES,
    HysteresisRegimeWrapper,
    MIN_BARS_TO_SWITCH,
)


def _inputs_for_strong_up() -> ClassifierInputs:
    """Inputs которые classify_bar возвращает STRONG_UP."""
    return ClassifierInputs(
        close=80000.0,
        ema50=79500.0,
        ema200=78000.0,
        ema50_slope_pct=0.5,
        adx_proxy=30.0,
        atr_pct_1h=1.0,
        bb_width_pct=2.0,
        bb_width_p20_30d=1.0,
        move_15m_pct=0.1,
        move_1h_pct=0.5,
        move_4h_pct=2.0,
        move_24h_pct=5.0,
        dist_to_ema200_pct=2.5,
    )


def _inputs_for_range() -> ClassifierInputs:
    """Inputs которые дают RANGE."""
    return ClassifierInputs(
        close=80000.0,
        ema50=80000.0,
        ema200=80000.0,
        ema50_slope_pct=0.0,
        adx_proxy=15.0,
        atr_pct_1h=0.5,
        bb_width_pct=2.0,
        bb_width_p20_30d=1.5,
        move_15m_pct=0.0,
        move_1h_pct=0.0,
        move_4h_pct=0.0,
        move_24h_pct=0.0,
        dist_to_ema200_pct=0.0,
    )


def _inputs_for_cascade_up() -> ClassifierInputs:
    """Cascade — fast move bypass hysteresis."""
    return ClassifierInputs(
        close=80000.0,
        ema50=78000.0,
        ema200=77000.0,
        ema50_slope_pct=0.5,
        adx_proxy=30.0,
        atr_pct_1h=2.0,
        bb_width_pct=3.0,
        bb_width_p20_30d=1.0,
        move_15m_pct=4.0,  # > CASCADE_15M_PCT (3.0)
        move_1h_pct=4.0,
        move_4h_pct=5.0,
        move_24h_pct=8.0,
        dist_to_ema200_pct=3.0,
    )


def test_first_bar_just_classifies():
    w = HysteresisRegimeWrapper()
    r = w.classify(_inputs_for_strong_up())
    # Первый бар — переход с initial RANGE на STRONG_UP требует >=3 баров
    # → пока остаёмся в RANGE
    assert r.regime == "RANGE"
    assert r.raw_classification == "STRONG_UP"
    assert r.transition is False
    assert r.bars_in_state == 0  # только что инициализировался не bumping


def test_hysteresis_requires_n_bars_to_switch():
    w = HysteresisRegimeWrapper()
    # Подряд STRONG_UP барам, проверяем что только после N сменится
    for i in range(MIN_BARS_TO_SWITCH - 1):
        r = w.classify(_inputs_for_strong_up())
        assert r.regime == "RANGE", f"После {i+1} баров не должен переключаться"
        assert r.transition is False

    # N-й бар — переключение
    r = w.classify(_inputs_for_strong_up())
    assert r.regime == "STRONG_UP", "После MIN_BARS_TO_SWITCH должен переключиться"
    assert r.transition is True
    assert r.bars_in_state == 1


def test_continuous_stable_state_no_dance():
    w = HysteresisRegimeWrapper(initial_state="STRONG_UP")
    # bars_in_state накапливается — confidence растёт
    for i in range(10):
        r = w.classify(_inputs_for_strong_up())
        assert r.regime == "STRONG_UP"
        assert r.transition is False
    # После 10 одинаковых баров confidence должна быть около 1.0
    assert r.confidence > 0.85


def test_one_off_flip_does_not_change_state():
    w = HysteresisRegimeWrapper(initial_state="STRONG_UP")
    # 5 STRONG_UP — стабилизировался
    for _ in range(5):
        w.classify(_inputs_for_strong_up())

    # Один RANGE-бар — не должен сменить
    r = w.classify(_inputs_for_range())
    assert r.regime == "STRONG_UP"
    assert r.raw_classification == "RANGE"  # raw разошёлся
    assert r.transition is False

    # Снова STRONG_UP — bars_in_state продолжает расти
    r = w.classify(_inputs_for_strong_up())
    assert r.regime == "STRONG_UP"
    assert r.bars_in_state >= 6


def test_cascade_bypasses_hysteresis():
    """CASCADE — единственное состояние мгновенного flip."""
    w = HysteresisRegimeWrapper(initial_state="STRONG_UP")
    for _ in range(5):
        w.classify(_inputs_for_strong_up())

    # Один CASCADE_UP бар — мгновенно state меняется
    r = w.classify(_inputs_for_cascade_up())
    assert r.regime == "CASCADE_UP"
    assert r.transition is True
    assert r.confidence == 1.0


def test_confidence_drops_when_candidate_pressure_grows():
    w = HysteresisRegimeWrapper(initial_state="STRONG_UP")
    # Установим стабильный STRONG_UP
    for _ in range(8):
        w.classify(_inputs_for_strong_up())
    conf_stable = w.classify(_inputs_for_strong_up()).confidence

    # Один RANGE — confidence падает (есть candidate)
    r = w.classify(_inputs_for_range())
    assert r.confidence < conf_stable, "При появлении кандидата confidence снижается"


def test_candidate_resets_if_raw_changes():
    """Если кандидат после 1-2 баров не подтверждается, он сбрасывается."""
    w = HysteresisRegimeWrapper(initial_state="STRONG_UP")
    for _ in range(5):
        w.classify(_inputs_for_strong_up())

    # 2 RANGE подряд (кандидат накапливается)
    w.classify(_inputs_for_range())
    w.classify(_inputs_for_range())
    assert w.state.candidate_regime == "RANGE"
    assert w.state.bars_in_candidate == 2

    # Затем STRONG_UP — кандидат сбрасывается
    w.classify(_inputs_for_strong_up())
    assert w.state.candidate_regime is None
    assert w.state.bars_in_candidate == 0


def test_reset_works():
    w = HysteresisRegimeWrapper(initial_state="STRONG_UP")
    for _ in range(10):
        w.classify(_inputs_for_strong_up())
    assert w.state.regime == "STRONG_UP"
    w.reset(initial="RANGE")
    assert w.state.regime == "RANGE"
    assert w.state.bars_in_state == 0


def test_cascade_states_constant_correct():
    assert "CASCADE_UP" in CASCADE_STATES
    assert "CASCADE_DOWN" in CASCADE_STATES
    assert "STRONG_UP" not in CASCADE_STATES
