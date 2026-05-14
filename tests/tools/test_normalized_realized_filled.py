"""Tests for fill_normalized_realized() — Fix A3 (TZ-ENGINE-BUG-FIX-PHASE-1)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.calibrate_ginarea import (
    CalibRow,
    fill_normalized_realized,
    group_stats,
)


def _make_row(bot_id: str, side: str, sim_realized: float, k_realized: float = 10.0) -> CalibRow:
    return CalibRow(
        bot_id=bot_id,
        side=side,
        contract="LINEAR" if side == "SHORT" else "INVERSE",
        td=0.25,
        sim_trades=100,
        ga_triggers=500 if side == "SHORT" else None,
        k_trades=5.0 if side == "SHORT" else None,
        sim_realized=sim_realized,
        ga_realized=sim_realized * k_realized,
        k_realized=k_realized,
        sim_volume=1000.0,
        ga_volume=10000.0,
        k_volume=10.0,
        normalized_sim_realized=0.0,  # starts unfilled — matches bug state
    )


def _make_groups(short_rows: list[CalibRow], long_rows: list[CalibRow]) -> dict:
    def _stats(rows: list[CalibRow], key: str) -> dict:
        vals = [getattr(r, key) for r in rows if not math.isnan(getattr(r, key, float("nan")))]
        return group_stats(vals)

    return {
        "SHORT / USDT-M (LINEAR)": {
            "rows": short_rows,
            "k_realized": _stats(short_rows, "k_realized"),
            "k_volume": _stats(short_rows, "k_volume"),
            "k_trades": group_stats([r.k_trades for r in short_rows if r.k_trades is not None]),
        },
        "LONG / COIN-M (INVERSE)": {
            "rows": long_rows,
            "k_realized": _stats(long_rows, "k_realized"),
            "k_volume": _stats(long_rows, "k_volume"),
            "k_trades": group_stats([]),
        },
    }


# ── test_normalized_filled_after_call ────────────────────────────────────────

def test_normalized_filled_after_call():
    """All rows must have normalized_sim_realized != 0.0 after fill_normalized_realized()."""
    short_rows = [
        _make_row("A", "SHORT", 4000.0, 9.73),
        _make_row("B", "SHORT", 4200.0, 10.15),
        _make_row("C", "SHORT", 3800.0, 10.25),
    ]
    long_rows = [
        _make_row("D", "LONG", -0.153, -0.82),
        _make_row("E", "LONG", -0.155, -0.86),
    ]

    # Pre-condition: all start at 0.0 (the bug)
    for r in short_rows + long_rows:
        assert r.normalized_sim_realized == 0.0

    groups = _make_groups(short_rows, long_rows)
    fill_normalized_realized(short_rows + long_rows, groups)

    # Post-condition: all filled
    for r in short_rows:
        assert r.normalized_sim_realized != 0.0, f"Row {r.bot_id} still 0.0 after fill"
    for r in long_rows:
        assert r.normalized_sim_realized != 0.0, f"Row {r.bot_id} still 0.0 after fill"


# ── test_normalized_uses_group_mean_not_individual_k ─────────────────────────

def test_normalized_uses_group_mean_not_individual_k():
    """normalized_sim_realized == sim_realized × group_mean_K, not individual K."""
    short_rows = [
        _make_row("A", "SHORT", 4000.0, 9.0),
        _make_row("B", "SHORT", 4200.0, 11.0),  # individual K differ
    ]
    groups = _make_groups(short_rows, [])
    fill_normalized_realized(short_rows, groups)

    group_mean_k = groups["SHORT / USDT-M (LINEAR)"]["k_realized"]["mean"]
    assert group_mean_k is not None

    for r in short_rows:
        expected = r.sim_realized * group_mean_k
        assert abs(r.normalized_sim_realized - expected) < 1e-9, (
            f"Row {r.bot_id}: expected {expected}, got {r.normalized_sim_realized}"
        )


# ── test_zero_mean_k_leaves_rows_at_zero ─────────────────────────────────────

def test_zero_mean_k_leaves_rows_at_zero():
    """When group mean K is 0 (degenerate), rows stay at 0.0 — no division by zero."""
    row_a = CalibRow(
        bot_id="Z", side="SHORT", contract="LINEAR", td=0.25,
        sim_trades=10, ga_triggers=10, k_trades=1.0,
        sim_realized=500.0, ga_realized=0.0, k_realized=0.0,
        sim_volume=1000.0, ga_volume=0.0, k_volume=0.0,
        normalized_sim_realized=0.0,
    )
    groups = {
        "SHORT / USDT-M (LINEAR)": {
            "rows": [row_a],
            "k_realized": group_stats([0.0]),  # mean = 0.0
            "k_volume": group_stats([0.0]),
            "k_trades": group_stats([1.0]),
        }
    }
    fill_normalized_realized([row_a], groups)
    # Should stay 0.0 without error
    assert row_a.normalized_sim_realized == 0.0
