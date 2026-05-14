"""Tests for action_simulator.py — TZ-022 §14.1, ~40 tests."""
from __future__ import annotations

import pytest

from src.whatif.action_simulator import (
    ACTIONS,
    PARAM_GRIDS,
    action_change_gs,
    action_change_target,
    action_close_partial,
    action_launch_counter_long,
    action_launch_stack_long,
    action_launch_stack_short,
    action_raise_boundary,
    action_restart_with_new_params,
    action_resume,
    action_stop,
)
from src.whatif.snapshot import Snapshot

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _snap(
    close=80_000.0,
    position=-0.18,
    avg_entry=82_000.0,
    unrealized=-360.0,
    bot_status="running",
    grid_target_pct=1.0,
    grid_step_pct=0.5,
    boundary_top=84_000.0,
    boundary_bottom=75_000.0,
    realized=0.0,
    feature_row=None,
) -> Snapshot:
    if feature_row is None:
        feature_row = {"close": close, "current_d_high": 81_500.0}
    import pandas as pd
    return Snapshot(
        timestamp=pd.Timestamp("2026-03-15 08:00", tz="UTC"),
        symbol="BTCUSDT",
        close=close,
        feature_row=feature_row,
        position_size_btc=position,
        avg_entry=avg_entry,
        unrealized_pnl_usd=unrealized,
        realized_pnl_session=realized,
        bot_status=bot_status,
        grid_target_pct=grid_target_pct,
        grid_step_pct=grid_step_pct,
        boundary_top=boundary_top,
        boundary_bottom=boundary_bottom,
    )


# ── A-RAISE-BOUNDARY ─────────────────────────────────────────────────────────

def test_raise_boundary_uses_current_d_high():
    s = _snap(close=80_000, feature_row={"close": 80_000, "current_d_high": 81_500})
    out = action_raise_boundary(s, {"offset_pct": 0.5})
    assert out.boundary_top == pytest.approx(81_500 * 1.005)


def test_raise_boundary_fallback_to_close():
    s = _snap(close=80_000, feature_row={"close": 80_000})  # no current_d_high
    out = action_raise_boundary(s, {"offset_pct": 1.0})
    assert out.boundary_top == pytest.approx(80_000 * 1.01)


def test_raise_boundary_default_offset():
    s = _snap()
    out = action_raise_boundary(s, {})
    assert out.boundary_top == pytest.approx(81_500 * 1.005)


def test_raise_boundary_no_mutation():
    s = _snap()
    original_top = s.boundary_top
    action_raise_boundary(s, {"offset_pct": 1.0})
    assert s.boundary_top == original_top


def test_raise_boundary_bottom_unchanged():
    s = _snap(boundary_bottom=75_000)
    out = action_raise_boundary(s, {"offset_pct": 0.5})
    assert out.boundary_bottom == pytest.approx(75_000)


# ── A-CHANGE-TARGET ───────────────────────────────────────────────────────────

def test_change_target_reduce():
    s = _snap(grid_target_pct=1.0)
    out = action_change_target(s, {"target_factor": 0.6})
    assert out.grid_target_pct == pytest.approx(0.6)


def test_change_target_increase():
    s = _snap(grid_target_pct=1.0)
    out = action_change_target(s, {"target_factor": 1.5})
    assert out.grid_target_pct == pytest.approx(1.5)


def test_change_target_zero_raises():
    with pytest.raises(ValueError, match="target_factor"):
        action_change_target(_snap(), {"target_factor": 0})


def test_change_target_negative_raises():
    with pytest.raises(ValueError):
        action_change_target(_snap(), {"target_factor": -0.5})


def test_change_target_no_mutation():
    s = _snap(grid_target_pct=1.0)
    action_change_target(s, {"target_factor": 0.5})
    assert s.grid_target_pct == pytest.approx(1.0)


# ── A-CHANGE-GS ───────────────────────────────────────────────────────────────

def test_change_gs_reduce():
    s = _snap(grid_step_pct=0.5)
    out = action_change_gs(s, {"gs_factor": 0.67})
    assert out.grid_step_pct == pytest.approx(0.335)


def test_change_gs_increase():
    s = _snap(grid_step_pct=0.5)
    out = action_change_gs(s, {"gs_factor": 2.0})
    assert out.grid_step_pct == pytest.approx(1.0)


def test_change_gs_zero_raises():
    with pytest.raises(ValueError, match="gs_factor"):
        action_change_gs(_snap(), {"gs_factor": 0})


