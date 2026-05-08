from __future__ import annotations

import pandas as pd

from src.whatif.horizon_runner import Fill, StateAtMinute
from src.whatif.outcome import compute_outcome
from src.whatif.snapshot import Snapshot


def _snapshot(*, position_size_btc: float, close: float = 80_000.0) -> Snapshot:
    return Snapshot(
        timestamp=pd.Timestamp("2026-04-30T00:00:00+00:00"),
        symbol="BTCUSDT",
        close=close,
        feature_row={"atr_1h": 500.0, "delta_24h_pct": 1.0},
        position_size_btc=position_size_btc,
        avg_entry=close,
        unrealized_pnl_usd=0.0,
        realized_pnl_session=0.0,
        bot_status="running",
        grid_target_pct=1.0,
        grid_step_pct=0.5,
        boundary_top=84_000.0,
        boundary_bottom=76_000.0,
        capital_usd=14_000.0,
    )


def _state(fill: Fill | None = None, *, realized: float = 100.0, close: float = 79_000.0, position_size_btc: float = -0.1) -> StateAtMinute:
    return StateAtMinute(
        ts=pd.Timestamp("2026-04-30T01:00:00+00:00"),
        open_=80_000.0,
        high=80_200.0,
        low=78_900.0,
        close=close,
        position_size_btc=position_size_btc,
        avg_entry=80_000.0,
        unrealized_pnl_usd=0.0,
        realized_pnl_cumulative=realized,
        counter_long_size=0.0,
        counter_long_ttl_remaining=0,
        bot_status="running",
        fills=[] if fill is None else [fill],
    )


def test_simulator_includes_costs() -> None:
    fill = Fill(
        ts=pd.Timestamp("2026-04-30T01:00:00+00:00"),
        order_type="grid_in",
        level_price=80_500.0,
        fill_price=80_500.0,
        size_btc=-0.05,
        realized_pnl_usd=0.0,
        fees_usd=0.0,
    )
    base_snapshot = _snapshot(position_size_btc=-0.1)
    action_snapshot = _snapshot(position_size_btc=-0.15)
    out = compute_outcome(
        [_state(fill)],
        14_000.0,
        action_snapshot=action_snapshot,
        baseline_snapshot=base_snapshot,
        action_name="A-LAUNCH-STACK-SHORT",
        play_id="P-2",
    )
    assert out.net_pnl_usd != out.gross_pnl_usd


def test_p2_p6_p7_costs_improve_pnl() -> None:
    fill_a = Fill(
        ts=pd.Timestamp("2026-04-30T01:00:00+00:00"),
        order_type="grid_in",
        level_price=80_500.0,
        fill_price=80_500.0,
        size_btc=-0.05,
        realized_pnl_usd=0.0,
        fees_usd=0.0,
    )
    fill_b = Fill(
        ts=pd.Timestamp("2026-04-30T01:30:00+00:00"),
        order_type="tp",
        level_price=79_500.0,
        fill_price=79_500.0,
        size_btc=0.15,
        realized_pnl_usd=0.0,
        fees_usd=0.0,
    )
    state1 = _state(fill_a, realized=120.0, position_size_btc=-0.15)
    state2 = _state(fill_b, realized=140.0, close=79_500.0, position_size_btc=0.0)
    base_snapshot = _snapshot(position_size_btc=-0.1)
    action_snapshot = _snapshot(position_size_btc=-0.15)
    out = compute_outcome(
        [state1, state2],
        14_000.0,
        action_snapshot=action_snapshot,
        baseline_snapshot=base_snapshot,
        action_name="A-LAUNCH-STACK-SHORT",
        play_id="P-6",
    )
    assert out.net_pnl_usd > out.gross_pnl_usd
