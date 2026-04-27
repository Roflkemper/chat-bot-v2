"""Action simulator — 10 actions from MASTER §5 / TZ-022 §6.

Each action is a pure function:
    action_*(snapshot: Snapshot, params: dict) -> Snapshot

Rules:
  - Always operates on snapshot.copy() — original never mutated
  - No I/O, no side effects
  - Invalid params raise ValueError (never silently corrupt state)
  - position=0 for position-requiring actions → no-op (returns copy unchanged)

PARAM_GRIDS: default grid search ranges per action (TZ-022 §6 + §9).
ACTIONS: name → function registry for runner.py.
"""
from __future__ import annotations

from typing import Callable

from src.whatif.snapshot import Snapshot, _unrealized

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_SLIPPAGE_PCT = 0.01  # default market fill slippage


def _fill_price(close: float, is_buy: bool, slippage_pct: float = _SLIPPAGE_PCT) -> float:
    """Market fill price with slippage. Buy fills higher, sell fills lower."""
    if is_buy:
        return close * (1 + slippage_pct / 100)
    return close * (1 - slippage_pct / 100)


def _weighted_avg_entry(
    size_a: float, entry_a: float, size_b: float, entry_b: float
) -> float:
    total = size_a + size_b
    if total == 0:
        return entry_b
    return (size_a * entry_a + size_b * entry_b) / total


# ─────────────────────────────────────────────────────────────────────────────
# §6.1  A-RAISE-BOUNDARY
# ─────────────────────────────────────────────────────────────────────────────

def action_raise_boundary(snapshot: Snapshot, params: dict) -> Snapshot:
    """Raise boundary_top above current day high + offset_pct.

    params:
        offset_pct: float  — % above current_d_high (default 0.5)
    """
    offset_pct = float(params.get("offset_pct", 0.5))
    ref_high = float(snapshot.feature_row.get("current_d_high", snapshot.close))
    s = snapshot.copy()
    s.boundary_top = ref_high * (1 + offset_pct / 100)
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.2  A-CHANGE-TARGET
# ─────────────────────────────────────────────────────────────────────────────

def action_change_target(snapshot: Snapshot, params: dict) -> Snapshot:
    """Multiply grid_target_pct by target_factor.

    params:
        target_factor: float  — must be > 0
    """
    factor = float(params["target_factor"])
    if factor <= 0:
        raise ValueError(f"target_factor must be > 0, got {factor}")
    s = snapshot.copy()
    s.grid_target_pct = s.grid_target_pct * factor
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.3  A-CHANGE-GS
# ─────────────────────────────────────────────────────────────────────────────

def action_change_gs(snapshot: Snapshot, params: dict) -> Snapshot:
    """Multiply grid_step_pct by gs_factor.

    params:
        gs_factor: float  — must be > 0
    """
    factor = float(params["gs_factor"])
    if factor <= 0:
        raise ValueError(f"gs_factor must be > 0, got {factor}")
    s = snapshot.copy()
    s.grid_step_pct = s.grid_step_pct * factor
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.4  A-STOP
# ─────────────────────────────────────────────────────────────────────────────

def action_stop(snapshot: Snapshot, params: dict) -> Snapshot:
    """Stop bot — position stays, no new grid orders placed."""
    s = snapshot.copy()
    s.bot_status = "stopped"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.5  A-RESUME
# ─────────────────────────────────────────────────────────────────────────────

def action_resume(snapshot: Snapshot, params: dict) -> Snapshot:
    """Resume bot from stopped/paused state."""
    s = snapshot.copy()
    s.bot_status = "running"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.6  A-CLOSE-PARTIAL
# ─────────────────────────────────────────────────────────────────────────────

