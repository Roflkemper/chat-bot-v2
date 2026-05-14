from __future__ import annotations

import pandas as pd

from services.defensive_actions_research.v3_correct import (
    FillLot,
    GridState,
    bootstrap_grid_state,
    replay_grid_correct,
)


def _path(rows: list[tuple[str, float, float, float]]) -> pd.DataFrame:
    index = pd.to_datetime([row[0] for row in rows], utc=True)
    return pd.DataFrame(
        {"high": [row[1] for row in rows], "low": [row[2] for row in rows], "close": [row[3] for row in rows]},
        index=index,
    )


def test_widen_only_affects_new_fills() -> None:
    path = _path(
        [
            ("2026-05-01T00:00:00Z", 99.6, 96.9, 97.2),
            ("2026-05-01T00:01:00Z", 100.4, 99.8, 100.3),
        ]
    )
    state = GridState(active_lots=[FillLot(100.0, 0.25, 0.0666666667, "existing")], anchor_price=100.0)
    result = replay_grid_correct(
        path,
        "long",
        state,
        original_target_pct=0.25,
        original_step_pct=0.03,
        new_target_pct=0.375,
        new_step_pct=0.03,
        scenario_name="widen_target",
    )
    closed_targets = sorted(round(lot.target_pct, 3) for lot in result["closed_lots"])
    assert closed_targets == [0.25, 0.375]


def test_widen_new_fills_use_new_target() -> None:
    path = _path([("2026-05-01T00:00:00Z", 97.2, 96.9, 97.1)])
    state = GridState(active_lots=[FillLot(100.0, 0.25, 0.0666666667, "existing")], anchor_price=100.0)
    result = replay_grid_correct(
        path,
        "long",
        state,
        original_target_pct=0.25,
        original_step_pct=0.03,
        new_target_pct=0.375,
        new_step_pct=0.03,
        scenario_name="widen_target",
    )
    assert any(round(lot.target_pct, 3) == 0.375 and lot.cohort == "new" for lot in result["active_lots"])


def test_outcome_per_fill_individual() -> None:
    path = _path([("2026-05-01T00:00:00Z", 100.3, 99.9, 100.2)])
    state = GridState(
        active_lots=[
            FillLot(100.0, 0.25, 0.0666666667, "existing"),
            FillLot(99.0, 1.50, 0.0666666667, "existing"),
        ],
        anchor_price=99.0,
    )
    result = replay_grid_correct(
        path,
        "long",
        state,
        original_target_pct=0.25,
        original_step_pct=0.03,
        new_target_pct=0.375,
        new_step_pct=0.03,
        scenario_name="actual_action",
    )
    closed_entries = [round(lot.entry_price, 2) for lot in result["closed_lots"]]
    remaining_entries = [round(lot.entry_price, 2) for lot in result["active_lots"]]
    assert closed_entries == [100.0]
    assert remaining_entries == [99.0]


def test_bootstrap_preserves_original_targets() -> None:
    pre_path = _path([("2026-05-01T00:00:00Z", 97.2, 96.9, 97.05)])
    state = bootstrap_grid_state(pre_path, entry_price=100.0, side="long", target_pct=0.25, step_pct=0.03)
    assert len(state.active_lots) == 2
    assert all(lot.target_pct == 0.25 for lot in state.active_lots)
