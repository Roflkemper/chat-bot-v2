"""Horizon runner — minute-by-minute What-If simulation.

Takes a Snapshot (after action applied) and rolls forward N minutes through
real OHLCV bars from features_out, simulating grid order fills.

Fill rules (TZ-022 §7):
  - Order fills at the level price, NOT at bar close.
  - Level is triggered when: bar.low ≤ level_price ≤ bar.high
  - Slippage is directional — always worse for the trader:
      BUY  fill = level_price × (1 + slippage_pct/100)
      SELL fill = level_price × (1 - slippage_pct/100)
  - Multiple fills per bar: sort by level_price ascending, process in order.
  - Fees applied per fill: abs(size) × fill_price × fees_pct/100

Grid mechanics (SHORT position example):
  - TP level    = avg_entry × (1 - target_pct/100)   → BUY  order (close short)
  - Grid IN lvl = avg_entry × (1 + gs_pct/100)       → SELL order (add to short)
  - Boundary check: IN orders only placed when in_price ≤ boundary_top (short)

Counter-long cancel triggers (P-3):
  - TTL expired  : close at bar.close (market fill)
  - Target hit   : bar.high ≥ tp_price
  - Stop hit     : bar.low  ≤ stop_price
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.whatif.snapshot import Snapshot

logger = logging.getLogger(__name__)

_SLIPPAGE_PCT   = 0.01
_FEES_MAKER_PCT = 0.04


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Fill:
    ts: pd.Timestamp
    order_type: str         # "tp" | "grid_in" | "cl_tp" | "cl_ttl" | "cl_stop"
    level_price: float      # intended order level (before slippage)
    fill_price: float       # actual fill (with slippage)
    size_btc: float         # signed position DELTA (+buy, -sell)
    realized_pnl_usd: float
    fees_usd: float


@dataclass
class StateAtMinute:
    ts: pd.Timestamp
    open_: float
    high: float
    low: float
    close: float
    position_size_btc: float
    avg_entry: float
    unrealized_pnl_usd: float
    realized_pnl_cumulative: float
    counter_long_size: float
    counter_long_ttl_remaining: int
    bot_status: str
    fills: list[Fill] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_bars_range(
    symbol: str,
    start_ts: pd.Timestamp,
    n_bars: int,
    features_dir: Path,
) -> pd.DataFrame:
    """Load up to n_bars of OHLC starting strictly after start_ts."""
    dfs = []
    current = start_ts.normalize()
    # buffer: scan enough days to cover horizon + partial first day
    for _ in range(n_bars // 1440 + 3):
        date_str = str(current.date())
        path = features_dir / symbol / f"{date_str}.parquet"
        if path.exists():
            df = pd.read_parquet(path, columns=["open", "high", "low", "close"])
            dfs.append(df)
        current += pd.Timedelta(days=1)

    if not dfs:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    combined = pd.concat(dfs).sort_index()
    after = combined[combined.index > start_ts]
    return after.iloc[:n_bars]


def _fill_price(level: float, is_buy: bool, slippage_pct: float) -> float:
    if is_buy:
        return level * (1 + slippage_pct / 100)
    return level * (1 - slippage_pct / 100)


def _fees(fill_p: float, size_btc: float, fees_pct: float) -> float:
    return abs(size_btc) * fill_p * fees_pct / 100


def _unrealized(pos: float, avg_e: float, close: float) -> float:
    if pos == 0 or avg_e == 0:
        return 0.0
    return pos * (close - avg_e)


def _weighted_avg(size_a: float, entry_a: float, size_b: float, entry_b: float) -> float:
    total = size_a + size_b
    if total == 0:
        return entry_b
    return (size_a * entry_a + size_b * entry_b) / total


# ─────────────────────────────────────────────────────────────────────────────
# Per-bar fill logic
# ─────────────────────────────────────────────────────────────────────────────

def _pending_orders(
    pos: float,
    avg_e: float,
    target_pct: float,
    gs_pct: float,
    bot_status: str,
    boundary_top: float,
    boundary_bottom: float,
    last_in_price: float | None = None,
) -> list[tuple[str, float, bool]]:
    """Return list of (order_type, level_price, is_buy) for current state.

    next in_level is computed from last_in_price (most recent grid IN fill price).
    Falls back to avg_e if last_in_price is None or 0.
    """
    if pos == 0:
        return []

    # last_in_price anchor: the price level of the most recent grid IN fill.
    # Next in_level steps one gs_pct away from it — not from avg_entry.
    lip = last_in_price if (last_in_price is not None and last_in_price > 0) else avg_e

    orders = []
    if pos < 0:  # SHORT
        tp_level = avg_e * (1 - target_pct / 100)
        orders.append(("tp", tp_level, True))   # buying back

        if bot_status == "running":
            in_level = lip * (1 + gs_pct / 100)
            if in_level <= boundary_top:
                orders.append(("grid_in", in_level, False))  # selling more
    else:  # LONG
        tp_level = avg_e * (1 + target_pct / 100)
        orders.append(("tp", tp_level, False))  # selling

        if bot_status == "running":
            in_level = lip * (1 - gs_pct / 100)
            if in_level >= boundary_bottom:
                orders.append(("grid_in", in_level, True))  # buying more

    return orders


def _process_bar_fills(
    pos: float,
    avg_e: float,
    realized: float,
    target_pct: float,
    gs_pct: float,
    bot_status: str,
    boundary_top: float,
    boundary_bottom: float,
    bar_high: float,
    bar_low: float,
    ts: pd.Timestamp,
    grid_unit_btc: float,
    slippage_pct: float,
    fees_pct: float,
    last_in_price: float | None = None,
) -> tuple[float, float, float, list[Fill]]:
    """Process all fills for one bar. Returns (new_pos, new_avg_e, new_realized, fills)."""
    pending = _pending_orders(pos, avg_e, target_pct, gs_pct, bot_status, boundary_top, boundary_bottom, last_in_price)

    # Only orders whose level is within bar range
    triggered = [
        (otype, level, is_buy)
        for otype, level, is_buy in pending
        if bar_low <= level <= bar_high
    ]
    # Sort ascending by level_price (lower fills first)
    triggered.sort(key=lambda x: x[1])

    fills: list[Fill] = []
    for otype, level, is_buy in triggered:
        fp = _fill_price(level, is_buy, slippage_pct)

        if otype == "tp":
            # Close full position
            close_size = pos          # signed position being closed (e.g. -0.18)
            pnl = close_size * (fp - avg_e)
            fee = _fees(fp, close_size, fees_pct)
            fills.append(Fill(
                ts=ts, order_type="tp",
                level_price=level, fill_price=fp,
                size_btc=-close_size,  # delta: opposite of position
                realized_pnl_usd=pnl, fees_usd=fee,
            ))
            realized += pnl - fee
            pos = 0.0
            avg_e = 0.0

        elif otype == "grid_in" and bot_status == "running":
            # Add one grid unit to position
            add = -grid_unit_btc if pos <= 0 else grid_unit_btc
            fee = _fees(fp, add, fees_pct)
            avg_e = _weighted_avg(pos, avg_e, add, fp) if pos != 0 else fp
            pos += add
            realized -= fee
            fills.append(Fill(
                ts=ts, order_type="grid_in",
                level_price=level, fill_price=fp,
                size_btc=add, realized_pnl_usd=-fee, fees_usd=fee,
            ))

    return pos, avg_e, realized, fills


def _process_counter_long(
    cl_size: float,
    cl_entry: float,
    cl_ttl: int,
    cl_tp_pct: float,
    cl_stop_pct: float,
    realized: float,
    bar_high: float,
    bar_low: float,
    bar_close: float,
    ts: pd.Timestamp,
    slippage_pct: float,
    fees_pct: float,
) -> tuple[float, float, int, float, list[Fill]]:
    """Process counter-long for one bar. Returns (cl_size, cl_entry, cl_ttl, realized, fills)."""
    if cl_size <= 0:
        return cl_size, cl_entry, cl_ttl, realized, []

    cl_ttl -= 1
    fills: list[Fill] = []

    # Check TP first (most profitable exit)
    if cl_tp_pct > 0:
        tp_level = cl_entry * (1 + cl_tp_pct / 100)
        if bar_low <= tp_level <= bar_high:
            fp = _fill_price(tp_level, is_buy=False, slippage_pct=slippage_pct)
            pnl = cl_size * (fp - cl_entry)
            fee = _fees(fp, cl_size, fees_pct)
            fills.append(Fill(
                ts=ts, order_type="cl_tp",
                level_price=tp_level, fill_price=fp,
                size_btc=-cl_size, realized_pnl_usd=pnl, fees_usd=fee,
            ))
            realized += pnl - fee
            return 0.0, 0.0, 0, realized, fills

    # Check stop
    if cl_stop_pct > 0:
        stop_level = cl_entry * (1 - cl_stop_pct / 100)
        if bar_low <= stop_level:
            fp = _fill_price(stop_level, is_buy=False, slippage_pct=slippage_pct)
            pnl = cl_size * (fp - cl_entry)
            fee = _fees(fp, cl_size, fees_pct)
            fills.append(Fill(
                ts=ts, order_type="cl_stop",
                level_price=stop_level, fill_price=fp,
                size_btc=-cl_size, realized_pnl_usd=pnl, fees_usd=fee,
            ))
            realized += pnl - fee
            return 0.0, 0.0, 0, realized, fills

    # Check TTL
    if cl_ttl <= 0:
        fp = _fill_price(bar_close, is_buy=False, slippage_pct=slippage_pct)
        pnl = cl_size * (fp - cl_entry)
        fee = _fees(fp, cl_size, fees_pct)
        fills.append(Fill(
            ts=ts, order_type="cl_ttl",
            level_price=bar_close, fill_price=fp,
            size_btc=-cl_size, realized_pnl_usd=pnl, fees_usd=fee,
        ))
        realized += pnl - fee
        return 0.0, 0.0, 0, realized, fills

    return cl_size, cl_entry, cl_ttl, realized, fills


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_horizon(
    snapshot: Snapshot,
    horizon_min: int = 240,
    features_dir: str | Path = "features_out",
    grid_unit_btc: float | None = None,
    slippage_pct: float = _SLIPPAGE_PCT,
    fees_maker_pct: float = _FEES_MAKER_PCT,
) -> list[StateAtMinute]:
    """Simulate horizon_min minutes from snapshot, processing grid fills bar-by-bar.

    Args:
        snapshot:       State after action has been applied (from action_simulator).
        horizon_min:    Number of 1m bars to simulate.
        features_dir:   Path to features_out directory.
        grid_unit_btc:  BTC added per grid IN fill. Default: 10% of initial position.
        slippage_pct:   Market slippage % (directional, always against trader).
        fees_maker_pct: Fee rate for fills, %.

    Returns:
        List of StateAtMinute, one per bar. Length ≤ horizon_min (truncated if data ends).
    """
    features_dir = Path(features_dir)

    if grid_unit_btc is None:
        grid_unit_btc = max(abs(snapshot.position_size_btc) * 0.1, 0.001)

    # Mutable simulation state
    pos        = snapshot.position_size_btc
    avg_e      = snapshot.avg_entry
    realized   = snapshot.realized_pnl_session
    bot_status = snapshot.bot_status
    b_top      = snapshot.boundary_top
    b_bot      = snapshot.boundary_bottom
    tgt_pct    = snapshot.grid_target_pct
    gs_pct     = snapshot.grid_step_pct

    # Counter-long state
    cl_size     = snapshot.counter_long_size_btc
    cl_entry    = snapshot.counter_long_entry
    cl_ttl      = snapshot.counter_long_ttl_min
    cl_tp_pct   = snapshot.counter_long_tp_pct
    cl_stop_pct = snapshot.counter_long_stop_pct

    # last_in_price: anchor for next grid IN level; 0 → fallback to avg_entry
    last_in_price = snapshot.last_in_price if snapshot.last_in_price > 0 else avg_e

    bars = _load_bars_range(snapshot.symbol, snapshot.timestamp, horizon_min, features_dir)

    states: list[StateAtMinute] = []

    for ts, row in bars.iterrows():
        bar_open  = float(row["open"])
        bar_high  = float(row["high"])
        bar_low   = float(row["low"])
        bar_close = float(row["close"])

        all_fills: list[Fill] = []

        # Counter-long processing (before main position — independent)
        cl_size, cl_entry, cl_ttl, realized, cl_fills = _process_counter_long(
            cl_size, cl_entry, cl_ttl, cl_tp_pct, cl_stop_pct,
            realized, bar_high, bar_low, bar_close,
            ts, slippage_pct, fees_maker_pct,
        )
        all_fills.extend(cl_fills)

        # Main position processing
        pos, avg_e, realized, main_fills = _process_bar_fills(
            pos, avg_e, realized,
            tgt_pct, gs_pct, bot_status, b_top, b_bot,
            bar_high, bar_low,
            ts, grid_unit_btc, slippage_pct, fees_maker_pct,
            last_in_price=last_in_price,
        )
        # Update last_in_price from any grid_in that fired this bar
        for f in main_fills:
            if f.order_type == "grid_in":
                last_in_price = f.level_price
        all_fills.extend(main_fills)

        upnl = _unrealized(pos, avg_e, bar_close)

        states.append(StateAtMinute(
            ts=ts,
            open_=bar_open, high=bar_high, low=bar_low, close=bar_close,
            position_size_btc=pos,
            avg_entry=avg_e,
            unrealized_pnl_usd=upnl,
            realized_pnl_cumulative=realized,
            counter_long_size=cl_size,
            counter_long_ttl_remaining=cl_ttl,
            bot_status=bot_status,
            fills=all_fills,
        ))

    return states