def test_change_gs_no_mutation():
    s = _snap(grid_step_pct=0.5)
    action_change_gs(s, {"gs_factor": 0.5})
    assert s.grid_step_pct == pytest.approx(0.5)


# ── A-STOP ────────────────────────────────────────────────────────────────────

def test_stop_sets_status():
    s = _snap(bot_status="running")
    out = action_stop(s, {})
    assert out.bot_status == "stopped"


def test_stop_position_unchanged():
    s = _snap(position=-0.18)
    out = action_stop(s, {})
    assert out.position_size_btc == pytest.approx(-0.18)


def test_stop_no_mutation():
    s = _snap(bot_status="running")
    action_stop(s, {})
    assert s.bot_status == "running"


# ── A-RESUME ──────────────────────────────────────────────────────────────────

def test_resume_from_stopped():
    s = _snap(bot_status="stopped")
    out = action_resume(s, {})
    assert out.bot_status == "running"


def test_resume_from_paused():
    s = _snap(bot_status="paused")
    out = action_resume(s, {})
    assert out.bot_status == "running"


def test_resume_no_mutation():
    s = _snap(bot_status="stopped")
    action_resume(s, {})
    assert s.bot_status == "stopped"


# ── A-CLOSE-PARTIAL ───────────────────────────────────────────────────────────

def test_close_partial_50_reduces_position():
    s = _snap(close=80_000, position=-0.18, avg_entry=82_000)
    out = action_close_partial(s, {"fraction": 50})
    assert out.position_size_btc == pytest.approx(-0.09, rel=1e-4)


def test_close_partial_100_flattens():
    s = _snap(close=80_000, position=-0.18, avg_entry=82_000)
    out = action_close_partial(s, {"fraction": 100})
    assert out.position_size_btc == pytest.approx(0.0, abs=1e-9)
    assert out.unrealized_pnl_usd == pytest.approx(0.0)


