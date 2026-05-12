"""Tests for walk_forward_t2mega module.

Эти тесты не запускают реальный sim (он 3+ секунды на окно). Проверяем
структуру модуля + edge-cases вокруг генерации окон.
"""
from __future__ import annotations

import pytest

from services.backtest.walk_forward_t2mega import (
    SIM_TO_PLATFORM_FACTOR,
    T2_MEGA_PARAMS,
    WindowResult,
    _gen_windows,
    format_walk_forward,
)


def test_t2_mega_params_match_v5_leader() -> None:
    """Параметры должны точно соответствовать T2-MEGA leader в V5 doc."""
    assert T2_MEGA_PARAMS["side"] == "LONG"
    assert T2_MEGA_PARAMS["grid_step_pct"] == 0.04
    assert T2_MEGA_PARAMS["target_pct"] == 0.9
    assert T2_MEGA_PARAMS["instop_pct"] == 0.018
    assert T2_MEGA_PARAMS["indicator_period"] == 30
    assert T2_MEGA_PARAMS["indicator_threshold_pct"] == 1.5


def test_gen_windows_correct_count() -> None:
    """90d span × 30d step over 2 years → ~22 windows."""
    windows = _gen_windows(
        span_days=90, step_days=30,
        start_iso="2024-05-01", end_iso="2026-04-29",
    )
    assert 20 <= len(windows) <= 24
    # First window starts at start
    assert windows[0][1] == "2024-05-01"
    # Step is 30 days
    assert windows[1][1] == "2024-05-31"


def test_gen_windows_respects_end() -> None:
    """Last window must end ≤ end_iso."""
    windows = _gen_windows(
        span_days=90, step_days=30,
        start_iso="2024-05-01", end_iso="2024-09-01",
    )
    assert len(windows) >= 1
    last_end = windows[-1][2]
    assert last_end <= "2024-09-01"


def test_format_handles_empty_results() -> None:
    assert format_walk_forward([]) == "Нет окон для прогона."


def test_format_reports_pos_count() -> None:
    results = [
        WindowResult(label="w1", start="", end="", bars=100,
                     realized_pnl_btc=0.01, realized_pnl_usd=1000.0,
                     unrealized_pnl_btc=0.0, trading_volume_usd=1e6,
                     num_fills=10, pct_of_ref_profit=50.0),
        WindowResult(label="w2", start="", end="", bars=100,
                     realized_pnl_btc=-0.01, realized_pnl_usd=-1000.0,
                     unrealized_pnl_btc=0.0, trading_volume_usd=1e6,
                     num_fills=10, pct_of_ref_profit=-50.0),
    ]
    out = format_walk_forward(results)
    assert "положительных: 1" in out


def test_sim_to_platform_factor_is_positive() -> None:
    assert SIM_TO_PLATFORM_FACTOR > 1.0