def action_close_partial(snapshot: Snapshot, params: dict) -> Snapshot:
    """Close fraction% of position at market price.

    params:
        fraction:     float — 25 / 50 / 75 / 100 (percent of position)
        slippage_pct: float — market fill slippage (default 0.01%)

    If position is flat, returns copy unchanged (no-op).
    """
    if snapshot.position_size_btc == 0:
        return snapshot.copy()

    fraction = float(params["fraction"])
    if not (0 < fraction <= 100):
        raise ValueError(f"fraction must be in (0, 100], got {fraction}")

    slippage = float(params.get("slippage_pct", _SLIPPAGE_PCT))
    s = snapshot.copy()

    closed_size = s.position_size_btc * (fraction / 100)
    is_buy = s.position_size_btc < 0  # closing short = buying back
    price = _fill_price(s.close, is_buy=is_buy, slippage_pct=slippage)

    # PnL: for short, closing at lower price is profit; for long, higher price is profit
    realized = closed_size * (price - s.avg_entry)
    s.realized_pnl_session += realized
    s.position_size_btc -= closed_size

    if abs(s.position_size_btc) < 1e-10:
        s.position_size_btc = 0.0
        s.unrealized_pnl_usd = 0.0
    else:
        s.unrealized_pnl_usd = _unrealized(s.position_size_btc, s.avg_entry, s.close)

    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.7  A-LAUNCH-STACK-SHORT
# ─────────────────────────────────────────────────────────────────────────────

def action_launch_stack_short(snapshot: Snapshot, params: dict) -> Snapshot:
    """Launch additional short bot at current price (stacks onto existing position).

    params:
        size_btc:     float  — additional short size (positive value)
        slippage_pct: float  — fill slippage (default 0.01%)
    """
    add_size = float(params["size_btc"])
    if add_size <= 0:
        raise ValueError(f"size_btc must be > 0, got {add_size}")

    slippage = float(params.get("slippage_pct", _SLIPPAGE_PCT))
    s = snapshot.copy()

    fill = _fill_price(s.close, is_buy=False, slippage_pct=slippage)  # selling
    new_short = -add_size
    new_total = s.position_size_btc + new_short

    s.avg_entry = _weighted_avg_entry(s.position_size_btc, s.avg_entry, new_short, fill)
    s.position_size_btc = new_total
    s.unrealized_pnl_usd = _unrealized(s.position_size_btc, s.avg_entry, s.close)
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.8  A-LAUNCH-STACK-LONG
# ─────────────────────────────────────────────────────────────────────────────

def action_launch_stack_long(snapshot: Snapshot, params: dict) -> Snapshot:
    """Launch additional long bot at current price (stacks onto existing position).

    params:
        size_btc:     float  — additional long size (positive value)
        slippage_pct: float  — fill slippage (default 0.01%)
    """
    add_size = float(params["size_btc"])
    if add_size <= 0:
        raise ValueError(f"size_btc must be > 0, got {add_size}")

    slippage = float(params.get("slippage_pct", _SLIPPAGE_PCT))
    s = snapshot.copy()

    fill = _fill_price(s.close, is_buy=True, slippage_pct=slippage)  # buying
    new_long = add_size
    new_total = s.position_size_btc + new_long

    s.avg_entry = _weighted_avg_entry(s.position_size_btc, s.avg_entry, new_long, fill)
    s.position_size_btc = new_total
    s.unrealized_pnl_usd = _unrealized(s.position_size_btc, s.avg_entry, s.close)
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.9  A-LAUNCH-COUNTER-LONG  (P-3 hedge — distinct from stack-long)
# ─────────────────────────────────────────────────────────────────────────────

def action_launch_counter_long(snapshot: Snapshot, params: dict) -> Snapshot:
    """Launch a counter-LONG hedge (P-3): small size, strict TTL, separate tracking.

    Distinct from A-LAUNCH-STACK-LONG:
      - Does NOT merge with main position (tracked as counter_long_* fields)
      - Has TTL: auto-closes after ttl_min minutes (enforced by horizon_runner)
      - Small size by default (0.05 BTC)
      - Has optional take_profit_pct exit

    params:
        size_btc:         float  — hedge size (default 0.05, should be small)
        ttl_min:          int    — time-to-live in minutes (default 60)
        take_profit_pct:  float  — TP above entry in % (default 1.0; 0 = disabled)
        slippage_pct:     float  — fill slippage (default 0.01%)
    """
    size = float(params.get("size_btc", 0.05))
    ttl = int(params.get("ttl_min", 60))
    slippage = float(params.get("slippage_pct", _SLIPPAGE_PCT))

    if size <= 0:
        raise ValueError(f"size_btc must be > 0, got {size}")
    if ttl <= 0:
        raise ValueError(f"ttl_min must be > 0, got {ttl}")

    s = snapshot.copy()
    fill = _fill_price(s.close, is_buy=True, slippage_pct=slippage)

    s.counter_long_size_btc = size
    s.counter_long_entry = fill
    s.counter_long_ttl_min = ttl
    # main position unchanged
    return s