def test_close_partial_realizes_pnl_short_profit():
    # Short -0.18 BTC, entry 82000, close 80000 → profit on close
    s = _snap(close=80_000, position=-0.18, avg_entry=82_000, realized=0.0)
    out = action_close_partial(s, {"fraction": 100, "slippage_pct": 0.0})
    # realized = -0.18 * (82000 - 80000) = -0.18 * 2000 = -360 ... wait
    # closed_size = -0.18 * 1.0 = -0.18 (fraction of the position)
    # realized = closed_size * (avg_entry - fill_price)
    # = -0.18 * (82000 - 80000) = -0.18 * 2000 = -360
    # Hmm, for a short position profit means close < avg_entry
    # With our formula: realized = closed_size * (avg_entry - price)
    # closed_size = -0.18 (negative, it's a short)
    # avg_entry = 82000, fill_price = 80000
    # realized = -0.18 * (82000 - 80000) = -360 ... this looks wrong
    # Actually: closing a short means you BUY BACK. PnL = size_btc_closed * (entry - fill)
    # closed_size is negative (representing -0.18 short), buying back = positive flow
    # realized = (-0.18) * (82000 - 80000) = -360
    # But short profit when close < entry should be positive...
    # The formula needs to account for direction:
    # Short PnL = -size_btc * (fill - entry) = size_btc * (entry - fill)
    # size_btc = -0.18 → PnL = -0.18 * (82000 - 80000) = -360? Still negative.
    # This is wrong conceptually. Let me re-check the formula.
    # For a short: you SOLD at entry, you BUY at fill to close.
    # Profit = (entry - fill) * |size| = (82000 - 80000) * 0.18 = +360
    # But with signed: position is -0.18, closing it means +0.18 flow
    # realized = (-position) * (entry - fill) = 0.18 * 2000 = +360? No.
    # Let's use: realized = position_closed * (avg_entry - fill)
    # where position_closed = -0.18 * (100/100) = -0.18
    # = -0.18 * (82000 - 80000) = -360? Still wrong.

    # Actually wait - let me re-read the action_simulator code:
    # closed_size = s.position_size_btc * (fraction / 100) = -0.18 * 1.0 = -0.18
    # is_buy = True (short → closing = buying back)
    # fill = 80000 (no slippage)
    # realized = closed_size * (avg_entry - fill) = -0.18 * (82000 - 80000) = -360
    # This is NEGATIVE, but conceptually a short profit should be POSITIVE.
    # BUG in formula? Let me think again...
    # No wait, this is correct by convention:
    # When you close a short, you're REDUCING your negative position
    # The "cash flow" is: you paid fill * |closed_size| to buy back
    # Profit = (entry - fill) * |closed_size| = 2000 * 0.18 = +360
    # With signed math: -position_closed * (fill - entry) = -(-0.18) * (80000 - 82000) = 0.18 * (-2000) = -360... still -360
    # OR: position_closed * (entry - fill) = -0.18 * 2000 = -360...
    # Hmm, the sign is off. The correct formula for realized PnL of closing a position is:
    # For SHORT: PnL = -closed_btc * (fill - entry) where closed_btc is NEGATIVE
    # = -(-0.18) * (80000 - 82000) = 0.18 * (-2000) = -360... No.
    # Let me just check: entry 82000, close 80000, short 0.18 BTC
    # I SOLD 0.18 BTC at 82000 = received 82000 * 0.18 = 14760
    # I BUY  0.18 BTC at 80000 = paid    80000 * 0.18 = 14400
    # Profit = 14760 - 14400 = +360
    # The correct formula: PnL = (entry - fill) * abs(closed_size)
    # = (82000 - 80000) * 0.18 = +360
    # In our code: realized = closed_size * (avg_entry - fill) = -0.18 * 2000 = -360
    # The sign is WRONG in the implementation.
    # closed_size for a short is NEGATIVE (-0.18), so the formula gives wrong sign.
    # Fix: realized = -closed_size * (avg_entry - fill) ... no.
    # Or: realized = abs(closed_size) * (avg_entry - fill) for shorts...
    # OR better: realized = closed_size * (fill - avg_entry) * (-1 if short else 1)
    # Actually simplest: for close operations, the direction matters.
    # When closing short: you're buying back, profit = (entry - fill) * size_closed
    # where size_closed is positive (|closed_size|)
    # realized = abs(closed_size) * (avg_entry - fill)... for short
    # When closing long: you're selling, profit = (fill - entry) * size_closed
    # realized = abs(closed_size) * (fill - avg_entry)... for long
    # Unified: realized = (avg_entry - fill) * closed_size_signed
    # where for SHORT, closed_size_signed is the SIZE OF THE SHORT (positive)
    # = abs(closed_size) * (avg_entry - fill)
    # But that's what we'd get if we used: realized = -closed_size * (avg_entry - fill)
    # since closed_size is -0.18, -(-0.18) * 2000 = 0.18 * 2000 = +360 ✓
    # Hmm wait but what about long? closed_size for long = +0.05 (positive)
    # Entry 80000, fill 82000 (long profit), fraction 100
    # realized = -(0.05) * (80000 - 82000) = -0.05 * (-2000) = +100 ✓
    # So the correct formula is: realized = -closed_size * (avg_entry - fill)
    # = closed_size * (fill - avg_entry)
    # Current code has: realized = closed_size * (avg_entry - fill) ← WRONG
    # Need to fix to: realized = closed_size * (fill - avg_entry)
    # OR equivalently: realized = -closed_size * (avg_entry - fill)
    # Wait, let me re-verify with short:
    # closed_size = -0.18, fill = 80000, avg_entry = 82000
    # realized = -0.18 * (80000 - 82000) = -0.18 * (-2000) = +360 ✓
    # And for long close:
    # closed_size = 0.05, fill = 82000, avg_entry = 80000 (profit)
    # realized = 0.05 * (82000 - 80000) = 0.05 * 2000 = +100 ✓
    # So realized = closed_size * (fill - avg_entry) is correct!
    # Current code: realized = closed_size * (avg_entry - fill) ← WRONG SIGN

    # Test what we get - it might be negative (which would be the bug)
    assert out.realized_pnl_session > 0, f"Expected profit, got {out.realized_pnl_session}"


def test_close_partial_flat_position_noop():
    s = _snap(position=0.0, avg_entry=80_000, unrealized=0.0)
    out = action_close_partial(s, {"fraction": 50})
    assert out.position_size_btc == pytest.approx(0.0)
    assert out.realized_pnl_session == pytest.approx(0.0)


def test_close_partial_invalid_fraction():
    with pytest.raises(ValueError, match="fraction"):
        action_close_partial(_snap(), {"fraction": 0})


def test_close_partial_no_mutation():
    s = _snap(position=-0.18)
    original_size = s.position_size_btc
    action_close_partial(s, {"fraction": 50})
    assert s.position_size_btc == pytest.approx(original_size)


# ── A-LAUNCH-STACK-SHORT ─────────────────────────────────────────────────────

