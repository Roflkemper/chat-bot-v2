"""Grid search — param space × episodes → aggregated Outcome DataFrame.

§9 TZ-022.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.whatif.snapshot import Snapshot

logger = logging.getLogger(__name__)

RESULT_COLUMNS = [
    "param_combo_id", "param_values", "n_episodes",
    "mean_pnl_usd", "median_pnl_usd", "p25_pnl_usd", "p75_pnl_usd",
    "mean_pnl_vs_baseline_usd",
    "win_rate", "mean_dd_pct", "max_dd_pct", "mean_dd_vs_baseline_pct",
    "mean_target_hit_pct", "mean_volume_traded_usd", "mean_duration_min",
]


# ─────────────────────────────────────────────────────────────────────────────
# Episode
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Episode:
    snapshot: Snapshot
    horizon_min: int = 240
    features_dir: str | Path = "features_out"
    grid_unit_btc: float | None = None
    slippage_pct: float = 0.01
    fees_maker_pct: float = 0.04
    episode_type: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Param grid utilities
# ─────────────────────────────────────────────────────────────────────────────

def cartesian_grid(param_space: dict[str, list]) -> list[dict]:
    """Expand param_space to Cartesian product of all param combinations.

    Example:
        cartesian_grid({"a": [1, 2], "b": [10, 20]})
        → [{"a": 1, "b": 10}, {"a": 1, "b": 20}, {"a": 2, "b": 10}, {"a": 2, "b": 20}]
    """
    if not param_space:
        return [{}]
    keys = list(param_space.keys())
    values = list(param_space.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def _param_combo_id(params: dict) -> str:
    """Stable 8-char hex ID derived from sorted param dict."""
    return hashlib.md5(
        json.dumps(params, sort_keys=True).encode()
    ).hexdigest()[:8]


# ─────────────────────────────────────────────────────────────────────────────
# Worker (module-level for picklability)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_episode(
    episode: Episode,
    action_name: str,
    params: dict,
    combo_id: str,
) -> dict:
    """Run one (episode × params) pair and return raw metrics dict."""
    from src.whatif.action_simulator import ACTIONS
    from src.whatif.horizon_runner import run_horizon
    from src.whatif.outcome import compute_outcome

    action_fn   = ACTIONS[action_name]
    action_snap = action_fn(episode.snapshot, params)

    run_kwargs = dict(
        horizon_min=episode.horizon_min,
        features_dir=str(episode.features_dir),
        grid_unit_btc=episode.grid_unit_btc,
        slippage_pct=episode.slippage_pct,
        fees_maker_pct=episode.fees_maker_pct,
    )
    baseline_states = run_horizon(episode.snapshot, **run_kwargs)
    action_states   = run_horizon(action_snap, **run_kwargs)
    out = compute_outcome(
        action_states,
        episode.snapshot.capital_usd,
        baseline_states=baseline_states,
    )

    return {
        "param_combo_id":      combo_id,
        "param_values":        json.dumps(params, sort_keys=True),
        "ts_start":            str(episode.snapshot.timestamp),
        "episode_type":        episode.episode_type,
        "pnl_usd":             out.pnl_usd,
        "pnl_vs_baseline_usd": out.pnl_vs_baseline_usd,
        "max_drawdown_pct":    out.max_drawdown_pct,
        "dd_vs_baseline_pct":  out.dd_vs_baseline_pct,
        "target_hit_count":    out.target_hit_count,
        "volume_traded_usd":   out.volume_traded_usd,
        "duration_min":        out.duration_min,
    }


def _worker(args: tuple) -> dict:
    """Unpack tuple args for ProcessPoolExecutor.map."""
    return _compute_episode(*args)


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate(rows: list[dict]) -> pd.DataFrame:
    """Aggregate per-episode raw rows into per-combo summary DataFrame."""
    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    df = pd.DataFrame(rows)
    results = []

    for combo_id, grp in df.groupby("param_combo_id", sort=False):
        pnl = grp["pnl_usd"]
        results.append({
            "param_combo_id":            combo_id,
            "param_values":              grp["param_values"].iloc[0],
            "n_episodes":                len(grp),
            "mean_pnl_usd":              pnl.mean(),
            "median_pnl_usd":            pnl.median(),
            "p25_pnl_usd":               pnl.quantile(0.25),
            "p75_pnl_usd":               pnl.quantile(0.75),
            "mean_pnl_vs_baseline_usd":  grp["pnl_vs_baseline_usd"].mean(),
            "win_rate":                  (grp["pnl_vs_baseline_usd"] > 0).mean(),
            "mean_dd_pct":               grp["max_drawdown_pct"].mean(),
            "max_dd_pct":                grp["max_drawdown_pct"].max(),
            "mean_dd_vs_baseline_pct":   grp["dd_vs_baseline_pct"].mean(),
            "mean_target_hit_pct":       (grp["target_hit_count"] > 0).mean(),
            "mean_volume_traded_usd":    grp["volume_traded_usd"].mean(),
            "mean_duration_min":         grp["duration_min"].mean(),
        })

    return pd.DataFrame(results, columns=RESULT_COLUMNS)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def grid_search_play(
    action_name: str,
    episodes: list[Episode],
    param_grids: list[dict],
    n_workers: int = 4,
    raw_output_path: Path | None = None,
) -> pd.DataFrame:
    """Run grid search: param_grids × episodes → aggregated Outcome DataFrame.

    Args:
        action_name:      Key from ACTIONS registry (e.g. "A-RAISE-BOUNDARY").
        episodes:         Market scenarios to test. Each contains a Snapshot + run config.
        param_grids:      List of param dicts.
        n_workers:        Parallel ProcessPoolExecutor workers. 1 = sequential (no fork).
        raw_output_path:  If set, per-episode raw rows are saved to this parquet path.

    Returns:
        DataFrame with one row per param_combo, aggregated over all episodes.
        Columns: see RESULT_COLUMNS.
    """
    if not episodes or not param_grids:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    tasks = [
        (ep, action_name, params, _param_combo_id(params))
        for params in param_grids
        for ep in episodes
    ]

    if n_workers == 1:
        rows = [_compute_episode(*t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            rows = list(pool.map(_worker, tasks))

    if raw_output_path is not None and rows:
        raw_output_path = Path(raw_output_path)
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(raw_output_path, compression="zstd", index=False)
        logger.info("Raw episodes written: %s (%d rows)", raw_output_path, len(rows))

    return _aggregate(rows)
