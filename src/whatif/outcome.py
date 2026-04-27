"""Outcome — episode metrics from a horizon simulation.

§8 TZ-022.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.whatif.horizon_runner import StateAtMinute


@dataclass
class Outcome:
    pnl_usd: float              # realized + unrealized at end of horizon
    pnl_pct: float              # pnl_usd / capital_usd * 100
    max_drawdown_pct: float     # max DD from peak equity, % of capital
    duration_min: int           # actual bars simulated (< horizon_min if data ended)
    volume_traded_usd: float    # sum abs(size_btc) * fill_price across all fills
    target_hit_count: int       # count of "tp" fills
    pnl_vs_baseline_usd: float  # pnl_usd − baseline.pnl_usd (positive = action better)
    dd_vs_baseline_pct: float   # max_drawdown_pct − baseline.max_drawdown_pct (negative = action better)


def _compute_max_drawdown_pct(states: list[StateAtMinute], capital_usd: float) -> float:
    """Max drawdown from equity peak (realized + unrealized), % of capital.

    Tracks running equity curve; DD measured from highest point reached so far.
    """
    if not states or capital_usd == 0:
        return 0.0
    peak = float("-inf")
    max_dd_usd = 0.0
    for s in states:
        equity = s.realized_pnl_cumulative + s.unrealized_pnl_usd
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_usd:
            max_dd_usd = dd
    return max_dd_usd / capital_usd * 100


def compute_outcome(
    states: list[StateAtMinute],
    capital_usd: float,
    baseline_states: list[StateAtMinute] | None = None,
) -> Outcome:
    """Compute Outcome metrics from a simulated horizon.

    Args:
        states:          Output of run_horizon (action applied).
        capital_usd:     Account capital for pnl_pct / dd_pct scaling.
        baseline_states: Output of run_horizon with no action applied.
                         If None, pnl_vs_baseline and dd_vs_baseline are 0.
    """
    if not states:
        return Outcome(
            pnl_usd=0.0, pnl_pct=0.0, max_drawdown_pct=0.0,
            duration_min=0, volume_traded_usd=0.0, target_hit_count=0,
            pnl_vs_baseline_usd=0.0, dd_vs_baseline_pct=0.0,
        )

    last = states[-1]
    pnl_usd = last.realized_pnl_cumulative + last.unrealized_pnl_usd
    pnl_pct = pnl_usd / capital_usd * 100 if capital_usd != 0 else 0.0
    duration_min = len(states)
    max_dd_pct = _compute_max_drawdown_pct(states, capital_usd)

    volume_traded_usd = sum(
        abs(f.size_btc) * f.fill_price
        for s in states
        for f in s.fills
    )
    target_hit_count = sum(
        1
        for s in states
        for f in s.fills
        if f.order_type == "tp"
    )

    if baseline_states is not None:
        base = compute_outcome(baseline_states, capital_usd)
        pnl_vs_baseline_usd = pnl_usd - base.pnl_usd
        dd_vs_baseline_pct  = max_dd_pct - base.max_drawdown_pct
    else:
        pnl_vs_baseline_usd = 0.0
        dd_vs_baseline_pct  = 0.0

    return Outcome(
        pnl_usd=pnl_usd,
        pnl_pct=pnl_pct,
        max_drawdown_pct=max_dd_pct,
        duration_min=duration_min,
        volume_traded_usd=volume_traded_usd,
        target_hit_count=target_hit_count,
        pnl_vs_baseline_usd=pnl_vs_baseline_usd,
        dd_vs_baseline_pct=dd_vs_baseline_pct,
    )
