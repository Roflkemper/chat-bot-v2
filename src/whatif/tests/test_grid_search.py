"""Tests for grid_search.py — §9 TZ-022."""
from __future__ import annotations

import json
import pytest
import pandas as pd
from unittest.mock import patch

from src.whatif.grid_search import (
    Episode,
    RESULT_COLUMNS,
    _aggregate,
    _param_combo_id,
    cartesian_grid,
    grid_search_play,
)
from src.whatif.snapshot import Snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _snap() -> Snapshot:
    return Snapshot(
        timestamp=pd.Timestamp("2026-03-15 08:00", tz="UTC"),
        symbol="BTCUSDT",
        close=82_000.0,
        feature_row={"current_d_high": 82_500.0},
        position_size_btc=-0.18,
        avg_entry=83_500.0,
        unrealized_pnl_usd=-270.0,
    )


def _ep() -> Episode:
    return Episode(snapshot=_snap())


def _row(combo_id: str, params: dict, pnl=100.0, vs_baseline=50.0, dd=0.5, dur=60,
         dd_vs_baseline=0.0, target_hit_count=0, volume_usd=0.0) -> dict:
    return {
        "param_combo_id":      combo_id,
        "param_values":        json.dumps(params, sort_keys=True),
        "pnl_usd":             pnl,
        "pnl_vs_baseline_usd": vs_baseline,
        "max_drawdown_pct":    dd,
        "dd_vs_baseline_pct":  dd_vs_baseline,
        "target_hit_count":    target_hit_count,
        "volume_traded_usd":   volume_usd,
        "duration_min":        dur,
    }


def _mock_compute(episode, action_name, params, combo_id) -> dict:
    """Controlled stand-in for _compute_episode — no I/O."""
    return _row(combo_id, params, pnl=float(params.get("offset_pct", 1.0)) * 100)


# ─────────────────────────────────────────────────────────────────────────────
# cartesian_grid
# ─────────────────────────────────────────────────────────────────────────────

def test_cartesian_single_param():
    result = cartesian_grid({"offset_pct": [0.3, 0.5, 0.7, 1.0]})
    assert len(result) == 4
    assert result[0] == {"offset_pct": 0.3}
    assert result[-1] == {"offset_pct": 1.0}


def test_cartesian_two_params():
    result = cartesian_grid({
        "target_factor": [0.4, 0.5, 0.6, 0.7, 0.8],
        "gs_factor":     [0.5, 0.6, 0.67, 0.75, 0.85],
    })
    assert len(result) == 25  # 5 × 5


def test_cartesian_two_params_all_combinations():
    result = cartesian_grid({"a": [1, 2], "b": [10, 20]})
    assert len(result) == 4
    assert {"a": 1, "b": 10} in result
    assert {"a": 2, "b": 20} in result


def test_cartesian_empty_space_gives_one_empty_combo():
    result = cartesian_grid({})
    assert result == [{}]


def test_cartesian_single_value_single_param():
    result = cartesian_grid({"x": [42]})
    assert result == [{"x": 42}]


# ─────────────────────────────────────────────────────────────────────────────
# _param_combo_id
# ─────────────────────────────────────────────────────────────────────────────

def test_combo_id_is_stable():
    id1 = _param_combo_id({"offset_pct": 0.5})
    id2 = _param_combo_id({"offset_pct": 0.5})
    assert id1 == id2


def test_combo_id_differs_for_different_params():
    assert _param_combo_id({"offset_pct": 0.3}) != _param_combo_id({"offset_pct": 0.5})


def test_combo_id_order_invariant():
    id1 = _param_combo_id({"a": 1, "b": 2})
    id2 = _param_combo_id({"b": 2, "a": 1})
    assert id1 == id2


def test_combo_id_is_8_chars():
    assert len(_param_combo_id({"x": 1})) == 8


# ─────────────────────────────────────────────────────────────────────────────
# _aggregate
# ─────────────────────────────────────────────────────────────────────────────

def test_aggregate_empty_returns_empty_df():
    df = _aggregate([])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == RESULT_COLUMNS
    assert len(df) == 0


def test_aggregate_single_combo_single_episode():
    rows = [_row("aaa", {"x": 1}, pnl=200.0, vs_baseline=100.0, dd=1.0, dur=120)]
    df = _aggregate(rows)
    assert len(df) == 1
    assert df.iloc[0]["n_episodes"] == 1
    assert df.iloc[0]["mean_pnl_usd"] == pytest.approx(200.0)
    assert df.iloc[0]["win_rate"] == pytest.approx(1.0)


def test_aggregate_mean_median_percentiles():
    pnl_values = [100.0, 200.0, 300.0, 400.0]
    rows = [_row("abc", {"x": 1}, pnl=v, vs_baseline=v) for v in pnl_values]
    df = _aggregate(rows)
    row = df.iloc[0]
    assert row["mean_pnl_usd"]   == pytest.approx(250.0)
    assert row["median_pnl_usd"] == pytest.approx(250.0)
    assert row["p25_pnl_usd"]    == pytest.approx(175.0)
    assert row["p75_pnl_usd"]    == pytest.approx(325.0)
    assert row["n_episodes"]     == 4