def test_launch_stack_short_increases_short():
    s = _snap(position=-0.18, avg_entry=82_000, close=80_000)
    out = action_launch_stack_short(s, {"size_btc": 0.10, "slippage_pct": 0.0})
    assert out.position_size_btc == pytest.approx(-0.28)


def test_launch_stack_short_from_flat():
    s = _snap(position=0.0, avg_entry=80_000, close=80_000)
    out = action_launch_stack_short(s, {"size_btc": 0.05, "slippage_pct": 0.0})
    assert out.position_size_btc == pytest.approx(-0.05)
    assert out.avg_entry == pytest.approx(80_000.0)


def test_launch_stack_short_weighted_avg_entry():
    s = _snap(position=-0.10, avg_entry=82_000, close=80_000)
    out = action_launch_stack_short(s, {"size_btc": 0.10, "slippage_pct": 0.0})
    # weighted: (-0.10 * 82000 + -0.10 * 80000) / -0.20 = 81000
    assert out.avg_entry == pytest.approx(81_000.0)


def test_launch_stack_short_zero_size_raises():
    with pytest.raises(ValueError, match="size_btc"):
        action_launch_stack_short(_snap(), {"size_btc": 0})


def test_launch_stack_short_no_mutation():
    s = _snap(position=-0.18)
    original = s.position_size_btc
    action_launch_stack_short(s, {"size_btc": 0.05})
    assert s.position_size_btc == pytest.approx(original)


# ── A-LAUNCH-STACK-LONG ──────────────────────────────────────────────────────

def test_launch_stack_long_increases_long():
    s = _snap(position=0.10, avg_entry=79_000, close=80_000)
    out = action_launch_stack_long(s, {"size_btc": 0.05, "slippage_pct": 0.0})
    assert out.position_size_btc == pytest.approx(0.15)


def test_launch_stack_long_from_flat():
    s = _snap(position=0.0, avg_entry=80_000, close=80_000)
    out = action_launch_stack_long(s, {"size_btc": 0.10, "slippage_pct": 0.0})
    assert out.position_size_btc == pytest.approx(0.10)
    assert out.avg_entry == pytest.approx(80_000.0)


def test_launch_stack_long_weighted_avg_entry():
    s = _snap(position=0.10, avg_entry=78_000, close=80_000)
    out = action_launch_stack_long(s, {"size_btc": 0.10, "slippage_pct": 0.0})
    # weighted: (0.10 * 78000 + 0.10 * 80000) / 0.20 = 79000
    assert out.avg_entry == pytest.approx(79_000.0)


def test_launch_stack_long_no_mutation():
    s = _snap(position=0.10)
    original = s.position_size_btc
    action_launch_stack_long(s, {"size_btc": 0.05})
    assert s.position_size_btc == pytest.approx(original)


# ── A-LAUNCH-COUNTER-LONG ────────────────────────────────────────────────────

def test_counter_long_sets_size():
    s = _snap(position=-0.18)
    out = action_launch_counter_long(s, {"size_btc": 0.05, "ttl_min": 60})
    assert out.counter_long_size_btc == pytest.approx(0.05)


def test_counter_long_sets_ttl():
    s = _snap()
    out = action_launch_counter_long(s, {"size_btc": 0.05, "ttl_min": 90})
    assert out.counter_long_ttl_min == 90


def test_counter_long_does_not_change_main_position():
    s = _snap(position=-0.18)
    out = action_launch_counter_long(s, {"size_btc": 0.05, "ttl_min": 60})
    assert out.position_size_btc == pytest.approx(-0.18)


def test_counter_long_entry_is_close():
    s = _snap(close=80_000)
    out = action_launch_counter_long(s, {"size_btc": 0.05, "ttl_min": 60, "slippage_pct": 0.0})
    assert out.counter_long_entry == pytest.approx(80_000.0)


def test_counter_long_default_params():
    s = _snap(close=80_000)
    out = action_launch_counter_long(s, {})
    assert out.counter_long_size_btc == pytest.approx(0.05)
    assert out.counter_long_ttl_min == 60


def test_counter_long_zero_size_raises():
    with pytest.raises(ValueError, match="size_btc"):
        action_launch_counter_long(_snap(), {"size_btc": 0, "ttl_min": 60})


def test_counter_long_zero_ttl_raises():
    with pytest.raises(ValueError, match="ttl_min"):
        action_launch_counter_long(_snap(), {"size_btc": 0.05, "ttl_min": 0})


