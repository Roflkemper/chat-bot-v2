"""Tests for outcome.py — §8 TZ-022."""
from __future__ import annotations

import pytest
import pandas as pd

from src.whatif.horizon_runner import Fill, StateAtMinute
from src.whatif.outcome import Outcome, _compute_max_drawdown_pct, compute_outcome

_CAPITAL = 14_000.0


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ts(minute: int = 0) -> pd.Timestamp:
    return pd.Timestamp("2026-03-15 08:00", tz="UTC") + pd.Timedelta(minutes=minute)


def _state(
    minute: int = 0,
    realized: float = 0.0,
    unrealized: float = 0.0,
    fills: list[Fill] | None = None,
    pos: float = -0.18,
) -> StateAtMinute:
    return StateAtMinute(
        ts=_ts(minute),
        open_=82_000.0, high=82_100.0, low=81_900.0, close=82_000.0,
        position_size_btc=pos,
        avg_entry=82_000.0,
        unrealized_pnl_usd=unrealized,
        realized_pnl_cumulative=realized,
        counter_long_size=0.0,
        counter_long_ttl_remaining=0,
        bot_status="running",
        fills=fills or [],
    )


def _fill(order_type: str, size_btc: float, fill_price: float, pnl: float = 0.0) -> Fill:
    return Fill(
        ts=_ts(0),
        order_type=order_type,
        level_price=fill_price,
        fill_price=fill_price,
        size_btc=size_btc,
        realized_pnl_usd=pnl,
        fees_usd=0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edge: empty states
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_states_returns_zero_outcome():
    out = compute_outcome([], capital_usd=_CAPITAL)
    assert out.pnl_usd == 0.0
    assert out.pnl_pct == 0.0
    assert out.max_drawdown_pct == 0.0
    assert out.duration_min == 0
    assert out.volume_traded_usd == 0.0
    assert out.target_hit_count == 0
    assert out.pnl_vs_baseline_usd == 0.0
    assert out.dd_vs_baseline_pct == 0.0


def test_empty_baseline_gives_zero_comparisons():
    states = [_state(0, realized=100.0, unrealized=-50.0)]
    out = compute_outcome(states, _CAPITAL, baseline_states=None)
    assert out.pnl_vs_baseline_usd == 0.0
    assert out.dd_vs_baseline_pct == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# pnl_usd = realized + unrealized at last bar
# ─────────────────────────────────────────────────────────────────────────────

def test_pnl_usd_realized_plus_unrealized():
    states = [
        _state(0, realized=100.0, unrealized=-30.0),
        _state(1, realized=200.0, unrealized=50.0),   # last bar
    ]
    out = compute_outcome(states, _CAPITAL)
    assert out.pnl_usd == pytest.approx(250.0)


def test_pnl_pct_ratio():
    states = [_state(0, realized=140.0, unrealized=0.0)]
    out = compute_outcome(states, capital_usd=_CAPITAL)
    # 140 / 14000 * 100 = 1.0%
    assert out.pnl_pct == pytest.approx(1.0)


def test_pnl_pct_negative():
    states = [_state(0, realized=-700.0, unrealized=0.0)]
    out = compute_outcome(states, capital_usd=_CAPITAL)
    assert out.pnl_pct == pytest.approx(-5.0)


# ─────────────────────────────────────────────────────────────────────────────
# duration_min = len(states)
# ─────────────────────────────────────────────────────────────────────────────

def test_duration_equals_len_states():
    states = [_state(i) for i in range(17)]
    out = compute_outcome(states, _CAPITAL)
    assert out.duration_min == 17


# ─────────────────────────────────────────────────────────────────────────────
# max_drawdown_pct
# ─────────────────────────────────────────────────────────────────────────────

def test_max_drawdown_from_peak_not_start():
    # equity: 0 → +100 → +30 → +60
    # peak=100, max DD = 100 - 30 = 70
    states = [
        _state(0, realized=0.0,   unrealized=0.0),
        _state(1, realized=0.0,   unrealized=100.0),
        _state(2, realized=0.0,   unrealized=30.0),
        _state(3, realized=0.0,   unrealized=60.0),
    ]
    out = compute_outcome(states, capital_usd=_CAPITAL)
    assert out.max_drawdown_pct == pytest.approx(70.0 / _CAPITAL * 100)


def test_max_drawdown_zero_if_monotone_increasing():
    states = [
        _state(i, realized=float(i * 10), unrealized=0.0) for i in range(10)
    ]
    out = compute_outcome(states, _CAPITAL)
    assert out.max_drawdown_pct == pytest.approx(0.0)


def test_max_drawdown_from_negative_equity():
    # equity starts at -200, drops to -500
    # peak = -200, max DD = 300
    states = [
        _state(0, realized=0.0, unrealized=-200.0),
        _state(1, realized=0.0, unrealized=-500.0),
        _state(2, realized=0.0, unrealized=-350.0),
    ]
    out = compute_outcome(states, capital_usd=_CAPITAL)
    assert out.max_drawdown_pct == pytest.approx(300.0 / _CAPITAL * 100)


def test_max_drawdown_combined_realized_unrealized():
    # realized part increases, unrealized swings
    # bar0: equity = 100 + 50 = 150
    # bar1: equity = 100 + 20 = 120  → DD = 30
    # bar2: equity = 200 + 0  = 200  → new peak, DD = 0
    # bar3: equity = 200 - 60 = 140  → DD = 60 (from 200)
    states = [
        _state(0, realized=100.0, unrealized=50.0),
        _state(1, realized=100.0, unrealized=20.0),
        _state(2, realized=200.0, unrealized=0.0),
        _state(3, realized=200.0, unrealized=-60.0),
    ]
    out = compute_outcome(states, capital_usd=_CAPITAL)
    assert out.max_drawdown_pct == pytest.approx(60.0 / _CAPITAL * 100)


# ─────────────────────────────────────────────────────────────────────────────
# volume_traded_usd and target_hit_count
# ─────────────────────────────────────────────────────────────────────────────

def test_volume_traded_usd_sum_of_fills():
    f1 = _fill("tp",      -0.18, 81_000.0)  # |size| * price = 0.18 * 81000 = 14580
    f2 = _fill("grid_in", -0.018, 82_500.0) # 0.018 * 82500 = 1485
    states = [
        _state(0, fills=[f1]),
        _state(1, fills=[f2]),
    ]
    out = compute_outcome(states, _CAPITAL)
    assert out.volume_traded_usd == pytest.approx(14_580.0 + 1_485.0)


def test_target_hit_count():
    tp1 = _fill("tp", -0.18, 81_000.0)
    tp2 = _fill("tp", -0.18, 81_000.0)
    gi  = _fill("grid_in", -0.018, 82_500.0)
    states = [
        _state(0, fills=[tp1, gi]),
        _state(1, fills=[tp2]),
    ]
    out = compute_outcome(states, _CAPITAL)
    assert out.target_hit_count == 2


def test_target_hit_count_zero_if_no_tp():
    gi = _fill("grid_in", -0.018, 82_500.0)
    states = [_state(0, fills=[gi])]
    out = compute_outcome(states, _CAPITAL)
    assert out.target_hit_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# vs baseline
# ─────────────────────────────────────────────────────────────────────────────

def test_pnl_vs_baseline_positive_when_action_better():
    action_states   = [_state(0, realized=500.0, unrealized=0.0)]
    baseline_states = [_state(0, realized=300.0, unrealized=0.0)]
    out = compute_outcome(action_states, _CAPITAL, baseline_states=baseline_states)
    assert out.pnl_vs_baseline_usd == pytest.approx(200.0)


def test_pnl_vs_baseline_negative_when_action_worse():
    action_states   = [_state(0, realized=100.0, unrealized=0.0)]
    baseline_states = [_state(0, realized=300.0, unrealized=0.0)]
    out = compute_outcome(action_states, _CAPITAL, baseline_states=baseline_states)
    assert out.pnl_vs_baseline_usd == pytest.approx(-200.0)


def test_dd_vs_baseline_negative_when_action_smaller_dd():
    # action has smaller DD → dd_vs_baseline negative = better
    action_states = [
        _state(0, unrealized=100.0),
        _state(1, unrealized=90.0),   # DD = 10
    ]
    baseline_states = [
        _state(0, unrealized=100.0),
        _state(1, unrealized=50.0),   # DD = 50
    ]
    out = compute_outcome(action_states, _CAPITAL, baseline_states=baseline_states)
    # action DD = 10/14000*100; baseline DD = 50/14000*100
    assert out.dd_vs_baseline_pct < 0


def test_action_no_effect_gives_zero_vs_baseline():
    # identical states → pnl_vs_baseline ≈ 0
    states = [_state(i, realized=float(i * 50), unrealized=-100.0) for i in range(5)]
    out = compute_outcome(states, _CAPITAL, baseline_states=list(states))
    assert out.pnl_vs_baseline_usd == pytest.approx(0.0)
    assert out.dd_vs_baseline_pct  == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Counter-long PnL included via realized_pnl_cumulative
# ─────────────────────────────────────────────────────────────────────────────

def test_counter_long_pnl_included_in_realized():
    # horizon_runner adds CL pnl to realized_pnl_cumulative — verify outcome picks it up
    cl_fill = _fill("cl_tp", -0.05, 81_000.0, pnl=50.0)
    states = [
        _state(0, realized=0.0,   unrealized=-100.0),
        _state(1, realized=50.0,  unrealized=-100.0, fills=[cl_fill]),  # CL closed at TP
        _state(2, realized=50.0,  unrealized=-80.0),
    ]
    out = compute_outcome(states, _CAPITAL)
    # pnl_usd = last.realized + last.unrealized = 50 + (-80) = -30
    assert out.pnl_usd == pytest.approx(-30.0)
    # volume includes CL fill
    assert out.volume_traded_usd == pytest.approx(0.05 * 81_000.0)