def test_aggregate_win_rate_70_percent():
    # 7 positive, 3 negative → win_rate = 0.7
    rows = (
        [_row("x1", {"p": 1}, pnl=100.0, vs_baseline= 50.0)] * 7 +
        [_row("x1", {"p": 1}, pnl=-50.0, vs_baseline=-10.0)] * 3
    )
    df = _aggregate(rows)
    assert df.iloc[0]["win_rate"] == pytest.approx(0.7)


def test_aggregate_two_combos_separate_rows():
    id_a = _param_combo_id({"offset_pct": 0.3})
    id_b = _param_combo_id({"offset_pct": 0.7})
    rows = (
        [_row(id_a, {"offset_pct": 0.3}, pnl=100.0)] * 3 +
        [_row(id_b, {"offset_pct": 0.7}, pnl=200.0)] * 3
    )
    df = _aggregate(rows)
    assert len(df) == 2
    means = set(df["mean_pnl_usd"].tolist())
    assert 100.0 in means
    assert 200.0 in means


def test_aggregate_max_dd_is_worst_case():
    rows = [
        _row("z1", {"q": 1}, dd=0.5),
        _row("z1", {"q": 1}, dd=2.0),
        _row("z1", {"q": 1}, dd=1.0),
    ]
    df = _aggregate(rows)
    assert df.iloc[0]["max_dd_pct"] == pytest.approx(2.0)
    assert df.iloc[0]["mean_dd_pct"] == pytest.approx(3.5 / 3)


def test_aggregate_mean_duration():
    rows = [_row("d1", {"k": 1}, dur=60), _row("d1", {"k": 1}, dur=120)]
    df = _aggregate(rows)
    assert df.iloc[0]["mean_duration_min"] == pytest.approx(90.0)


def test_aggregate_columns_match_spec():
    rows = [_row("aa", {"x": 1})]
    df = _aggregate(rows)
    assert list(df.columns) == RESULT_COLUMNS


# ─────────────────────────────────────────────────────────────────────────────
# grid_search_play (mocked _compute_episode)
# ─────────────────────────────────────────────────────────────────────────────

def test_grid_search_empty_episodes_returns_empty():
    df = grid_search_play("A-STOP", [], [{}])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_grid_search_empty_param_grids_returns_empty():
    df = grid_search_play("A-STOP", [_ep()], [])
    assert len(df) == 0


def test_grid_search_correct_combo_count():
    param_grids = [{"offset_pct": v} for v in [0.3, 0.5, 0.7, 1.0]]  # 4 combos
    episodes    = [_ep()] * 3  # 3 episodes
    # 4 combos × 3 episodes = 12 tasks → 4 rows in result

    with patch("src.whatif.grid_search._compute_episode", side_effect=_mock_compute):
        df = grid_search_play("A-RAISE-BOUNDARY", episodes, param_grids, n_workers=1)

    assert len(df) == 4
    assert all(df["n_episodes"] == 3)


def test_grid_search_single_combo_single_episode():
    param_grids = [{"offset_pct": 0.5}]
    with patch("src.whatif.grid_search._compute_episode", side_effect=_mock_compute):
        df = grid_search_play("A-RAISE-BOUNDARY", [_ep()], param_grids, n_workers=1)
    assert len(df) == 1
    assert df.iloc[0]["n_episodes"] == 1


def test_grid_search_result_has_correct_columns():
    param_grids = [{"offset_pct": 0.5}]
    with patch("src.whatif.grid_search._compute_episode", side_effect=_mock_compute):
        df = grid_search_play("A-RAISE-BOUNDARY", [_ep()], param_grids, n_workers=1)
    assert list(df.columns) == RESULT_COLUMNS


def test_grid_search_param_values_stored_as_json():
    param_grids = [{"offset_pct": 0.5}]
    with patch("src.whatif.grid_search._compute_episode", side_effect=_mock_compute):
        df = grid_search_play("A-RAISE-BOUNDARY", [_ep()], param_grids, n_workers=1)
    stored = json.loads(df.iloc[0]["param_values"])
    assert stored == {"offset_pct": 0.5}


def test_grid_search_sequential_deterministic():
    param_grids = [{"offset_pct": v} for v in [0.3, 0.5, 1.0]]
    episodes    = [_ep()] * 4

    with patch("src.whatif.grid_search._compute_episode", side_effect=_mock_compute):
        df1 = grid_search_play("A-RAISE-BOUNDARY", episodes, param_grids, n_workers=1)

    with patch("src.whatif.grid_search._compute_episode", side_effect=_mock_compute):
        df2 = grid_search_play("A-RAISE-BOUNDARY", episodes, param_grids, n_workers=1)

    pd.testing.assert_frame_equal(
        df1.sort_values("param_combo_id").reset_index(drop=True),
        df2.sort_values("param_combo_id").reset_index(drop=True),
    )
