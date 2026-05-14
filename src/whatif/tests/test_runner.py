"""Tests for runner.py — §10-11 TZ-022."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.whatif.runner import (
    PLAY_CONFIGS,
    PlayConfig,
    _load_episodes_fallback,
    _load_episodes_from_parquet,
    load_episodes,
    parse_args,
    run_play,
    write_manifest,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _episodes_df(n: int = 3, episode_type: str = "rally_strong") -> pd.DataFrame:
    ts = pd.date_range("2026-03-15 08:00", periods=n, freq="1D", tz="UTC")
    return pd.DataFrame({
        "ts_start": ts,
        "ts_end":   ts + pd.Timedelta(minutes=60),
        "symbol":   ["BTCUSDT"] * n,
        "episode_type": [episode_type] * n,
        "duration_minutes": [60] * n,
        "magnitude": [2.5] * n,
        "kz_active_at_start": [""] * n,
        "atr_1h_pct_at_start": [0.3] * n,
        "episode_id": [f"ep_{i}" for i in range(n)],
        "notes": [""] * n,
    })


def _result_df() -> pd.DataFrame:
    return pd.DataFrame({
        "param_combo_id": ["abc123"],
        "param_values": ['{"offset_pct": 0.5}'],
        "n_episodes": [3],
        "mean_pnl_usd": [100.0],
        "median_pnl_usd": [100.0],
        "p25_pnl_usd": [80.0],
        "p75_pnl_usd": [120.0],
        "win_rate": [0.67],
        "mean_dd_pct": [0.5],
        "max_dd_pct": [1.0],
        "mean_duration_min": [240.0],
    })


# ─────────────────────────────────────────────────────────────────────────────
# PLAY_CONFIGS correctness
# ─────────────────────────────────────────────────────────────────────────────

def test_play_configs_has_12_plays():
    assert len(PLAY_CONFIGS) == 12


def test_all_play_ids_p1_to_p12():
    expected = {f"P-{i}" for i in range(1, 13)}
    assert set(PLAY_CONFIGS.keys()) == expected


def test_play_configs_action_names_in_param_grids():
    from src.whatif.action_simulator import PARAM_GRIDS
    for play_id, config in PLAY_CONFIGS.items():
        assert config.action_name in PARAM_GRIDS, \
            f"{play_id}.action_name={config.action_name!r} not in PARAM_GRIDS"


def test_play_configs_presets_valid():
    from src.whatif.snapshot import POSITION_PRESETS
    for play_id, config in PLAY_CONFIGS.items():
        assert config.preset in POSITION_PRESETS, \
            f"{play_id}.preset={config.preset!r} not in POSITION_PRESETS"


def test_p12_uses_adaptive_grid_action():
    assert PLAY_CONFIGS["P-12"].action_name == "A-ADAPTIVE-GRID"


def test_p6_uses_composite_action():
    assert PLAY_CONFIGS["P-6"].action_name == "A-RAISE-AND-STACK-SHORT"


# ─────────────────────────────────────────────────────────────────────────────
# CLI parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_args_defaults():
    args = parse_args([])
    assert args.play == "P-1"
    assert args.horizon_min == 240
    assert args.n_workers == 4
    assert args.dry_run is False
    assert args.episodes is None


def test_parse_args_play_all():
    args = parse_args(["--play", "all"])
    assert args.play == "all"


def test_parse_args_horizon():
    args = parse_args(["--horizon-min", "60"])
    assert args.horizon_min == 60


def test_parse_args_dry_run():
    args = parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parse_args_episodes_path():
    args = parse_args(["--episodes", "frozen/labels/episodes.parquet"])
    assert args.episodes == Path("frozen/labels/episodes.parquet")


def test_parse_args_n_workers():
    args = parse_args(["--n-workers", "8"])
    assert args.n_workers == 8


def test_parse_args_symbols():
    args = parse_args(["--symbols", "BTCUSDT", "ETHUSDT"])
    assert args.symbols == ["BTCUSDT", "ETHUSDT"]


# ─────────────────────────────────────────────────────────────────────────────
# _load_episodes_from_parquet
# ─────────────────────────────────────────────────────────────────────────────

def test_load_from_parquet_filters_by_episode_type(tmp_path):
    df = _episodes_df(6)
    df.loc[3:, "episode_type"] = "rally_critical"
    parquet = tmp_path / "episodes.parquet"
    df.to_parquet(parquet, index=False)

    result = _load_episodes_from_parquet(parquet, ["rally_strong"])
    assert len(result) == 3
    assert (result["episode_type"] == "rally_strong").all()


def test_load_from_parquet_empty_type_list_returns_all(tmp_path):
    df = _episodes_df(5)
    parquet = tmp_path / "episodes.parquet"
    df.to_parquet(parquet, index=False)
    result = _load_episodes_from_parquet(parquet, [])
    assert len(result) == 5


# ─────────────────────────────────────────────────────────────────────────────
# load_episodes routing
# ─────────────────────────────────────────────────────────────────────────────

def test_load_episodes_uses_parquet_if_exists(tmp_path):
    df = _episodes_df(4, "rally_strong")
    parquet = tmp_path / "episodes.parquet"
    df.to_parquet(parquet, index=False)
    config = PLAY_CONFIGS["P-1"]
    result = load_episodes(config, parquet, tmp_path, ["BTCUSDT"])
    assert len(result) == 4


def test_load_episodes_fallback_if_parquet_missing(tmp_path):
    config = PLAY_CONFIGS["P-1"]
    mock_df = _episodes_df(2)

    with patch("src.whatif.runner._load_episodes_fallback", return_value=mock_df) as mock_fn:
        result = load_episodes(config, None, tmp_path, ["BTCUSDT"])
        mock_fn.assert_called_once()
    assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# run_play
# ─────────────────────────────────────────────────────────────────────────────

def test_run_play_empty_episodes_returns_empty_df(tmp_path):
    with patch("src.whatif.runner.load_episodes", return_value=pd.DataFrame()):
        result = run_play("P-1", tmp_path, tmp_path / "out", dry_run=True)
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_run_play_dry_run_does_not_write(tmp_path):
    eps = _episodes_df(2)
    result_mock = _result_df()

    with patch("src.whatif.runner.load_episodes", return_value=eps), \
         patch("src.whatif.runner._build_episode_list", return_value=[MagicMock()]), \
         patch("src.whatif.runner.grid_search_play", return_value=result_mock):

        out_dir = tmp_path / "whatif_results"
        run_play("P-1", tmp_path, out_dir, dry_run=True)

    assert not any(out_dir.glob("*.parquet")) if not out_dir.exists() else \
           not any(out_dir.glob("*.parquet"))


def test_run_play_writes_parquet_when_not_dry_run(tmp_path):
    eps = _episodes_df(2)
    result_mock = _result_df()

    with patch("src.whatif.runner.load_episodes", return_value=eps), \
         patch("src.whatif.runner._build_episode_list", return_value=[MagicMock()]), \
         patch("src.whatif.runner.grid_search_play", return_value=result_mock):

        out_dir = tmp_path / "whatif_results"
        run_play("P-1", tmp_path, out_dir, dry_run=False)

    parquets = list(out_dir.glob("P-1_*.parquet"))
    assert len(parquets) == 1


def test_run_play_output_filename_contains_play_and_date(tmp_path):
    result_mock = _result_df()

    with patch("src.whatif.runner.load_episodes", return_value=_episodes_df(1)), \
         patch("src.whatif.runner._build_episode_list", return_value=[MagicMock()]), \
         patch("src.whatif.runner.grid_search_play", return_value=result_mock):

        out_dir = tmp_path / "out"
        run_play("P-3", tmp_path, out_dir, dry_run=False)

    files = list(out_dir.glob("*.parquet"))
    assert len(files) == 1
    assert files[0].name.startswith("P-3_")


def test_run_play_unknown_play_raises():
    with pytest.raises(ValueError, match="Unknown play"):
        run_play("P-99", Path("."), Path("."))


# ─────────────────────────────────────────────────────────────────────────────
# write_manifest
# ─────────────────────────────────────────────────────────────────────────────

def test_write_manifest_creates_json(tmp_path):
    path = write_manifest(tmp_path, ["P-1", "P-3"], 240, 4, Path("features_out"))
    assert path.exists()


def test_write_manifest_fields(tmp_path):
    write_manifest(tmp_path, ["P-1", "P-2"], 120, 2, Path("features_out"))
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["version"] == "v1"
    assert data["plays_processed"] == ["P-1", "P-2"]
    assert data["horizon_min"] == 120
    assert data["n_workers"] == 2
    assert "timestamp" in data
    assert "params_hash" in data
    assert len(data["params_hash"]) == 8


def test_write_manifest_params_hash_stable(tmp_path):
    p1 = write_manifest(tmp_path / "a", ["P-1"], 240, 4, Path("features_out"))
    p2 = write_manifest(tmp_path / "b", ["P-1"], 240, 4, Path("features_out"))
    h1 = json.loads(p1.read_text())["params_hash"]
    h2 = json.loads(p2.read_text())["params_hash"]
    assert h1 == h2
