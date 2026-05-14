"""H10 grid probe simulator."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd

from services.h10_detector import H10Setup


@dataclass(frozen=True)
class ProbeParams:
    grid_steps: int = 6
    grid_step_pct: float = 0.0025
    total_btc: float = 0.15
    tp_pct: float = 0.005
    time_stop_hours: int = 2
    protective_stop_pct: float | None = None


@dataclass
class ProbeResult:
    setup_ts: datetime
    n_orders_filled: int
    avg_entry: float
    exit_price: float
    exit_reason: Literal["tp", "time_stop", "protective_stop"]
    pnl_btc: float
    pnl_usd: float
    volume_btc: float
    volume_usd: float
    duration_minutes: int
    max_drawdown_pct: float


def simulate_probe(
    setup: H10Setup,
    ohlcv_1m: pd.DataFrame,
    params: ProbeParams,
) -> ProbeResult | None:
    # Perf: assume ohlcv_1m has a sorted DatetimeIndex (set in _load_ohlcv).
    # `.loc[start:end]` is O(log n) on a sorted index; the previous
    # boolean-mask + .sort_index() was O(n) and ran on the full ~1M-row
    # DataFrame for every (bar × params) call.
    # Upper bound: 24h is well above any reasonable time_stop_hours
    # (default 2, max in full-grid 4), so we never miss an exit but cap
    # the worst-case loop length at ≤1440 rows even when grid never fills.
    start_ts = _to_utc(setup.timestamp)
    end_ts = start_ts + pd.Timedelta(hours=24)
    sim = ohlcv_1m.loc[start_ts:end_ts]
    if sim.empty:
        return None

    size_per_order = params.total_btc / params.grid_steps
    grid_prices = _build_grid_prices(setup, params)
    fills: list[tuple[float, float]] = []
    first_fill_ts: pd.Timestamp | None = None
    max_drawdown_pct = 0.0

    # Perf: itertuples is ~5x faster than iterrows on this row count.
    for row in sim.itertuples():
        bar_ts = row.Index
        bar_low = float(row.low)
        bar_high = float(row.high)
        bar_close = float(row.close)
        for price in list(grid_prices):
            touched = (
                setup.target_side == "long_probe" and bar_low <= price
            ) or (
                setup.target_side == "short_probe" and bar_high >= price
            )
            if touched:
                fills.append((price, size_per_order))
                grid_prices.remove(price)

        if not fills:
            continue
        if first_fill_ts is None:
            first_fill_ts = bar_ts

        avg_entry = _vwap(fills)
        exit_close = bar_close
        unrealized_pct = _unrealized_pct(setup.target_side, avg_entry, exit_close)
        max_drawdown_pct = min(max_drawdown_pct, unrealized_pct)

        if params.protective_stop_pct is not None and unrealized_pct < params.protective_stop_pct:
            return _make_result(
                setup=setup,
                fills=fills,
                exit_price=exit_close,
                exit_reason="protective_stop",
                first_fill_ts=first_fill_ts,
                exit_ts=bar_ts,
                max_drawdown_pct=max_drawdown_pct,
            )

        tp_price = _tp_price(setup.target_side, avg_entry, params.tp_pct)
        tp_hit = (
            setup.target_side == "long_probe" and bar_high >= tp_price
        ) or (
            setup.target_side == "short_probe" and bar_low <= tp_price
        )
        if tp_hit:
            return _make_result(
                setup=setup,
                fills=fills,
                exit_price=tp_price,
                exit_reason="tp",
                first_fill_ts=first_fill_ts,
                exit_ts=bar_ts,
                max_drawdown_pct=max_drawdown_pct,
            )

        if bar_ts >= first_fill_ts + pd.Timedelta(hours=params.time_stop_hours):
            return _make_result(
                setup=setup,
                fills=fills,
                exit_price=exit_close,
                exit_reason="time_stop",
                first_fill_ts=first_fill_ts,
                exit_ts=bar_ts,
                max_drawdown_pct=max_drawdown_pct,
            )

    if not fills or first_fill_ts is None:
        return None

    last_ts = sim.index[-1]
    return _make_result(
        setup=setup,
        fills=fills,
        exit_price=float(sim["close"].iloc[-1]),
        exit_reason="time_stop",
        first_fill_ts=first_fill_ts,
        exit_ts=last_ts,
        max_drawdown_pct=max_drawdown_pct,
    )


def _build_grid_prices(setup: H10Setup, params: ProbeParams) -> list[float]:
    center = setup.target_zone.price_level
    prices = []
    for idx in range(params.grid_steps):
        offset = center * params.grid_step_pct * idx
        if setup.target_side == "long_probe":
            prices.append(center - offset)
        else:
            prices.append(center + offset)
    return prices


def _tp_price(target_side: Literal["long_probe", "short_probe"], avg_entry: float, tp_pct: float) -> float:
    if target_side == "long_probe":
        return avg_entry * (1.0 + tp_pct)
    return avg_entry * (1.0 - tp_pct)


def _unrealized_pct(target_side: Literal["long_probe", "short_probe"], avg_entry: float, mark_price: float) -> float:
    if target_side == "long_probe":
        return (mark_price - avg_entry) / avg_entry
    return (avg_entry - mark_price) / avg_entry


def _vwap(fills: list[tuple[float, float]]) -> float:
    notional = sum(price * size for price, size in fills)
    size = sum(size for _, size in fills)
    return notional / size if size else 0.0


def _make_result(
    *,
    setup: H10Setup,
    fills: list[tuple[float, float]],
    exit_price: float,
    exit_reason: Literal["tp", "time_stop", "protective_stop"],
    first_fill_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    max_drawdown_pct: float,
) -> ProbeResult:
    position_btc = sum(size for _, size in fills)
    avg_entry = _vwap(fills)
    entry_notional = sum(price * size for price, size in fills)
    exit_notional = position_btc * exit_price
    if setup.target_side == "long_probe":
        pnl_usd = exit_notional - entry_notional
    else:
        pnl_usd = entry_notional - exit_notional
    pnl_btc = pnl_usd / exit_price if exit_price > 0 else 0.0
    volume_btc = position_btc + position_btc
    volume_usd = entry_notional + exit_notional
    duration_minutes = int((exit_ts - first_fill_ts).total_seconds() // 60)
    return ProbeResult(
        setup_ts=setup.timestamp,
        n_orders_filled=len(fills),
        avg_entry=avg_entry,
        exit_price=exit_price,
        exit_reason=exit_reason,
        pnl_btc=pnl_btc,
        pnl_usd=pnl_usd,
        volume_btc=volume_btc,
        volume_usd=volume_usd,
        duration_minutes=duration_minutes,
        max_drawdown_pct=max_drawdown_pct,
    )


def _to_utc(ts: datetime) -> pd.Timestamp:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
