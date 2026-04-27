"""Snapshot — состояние мира на конкретный timestamp для What-If симуляции.

Snapshot строится из features_out партиций (TZ-017) и синтетического
position state (v1). В v2 position state будет браться из реальных
bot snapshots.

Использование:
    snap = build_snapshot(
        timestamp=pd.Timestamp("2026-03-15 08:00", tz="UTC"),
        symbol="BTCUSDT",
        features_dir="features_out",
        position_size_btc=-0.18,
        avg_entry=85000.0,
        grid_target_pct=1.0,
        grid_step_pct=0.5,
        boundary_top=87000.0,
        boundary_bottom=80000.0,
    )
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

_DEFAULT_CAPITAL_USD = 14_000.0

# Pre-set position scenarios (v1).
# Values are relative to close where applicable (avg_entry_offset_pct).
# Use with build_snapshot(..., preset="short_large_drawdown").
POSITION_PRESETS: dict[str, dict] = {
    # No open position — for P-3 counter-LONG, P-7 longs-after-dump
    "flat": {
        "position_size_btc": 0.0,
        "avg_entry_offset_pct": 0.0,
        "grid_target_pct": 1.0,
        "grid_step_pct": 0.5,
        "boundary_offset_top_pct": 5.0,
        "boundary_offset_bottom_pct": 5.0,
    },
    # Small short, minimal drawdown — routine operation
    "short_small_drawdown": {
        "position_size_btc": -0.05,
        "avg_entry_offset_pct": -0.2,   # entry ~0.2% below close → small loss
        "last_in_price_offset_pct": 0.1, # last IN was 0.1% above close
        "grid_target_pct": 1.0,
        "grid_step_pct": 0.5,
        "boundary_offset_top_pct": 3.0,
        "boundary_offset_bottom_pct": 5.0,
    },
    # Typical short with drawdown — P-1/P-12 scenario
    "short_large_drawdown": {
        "position_size_btc": -0.18,
        "avg_entry_offset_pct": -1.8,   # entry ~1.8% below close → ~-$300 unrealized
        "last_in_price_offset_pct": 0.3, # last IN was 0.3% above close → next in_level = close*1.003*1.005 ≈ close*1.008
        "grid_target_pct": 1.0,
        "grid_step_pct": 0.5,
        "boundary_offset_top_pct": 5.0,
        "boundary_offset_bottom_pct": 8.0,
    },
    # Critical short, near liquidation — P-4/P-5 stop/partial-close
    "short_critical": {
        "position_size_btc": -0.60,
        "avg_entry_offset_pct": -1.0,   # entry ~1% below close → heavy loss
        "last_in_price_offset_pct": 0.5, # last IN was 0.5% above close
        "grid_target_pct": 1.0,
        "grid_step_pct": 0.5,
        "boundary_offset_top_pct": 2.0,
        "boundary_offset_bottom_pct": 10.0,
    },
    # Small long — P-9 fix-branch / counter-LONG
    "long_small_position": {
        "position_size_btc": 0.05,
        "avg_entry_offset_pct": 0.3,    # entry 0.3% above close → small unrealized loss
        "grid_target_pct": 0.5,
        "grid_step_pct": 0.3,
        "boundary_offset_top_pct": 3.0,
        "boundary_offset_bottom_pct": 3.0,
    },
}


@dataclass
class Snapshot:
    timestamp: pd.Timestamp   # UTC
    symbol: str

    # ── Market state ──────────────────────────────────────────────────────────
    close: float
    feature_row: dict[str, Any]  # ~179 cols from features_out

    # ── Position state (v1: synthetic; v2: from bot snapshots) ───────────────
    position_size_btc: float    # >0 = long, <0 = short, 0 = flat
    avg_entry: float            # average entry price (USD)
    unrealized_pnl_usd: float   # computed from position & close
    realized_pnl_session: float = 0.0

    # ── Bot config ────────────────────────────────────────────────────────────
    bot_status: str = "running"   # "running" | "stopped" | "paused"
    grid_target_pct: float = 1.0  # current TP distance, %
    grid_step_pct: float = 0.5    # grid step, %
    boundary_top: float = 0.0
    boundary_bottom: float = 0.0

    # ── Grid state ────────────────────────────────────────────────────────────
    # Price level of the most recent grid IN fill. Next in_level is computed
    # as last_in_price * (1 ± gs_pct/100). 0.0 = fallback to avg_entry.
    last_in_price: float = 0.0

    # ── Counter-LONG hedge (P-3) — separate from main position ──────────────
    counter_long_size_btc: float = 0.0   # 0 = no active counter-long
    counter_long_entry: float = 0.0
    counter_long_ttl_min: int = 0        # remaining TTL in minutes
    counter_long_tp_pct: float = 1.0     # TP above entry %; 0 = disabled
    counter_long_stop_pct: float = 0.5   # stop below entry %; 0 = disabled

    # ── Capital ───────────────────────────────────────────────────────────────
    capital_usd: float = _DEFAULT_CAPITAL_USD

    def copy(self) -> "Snapshot":
        s = copy.copy(self)
        s.feature_row = dict(self.feature_row)
        return s

    @property
    def is_long(self) -> bool:
        return self.position_size_btc > 0

    @property
    def is_short(self) -> bool:
        return self.position_size_btc < 0

    @property
    def is_flat(self) -> bool:
        return self.position_size_btc == 0

    @property
    def notional_usd(self) -> float:
        return abs(self.position_size_btc) * self.close


def _unrealized(position_size_btc: float, avg_entry: float, close: float) -> float:
    """Unrealized PnL для BTC inverse-style (BitMEX): USD = size × (1/entry - 1/close)."""
    if position_size_btc == 0 or avg_entry == 0:
        return 0.0
    # For inverse contracts: PnL ≈ size_btc × (close - avg_entry) in USD
    # We approximate with linear for v1 (close to avg_entry)
    return position_size_btc * (close - avg_entry)


def _load_feature_row(
    timestamp: pd.Timestamp,
    symbol: str,
    features_dir: Path,
) -> tuple[float, dict[str, Any]]:
    """Read one row from features_out partition. Returns (close, feature_dict)."""
    ts_utc = timestamp.tz_convert("UTC") if timestamp.tzinfo else timestamp.tz_localize("UTC")
    date_str = str(ts_utc.date())
    path = features_dir / symbol / f"{date_str}.parquet"

    if not path.exists():
        raise FileNotFoundError(
            f"Feature partition not found: {path}. "
            f"Run pipeline first (scripts/run_features.py)."
        )

    df = pd.read_parquet(path)

    if ts_utc not in df.index:
        # nearest neighbour fallback (in case of rounding)
        idx = df.index.get_indexer([ts_utc], method="nearest")[0]
        row = df.iloc[idx]
    else:
        row = df.loc[ts_utc]

    close = float(row["close"])
    feature_dict = row.to_dict()
    return close, feature_dict


def build_snapshot(
    timestamp: pd.Timestamp | str,
    symbol: str,
    features_dir: str | Path = "features_out",
    *,
    preset: str | None = None,
    position_size_btc: float | None = None,
    avg_entry: float | None = None,
    unrealized_pnl_usd: float | None = None,
    realized_pnl_session: float = 0.0,
    bot_status: str = "running",
    grid_target_pct: float | None = None,
    grid_step_pct: float | None = None,
    boundary_top: float | None = None,
    boundary_bottom: float | None = None,
    capital_usd: float = _DEFAULT_CAPITAL_USD,
) -> Snapshot:
    """Build a Snapshot for the given timestamp and symbol.

    Args:
        timestamp:           UTC timestamp to build snapshot for.
        symbol:              e.g. 'BTCUSDT'.
        features_dir:        Path to features_out directory.
        position_size_btc:   Signed BTC size (neg = short).
        avg_entry:           Average entry price. Defaults to close.
        unrealized_pnl_usd:  Override unrealized PnL; computed from position if None.
        realized_pnl_session: Already-realized PnL this session.
        bot_status:          'running' | 'stopped' | 'paused'.
        grid_target_pct:     Grid TP width, %.
        grid_step_pct:       Grid step, %.
        boundary_top:        Upper boundary. Defaults to close × 1.05.
        boundary_bottom:     Lower boundary. Defaults to close × 0.95.
        capital_usd:         Account capital for pnl_pct calculation.
    """
    if isinstance(timestamp, str):
        timestamp = pd.Timestamp(timestamp, tz="UTC")

    features_dir = Path(features_dir)
    close, feature_row = _load_feature_row(timestamp, symbol, features_dir)

    # Apply preset defaults, then override with any explicitly passed kwargs
    p: dict = {}
    if preset is not None:
        if preset not in POSITION_PRESETS:
            raise ValueError(f"Unknown preset '{preset}'. Valid: {list(POSITION_PRESETS)}")
        p = POSITION_PRESETS[preset]

    pos_size = position_size_btc if position_size_btc is not None else p.get("position_size_btc", 0.0)
    tgt_pct  = grid_target_pct   if grid_target_pct   is not None else p.get("grid_target_pct",   1.0)
    gs_pct   = grid_step_pct     if grid_step_pct      is not None else p.get("grid_step_pct",    0.5)

    offset_pct = p.get("avg_entry_offset_pct", 0.0)
    entry = avg_entry if avg_entry is not None else close * (1 + offset_pct / 100)

    upnl = (
        unrealized_pnl_usd
        if unrealized_pnl_usd is not None
        else _unrealized(pos_size, entry, close)
    )

    top_offset    = p.get("boundary_offset_top_pct",    5.0)
    bottom_offset = p.get("boundary_offset_bottom_pct", 5.0)
    top    = boundary_top    if boundary_top    is not None else close * (1 + top_offset    / 100)
    bottom = boundary_bottom if boundary_bottom is not None else close * (1 - bottom_offset / 100)

    lip_offset_pct = p.get("last_in_price_offset_pct", 0.0)
    last_in_price  = close * (1 + lip_offset_pct / 100) if lip_offset_pct != 0.0 else 0.0

    return Snapshot(
        timestamp=timestamp,
        symbol=symbol,
        close=close,
        feature_row=feature_row,
        position_size_btc=pos_size,
        avg_entry=entry,
        unrealized_pnl_usd=upnl,
        realized_pnl_session=realized_pnl_session,
        bot_status=bot_status,
        grid_target_pct=tgt_pct,
        grid_step_pct=gs_pct,
        boundary_top=top,
        boundary_bottom=bottom,
        last_in_price=last_in_price,
        capital_usd=capital_usd,
    )