# ─────────────────────────────────────────────────────────────────────────────
# §6.10  A-RESTART-WITH-NEW-PARAMS
# ─────────────────────────────────────────────────────────────────────────────

def action_restart_with_new_params(snapshot: Snapshot, params: dict) -> Snapshot:
    """Close current position at market + restart bot with new boundaries centered on close.

    params:
        boundary_width_pct: float  — half-width of new boundaries (default 5.0%)
        new_target_pct:     float  — new grid TP% (default: keep current)
        new_gs_pct:         float  — new grid step% (default: keep current)
        slippage_pct:       float  — fill slippage (default 0.01%)
    """
    width = float(params.get("boundary_width_pct", 5.0))
    slippage = float(params.get("slippage_pct", _SLIPPAGE_PCT))
    s = snapshot.copy()

    # Close existing position
    if s.position_size_btc != 0:
        is_buy = s.position_size_btc < 0
        price = _fill_price(s.close, is_buy=is_buy, slippage_pct=slippage)
        realized = s.position_size_btc * (price - s.avg_entry)
        s.realized_pnl_session += realized
        s.position_size_btc = 0.0
        s.unrealized_pnl_usd = 0.0

    # New bot config centered on current close
    s.avg_entry = s.close
    s.boundary_top    = s.close * (1 + width / 100)
    s.boundary_bottom = s.close * (1 - width / 100)
    s.grid_target_pct = float(params.get("new_target_pct", s.grid_target_pct))
    s.grid_step_pct   = float(params.get("new_gs_pct",     s.grid_step_pct))
    s.bot_status      = "running"
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

ACTIONS: dict[str, Callable[[Snapshot, dict], Snapshot]] = {
    "A-RAISE-BOUNDARY":         action_raise_boundary,
    "A-CHANGE-TARGET":          action_change_target,
    "A-CHANGE-GS":              action_change_gs,
    "A-STOP":                   action_stop,
    "A-RESUME":                 action_resume,
    "A-CLOSE-PARTIAL":          action_close_partial,
    "A-LAUNCH-STACK-SHORT":     action_launch_stack_short,
    "A-LAUNCH-STACK-LONG":      action_launch_stack_long,
    "A-LAUNCH-COUNTER-LONG":    action_launch_counter_long,
    "A-RESTART-WITH-NEW-PARAMS": action_restart_with_new_params,
}

# Default param grids for grid_search (TZ-022 §6 + §9)
PARAM_GRIDS: dict[str, list[dict]] = {
    "A-RAISE-BOUNDARY": [
        {"offset_pct": v} for v in [0.3, 0.5, 0.7, 1.0]
    ],
    "A-CHANGE-TARGET": [
        {"target_factor": v} for v in [0.4, 0.5, 0.6, 0.7, 0.8]
    ],
    "A-CHANGE-GS": [
        {"gs_factor": v} for v in [0.5, 0.6, 0.67, 0.75, 0.85]
    ],
    "A-STOP":   [{}],
    "A-RESUME": [{}],
    "A-CLOSE-PARTIAL": [
        {"fraction": v} for v in [25, 50, 75, 100]
    ],
    "A-LAUNCH-STACK-SHORT": [
        {"size_btc": v} for v in [0.05, 0.10, 0.18]
    ],
    "A-LAUNCH-STACK-LONG": [
        {"size_btc": v} for v in [0.05, 0.10, 0.18]
    ],
    "A-LAUNCH-COUNTER-LONG": [
        {"size_btc": s, "ttl_min": t}
        for s in [0.03, 0.05, 0.10]
        for t in [30, 60, 120]
    ],
    "A-RESTART-WITH-NEW-PARAMS": [
        {"boundary_width_pct": w, "new_target_pct": t}
        for w in [3.0, 5.0, 7.0]
        for t in [0.8, 1.0, 1.2]
    ],
}