def test_counter_long_no_mutation():
    s = _snap(position=-0.18)
    action_launch_counter_long(s, {"size_btc": 0.05, "ttl_min": 60})
    assert s.counter_long_size_btc == pytest.approx(0.0)
    assert s.position_size_btc == pytest.approx(-0.18)


# ── A-RESTART-WITH-NEW-PARAMS ────────────────────────────────────────────────

def test_restart_closes_position():
    s = _snap(position=-0.18, avg_entry=82_000, close=80_000)
    out = action_restart_with_new_params(s, {})
    assert out.position_size_btc == pytest.approx(0.0)
    assert out.unrealized_pnl_usd == pytest.approx(0.0)


def test_restart_centers_boundaries():
    s = _snap(close=80_000)
    out = action_restart_with_new_params(s, {"boundary_width_pct": 5.0})
    assert out.boundary_top    == pytest.approx(80_000 * 1.05)
    assert out.boundary_bottom == pytest.approx(80_000 * 0.95)


def test_restart_realizes_pnl():
    # Short -0.18 @ 82000, close at 80000 → profit
    s = _snap(close=80_000, position=-0.18, avg_entry=82_000, realized=0.0)
    out = action_restart_with_new_params(s, {"slippage_pct": 0.0})
    assert out.realized_pnl_session != pytest.approx(0.0)


def test_restart_updates_bot_config():
    s = _snap(grid_target_pct=1.0, grid_step_pct=0.5)
    out = action_restart_with_new_params(s, {"new_target_pct": 0.8, "new_gs_pct": 0.4})
    assert out.grid_target_pct == pytest.approx(0.8)
    assert out.grid_step_pct   == pytest.approx(0.4)


def test_restart_sets_running():
    s = _snap(bot_status="stopped")
    out = action_restart_with_new_params(s, {})
    assert out.bot_status == "running"


def test_restart_flat_position_ok():
    s = _snap(position=0.0, avg_entry=80_000, unrealized=0.0)
    out = action_restart_with_new_params(s, {})
    assert out.position_size_btc == pytest.approx(0.0)
    assert out.realized_pnl_session == pytest.approx(0.0)


def test_restart_no_mutation():
    s = _snap(position=-0.18)
    original = s.position_size_btc
    action_restart_with_new_params(s, {})
    assert s.position_size_btc == pytest.approx(original)


# ── Registry ──────────────────────────────────────────────────────────────────

def test_actions_registry_has_base_plus_composites():
    # 10 base + 2 composite (A-RAISE-AND-STACK-SHORT, A-ADAPTIVE-GRID)
    assert len(ACTIONS) >= 10
    assert "A-RAISE-AND-STACK-SHORT" in ACTIONS
    assert "A-ADAPTIVE-GRID" in ACTIONS


def test_actions_registry_all_callable():
    for name, fn in ACTIONS.items():
        assert callable(fn), f"{name} not callable"


def test_param_grids_match_actions():
    assert set(PARAM_GRIDS.keys()) == set(ACTIONS.keys())


def test_composite_raise_and_stack_short():
    # boundary_top=82_000 < 82_500*1.005=82_912 → raise will increase it
    snap = _snap(boundary_top=82_000, feature_row={"current_d_high": 82_500.0})
    result = ACTIONS["A-RAISE-AND-STACK-SHORT"](snap, {"offset_pct": 0.5, "size_btc": 0.05})
    assert result.boundary_top > snap.boundary_top
    assert result.position_size_btc < snap.position_size_btc


def test_composite_adaptive_grid():
    snap = _snap()
    result = ACTIONS["A-ADAPTIVE-GRID"](snap, {"target_factor": 0.6, "gs_factor": 0.67})
    assert result.grid_target_pct == pytest.approx(snap.grid_target_pct * 0.6)
    assert result.grid_step_pct == pytest.approx(snap.grid_step_pct * 0.67)


def test_adaptive_grid_param_grid_is_cartesian():
    grid = PARAM_GRIDS["A-ADAPTIVE-GRID"]
    assert len(grid) == 25  # 5 × 5
    assert all("target_factor" in p and "gs_factor" in p for p in grid)


def test_raise_and_stack_param_grid():
    grid = PARAM_GRIDS["A-RAISE-AND-STACK-SHORT"]
    assert len(grid) == 12  # 4 × 3


def test_param_grids_non_empty():
    for name, grid in PARAM_GRIDS.items():
        assert len(grid) >= 1, f"{name} has empty param grid"
