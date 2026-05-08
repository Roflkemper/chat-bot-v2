"""Tests for candle_patterns module."""
from __future__ import annotations

import pandas as pd
import pytest

from services.setup_detector.candle_patterns import (
    candle_confirmation,
    is_bearish_engulfing,
    is_bullish_engulfing,
    is_bullish_hammer,
    is_shooting_star,
)


def _make_df(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """rows = [(open, high, low, close), ...]"""
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_bullish_engulfing_true() -> None:
    df = _make_df([
        (100, 101, 95, 96),    # red
        (95, 102, 94, 101),    # green, body engulfs
    ])
    assert is_bullish_engulfing(df) is True


def test_bullish_engulfing_no_engulf() -> None:
    df = _make_df([
        (100, 101, 95, 96),
        (97, 99, 96, 98),  # green but body doesn't engulf
    ])
    assert is_bullish_engulfing(df) is False


def test_bearish_engulfing_true() -> None:
    df = _make_df([
        (95, 100, 94, 99),     # green
        (100, 101, 93, 94),    # red, body engulfs
    ])
    assert is_bearish_engulfing(df) is True


def test_bullish_hammer_true() -> None:
    # body=1 (close=100, open=99), lower_wick=2 (open-low=99-97=2), upper_wick=0
    # ratio = 2/1 = 2.0 → meets wick_to_body_min=2.0
    df = _make_df([(99, 100, 97, 100)])
    assert is_bullish_hammer(df) is True


def test_bullish_hammer_too_long_upper_wick() -> None:
    # body=1, lower_wick=2, upper_wick=2 (= body, not <body)
    df = _make_df([(99, 102, 97, 100)])
    assert is_bullish_hammer(df) is False


def test_shooting_star_true() -> None:
    # body=1 (open=100, close=99), upper_wick=2, lower_wick=0
    df = _make_df([(100, 102, 99, 99)])
    assert is_shooting_star(df) is True


def test_candle_confirmation_long_engulfing() -> None:
    df = _make_df([
        (100, 101, 95, 96),
        (95, 102, 94, 101),
    ])
    assert candle_confirmation(df, side="long") == "bullish_engulfing"


def test_candle_confirmation_short_engulfing() -> None:
    df = _make_df([
        (95, 100, 94, 99),
        (100, 101, 93, 94),
    ])
    assert candle_confirmation(df, side="short") == "bearish_engulfing"


def test_candle_confirmation_returns_none_when_no_pattern() -> None:
    df = _make_df([(100, 101, 99, 100), (100, 101, 99, 100)])
    assert candle_confirmation(df, side="long") is None
