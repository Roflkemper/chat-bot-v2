"""Tests for horizon_runner.py — TZ-022 §14.3 + §7 fill rules.

Synthetic bar fixtures: no real features_out dependency.
We monkeypatch _load_bars_range to inject known bars.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.whatif.horizon_runner import (
    Fill,
    StateAtMinute,
    _fill_price,
    _load_bars_range,
    _pending_orders,
    _process_bar_fills,
    _process_counter_long,
    run_horizon,
)
from src.whatif.snapshot import Snapshot

# ── Helpers ───────────────────────────────────────────────────────────────────

_FEATURES_DIR = Path("features_out")
_SYMBOL = "BTCUSDT"


def _ts(minute: int = 0) -> pd.Timestamp:
    return pd.Timestamp(f"2026-03-15 08:{minute:02d}:00", tz="UTC")


def _make_bars(ohlc_list: list[tuple]) -> pd.DataFrame:
    """Build a DataFrame of bars from [(open, high, low, close), ...] list."""
    idx = pd.date_range("2026-03-15 08:01", periods=len(ohlc_list), freq="1min", tz="UTC")
    return pd.DataFrame(
        [{"open": o, "high": h, "low": lo, "close": c} for o, h, lo, c in ohlc_list],
        index=idx,
    )


def _snap(
    close=82_000.0,
    pos=-0.18,
    avg_entry=82_000.0,
    unrealized=0.0,
    target_pct=1.0,
    gs_pct=0.5,
    bot_status="running",
    boundary_top=90_000.0,
    boundary_bottom=70_000.0,
    realized=0.0,
    counter_long_size=0.0,
    counter_long_entry=0.0,
    counter_long_ttl=0,
    counter_long_tp_pct=1.0,
    counter_long_stop_pct=0.5,
) -> Snapshot:
    return Snapshot(
        timestamp=_ts(0),
        symbol=_SYMBOL,
        close=close,
        feature_row={"close": close},
        position_size_btc=pos,
        avg_entry=avg_entry,
        unrealized_pnl_usd=unrealized,
        realized_pnl_session=realized,
        bot_status=bot_status,
        grid_target_pct=target_pct,
        grid_step_pct=gs_pct,
        boundary_top=boundary_top,
        boundary_bottom=boundary_bottom,
        counter_long_size_btc=counter_long_size,
        counter_long_entry=counter_long_entry,
        counter_long_ttl_min=counter_long_ttl,
        counter_long_tp_pct=counter_long_tp_pct,
        counter_long_stop_pct=counter_long_stop_pct,
    )


def _run(snap, bars, **kwargs):
    with patch("src.whatif.horizon_runner._load_bars_range", return_value=bars):
        return run_horizon(snap, horizon_min=len(bars), features_dir=_FEATURES_DIR, **kwargs)


# ── _fill_price ───────────────────────────────────────────────────────────────

def test_fill_price_buy_is_higher():
    # Buying: fill above level (worse for buyer)
    assert _fill_price(80_000, is_buy=True, slippage_pct=0.01) > 80_000


def test_fill_price_sell_is_lower():
    # Selling: fill below level (worse for seller)
    assert _fill_price(80_000, is_buy=False, slippage_pct=0.01) < 80_000


def test_fill_price_zero_slippage():
    assert _fill_price(80_000, is_buy=True, slippage_pct=0.0) == pytest.approx(80_000)


# ── _pending_orders ───────────────────────────────────────────────────────────

def test_pending_short_has_tp_and_in():
    orders = _pending_orders(-0.18, 82_000, 1.0, 0.5, "running", 90_000, 70_000)
    types = {o[0] for o in orders}
    assert "tp" in types
    assert "grid_in" in types


def test_pending_short_tp_below_entry():
    orders = _pending_orders(-0.18, 82_000, 1.0, 0.5, "running", 90_000, 70_000)
    tp = next(o for o in orders if o[0] == "tp")
    assert tp[1] < 82_000


def test_pending_short_in_above_entry():
    orders = _pending_orders(-0.18, 82_000, 1.0, 0.5, "running", 90_000, 70_000)
    in_ord = next(o for o in orders if o[0] == "grid_in")
    assert in_ord[1] > 82_000


def test_pending_stopped_no_in():
    orders = _pending_orders(-0.18, 82_000, 1.0, 0.5, "stopped", 90_000, 70_000)
    types = {o[0] for o in orders}
    assert "grid_in" not in types


def test_pending_flat_empty():
    orders = _pending_orders(0.0, 82_000, 1.0, 0.5, "running", 90_000, 70_000)
    assert orders == []


def test_pending_long_tp_above_entry():
    orders = _pending_orders(0.10, 80_000, 1.0, 0.5, "running", 90_000, 70_000)
    tp = next(o for o in orders if o[0] == "tp")
    assert tp[1] > 80_000


# ── _process_bar_fills: basic ─────────────────────────────────────────────────

def test_tp_hit_closes_short():
    # Short -0.18 at 82000, TP at 82000*(1-1%)=81180
    # Bar: low=80000, high=82000 → TP level 81180 is in range
    pos, avg_e, realized, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 82_000, 80_000,
        _ts(1), 0.018, 0.0, 0.0,
    )
    assert pos == pytest.approx(0.0)
    assert len(fills) == 1
    assert fills[0].order_type == "tp"


def test_tp_not_hit_when_bar_range_miss():
    # Short -0.18 at 82000, TP at 81180
    # Bar: low=81500, high=82500 → TP 81180 NOT in range
    # boundary_top=82000 blocks grid_in at 82410 (in_level > boundary_top)
    pos, avg_e, realized, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        82_000, 70_000, 82_500, 81_500,
        _ts(1), 0.018, 0.0, 0.0,
    )
    assert pos == pytest.approx(-0.18)
    assert len(fills) == 0


def test_tp_fill_price_includes_slippage():
    # SHORT TP = BUY order → fill above level
    tp_level = 82_000 * (1 - 1.0 / 100)  # 81180
    _, _, _, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 82_000, 80_000,
        _ts(1), 0.018, slippage_pct=0.1, fees_pct=0.0,
    )
    assert fills[0].fill_price == pytest.approx(tp_level * (1 + 0.1 / 100))


def test_tp_fill_realizes_profit_for_short():
    # Short -0.18 at 82000, TP at 81180 (below entry → profit)
    _, _, realized, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 82_000, 80_000,
        _ts(1), 0.018, slippage_pct=0.0, fees_pct=0.0,
    )
    assert fills[0].realized_pnl_usd > 0
    assert realized > 0


def test_in_fill_adds_to_short():
    # Short -0.18 at 82000, IN at 82000*(1+0.5%)=82410
    # Bar: low=82000, high=82500 → IN at 82410 in range
    pos, avg_e, _, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 82_500, 82_000,
        _ts(1), grid_unit_btc=0.018, slippage_pct=0.0, fees_pct=0.0,
    )
    assert pos < -0.18  # more short
    in_fill = next(f for f in fills if f.order_type == "grid_in")
    assert in_fill.size_btc < 0  # sold


# ── Multiple fills in one bar ─────────────────────────────────────────────────

def test_both_tp_and_in_same_bar():
    """Bar covers both TP (lower) and IN (higher) levels — both fill in price order."""
    # Short -0.18 at 82000
    # TP  = 82000 * 0.99 = 81180
    # IN  = 82000 * 1.005 = 82410
    # Bar: low=80000, high=83000 → covers both
    pos, avg_e, realized, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 83_000, 80_000,
        _ts(1), grid_unit_btc=0.018, slippage_pct=0.0, fees_pct=0.0,
    )
    assert len(fills) == 2
    assert fills[0].order_type == "tp"
    assert fills[1].order_type == "grid_in"
    # TP fills first (lower price 81180 < IN 82410)
    assert fills[0].level_price < fills[1].level_price


def test_both_fills_price_order_ascending():
    _, _, _, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 83_000, 80_000,
        _ts(1), grid_unit_btc=0.018, slippage_pct=0.0, fees_pct=0.0,
    )
    prices = [f.level_price for f in fills]
    assert prices == sorted(prices)


# ── Slippage direction ────────────────────────────────────────────────────────

def test_short_tp_slippage_is_buy_direction():
    """SHORT TP is a BUY order — fill above level (worse for trader)."""
    tp_level = 82_000 * 0.99
    _, _, _, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 82_000, 80_000,
        _ts(1), 0.018, slippage_pct=0.5, fees_pct=0.0,
    )
    assert fills[0].fill_price > fills[0].level_price


def test_long_tp_slippage_is_sell_direction():
    """LONG TP is a SELL order — fill below level (worse for trader)."""
    _, _, _, fills = _process_bar_fills(
        0.10, 80_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 82_000, 79_000,
        _ts(1), 0.01, slippage_pct=0.5, fees_pct=0.0,
    )
    tp = next(f for f in fills if f.order_type == "tp")
    assert tp.fill_price < tp.level_price


def test_short_in_slippage_is_sell_direction():
    """SHORT IN is a SELL order — fill below level."""
    _, _, _, fills = _process_bar_fills(
        -0.18, 82_000, 0.0, 1.0, 0.5, "running",
        90_000, 70_000, 83_000, 82_200,
        _ts(1), 0.018, slippage_pct=0.5, fees_pct=0.0,
    )
    in_fill = next((f for f in fills if f.order_type == "grid_in"), None)
    if in_fill:
        assert in_fill.fill_price < in_fill.level_price


# ── Counter-long ──────────────────────────────────────────────────────────────

def test_counter_long_tp_hit():
    """Bar.high reaches counter_long TP → exit with profit."""
    cl_entry = 80_000.0
    tp_level = cl_entry * 1.01  # 80800
    cl_size, _, cl_ttl, realized, fills = _process_counter_long(
        0.05, cl_entry, 60, tp_pct := 1.0, 0.5,
        0.0, bar_high=81_000, bar_low=79_500, bar_close=80_900,
        ts=_ts(1), slippage_pct=0.0, fees_pct=0.0,
    )
    assert cl_size == pytest.approx(0.0)
    assert cl_ttl == 0
    assert len(fills) == 1
    assert fills[0].order_type == "cl_tp"
    assert realized > 0


def test_counter_long_ttl_expiry():
    """TTL hits 0 → close at bar.close."""
    cl_size, _, cl_ttl, realized, fills = _process_counter_long(
        0.05, 80_000, 1,  # TTL=1, will reach 0 this bar
        1.0, 0.5,
        0.0, bar_high=80_500, bar_low=79_800, bar_close=80_200,
        ts=_ts(1), slippage_pct=0.0, fees_pct=0.0,
    )
    assert cl_size == pytest.approx(0.0)
    assert cl_ttl == 0
    assert fills[0].order_type == "cl_ttl"


def test_counter_long_stop_hit():
    """Bar.low below stop_level → stop loss exit."""
    cl_entry = 80_000.0
    stop_level = cl_entry * (1 - 0.5 / 100)  # 79600
    cl_size, _, cl_ttl, realized, fills = _process_counter_long(
        0.05, cl_entry, 60, 1.0, 0.5,
        0.0, bar_high=80_000, bar_low=79_400,  # below stop
        bar_close=79_500,
        ts=_ts(1), slippage_pct=0.0, fees_pct=0.0,
    )
    assert cl_size == pytest.approx(0.0)
    assert fills[0].order_type == "cl_stop"
    assert realized < 0  # stop = loss


def test_counter_long_stays_active_when_no_trigger():
    """Neither TP, stop, nor TTL → counter_long stays active."""
    # TP at 80800, stop at 79600, TTL=5
    # Bar: high=80500, low=79700 → TP not hit, stop not hit, TTL not expired
    cl_size, _, cl_ttl, _, fills = _process_counter_long(
        0.05, 80_000, 5, 1.0, 0.5,
        0.0, bar_high=80_500, bar_low=79_700, bar_close=80_200,
        ts=_ts(1), slippage_pct=0.0, fees_pct=0.0,
    )
    assert cl_size == pytest.approx(0.05)
    assert cl_ttl == 4   # decremented by 1
    assert fills == []


def test_counter_long_tp_priority_over_stop():
    """If both TP and stop levels in bar range, TP fires first."""
    # Entry 80000, TP at 80800, stop at 79600
    # Bar: low=79400, high=81000 → both hit
    cl_size, _, _, _, fills = _process_counter_long(
        0.05, 80_000, 60, 1.0, 0.5,
        0.0, bar_high=81_000, bar_low=79_400, bar_close=80_000,
        ts=_ts(1), slippage_pct=0.0, fees_pct=0.0,
    )
    assert cl_size == pytest.approx(0.0)
    assert fills[0].order_type == "cl_tp"


# ── run_horizon: integration ──────────────────────────────────────────────────

def test_horizon_returns_correct_count():
    snap = _snap()
    bars = _make_bars([(82_000, 82_100, 81_700, 82_000)] * 5)
    states = _run(snap, bars)
    assert len(states) == 5


def test_horizon_1min_target_hit():
    """1-minute horizon: target hit on bar 1 → fill recorded."""
    snap = _snap(pos=-0.18, avg_entry=82_000, target_pct=1.0)
    # TP = 82000 * 0.99 = 81180; bar covers it
    bars = _make_bars([(82_000, 82_000, 80_000, 81_000)])
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)

    assert len(states) == 1
    tp_fills = [f for f in states[0].fills if f.order_type == "tp"]
    assert len(tp_fills) == 1
    assert states[0].position_size_btc == pytest.approx(0.0)


def test_horizon_60min_no_target_exit_by_horizon():
    """60-minute horizon, TP never reached → position remains, unrealized computed."""
    snap = _snap(pos=-0.18, avg_entry=83_000, target_pct=1.0)
    # Tight bars: high=82100, low=81900 → TP at 82170 never touched; close≠avg_entry
    bars = _make_bars([(82_000, 82_100, 81_900, 82_000)] * 60)
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)

    assert len(states) == 60
    # No TP fills
    all_fills = [f for s in states for f in s.fills if f.order_type == "tp"]
    assert len(all_fills) == 0
    # Still in position
    assert states[-1].position_size_btc == pytest.approx(-0.18)
    # Unrealized is non-zero
    assert states[-1].unrealized_pnl_usd != 0.0


def test_horizon_counter_long_ttl_15min():
    """Counter-long TTL=15: at minute 15 it closes by TTL."""
    snap = _snap(
        counter_long_size=0.05, counter_long_entry=80_000,
        counter_long_ttl=15, counter_long_tp_pct=2.0, counter_long_stop_pct=1.0,
    )
    # Bars: no TP/stop triggered (high < 81600, low > 79200)
    bars = _make_bars([(80_000, 80_300, 79_800, 80_100)] * 15)
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)

    # TTL closes at bar 15
    ttl_fills = [f for s in states for f in s.fills if f.order_type == "cl_ttl"]
    assert len(ttl_fills) == 1
    # After close: counter_long_size = 0
    assert states[-1].counter_long_size == pytest.approx(0.0)
    assert states[-1].counter_long_ttl_remaining == 0


def test_horizon_unrealized_updates_each_bar():
    """Unrealized PnL updates each bar based on bar.close."""
    snap = _snap(pos=-0.18, avg_entry=82_000, target_pct=5.0)
    # Two bars with different closes (TP at 82000*0.95=77900, won't be hit)
    bars = _make_bars([
        (82_000, 82_100, 81_900, 82_000),
        (82_000, 82_200, 82_000, 82_100),
    ])
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)

    # unrealized changes between bars
    assert states[0].unrealized_pnl_usd != states[1].unrealized_pnl_usd


def test_horizon_realized_accumulates():
    """Realized PnL accumulates across multiple TP events (after re-entry via IN)."""
    snap = _snap(pos=-0.18, avg_entry=82_000, target_pct=1.0, gs_pct=0.5)
    # Bar 1: large range → both TP (81180) and IN (82410) hit → position re-enters
    # Bar 2: small range → nothing
    bars = _make_bars([
        (82_000, 83_000, 80_000, 82_000),  # TP+IN both triggered
        (82_000, 82_100, 81_900, 82_050),  # quiet
    ])
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0, grid_unit_btc=0.018)

    bar1_fills = states[0].fills
    assert len(bar1_fills) == 2  # TP then IN
    assert bar1_fills[0].order_type == "tp"
    assert bar1_fills[1].order_type == "grid_in"


def test_horizon_stopped_bot_no_in_fills():
    """Stopped bot: no grid IN fills, only TP remains."""
    snap = _snap(pos=-0.18, avg_entry=82_000, bot_status="stopped")
    bars = _make_bars([(82_000, 83_000, 80_000, 82_000)])  # large bar
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)

    fill_types = {f.order_type for f in states[0].fills}
    assert "grid_in" not in fill_types


def test_horizon_flat_position_no_fills():
    """Flat position → no TP or IN fills."""
    snap = _snap(pos=0.0, avg_entry=0.0, unrealized=0.0)
    bars = _make_bars([(82_000, 83_000, 80_000, 82_000)])
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)
    assert states[0].fills == []


def test_horizon_boundary_prevents_in_above_top():
    """Grid IN blocked when in_price > boundary_top."""
    snap = _snap(
        pos=-0.18, avg_entry=82_000,
        target_pct=1.0, gs_pct=0.5,
        boundary_top=82_100,  # IN at 82410 > boundary_top → blocked
    )
    bars = _make_bars([(82_000, 83_000, 80_000, 82_000)])
    states = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)
    in_fills = [f for f in states[0].fills if f.order_type == "grid_in"]
    assert len(in_fills) == 0


def test_horizon_fees_reduce_realized():
    """Fees applied per fill reduce realized PnL."""
    snap = _snap(pos=-0.18, avg_entry=82_000, target_pct=1.0)
    bars = _make_bars([(82_000, 82_000, 80_000, 81_000)])
    states_no_fees = _run(snap, bars, slippage_pct=0.0, fees_maker_pct=0.0)
    snap2 = _snap(pos=-0.18, avg_entry=82_000, target_pct=1.0)
    states_fees = _run(snap2, bars, slippage_pct=0.0, fees_maker_pct=0.04)

    r_no_fees = states_no_fees[-1].realized_pnl_cumulative
    r_fees = states_fees[-1].realized_pnl_cumulative
    assert r_fees < r_no_fees


def test_horizon_real_data():
    """Smoke test on real features_out — just check no crash and correct length."""
    import os
    if not Path("features_out/BTCUSDT/2026-03-15.parquet").exists():
        pytest.skip("features_out not available")

    snap = _snap()
    states = run_horizon(snap, horizon_min=60, features_dir=_FEATURES_DIR)
    assert len(states) == 60
    for s in states:
        assert s.position_size_btc is not None
        assert s.unrealized_pnl_usd is not None
